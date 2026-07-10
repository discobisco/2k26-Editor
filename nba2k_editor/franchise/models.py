from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FranchiseTeamOption:
    team_index: int
    label: str
    display_label: str


@dataclass(frozen=True)
class FranchiseSetup:
    start_year: int
    keep_full_league_save: bool
    llm_gm_team_indexes: tuple[int, ...]
    fantasy_draft: bool
    user_team_index: int = 0


@dataclass(frozen=True)
class FranchiseRecord:
    setup: FranchiseSetup
    team_options: tuple[FranchiseTeamOption, ...]
    database_path: str
    full_league_save_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FantasyDraftState:
    current_pick_number: int
    team_count: int
    user_team_index: int
    started_at: str
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
    raw_llm_response: str = ""
    rationale: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class TeamRecommendation:

    team_index: int
    team_label: str
    recommended_action: str
    reasoning: str
    owner_approval_required: bool
    blocked_reason: str
    raw_llm_response: str = ""
    status: str = "pending"
    created_at: str = ""
    recommendation_id: int = 0
