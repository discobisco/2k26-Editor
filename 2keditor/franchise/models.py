from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LEAGUE_MODE_NBA = "nba"
LEAGUE_MODE_COLLEGE = "college"
LEAGUE_MODES = (LEAGUE_MODE_NBA, LEAGUE_MODE_COLLEGE)


def normalize_league_mode(value: str) -> str:
    mode = str(value).strip().casefold()
    if mode not in LEAGUE_MODES:
        raise ValueError(f"unknown franchise league mode: {value}")
    return mode


def league_mode_label(value: str) -> str:
    return "College" if normalize_league_mode(value) == LEAGUE_MODE_COLLEGE else "NBA"


@dataclass(frozen=True)
class FranchiseTeamOption:
    team_index: int
    label: str
    display_label: str


@dataclass(frozen=True)
class FranchiseSetup:
    start_year: int
    keep_full_league_save: bool
    fantasy_draft: bool
    user_team_index: int = 0
    league_mode: str = LEAGUE_MODE_NBA


@dataclass(frozen=True)
class FranchiseRecord:
    setup: FranchiseSetup
    team_options: tuple[FranchiseTeamOption, ...]
    database_path: str
    full_league_save_count: int
    created_at: str
    updated_at: str
    franchise_id: str = ""


@dataclass(frozen=True)
class FantasyDraftState:
    current_pick_number: int
    team_count: int
    user_team_index: int
    team_order: tuple[int, ...]
    started_at: str
    updated_at: str


@dataclass(frozen=True)
class FranchiseSimState:
    sim_year: int
    current_phase: str
    status: str
    expansion_draft_required: bool
    expected_next_phase: str
    expected_next_year: int
    required_user_action: str
    updated_at: str


@dataclass(frozen=True)
class FantasyDraftStoredPick:
    pick_number: int
    round_number: int
    team_index: int
    team_label: str
    player_index: int
    player_label: str
    source_team_index: int
    source_slot: int
    source_slot_field: str
    picked_by: str
    created_at: str = ""


@dataclass(frozen=True)
class ManualDraftPick:
    draft_year: int
    round_number: int
    original_team_index: int
    current_team_index: int


COLLEGE_PLAYER_ACTIVE = "active"
COLLEGE_PLAYER_DEPARTED = "departed"


@dataclass(frozen=True)
class CollegeConference:
    conference_id: str
    name: str


@dataclass(frozen=True)
class CollegeProgram:
    program_id: str
    conference_id: str
    name: str
    short_name: str
    team_fields: dict[str, Any]


@dataclass(frozen=True)
class CollegePlayer:
    player_id: str
    program_id: str
    display_name: str
    roster_order: int
    eligibility_remaining: int
    status: str
    player_fields: dict[str, Any]
    entry_year: int
    departure_year: int | None = None


@dataclass(frozen=True)
class CollegeTeamProjection:
    true_sim_year: int
    game_team_index: int
    program_id: str
    program_name: str
    selection_reason: str


@dataclass(frozen=True)
class CollegePlayerProjection:
    true_sim_year: int
    stage: str
    game_team_index: int
    roster_slot: int
    slot_field: str
    game_player_index: int
    canonical_player_id: str | None


@dataclass(frozen=True)
class CollegeTournamentGame:
    true_sim_year: int
    round_number: int
    game_number: int
    first_program_id: str
    second_program_id: str
    winner_program_id: str | None
