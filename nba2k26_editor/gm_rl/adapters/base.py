from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, TypedDict

import numpy as np

try:
    # Optional torch typing for signatures; torch is required at runtime by PPO.
    import torch  # noqa: F401
except ImportError:  # pragma: no cover - torch is declared in pyproject
    torch = None  # type: ignore

# Core data containers -----------------------------------------------------


@dataclass
class PhysicalAttributes:
    """Biomechanical proxies required by the feature encoder."""

    strength_upper: float
    strength_lower: float
    speed: float
    agility: float
    endurance: float
    height_in: float
    standing_reach_in: float
    wingspan_in: float
    flexibility: float
    balance: float
    contact_management: float
    high_intensity_capacity: float


@dataclass
class PlayerStats:
    """Per-player season stats and advanced metrics."""

    # Offensive
    two_pa: float
    two_p: float
    two_p_pct: float
    three_pa: float
    three_p: float
    three_p_pct: float
    fga: float
    fg: float
    fg_pct: float
    efg_pct: float
    fta: float
    ft: float
    ft_pct: float
    pts: float
    ast: float
    oreb: float
    tov: float
    ftr: float
    ast_pct: float
    three_par: float
    oreb_pct: float
    bench_pts: float
    pts_per_poss: float
    paint_pts: float
    tov_pct: float
    # Defensive
    stl: float
    blk: float
    pf: float
    dreb: float
    dflc: float
    chrg: float
    recov: float
    dreb_pct: float
    stl_pct: float
    blk_pct: float
    # Other
    tf: float
    inf: float
    minutes: float
    plus_minus: float
    eff: float
    pie: float
    # Pro-level optional (config gated)
    per: Optional[float] = None
    dpr: Optional[float] = None
    pir: Optional[float] = None
    tsp: Optional[float] = None
    apm: Optional[float] = None
    bpm: Optional[float] = None
    vorp: Optional[float] = None
    opr: Optional[float] = None
    similarity_score: Optional[float] = None
    pecota_forecast: Optional[float] = None


@dataclass
class ContractInfo:
    salary: float
    years_left: int
    is_extension: bool = False


@dataclass
class PlayerState:
    player_id: int
    name: str
    position: str
    age: int
    stats: PlayerStats
    physicals: PhysicalAttributes
    contract: ContractInfo
    role: str
    fatigue: float
    injury_risk: float
    team_id: int
    minutes_per_game: float


@dataclass
class TeamState:
    team_id: int
    name: str
    wins: int
    losses: int
    division: str
    conference: str
    playoff_rank: int
    possessions_per_game: float
    salary_cap: float
    payroll: float
    luxury_tax_line: float
    roster: List[int]
    rotation: Dict[int, float]  # player_id -> minutes share
    assets: Dict[str, float]  # draft picks and future value proxies
    defensive_rating: float = 0.0
    offensive_rating: float = 0.0

    def roster_size(self) -> int:
        return len(self.roster)


@dataclass
class LeagueContext:
    season_year: int
    total_weeks: int
    current_week: int
    games_played: int
    games_per_season: int
    trade_deadline_week: int
    soft_cap: float
    hard_cap: float
    luxury_tax_line: float
    minimum_roster: int
    maximum_roster: int
    max_minutes_per_game: float
    first_apron_level: float = 0.0
    second_apron_level: float = 0.0
    moratorium_start: str = "July 1 12:01 AM ET"
    moratorium_end: str = "July 6 12:00 PM ET"


@dataclass
class RosterState:
    teams: Dict[int, TeamState]
    players: Dict[int, PlayerState]
    context: LeagueContext

    def get_team(self, team_id: int) -> TeamState:
        return self.teams[team_id]

    def get_player(self, player_id: int) -> PlayerState:
        return self.players[player_id]


class GMActionPayload(TypedDict, total=False):
    team_id: int
    target_player_id: int
    secondary_player_id: int
    draft_slot: int
    minutes: Dict[int, float]
    contract_value: float
    contract_years: int
    waive_player_id: int
    sign_player_id: int
    trade_assets: Dict[str, float]
    accept: bool


@dataclass
class GMActionResult:
    new_state: RosterState
    metadata: Dict[str, float]


class EditorAdapter(Protocol):
    """Abstract adapter for sourcing editor data into the RL environment."""

    def load_roster_state(self, seed: Optional[int] = None) -> RosterState:
        """Return the full league snapshot used to reset the environment."""
        ...

    def load_league_context(self) -> LeagueContext:
        """Return league-level metadata without loading full rosters."""
        ...

    def apply_gm_action(self, action: "GMTransaction") -> GMActionResult:
        """Apply the transaction and return the updated state and metadata."""
        ...

    # Optional salary/cap interfaces (stubs acceptable for live adapter)
    def get_salary_cap(self, team_id: int) -> float:
        ...

    def get_payroll(self, team_id: int) -> float:
        ...


# Utility ------------------------------------------------------------------


def safe_ratio(numer: float, denom: float) -> float:
    """Compute numer/denom guarding against division-by-zero and NaNs."""
    if np.isnan(numer) or np.isnan(denom):
        return 0.0
    if abs(denom) < 1e-8:
        return 0.0
    return float(numer / denom)


# Type imported late to avoid circular import in type checking
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from nba2k_editor.gm_rl.actions import GMTransaction
