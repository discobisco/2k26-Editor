from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SeasonPhase(StrEnum):
    PRESEASON = "preseason"
    REGULAR_SEASON = "regular_season"
    PLAYOFFS = "playoffs"
    CHAMPIONSHIP = "championship"
    RETIREMENTS = "retirements"
    OWNER_EVALUATION = "owner_evaluation"
    GM_EVALUATION = "gm_evaluation"
    DRAFT_PREPARATION = "draft_preparation"
    DRAFT = "draft"
    FREE_AGENCY = "free_agency"
    TRAINING_CAMP = "training_camp"
    PROGRESSION_REGRESSION = "progression_regression"
    NEXT_SEASON = "next_season"


SEASON_FLOW: tuple[SeasonPhase, ...] = (
    SeasonPhase.PRESEASON,
    SeasonPhase.REGULAR_SEASON,
    SeasonPhase.PLAYOFFS,
    SeasonPhase.CHAMPIONSHIP,
    SeasonPhase.RETIREMENTS,
    SeasonPhase.OWNER_EVALUATION,
    SeasonPhase.GM_EVALUATION,
    SeasonPhase.DRAFT_PREPARATION,
    SeasonPhase.DRAFT,
    SeasonPhase.FREE_AGENCY,
    SeasonPhase.TRAINING_CAMP,
    SeasonPhase.PROGRESSION_REGRESSION,
    SeasonPhase.NEXT_SEASON,
)


class ControlMode(StrEnum):
    USER = "user"
    AI = "ai"


class StopPriority(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
    EMERGENCY = "emergency"


class TeamDirection(StrEnum):
    CONTEND = "contend"
    REBUILD = "rebuild"
    EVALUATE = "evaluate"
    TANK = "tank"


class ImportedDataKind(StrEnum):
    STANDINGS = "standings"
    TEAM_STATS = "team_stats"
    PLAYER_STATS = "player_stats"
    INJURIES = "injuries"
    MINUTES = "minutes"
    TRADES = "trades"
    AWARDS = "awards"
    CONTRACTS = "contracts"
    PLAYOFF_RESULTS = "playoff_results"


class DraftClassMode(StrEnum):
    DRAFT_PICKS = "draft_picks"
    ROOKIE_YEAR = "rookie_year"


@dataclass(frozen=True)
class RealismSettings:
    historical_accuracy: int = 70
    randomness: int = 30
    injury_severity: int = 50
    owner_patience: int = 50
    gm_aggression: int = 50
    draft_accuracy: int = 70
    bust_frequency: int = 30
    steal_frequency: int = 30
    trade_frequency: int = 50
    player_loyalty: int = 50
    salary_inflation: int = 50
    alternate_history_strength: int = 30


@dataclass(frozen=True)
class OwnerProfile:
    name: str
    patience: int = 50
    spending_willingness: int = 50
    loyalty: int = 50
    risk_tolerance: int = 50
    rebuild_tolerance: int = 50
    championship_expectations: int = 50
    profit_motivation: int = 50
    market_pressure_sensitivity: int = 50
    veteran_preference: int = 50
    youth_preference: int = 50
    firing_threshold: int = 50
    personality_notes: str = ""


@dataclass(frozen=True)
class GMProfile:
    name: str
    aggression: int = 50
    patience: int = 50
    draft_skill: int = 50
    scouting_skill: int = 50
    contract_discipline: int = 50
    trade_frequency: int = 50
    risk_tolerance: int = 50
    veteran_preference: int = 50
    prospect_preference: int = 50
    position_preferences: tuple[str, ...] = ()
    team_building_style: str = "balanced"


@dataclass(frozen=True)
class TeamControl:
    owner: ControlMode = ControlMode.AI
    gm: ControlMode = ControlMode.AI


@dataclass(frozen=True)
class FranchiseTeam:
    team_id: str
    display_name: str
    owner: OwnerProfile
    gm: GMProfile
    control: TeamControl = field(default_factory=TeamControl)


@dataclass(frozen=True)
class StopPoint:
    season: int
    phase: SeasonPhase
    date_label: str
    reason: str
    priority: StopPriority = StopPriority.REQUIRED
    team_id: str | None = None
    resolved: bool = False


@dataclass(frozen=True)
class ImportedSnapshot:
    season: int
    stop_id: int | None
    kind: ImportedDataKind
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReasonLog:
    season: int
    team_id: str
    actor: str
    message: str
    action: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamEvaluation:
    team_id: str
    direction: TeamDirection
    owner_report: str
    gm_report: str
    recommended_actions: tuple[str, ...]
    reason_logs: tuple[ReasonLog, ...]


@dataclass(frozen=True)
class DraftProspect:
    draft_year: int
    rookie_season: int
    player_id: str
    name: str
    position: str = ""
    historical_team: str = ""
    ratings: dict[str, Any] = field(default_factory=dict)
    tendencies: dict[str, Any] = field(default_factory=dict)
    badges: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def clamp_score(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer 0..100")
    if value < 0 or value > 100:
        raise ValueError(f"{field_name} must be an integer 0..100")
    return value


def validate_profile_scores(profile: OwnerProfile | GMProfile) -> None:
    for key, value in profile.__dict__.items():
        if isinstance(value, int) and not isinstance(value, bool):
            clamp_score(value, field_name=key)
