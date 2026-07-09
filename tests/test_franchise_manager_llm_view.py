from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.control_room import (
    build_franchise_control_room_markdown,
    build_franchise_screen_context,
    build_screen_context_markdown,
)
from nba2k_editor.franchise.draft_room import (
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
from nba2k_editor.franchise.llm_view import build_franchise_llm_markdown, build_franchise_llm_view
from nba2k_editor.franchise.models import FranchiseRecord, FranchiseSetup


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
        self.selected_items = {"Players": self.player, "Teams": self.team}
        self.write_called = False

    def _field_by_normalized_name(self, domain: str, name: str) -> str | None:
        if domain == "Players" and name == "ISACTIVE":
            return "ISACTIVE"
        return None

    def read_entry_value(self, entry: str, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        active = entry == "ISACTIVE" and int(index) == int(self.player.index)
        return {"raw_value": 1 if active else 0, "display_value": "Yes" if active else "No"}

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
    assert all(player.player_label != "[8] Unused Player" for player in pool)
    assert model.write_called is False


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
    assert draft_position(4, team_order=order).team_index == 3
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
