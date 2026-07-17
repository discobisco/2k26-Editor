from __future__ import annotations

import os
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication, QGroupBox, QPushButton

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
from nba2k_editor.franchise.models import FantasyDraftStoredPick, FranchiseRecord, FranchiseSetup, FranchiseSimState, FranchiseTeamOption, TeamRecommendation
from nba2k_editor.franchise.profile_generation import GeneratedTeamProfile, write_generated_team_profile
from nba2k_editor.franchise.qt_screen import FranchiseScreen
from nba2k_editor.franchise.recommendations import (
    TeamRecommendationRequest,
    build_team_recommendation_requests,
    recommendation_from_response,
    run_team_recommendation_request,
)
from nba2k_editor.franchise.sim_phases import (
    STATUS_READY,
    STATUS_WAITING_FOR_GAME_ADVANCE,
    STATUS_WAITING_FOR_USER_TRADE,
    franchise_phase_sequence,
)
from nba2k_editor.franchise.storage import FranchiseRepository


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def flush_qt_events(app: QApplication) -> None:
    for _ in range(3):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, 0)
        app.processEvents()


def write_ready_team_profiles(record: FranchiseRecord) -> None:
    for team in record.team_options:
        gm_control = "human" if team.team_index == record.setup.user_team_index else "llm"
        write_generated_team_profile(
            record,
            GeneratedTeamProfile(
                team_index=team.team_index,
                team_label=team.label,
                gm_control=gm_control,
                organizational_identity="Persistent organizational identity.",
                owner="Persistent LLM owner identity.",
                general_manager="Persistent general manager relationship.",
                coach="Persistent LLM coach identity.",
                scout="Persistent LLM scout identity.",
                raw_response="{}",
            ),
        )


class FakeTeamProfileClient:
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        payload = json.loads(prompt)
        team = payload["team"]
        gm_control = str(team["gm_control"])
        return json.dumps(
            {
                "team_index": int(team["team_index"]),
                "team_label": str(team["team_label"]),
                "gm_control": gm_control,
                "organizational_identity": "Persistent organizational identity.",
                "owner": "Persistent LLM owner identity.",
                "general_manager": (
                    "The human user owns all GM decisions."
                    if gm_control == "human"
                    else "Persistent LLM general manager identity."
                ),
                "coach": "Persistent LLM coach identity.",
                "scout": "Persistent LLM scout identity.",
            }
        )


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


class FullLeagueFranchiseModel(ReadOnlyFranchiseModel):
    def __init__(self) -> None:
        super().__init__()
        teams = {}
        for index in range(30):
            label = "Los Angeles Lakers" if index == 13 else f"Team {index}"
            item = FakeItem("Teams", index, 9000 + index * 100, label, f"[{index}] {label}")
            teams[item.display_label] = item
        self.loaded_items["Teams"] = teams


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
    record = repository.replace_franchise(
        FranchiseSetup(
            start_year=1946,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=fantasy_draft,
            user_team_index=5,
        ),
        (
            FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),
            FranchiseTeamOption(5, "User Team", "[5] User Team"),
        ),
        target_executable="NBA2K26.exe",
    )
    write_ready_team_profiles(record)
    screen = FranchiseScreen(ReadOnlyFranchiseModel(), db_path=db_path)
    screen._load_franchise_dashboard()
    app.processEvents()
    screen._test_qt_app = app
    return screen


def _franchise_group_titles(screen: FranchiseScreen) -> set[str]:
    return {group.title() for group in screen.findChildren(QGroupBox)}


def test_missing_franchise_scoped_profiles_block_dashboard_and_include_user_team_roles(tmp_path: Path) -> None:
    app = qt_app()
    db_path = tmp_path / "profiles.sqlite"
    repository = FranchiseRepository(db_path)
    repository.replace_franchise(
        FranchiseSetup(
            start_year=2001,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=False,
            user_team_index=5,
        ),
        (
            FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),
            FranchiseTeamOption(5, "User Team", "[5] User Team"),
        ),
    )

    screen = FranchiseScreen(ReadOnlyFranchiseModel(), db_path=db_path)
    screen._load_franchise_dashboard()
    app.processEvents()

    titles = _franchise_group_titles(screen)
    assert "Franchise Phase Controller" not in titles
    assert screen.profile_status_text is not None
    text = screen.profile_status_text.toPlainText()
    assert "[missing] [0] Team Zero: Owner=LLM, GM=LLM, Coach=LLM, Scout=LLM" in text
    assert "[missing] [5] User Team: Owner=LLM, GM=human user, Coach=LLM, Scout=LLM" in text


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
    assert "Franchise Phase Controller" in titles
    assert "Team GM Recommendations" in titles
    assert "Fantasy Draft Room" not in titles
    assert screen.phase_status_text is not None
    assert "Current Phase: Season" in screen.phase_status_text.toPlainText()
    assert screen.recommendation_text is not None
    assert screen.draft_status_text is None


def test_new_franchise_setup_defaults_to_lakers_user_team_and_all_other_ai_teams(tmp_path: Path) -> None:
    app = qt_app()
    screen = FranchiseScreen(FullLeagueFranchiseModel(), db_path=tmp_path / "franchise.sqlite")
    screen._test_qt_app = app

    assert screen.user_team_combo is not None
    assert screen._selected_user_team_index() == 13
    assert screen.user_team_combo.currentText() == "[13] Los Angeles Lakers"
    assert screen._selected_team_indexes() == tuple(index for index in range(30) if index != 13)
    assert screen.team_checkboxes[13].isChecked() is False
    assert screen.team_checkboxes[13].isEnabled() is False
    for index, checkbox in screen.team_checkboxes.items():
        if index == 13:
            continue
        assert checkbox.isChecked() is True
        assert checkbox.isEnabled() is True


def test_starting_non_fantasy_replaces_setup_controls_in_visible_ui(tmp_path: Path) -> None:
    app = qt_app()
    db_path = tmp_path / "franchise.sqlite"
    repository = FranchiseRepository(db_path)
    repository.replace_franchise(
        FranchiseSetup(
            start_year=1946,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=True,
            user_team_index=5,
        ),
        (
            FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),
            FranchiseTeamOption(5, "User Team", "[5] User Team"),
        ),
        target_executable="NBA2K26.exe",
    )

    repository.start_fantasy_draft(team_count=2, user_team_index=5)
    screen = FranchiseScreen(
        ReadOnlyFranchiseModel(),
        db_path=db_path,
        profile_client=FakeTeamProfileClient(),
    )
    screen.show()
    screen._show_new_franchise_setup()
    assert screen.fantasy_draft_checkbox is not None
    screen.fantasy_draft_checkbox.setChecked(False)
    for team_index, checkbox in screen.team_checkboxes.items():
        if team_index != screen._selected_user_team_index():
            checkbox.setChecked(team_index == 0)

    screen._start_franchise()
    for _ in range(100):
        flush_qt_events(app)
        screen._poll_team_profile_generation()
        if screen.phase_status_text is not None:
            break
    flush_qt_events(app)

    visible_titles = {group.title() for group in screen.findChildren(QGroupBox) if group.isVisible()}
    visible_buttons = {button.text() for button in screen.findChildren(QPushButton) if button.isVisible()}
    assert screen.repository.load().setup.fantasy_draft is False
    assert screen.repository.load_fantasy_draft_state() is None
    assert "Team GM Recommendations" in visible_titles
    assert "League Setup" not in visible_titles
    assert "AI League Teams" not in visible_titles
    assert "Fantasy Draft Room" not in visible_titles
    assert "Start Franchise" not in visible_buttons
    assert "Back" not in visible_buttons


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


def _franchise_sim_state(*, sim_year: int = 1946, phase: str = "season") -> FranchiseSimState:
    return FranchiseSimState(
        sim_year=sim_year,
        current_phase=phase,
        status=STATUS_READY,
        expansion_draft_required=False,
        expected_next_phase="",
        expected_next_year=sim_year,
        required_user_action="",
        updated_at="",
    )


def _write_offseason_growth_fixture(root: Path) -> None:
    pool_dir = root / "player_generation_pool"
    pool_dir.mkdir(parents=True)
    connection = sqlite3.connect(pool_dir / "player_generation_pool.sqlite")
    try:
        connection.executescript(
            """
            CREATE TABLE pool_runs(run_id TEXT);
            CREATE TABLE candidate_pool(run_id TEXT, player_index INTEGER, master_player_id TEXT, master_player TEXT);
            """
        )
        connection.execute("INSERT INTO pool_runs(run_id) VALUES(?)", ("editor_capture_test",))
        connection.execute(
            "INSERT INTO candidate_pool(run_id, player_index, master_player_id, master_player) VALUES(?,?,?,?)",
            ("editor_capture_test", 4, "jamesle01", "LeBron James"),
        )
        connection.commit()
    finally:
        connection.close()

    growth_dir = root / "statistical_growth_model"
    growth_dir.mkdir(parents=True)
    connection = sqlite3.connect(growth_dir / "player_growth_model.sqlite")
    try:
        connection.executescript(
            """
            CREATE TABLE player_growth_profile(
                player_id TEXT, player TEXT, season INTEGER, next_season INTEGER,
                total_metric_count INTEGER, improved_count INTEGER, declined_count INTEGER, unchanged_count INTEGER,
                strongest_source_table TEXT, weakest_source_table TEXT, coverage_confidence TEXT
            );
            CREATE TABLE player_growth_source_profile(player_id TEXT, season INTEGER, source_table TEXT, metric_count INTEGER);
            """
        )
        connection.execute(
            "INSERT INTO player_growth_profile VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("jamesle01", "LeBron James", 2004, 2005, 291, 230, 57, 4, "crafted_standardized_metrics", "player_totals", "full"),
        )
        connection.execute(
            "INSERT INTO player_growth_source_profile VALUES(?,?,?,?)",
            ("jamesle01", 2004, "player_per_game", 25),
        )
        connection.commit()
    finally:
        connection.close()


def test_franchise_llm_view_adds_growth_only_as_offseason_progression_context(tmp_path: Path) -> None:
    _write_offseason_growth_fixture(tmp_path)
    model = ReadOnlyFranchiseModel()

    view = build_franchise_llm_view(model, progression_season=2004, growth_data_root=tmp_path)

    facts = dict(view.roster_slots[0].offseason_progression_facts)
    assert facts["growth_model_mapping_source"] == "player_generation_pool:editor_capture_test:player_index"
    assert facts["growth_model_master_player_id"] == "jamesle01"
    assert facts["growth_model_next_season"] == "2005"
    assert facts["growth_model_metric_count"] == "291"
    assert "growth_model_sources" in facts


def test_team_recommendation_prompt_carries_growth_for_offseason_progression_not_draft(tmp_path: Path) -> None:
    _write_offseason_growth_fixture(tmp_path)
    (tmp_path / "team_00_profile.md").write_text(
        "---\nname: Team Zero Staff\n---\n# Team Zero\nGM: develop real players\n",
        encoding="utf-8",
    )
    model = ReadOnlyFranchiseModel()
    record = _franchise_record_for_recommendations()

    requests = build_team_recommendation_requests(
        record,
        model,
        sim_state=_franchise_sim_state(sim_year=2004, phase="player_progression"),
        profile_dir=tmp_path,
        progression_season=2004,
        growth_data_root=tmp_path,
    )
    payload = json.loads(requests[0].task.prompt)

    progression = payload["team"]["current_roster"][0]["offseason_progression"]
    assert progression["growth_model_master_player_id"] == "jamesle01"
    assert progression["growth_model_metric_count"] == "291"
    assert "offseason_player_progression" in payload["allowed_recommendation_types"]
    assert any("not fantasy draft decisions" in rule for rule in payload["rules"])


class FakeRecommendationClient:
    def available(self) -> bool:
        return True

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        assert "franchise_team_gm_recommendation" in prompt
        assert "team-GM recommendation" in system_prompt
        return (
            '{"team_index":0,"team_label":"Team 0","recommended_action":"Set a conservative 1946 scouting focus",'
            '"reasoning":"Roster is thin and era rules favor real-player discovery.",'
            '"owner_approval_required":true,"trade_with_user_team":false,"blocked_reason":""}'
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

    requests = build_team_recommendation_requests(
        record,
        model,
        sim_state=_franchise_sim_state(phase="season"),
        profile_dir=tmp_path,
    )

    assert len(requests) == 1
    assert requests[0].team_index == 0
    assert requests[0].task.task_name == "franchise_team_gm_recommendation"
    assert requests[0].task.profile.name == "Team Zero Staff"
    assert "franchise_team_gm_recommendation" in requests[0].task.prompt
    assert '"true_sim_year": 1946' in requests[0].task.prompt
    assert '"current_phase": "season"' in requests[0].task.prompt
    assert '"trade_with_user_team"' in requests[0].task.prompt
    assert "Team Zero Staff" in requests[0].task.prompt
    assert "[4] Player Four" in requests[0].task.prompt
    assert model.write_called is False


def test_team_recommendation_response_and_runner_are_structured() -> None:
    request = _recommendation_request()

    recommendation = run_team_recommendation_request(request, client=FakeRecommendationClient())

    assert recommendation.team_index == 0
    assert recommendation.recommended_action == "Set a conservative 1946 scouting focus"
    assert recommendation.owner_approval_required is True
    assert recommendation.trade_with_user_team is False
    assert recommendation.status == "pending"
    assert recommendation.raw_llm_response.startswith("{")


def test_team_recommendation_parser_rejects_wrong_team() -> None:
    request = _recommendation_request(team_index=7, prompt="{}")
    response = (
        '{"team_index":0,"team_label":"Team 0","recommended_action":"No action",'
        '"reasoning":"Wrong team.","owner_approval_required":false,'
        '"trade_with_user_team":false,"blocked_reason":""}'
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
            trade_with_user_team=False,
            blocked_reason="",
            raw_llm_response='{"team_index":0}',
        )
    )

    recommendations = repository.list_team_recommendations()

    assert saved.recommendation_id == 1
    assert len(recommendations) == 1
    assert recommendations[0].recommended_action == "Scout real centers only"
    assert recommendations[0].owner_approval_required is False
    assert recommendations[0].trade_with_user_team is False


def test_existing_recommendation_table_adds_explicit_user_trade_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "franchise.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE team_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_index INTEGER NOT NULL,
                team_label TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                owner_approval_required INTEGER NOT NULL,
                blocked_reason TEXT NOT NULL,
                raw_llm_response TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO team_recommendations(
                team_index, team_label, recommended_action, reasoning,
                owner_approval_required, blocked_reason, raw_llm_response, status, created_at
            ) VALUES(0, 'Team Zero', 'No action', 'Existing record', 0, '', '{}', 'pending', '2032-01-01');
            """
        )
        connection.commit()
    finally:
        connection.close()

    recommendations = FranchiseRepository(db_path).list_team_recommendations()

    assert len(recommendations) == 1
    assert recommendations[0].trade_with_user_team is False


def _repository_with_franchise(tmp_path: Path, *, start_year: int = 2032) -> FranchiseRepository:
    repository = FranchiseRepository(tmp_path / "franchise.sqlite")
    record = repository.replace_franchise(
        FranchiseSetup(
            start_year=start_year,
            keep_full_league_save=False,
            llm_gm_team_indexes=(0,),
            fantasy_draft=False,
            user_team_index=13,
        ),
        (
            FranchiseTeamOption(0, "Team Zero", "[0] Team Zero"),
            FranchiseTeamOption(13, "Los Angeles Lakers", "[13] Los Angeles Lakers"),
        ),
    )
    write_ready_team_profiles(record)
    return repository


def test_franchise_phase_sequence_matches_game_and_conditionally_inserts_expansion_draft() -> None:
    expected_without_expansion = (
        "season",
        "playoffs",
        "player_retirements",
        "staff_retirements",
        "hall_of_fame_inductees",
        "league_meetings",
        "staff_signing",
        "draft_lottery",
        "draft_combine",
        "pre_draft_workouts",
        "nba_draft",
        "rookie_signing",
        "team_player_options",
        "qualifying_offers",
        "free_agency",
        "player_progression",
        "nba_summer_league",
        "fiba_friendlies",
        "all_star_city_selection",
        "2k_hoops_summit",
        "advance_to_next_season",
    )

    without_expansion = tuple(
        phase.key for phase in franchise_phase_sequence(expansion_draft_required=False)
    )
    with_expansion = tuple(
        phase.key for phase in franchise_phase_sequence(expansion_draft_required=True)
    )

    assert without_expansion == expected_without_expansion
    expansion_index = with_expansion.index("expansion_draft")
    assert with_expansion[:expansion_index] == expected_without_expansion[:10]
    assert with_expansion[expansion_index + 1 :] == expected_without_expansion[10:]


def test_phase_controller_pauses_for_conditional_expansion_then_main_draft(tmp_path: Path) -> None:
    repository = _repository_with_franchise(tmp_path)
    repository.sync_sim_state(sim_year=2032, current_phase="pre_draft_workouts")
    repository.set_expansion_draft_required(True)

    waiting_for_expansion = repository.pause_for_game_advance()

    assert waiting_for_expansion.status == STATUS_WAITING_FOR_GAME_ADVANCE
    assert waiting_for_expansion.expected_next_phase == "expansion_draft"
    assert "Expansion Draft" in waiting_for_expansion.required_user_action

    expansion = repository.sync_and_resume(observed_phase="expansion_draft", observed_sim_year=2032)
    assert expansion.status == STATUS_READY
    assert expansion.current_phase == "expansion_draft"

    waiting_for_main_draft = repository.pause_for_game_advance()
    assert waiting_for_main_draft.expected_next_phase == "nba_draft"


def test_phase_controller_skips_expansion_when_no_team_was_added(tmp_path: Path) -> None:
    repository = _repository_with_franchise(tmp_path)
    repository.sync_sim_state(sim_year=2032, current_phase="pre_draft_workouts")

    waiting = repository.pause_for_game_advance()

    assert waiting.expected_next_phase == "nba_draft"
    assert "NBA Draft" in waiting.required_user_action


def test_advance_to_next_season_increments_true_year_and_clears_expansion_flag(tmp_path: Path) -> None:
    repository = _repository_with_franchise(tmp_path)
    repository.sync_sim_state(sim_year=2032, current_phase="advance_to_next_season")
    repository.set_expansion_draft_required(True)

    waiting = repository.pause_for_game_advance()
    assert waiting.expected_next_phase == "season"
    assert waiting.expected_next_year == 2033

    resumed = repository.sync_and_resume(observed_phase="season", observed_sim_year=2033)
    assert resumed.current_phase == "season"
    assert resumed.sim_year == 2033
    assert resumed.status == STATUS_READY
    assert resumed.expansion_draft_required is False


def test_user_team_trade_recommendation_pauses_controller_until_resolved(tmp_path: Path) -> None:
    repository = _repository_with_franchise(tmp_path)

    paused = repository.pause_for_user_trade(
        "Team Zero proposes a trade with the user-controlled Los Angeles Lakers."
    )

    assert paused.status == STATUS_WAITING_FOR_USER_TRADE
    assert "Los Angeles Lakers" in paused.required_user_action

    resumed = repository.resume_after_user_trade()
    assert resumed.status == STATUS_READY
    assert resumed.required_user_action == ""


def test_franchise_screen_trade_recommendation_enters_user_pause(tmp_path: Path) -> None:
    app = qt_app()
    db_path = tmp_path / "franchise.sqlite"
    repository = _repository_with_franchise(tmp_path)
    screen = FranchiseScreen(ReadOnlyFranchiseModel(), db_path=db_path)
    screen._test_qt_app = app
    screen._load_franchise_dashboard()

    screen._finish_team_recommendations(
        (
            TeamRecommendation(
                team_index=0,
                team_label="Team Zero",
                recommended_action="Offer two players for the Lakers center",
                reasoning="The roster needs size.",
                owner_approval_required=True,
                trade_with_user_team=True,
                blocked_reason="",
            ),
        )
    )

    state = repository.load_sim_state()
    assert state is not None
    assert state.status == STATUS_WAITING_FOR_USER_TRADE
    assert "Team Zero" in state.required_user_action
    assert screen.phase_status_text is not None
    assert "WAITING FOR USER-TEAM TRADE DECISION" in screen.phase_status_text.toPlainText()
