from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGroupBox

from nba2k_editor.franchise.models import (
    LEAGUE_MODE_COLLEGE,
    LEAGUE_MODE_NBA,
    FranchiseSetup,
    FranchiseTeamOption,
)
from nba2k_editor.franchise.profile_generation import (
    copy_missing_team_profiles,
    pregenerated_team_profile_path,
    team_profile_path,
    team_profiles_complete,
)
from nba2k_editor.franchise.qt_screen import FranchiseScreen
from nba2k_editor.franchise.recommendations import build_team_recommendation_requests
from nba2k_editor.franchise.sim_phases import franchise_phase_sequence
from nba2k_editor.franchise.storage import FranchiseRepository


@dataclass(frozen=True)
class FakeItem:
    index: int
    label: str
    display_label: str


class CollegeModel:
    target_executable = "NBA2K26.exe"

    def __init__(self) -> None:
        team_zero = FakeItem(0, "College Zero", "[0] College Zero")
        team_one = FakeItem(1, "College One", "[1] College One")
        self.loaded_items = {
            "Players": {},
            "Teams": {
                team_zero.display_label: team_zero,
                team_one.display_label: team_one,
            },
        }

    def player_roster_slot_items_for_team_items(self, _teams):
        return ()

    def runtime_status_text(self) -> str:
        return "attached"



def college_setup() -> FranchiseSetup:
    return FranchiseSetup(
        start_year=1985,
        keep_full_league_save=False,
        llm_gm_team_indexes=(1,),
        fantasy_draft=False,
        user_team_index=0,
        league_mode=LEAGUE_MODE_COLLEGE,
    )


def college_teams() -> tuple[FranchiseTeamOption, ...]:
    return (
        FranchiseTeamOption(0, "College Zero", "[0] College Zero"),
        FranchiseTeamOption(1, "College One", "[1] College One"),
    )


def write_ready_college_profiles(record) -> None:
    copy_missing_team_profiles(record)


def test_college_mode_persists_and_uses_separate_phase_cycle(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "college.sqlite")
    record = repository.replace_franchise(college_setup(), college_teams())

    assert record.setup.league_mode == LEAGUE_MODE_COLLEGE
    state = repository.ensure_sim_state()
    assert state.current_phase == "preseason"
    assert tuple(
        phase.key
        for phase in franchise_phase_sequence(
            expansion_draft_required=False,
            league_mode=LEAGUE_MODE_COLLEGE,
        )
    ) == (
        "preseason",
        "regular_season",
        "postseason",
        "roster_departures",
        "player_transfers",
        "recruiting",
        "player_development",
        "advance_to_next_season",
    )

    waiting = repository.pause_for_game_advance()
    assert waiting.expected_next_phase == "regular_season"
    assert "Regular Season" in waiting.required_user_action
    resumed = repository.sync_and_resume(observed_phase="regular_season", observed_sim_year=1985)
    assert resumed.current_phase == "regular_season"

    with pytest.raises(ValueError, match="Expansion Draft"):
        repository.set_expansion_draft_required(True)


def test_college_mode_rejects_nba_fantasy_draft(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "college.sqlite")
    invalid_setup = FranchiseSetup(
        start_year=2025,
        keep_full_league_save=False,
        llm_gm_team_indexes=(1,),
        fantasy_draft=True,
        user_team_index=0,
        league_mode=LEAGUE_MODE_COLLEGE,
    )

    with pytest.raises(ValueError, match="fantasy draft"):
        repository.replace_franchise(invalid_setup, college_teams())


def test_saved_franchise_without_mode_key_loads_as_nba(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    repository = FranchiseRepository(db_path)
    repository.replace_franchise(
        FranchiseSetup(2025, False, (1,), False, 0),
        college_teams(),
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM franchise_meta WHERE key = 'league_mode'")
        connection.commit()

    assert repository.load().setup.league_mode == LEAGUE_MODE_NBA


def test_college_mode_copies_the_pregenerated_team_profiles(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "college.sqlite")
    record = repository.replace_franchise(college_setup(), college_teams())
    copied = copy_missing_team_profiles(record)

    assert copied == (team_profile_path(record, 0), team_profile_path(record, 1))
    assert team_profile_path(record, 0).read_bytes() == pregenerated_team_profile_path(0).read_bytes()
    assert team_profile_path(record, 1).read_bytes() == pregenerated_team_profile_path(1).read_bytes()
    assert team_profiles_complete(record) is True


def test_college_recommendation_prompt_excludes_nba_action_types(tmp_path: Path) -> None:
    repository = FranchiseRepository(tmp_path / "college.sqlite")
    record = repository.replace_franchise(college_setup(), college_teams())
    write_ready_college_profiles(record)

    request = build_team_recommendation_requests(
        record,
        CollegeModel(),
        sim_state=repository.ensure_sim_state(),
    )[0]
    payload = json.loads(request.task.prompt)

    assert request.task.task_name == "college_program_recommendation"
    assert payload["franchise"]["league_mode"] == LEAGUE_MODE_COLLEGE
    assert payload["franchise"]["current_phase"] == "preseason"
    assert "recruiting_focus" in payload["allowed_recommendation_types"]
    assert "transfer_evaluation" in payload["allowed_recommendation_types"]
    assert "trade_target" not in payload["allowed_recommendation_types"]
    assert "signing_target" not in payload["allowed_recommendation_types"]
    assert "draft_strategy" not in payload["allowed_recommendation_types"]
    rules = " ".join(payload["rules"])
    assert "do not apply modern rules to earlier eras" in rules
    assert "college programs do not trade players" in rules


def test_college_setup_and_dashboard_use_college_controls(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    model = CollegeModel()
    setup_screen = FranchiseScreen(model, db_path=tmp_path / "setup.sqlite")
    assert setup_screen.league_mode_combo is not None
    college_index = setup_screen.league_mode_combo.findData(LEAGUE_MODE_COLLEGE)
    setup_screen.league_mode_combo.setCurrentIndex(college_index)
    app.processEvents()

    assert setup_screen._current_setup().league_mode == LEAGUE_MODE_COLLEGE
    assert setup_screen.fantasy_draft_checkbox is not None
    assert setup_screen.fantasy_draft_checkbox.isChecked() is False
    assert setup_screen.fantasy_draft_checkbox.isEnabled() is False

    db_path = tmp_path / "dashboard.sqlite"
    repository = FranchiseRepository(db_path)
    record = repository.replace_franchise(college_setup(), college_teams())
    write_ready_college_profiles(record)
    screen = FranchiseScreen(model, db_path=db_path)
    screen._load_franchise_dashboard()
    screen.show()
    app.processEvents()

    titles = {group.title() for group in screen.findChildren(QGroupBox) if group.isVisible()}
    assert "College Program Phase Controller" in titles
    assert "College Program Recommendations" in titles
    assert "Fantasy Draft Room" not in titles
    assert screen.phase_status_text is not None
    phase_text = screen.phase_status_text.toPlainText()
    assert "Current Phase: Preseason" in phase_text
    assert "Recruiting" in phase_text
    assert "NBA Draft" not in phase_text
    assert "Free Agency" not in phase_text
    assert screen.phase_combo is not None
    assert tuple(screen.phase_combo.itemData(index) for index in range(screen.phase_combo.count())) == (
        "preseason",
        "regular_season",
        "postseason",
        "roster_departures",
        "player_transfers",
        "recruiting",
        "player_development",
        "advance_to_next_season",
    )
    screen.close()
    setup_screen.close()
