from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

import pytest
from PyQt6.QtWidgets import QApplication, QGroupBox

from nba2k_editor.franchise.college_dynasty import (
    PROJECTION_STAGE_SWEET16,
    CollegeDynastyRepository,
)
from nba2k_editor.franchise.models import (
    COLLEGE_PLAYER_ACTIVE,
    CollegeConference,
    CollegePlayer,
    CollegeProgram,
    FranchiseSetup,
    FranchiseTeamOption,
    LEAGUE_MODE_COLLEGE,
)
from nba2k_editor.franchise.profile_generation import copy_missing_team_profiles
from nba2k_editor.franchise.qt_screen import FranchiseScreen
from nba2k_editor.franchise.storage import FranchiseRepository


@dataclass(frozen=True)
class FakeItem:
    domain: str
    index: int
    address: int
    label: str

    @property
    def display_label(self) -> str:
        return f"[{self.index}] {self.label}"


@dataclass(frozen=True)
class FakeEntry:
    domain: str
    normalized_name: str


class ProjectionModel:
    target_executable = "NBA2K26.exe"

    def __init__(self) -> None:
        teams = tuple(FakeItem("Teams", index, 0x100000 + index * 0x1000, f"Team {index}") for index in range(30))
        players = tuple(FakeItem("Players", index, 0x200000 + index * 0x1000, f"Player {index}") for index in range(450))
        self.loaded_items = {
            "Teams": {item.display_label: item for item in teams},
            "Players": {item.display_label: item for item in players},
        }
        self._teams = {item.index: item for item in teams}
        self._players = {item.index: item for item in players}

        self._entries: dict[tuple[str, str], FakeEntry] = {}
        for name in (
            "FIRSTNAME",
            "LASTNAME",
            "HEIGHT",
            "WEIGHT",
            "WINGSPANCM",
            "CURRENTTEAM",
            "CONTRACTTEAM",
            "CONTRACTLENGTH",
            "YEARSLEFT",
            "ORIGINALCONTRACTYEARS",
            "OVR",
        ):
            self._entries[("Players", name)] = FakeEntry("Players", name)
        for name in ("TEAMNAME", "CITYNAME", *(f"PLAYER{slot}" for slot in range(1, 16))):
            self._entries[("Teams", name)] = FakeEntry("Teams", name)
        self.values: dict[tuple[str, int, str], object] = {}
        self.slots: dict[tuple[int, str], int] = {}
        for team in teams:
            for roster_slot in range(1, 16):
                player_index = team.index * 15 + roster_slot - 1
                player = self._players[player_index]
                slot_name = f"PLAYER{roster_slot}"
                self.slots[(team.index, slot_name)] = player.address
                self.values[("Players", player.index, "CURRENTTEAM")] = team.address
                self.values[("Players", player.index, "CONTRACTTEAM")] = team.address

    def runtime_status_text(self) -> str:
        return "attached"

    def _field_by_normalized_name(self, domain: str, name: str):
        return self._entries.get((domain, str(name).upper()))

    def player_roster_slot_items_for_team_items(self, teams):
        rows = []
        for team in teams:
            for roster_slot in range(1, 16):
                player = self._players[team.index * 15 + roster_slot - 1]
                rows.append(
                    (
                        player,
                        {
                            "team_index": team.index,
                            "team_label": team.label,
                            "team_slot": roster_slot,
                            "team_slot_field": f"PLAYER{roster_slot}",
                        },
                    )
                )
        return rows

    def read_entry_value_for_item(self, entry: FakeEntry, item: FakeItem):
        if entry.domain == "Teams" and entry.normalized_name.startswith("PLAYER"):
            value = self.slots[(item.index, entry.normalized_name)]
        else:
            value = self.values.get((entry.domain, item.index, entry.normalized_name), 0)
        return {"raw_value": value, "display_value": value}


def build_catalog() -> tuple[tuple[CollegeConference, ...], tuple[CollegeProgram, ...], tuple[CollegePlayer, ...]]:
    conferences = tuple(CollegeConference(f"c{index:02d}", f"Conference {index:02d}") for index in range(31))
    programs = tuple(
        CollegeProgram(
            program_id=f"p{index:03d}",
            conference_id=f"c{index % 31:02d}",
            name=f"Program {index:03d}",
            short_name=f"P{index:03d}",
            team_fields={"CITYNAME": f"City {index:03d}"},
        )
        for index in range(365)
    )
    players = tuple(
        CollegePlayer(
            player_id=f"p{program_index:03d}-player-{roster_order}",
            program_id=f"p{program_index:03d}",
            display_name=f"Canonical {program_index:03d}-{roster_order}",
            roster_order=roster_order,
            eligibility_remaining=4 if roster_order == 1 else 1,
            status=COLLEGE_PLAYER_ACTIVE,
            player_fields={
                "FIRSTNAME": f"First{program_index:03d}",
                "LASTNAME": f"Last{roster_order}",
                "OVR": 70 + roster_order,
            },
            entry_year=2025,
        )
        for program_index in range(365)
        for roster_order in range(1, 3)
    )
    return conferences, programs, players


def build_repository(tmp_path: Path) -> tuple[FranchiseRepository, CollegeDynastyRepository]:
    franchise = FranchiseRepository(tmp_path / "college.sqlite")
    teams = tuple(FranchiseTeamOption(index, f"Team {index}", f"[{index}] Team {index}") for index in range(30))
    franchise.replace_franchise(
        FranchiseSetup(
            start_year=2025,
            keep_full_league_save=False,
            llm_gm_team_indexes=tuple(index for index in range(30) if index != 13),
            fantasy_draft=False,
            user_team_index=13,
            league_mode=LEAGUE_MODE_COLLEGE,
        ),
        teams,
    )
    college = CollegeDynastyRepository(franchise)
    college.replace_catalog(*build_catalog())
    return franchise, college


def test_college_catalog_and_30_team_projection_are_persistent(tmp_path: Path) -> None:
    _franchise, college = build_repository(tmp_path)

    assert college.catalog_counts() == (31, 365, 730)
    first = college.plan_season(true_sim_year=2025, user_program_id="p000", random_seed=57)
    second = college.plan_season(true_sim_year=2025, user_program_id="p000", random_seed=999)

    assert first == second
    assert len(first) == 30
    assert next(row for row in first if row.selection_reason == "user").game_team_index == 13
    selected_ids = {row.program_id for row in first}
    expected_conference = {row.program_id for row in college.list_programs() if row.conference_id == "c00"}
    assert expected_conference.issubset(selected_ids)
    assert sum(row.selection_reason == "nonconference" for row in first) == 30 - len(expected_conference)


def test_projection_slot_mapping_persists_canonical_identity_and_supports_sync(tmp_path: Path) -> None:
    _franchise, college = build_repository(tmp_path)
    model = ProjectionModel()
    college.plan_season(true_sim_year=2025, user_program_id="p000", random_seed=57)
    mappings = college.capture_projection_slots(model, true_sim_year=2025)

    assert len(mappings) == 450
    assert len({row.game_player_index for row in mappings}) == 450
    user_mapping = next(row for row in mappings if row.game_team_index == 13 and row.roster_slot == 1)
    assert user_mapping.canonical_player_id is not None
    model.values[("Players", user_mapping.game_player_index, "OVR")] = 88
    synced = college.sync_projected_players_from_game(model, true_sim_year=2025)
    assert user_mapping.canonical_player_id in synced
    canonical = next(row for row in college.list_players() if row.player_id == user_mapping.canonical_player_id)
    assert canonical.player_fields["OVR"] == 88


def test_free_agent_departure_and_eligibility_advance_are_persistent_and_idempotent(tmp_path: Path) -> None:
    _franchise, college = build_repository(tmp_path)
    model = ProjectionModel()
    college.plan_season(true_sim_year=2025, user_program_id="p000", random_seed=57)
    projections = college.capture_projection_slots(model, true_sim_year=2025)
    projected_real = next(row for row in projections if row.canonical_player_id is not None)
    model.values[("Players", projected_real.game_player_index, "CURRENTTEAM")] = 0

    departed = college.record_free_agent_departures(model, true_sim_year=2025)
    assert departed == (projected_real.canonical_player_id,)
    player = next(row for row in college.list_players() if row.player_id == projected_real.canonical_player_id)
    assert player.status == "departed"
    assert player.eligibility_remaining == 0
    replacement = CollegePlayer(
        player_id=f"{player.program_id}-new-recruit",
        program_id=player.program_id,
        display_name="New Recruit",
        roster_order=player.roster_order,
        eligibility_remaining=4,
        status=COLLEGE_PLAYER_ACTIVE,
        player_fields={"FIRSTNAME": "New", "LASTNAME": "Recruit"},
        entry_year=2026,
    )
    assert college.upsert_players((replacement,)) == (replacement.player_id,)
    with pytest.raises(ValueError, match="cannot be restored"):
        college.upsert_players(
            (
                CollegePlayer(
                    player_id=player.player_id,
                    program_id=player.program_id,
                    display_name=player.display_name,
                    roster_order=player.roster_order,
                    eligibility_remaining=4,
                    status=COLLEGE_PLAYER_ACTIVE,
                    player_fields=player.player_fields,
                    entry_year=player.entry_year,
                ),
            )
        )

    exhausted = college.advance_eligibility(true_sim_year=2025)
    assert exhausted
    replacement_after_advance = next(row for row in college.list_players() if row.player_id == replacement.player_id)
    assert replacement_after_advance.eligibility_remaining == 4
    assert college.advance_eligibility(true_sim_year=2025) == ()
    remaining = next(row for row in college.list_players() if row.player_id == "p364-player-1")
    assert remaining.eligibility_remaining == 3


def test_external_rounds_produce_sweet16_and_map_to_16_playoff_teams(tmp_path: Path) -> None:
    _franchise, college = build_repository(tmp_path)
    model = ProjectionModel()
    bracket = tuple(f"p{index:03d}" for index in range(64))
    round_one = college.create_tournament(true_sim_year=2025, bracket_program_ids=bracket)
    assert len(round_one) == 32

    for game in round_one:
        college.record_tournament_winner(
            true_sim_year=2025,
            round_number=1,
            game_number=game.game_number,
            winner_program_id=game.first_program_id,
        )
    round_two = college.list_tournament_games(2025, round_number=2)
    assert len(round_two) == 16
    for game in round_two:
        college.record_tournament_winner(
            true_sim_year=2025,
            round_number=2,
            game_number=game.game_number,
            winner_program_id=game.first_program_id,
        )

    sweet16 = college.sweet16_program_ids(2025)
    assert len(sweet16) == 16
    mapped = college.plan_sweet16_projection(true_sim_year=2025, playoff_team_indexes=range(16))
    assert tuple(row.program_id for row in mapped) == sweet16
    player_mappings = college.capture_projection_slots(
        model,
        true_sim_year=2025,
        stage=PROJECTION_STAGE_SWEET16,
    )
    assert len(player_mappings) == 240
    for round_number, expected_games in ((3, 8), (4, 4), (5, 2), (6, 1)):
        games = college.list_tournament_games(2025, round_number=round_number)
        assert len(games) == expected_games
        for game in games:
            college.record_tournament_winner(
                true_sim_year=2025,
                round_number=round_number,
                game_number=game.game_number,
                winner_program_id=game.first_program_id,
            )
    assert college.champion_program_id(2025) == "p000"


def test_tournament_rejects_nonparticipant_winner(tmp_path: Path) -> None:
    _franchise, college = build_repository(tmp_path)
    college.create_tournament(true_sim_year=2025, bracket_program_ids=(f"p{index:03d}" for index in range(64)))

    with pytest.raises(ValueError, match="two programs"):
        college.record_tournament_winner(
            true_sim_year=2025,
            round_number=1,
            game_number=1,
            winner_program_id="p100",
        )


def test_college_schema_migrates_old_player_and_two_round_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "old-college.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE college_players (
                player_id TEXT PRIMARY KEY,
                program_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                roster_order INTEGER NOT NULL,
                eligibility_remaining INTEGER NOT NULL CHECK (eligibility_remaining BETWEEN 0 AND 4),
                status TEXT NOT NULL CHECK (status IN ('active', 'departed')),
                player_fields_json TEXT NOT NULL,
                entry_year INTEGER NOT NULL,
                departure_year INTEGER,
                UNIQUE(program_id, roster_order)
            );
            CREATE TABLE college_tournament_games (
                true_sim_year INTEGER NOT NULL,
                round_number INTEGER NOT NULL CHECK (round_number IN (1, 2)),
                game_number INTEGER NOT NULL,
                first_program_id TEXT NOT NULL,
                second_program_id TEXT NOT NULL,
                winner_program_id TEXT,
                PRIMARY KEY(true_sim_year, round_number, game_number)
            );
            """
        )
    repository = FranchiseRepository(db_path)
    connection = repository._connect()
    try:
        repository.initialize(connection)
        player_sql = str(
            connection.execute("SELECT sql FROM sqlite_master WHERE name = 'college_players'").fetchone()[0]
        )
        game_sql = str(
            connection.execute("SELECT sql FROM sqlite_master WHERE name = 'college_tournament_games'").fetchone()[0]
        )
        active_index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_college_players_active_roster'"
        ).fetchone()
    finally:
        connection.close()
    assert "UNIQUE(program_id, roster_order)" not in player_sql
    assert "BETWEEN 1 AND 6" in game_sql
    assert active_index == ("idx_college_players_active_roster",)


def test_visible_college_dashboard_shows_canonical_projection_and_sweet16_state(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    franchise, college = build_repository(tmp_path)
    model = ProjectionModel()
    college.plan_season(true_sim_year=2025, user_program_id="p000", random_seed=57)
    college.capture_projection_slots(model, true_sim_year=2025)
    round_one = college.create_tournament(
        true_sim_year=2025,
        bracket_program_ids=(f"p{index:03d}" for index in range(64)),
    )
    for game in round_one:
        college.record_tournament_winner(
            true_sim_year=2025,
            round_number=1,
            game_number=game.game_number,
            winner_program_id=game.first_program_id,
        )
    for game in college.list_tournament_games(2025, round_number=2):
        college.record_tournament_winner(
            true_sim_year=2025,
            round_number=2,
            game_number=game.game_number,
            winner_program_id=game.first_program_id,
        )
    college.plan_sweet16_projection(true_sim_year=2025, playoff_team_indexes=range(16))
    college.capture_projection_slots(model, true_sim_year=2025, stage=PROJECTION_STAGE_SWEET16)

    record = franchise.load()
    copy_missing_team_profiles(record)

    screen = FranchiseScreen(model, db_path=tmp_path / "college.sqlite")
    screen._load_franchise_dashboard()
    screen.show()
    app.processEvents()

    visible_groups = {group.title() for group in screen.findChildren(QGroupBox) if group.isVisible()}
    assert "College Dynasty Universe" in visible_groups
    assert screen.college_status_text is not None
    status = screen.college_status_text.toPlainText()
    assert "Conferences: 31/31" in status
    assert "Programs: 365/365" in status
    assert "Season Teams: 30/30" in status
    assert "Reserved Season Player Records: 450/450" in status
    assert "Sweet 16 Winners: 16/16" in status
    assert "Reserved Sweet 16 Player Records: 240/240" in status
    screen.close()
