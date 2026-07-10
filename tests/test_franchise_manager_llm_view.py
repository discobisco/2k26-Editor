from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGroupBox

from nba2k_editor.franchise.control_room import (
    build_franchise_control_room_markdown,
    build_franchise_screen_context,
    build_screen_context_markdown,
)
from nba2k_editor.franchise.draft_room import (
    TeamProfile,
    available_players,
    build_fantasy_draft_board,
    build_fantasy_draft_markdown,
    build_active_player_draft_pool,
    draft_position,
    draft_turn_owner,
    find_available_player,
    league_team_indexes,
    make_pick,
)
from nba2k_editor.franchise.llm_client import LLMClient
from nba2k_editor.franchise.llm_pick_runner import run_llm_fantasy_draft_pick
from nba2k_editor.franchise.llm_tasks import FranchiseLlmTask
from nba2k_editor.franchise.llm_view import build_franchise_llm_markdown, build_franchise_llm_view
from nba2k_editor.franchise.prompts import build_fantasy_draft_pick_prompt
from nba2k_editor.franchise.models import FantasyDraftStoredPick, FranchiseRecord, FranchiseSetup, FranchiseTeamOption, TeamRecommendation
from nba2k_editor.franchise.qt_screen import FranchiseScreen
from nba2k_editor.franchise.recommendations import (
    TeamRecommendationRequest,
    build_team_recommendation_requests,
    recommendation_from_response,
    run_team_recommendation_request,
)
from nba2k_editor.franchise.storage import FranchiseRepository


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@dataclass(frozen=True)
class FakeItem:
    domain: str
    index: int
    address: int
    label: str
    display_label: str


class ReadOnlyFranchiseModel:
    target_executable = "NBA2K26.exe"

    def __init__(self) -> None:
        self.player = FakeItem("Players", 4, 4000, "Player Four", "[4] Player Four")
        self.unused_player = FakeItem("Players", 8, 8000, "Unused Player", "[8] Unused Player")
        self.team = FakeItem("Teams", 0, 9000, "Team Zero", "[0] Team Zero")
        self.loaded_items = {
            "Players": {self.player.display_label: self.player, self.unused_player.display_label: self.unused_player},
            "Teams": {self.team.display_label: self.team},
        }
        self.player_values = {
            4: {"ISACTIVE": (1, "Yes"), "OVERALL": (88, "88"), "POSITION": (1, "PG"), "BIRTHYEAR": (1988, "1988")},
            8: {"ISACTIVE": (0, "No"), "OVERALL": (40, "40"), "POSITION": (5, "C"), "BIRTHYEAR": (2006, "2006")},
        }
        self.selected_items = {"Players": self.player, "Teams": self.team}
        self.write_called = False

    def _field_by_normalized_name(self, domain: str, name: str) -> str | None:
        normalized = str(name).upper()
        if domain == "Players" and normalized in {"ISACTIVE", "OVERALL", "OVR", "POSITION", "HEIGHT", "WEIGHT", "BIRTHYEAR"}:
            return "OVERALL" if normalized == "OVR" else normalized
        return None

    def read_entry_value(self, entry: str, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        raw, display = self.player_values.get(int(index), {}).get(str(entry), (0, ""))
        return {"raw_value": raw, "display_value": display}

    def runtime_status_text(self) -> str:
        return "attached"

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def selected_item(self, domain: str) -> FakeItem | None:
        return self.selected_items.get(domain)

    def selected_player_detail_values(self) -> dict[str, str]:
        return {"OVR": "88", "Position": "PG"}

    def selected_team_summary_values(self) -> dict[str, str]:
        return {"Team Name": "Zero", "City Name": "Test City"}

    def player_roster_slot_items_for_team_items(self, teams: Iterable[FakeItem]) -> list[tuple[FakeItem, dict[str, Any]]]:
        team = tuple(teams)[0]
        return [(self.player, {"team_index": team.index, "team_label": team.label, "team_slot": 1, "team_slot_field": "PLAYER1"})]

    def write_entry_value(self, *args: object, **kwargs: object) -> None:
        self.write_called = True
        raise AssertionError("LLM view must not write")

    def save_selected_team_summary(self, *args: object, **kwargs: object) -> None:
        self.write_called = True
        raise AssertionError("LLM view must not save")


def test_franchise_llm_view_reads_loaded_players_and_teams_without_write_calls() -> None:
    model = ReadOnlyFranchiseModel()

    view = build_franchise_llm_view(model)

    assert view.mode == "read_only"
    assert view.source_screens == ("Players", "Teams")
    assert view.player_count == 2
    assert view.team_count == 1
    assert view.selected_player is not None
    assert view.selected_player.values == {"OVR": "88", "Position": "PG"}
    assert view.selected_team is not None
    assert view.selected_team.values["Team Name"] == "Zero"
    assert len(view.roster_slots) == 1
    assert view.roster_slots[0].team_slot_field == "PLAYER1"
    assert model.write_called is False


def test_franchise_llm_markdown_declares_read_only_context() -> None:
    text = build_franchise_llm_markdown(ReadOnlyFranchiseModel())

    assert "Mode: read-only" in text
    assert "Do not edit, write, save, or import" in text
    assert "## Selected Player" in text
    assert "OVR: 88" in text
    assert "PLAYER1" in text


def test_fantasy_draft_pool_uses_active_player_offset_only() -> None:
    model = ReadOnlyFranchiseModel()

    pool = build_active_player_draft_pool(model, team_count=30)

    assert [player.player_label for player in pool] == ["[4] Player Four"]
    assert pool[0].source_slot_field == "ISACTIVE"
    assert dict(pool[0].draft_facts)["overall"] == "88"
    assert dict(pool[0].draft_facts)["position"] == "PG"
    assert all(player.player_label != "[8] Unused Player" for player in pool)
    assert model.write_called is False


def test_fantasy_draft_prompt_uses_ranked_board_with_player_facts() -> None:
    model = ReadOnlyFranchiseModel()
    late_star = FakeItem("Players", 12, 12000, "Late Star", "[12] Late Star")
    model.loaded_items["Players"][late_star.display_label] = late_star
    model.player_values[8]["ISACTIVE"] = (1, "Yes")
    model.player_values[12] = {"ISACTIVE": (1, "Yes"), "OVERALL": (96, "96"), "POSITION": (3, "SF"), "BIRTHYEAR": (1971, "1971")}
    pool = build_active_player_draft_pool(model, team_count=30)

    prompt = build_fantasy_draft_pick_prompt(
        record=_franchise_record_for_recommendations(),
        position=draft_position(1, team_order=(0,)),
        team_profile=TeamProfile(0, "", False, "Team Zero Staff", ""),
        available_players=pool,
        drafted_picks=(),
    )
    payload = json.loads(prompt)

    assert [player["player_label"] for player in payload["available_players"]] == ["[12] Late Star", "[4] Player Four", "[8] Unused Player"]
    assert payload["available_players"][0]["draft_rank"] == 1
    assert payload["available_players"][0]["draft_facts"] == {"overall": "96", "position": "SF", "birth_year": "1971"}
    assert payload["available_players"][1]["draft_facts"]["overall"] == "88"
    assert any("higher overall-rated real players first" in rule for rule in payload["rules"])


def test_fantasy_draft_board_loads_on_clock_team_profile(tmp_path: Path) -> None:
    (tmp_path / "team_00_profile.md").write_text("---\nname: Team Zero Profile\n---\n# Team Zero\nDraft guards\n", encoding="utf-8")

    board = build_fantasy_draft_board(ReadOnlyFranchiseModel(), user_team_index=1, team_count=1, profile_dir=tmp_path)

    assert board.mode == "read_only_fantasy_draft"
    assert board.source == "Players/ISACTIVE active player offset"
    assert board.current_position.team_index == 0
    assert board.profile.exists is True
    assert board.profile.name == "Team Zero Profile"
    assert board.pool_count == 1
    assert board.available_count == 1


def test_fantasy_draft_mark_pick_taken_removes_player_locally(tmp_path: Path) -> None:
    model = ReadOnlyFranchiseModel()
    pool = build_active_player_draft_pool(model, team_count=30)
    player = find_available_player(pool, (), "Player Four")
    assert player is not None

    pick = make_pick(player, position=draft_position(1, team_count=30, user_team_index=5, team_labels={0: "Team Zero"}))

    assert available_players(pool, (pick,)) == ()
    text = build_fantasy_draft_markdown(model, user_team_index=5, team_count=30, drafted_picks=(pick,), current_pick_number=2, profile_dir=tmp_path)
    assert "Draft pool source: Players/ISACTIVE active player offset" in text
    assert "Pool uses Players/ISACTIVE from the in-game draft page." in text
    assert "Pick 1 R1 Team 0 Team Zero: [4] Player Four" in text
    assert "Available now: 0" in text


def _stored_pick(pick_number: int, *, picked_by: str, player_label: str = "Player") -> FantasyDraftStoredPick:
    return FantasyDraftStoredPick(
        pick_number=pick_number,
        round_number=1,
        team_index=pick_number - 1,
        team_label=f"Team {pick_number - 1}",
        player_index=pick_number * 10,
        player_label=player_label,
        source_team_index=-1,
        source_slot=0,
        source_slot_field="ISACTIVE",
        picked_by=picked_by,
    )


def test_undo_last_fantasy_draft_pick_rolls_back_latest_ai_pick(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "franchise.sqlite")
    repository.start_fantasy_draft(team_count=3, user_team_index=0)
    repository.record_fantasy_draft_pick(_stored_pick(1, picked_by="user", player_label="Real Player"))
    repository.record_fantasy_draft_pick(_stored_pick(2, picked_by="llm", player_label="Roster Filler"))

    undone = repository.undo_last_fantasy_draft_pick(picked_by="llm")

    assert undone is not None
    assert undone.pick_number == 2
    assert undone.player_label == "Roster Filler"
    assert [pick.pick_number for pick in repository.list_fantasy_draft_picks()] == [1]
    state = repository.load_fantasy_draft_state()
    assert state is not None
    assert state.current_pick_number == 2


def test_undo_last_fantasy_draft_pick_does_not_remove_latest_user_pick(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "franchise.sqlite")
    repository.start_fantasy_draft(team_count=3, user_team_index=0)
    repository.record_fantasy_draft_pick(_stored_pick(1, picked_by="llm", player_label="AI Player"))
    repository.record_fantasy_draft_pick(_stored_pick(2, picked_by="user", player_label="User Player"))

    undone = repository.undo_last_fantasy_draft_pick(picked_by="llm")

    assert undone is None
    assert [pick.pick_number for pick in repository.list_fantasy_draft_picks()] == [1, 2]
    state = repository.load_fantasy_draft_state()
    assert state is not None
    assert state.current_pick_number == 3


def test_selected_user_and_ai_teams_are_the_only_fantasy_draft_league_teams() -> None:
    record = FranchiseRecord(
        setup=FranchiseSetup(
            start_year=2025,
            keep_full_league_save=False,
            llm_gm_team_indexes=(3, 8),
            fantasy_draft=True,
            user_team_index=5,
        ),
        team_options=(),
        database_path=":memory:",
        full_league_save_count=0,
        created_at="",
        updated_at="",
    )

    order = league_team_indexes(record)
    assert order == (3, 5, 8)
    assert draft_position(1, team_order=order).team_index == 3
    assert draft_position(2, team_order=order).team_index == 5
    assert draft_position(3, team_order=order).team_index == 8
    assert draft_position(4, team_order=order).team_index == 8
    assert draft_position(5, team_order=order).team_index == 5
    assert draft_position(6, team_order=order).team_index == 3
    assert draft_position(7, team_order=order).team_index == 3
    assert draft_turn_owner(draft_position(1, team_order=order), record) == "llm"
    assert draft_turn_owner(draft_position(2, team_order=order), record) == "user"
    assert draft_turn_owner(draft_position(3, team_order=order), record) == "llm"
    assert draft_turn_owner(draft_position(1, team_order=(0,)), record) == "excluded"


def test_control_room_keeps_draft_as_one_section_of_broader_framework(tmp_path: Path) -> None:
    (tmp_path / "team_00_profile.md").write_text("---\nname: Team Zero Profile\n---\n# Team Zero\n", encoding="utf-8")

    text = build_franchise_control_room_markdown(
        ReadOnlyFranchiseModel(),
        user_team_index=5,
        team_count=1,
        current_pick_number=1,
        profile_dir=tmp_path,
    )

    assert "# Franchise Manager Control Room" in text
    assert "Screen Context: loaded Players and Teams" in text
    assert "Team Profiles: team_00_profile.md through team_29_profile.md" in text
    assert "Fantasy Draft Room: one workflow" in text
    assert "Future franchise decisions: trades, rotations, contracts, scouting, and season actions" in text
    assert "# Franchise Manager LLM View" in text
    assert "## Team Profiles" in text
    assert "# Franchise Manager Fantasy Draft Room" in text
    assert "No game-memory write, save, import, apply" in text


def _franchise_screen_for_mode(tmp_path: Path, *, fantasy_draft: bool) -> FranchiseScreen:
    app = qt_app()
    db_path = tmp_path / ("fantasy.sqlite" if fantasy_draft else "systems.sqlite")
    repository = FranchiseRepository(db_path)
    repository.replace_franchise(
        FranchiseSetup(
            start_year=1946,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=fantasy_draft,
            user_team_index=5,
        ),
        (FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),),
        target_executable="NBA2K26.exe",
    )
    screen = FranchiseScreen(ReadOnlyFranchiseModel(), db_path=db_path)
    screen._load_franchise_dashboard()
    app.processEvents()
    screen._test_qt_app = app
    return screen


def _franchise_group_titles(screen: FranchiseScreen) -> set[str]:
    return {group.title() for group in screen.findChildren(QGroupBox)}


def test_fantasy_draft_franchise_shows_only_draft_page(tmp_path: Path) -> None:
    screen = _franchise_screen_for_mode(tmp_path, fantasy_draft=True)

    titles = _franchise_group_titles(screen)
    assert "Fantasy Draft Room" in titles
    assert "Team GM Recommendations" not in titles
    assert screen.draft_status_text is not None
    assert screen.recommendation_text is None


def test_non_fantasy_franchise_shows_system_pages_without_draft_room(tmp_path: Path) -> None:
    screen = _franchise_screen_for_mode(tmp_path, fantasy_draft=False)

    titles = _franchise_group_titles(screen)
    assert "Team GM Recommendations" in titles
    assert "Fantasy Draft Room" not in titles
    assert screen.recommendation_text is not None
    assert screen.draft_status_text is None


def _franchise_record_for_recommendations() -> FranchiseRecord:
    return FranchiseRecord(
        setup=FranchiseSetup(
            start_year=1946,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=False,
            user_team_index=5,
        ),
        team_options=(),
        database_path=":memory:",
        full_league_save_count=0,
        created_at="",
        updated_at="",
    )


class FakeRecommendationClient:
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        assert "franchise_team_gm_recommendation" in prompt
        assert "team-GM recommendation" in system_prompt
        return (
            '{"team_index":0,"team_label":"Team 0","recommended_action":"Set a conservative 1946 scouting focus",'
            '"reasoning":"Roster is thin and era rules favor real-player discovery.",'
            '"owner_approval_required":true,"blocked_reason":""}'
        )


class FakeDraftPickClient:
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        assert "fantasy_draft_pick" in prompt
        assert "fantasy draft decision" in system_prompt
        assert "Team Zero Staff" in prompt
        assert "draft task no matter which Franchise Manager mode launched it" in prompt
        payload = json.loads(prompt)
        assert payload["available_players"][0]["draft_rank"] == 1
        assert payload["available_players"][0]["draft_facts"]["overall"] == "88"
        assert payload["available_players"][0]["draft_facts"]["position"] == "PG"
        return '{"team_index":0,"pick_number":1,"selected_player_index":4,"selected_player_label":"[4] Player Four","rationale":"Profile wants real players only."}'


def _recommendation_request(team_index: int = 0, prompt: str = '{"task":"franchise_team_gm_recommendation"}') -> TeamRecommendationRequest:
    profile = TeamProfile(team_index, "", False, f"Team {team_index} Staff", "")
    task = FranchiseLlmTask(
        task_name="franchise_team_gm_recommendation",
        team_index=team_index,
        team_label=f"Team {team_index}",
        profile=profile,
        prompt=prompt,
        system_prompt="Return only valid JSON for the requested NBA2K franchise team-GM recommendation.",
    )
    return TeamRecommendationRequest(team_index=team_index, team_label=f"Team {team_index}", task=task)


def test_fantasy_draft_pick_uses_same_team_profile_task_system(tmp_path: Path) -> None:
    (tmp_path / "team_00_profile.md").write_text(
        "---\nname: Team Zero Staff\n---\n# Team Zero\nOwner: refuses filler\nGM: draft real players\n",
        encoding="utf-8",
    )
    model = ReadOnlyFranchiseModel()
    record = _franchise_record_for_recommendations()
    pool = build_active_player_draft_pool(model, team_count=30)

    result = run_llm_fantasy_draft_pick(
        record=record,
        position=draft_position(1, team_order=(0,)),
        available_players=pool,
        drafted_picks=(),
        profile_dir=tmp_path,
        client=FakeDraftPickClient(),
    )

    assert result.selected_player_index == 4
    assert result.selected_player_label == "[4] Player Four"
    assert result.rationale == "Profile wants real players only."


def test_team_recommendation_prompt_uses_profiles_roster_and_true_year(tmp_path: Path) -> None:
    (tmp_path / "team_00_profile.md").write_text(
        "---\nname: Team Zero Staff\n---\n# Team Zero\nOwner: patient\nGM: scout first\n",
        encoding="utf-8",
    )
    model = ReadOnlyFranchiseModel()
    record = _franchise_record_for_recommendations()

    requests = build_team_recommendation_requests(record, model, profile_dir=tmp_path)

    assert len(requests) == 1
    assert requests[0].team_index == 0
    assert requests[0].task.task_name == "franchise_team_gm_recommendation"
    assert requests[0].task.profile.name == "Team Zero Staff"
    assert "franchise_team_gm_recommendation" in requests[0].task.prompt
    assert '"true_sim_year": 1946' in requests[0].task.prompt
    assert "Team Zero Staff" in requests[0].task.prompt
    assert "[4] Player Four" in requests[0].task.prompt
    assert model.write_called is False


def test_team_recommendation_response_and_runner_are_structured() -> None:
    request = _recommendation_request()

    recommendation = run_team_recommendation_request(request, client=FakeRecommendationClient())

    assert recommendation.team_index == 0
    assert recommendation.recommended_action == "Set a conservative 1946 scouting focus"
    assert recommendation.owner_approval_required is True
    assert recommendation.status == "pending"
    assert recommendation.raw_llm_response.startswith("{")


def test_team_recommendation_parser_rejects_wrong_team() -> None:
    request = _recommendation_request(team_index=7, prompt="{}")
    response = (
        '{"team_index":0,"team_label":"Team 0","recommended_action":"No action",'
        '"reasoning":"Wrong team.","owner_approval_required":false,"blocked_reason":""}'
    )

    try:
        recommendation_from_response(request, response)
    except ValueError as exc:
        assert "team_index" in str(exc)
    else:
        raise AssertionError("wrong-team recommendation should fail")


def test_team_recommendations_persist_without_game_writes(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "franchise.sqlite")
    saved = repository.record_team_recommendation(
        TeamRecommendation(
            team_index=0,
            team_label="Team 0",
            recommended_action="Scout real centers only",
            reasoning="1946 roster needs size and no filler signings are allowed.",
            owner_approval_required=False,
            blocked_reason="",
            raw_llm_response='{"team_index":0}',
        )
    )

    recommendations = repository.list_team_recommendations()

    assert saved.recommendation_id == 1
    assert len(recommendations) == 1
    assert recommendations[0].recommended_action == "Scout real centers only"
    assert recommendations[0].owner_approval_required is False
