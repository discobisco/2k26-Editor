from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


LockerRoomEra = Literal["1980s", "1990s", "2000s", "modern"]
PersonalityArchetype = Literal[
    "leader",
    "alpha_competitor",
    "diva",
    "mentor",
    "loyalist",
    "mercenary",
    "locker_room_cancer",
]
LockerRoomHierarchyRole = Literal["star", "starter", "role_player", "rookie"]
ConflictType = Literal["ego_clash", "rookie_minutes", "trade_rumor", "media_pressure"]


class ValidationIssue(StrictModel):
    field: str
    message: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None


class WriteOperationResult(StrictModel):
    entity_id: str
    field: str
    old_value: Any = None
    new_value: Any = None
    bounds_source: str
    success: bool
    error: str | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)


class LiveWriteOperation(StrictModel):
    entity_id: str
    field: str
    value: Any
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    bounds_source: str = "request"


class EraConfig(StrictModel):
    era: str
    season: str
    pace_factor: float
    hand_checking: bool
    defensive_three_seconds: bool
    salary_cap: float
    luxury_tax_line: float


class LeagueRuleSet(StrictModel):
    season: str
    salary_cap_percent_bri: float
    first_apron: float
    second_apron: float
    hard_cap: float
    luxury_tax_line: float
    min_roster: int
    max_roster: int


class RosterPlayer(StrictModel):
    player_id: int
    name: str
    team: str
    age: int
    overall: float = Field(ge=0, le=100)
    potential: float = Field(ge=0, le=100)
    contract_years: int = Field(ge=0, le=8)
    salary: float = Field(ge=0)


class PlayerPersonality(StrictModel):
    leadership: float = Field(ge=0, le=100)
    ego: float = Field(ge=0, le=100)
    loyalty: float = Field(ge=0, le=100)
    competitiveness: float = Field(ge=0, le=100)
    professionalism: float = Field(ge=0, le=100)
    media_sensitivity: float = Field(ge=0, le=100, alias="mediaSensitivity")
    mentorship: float = Field(ge=0, le=100)
    temperament: float = Field(ge=0, le=100)


class RoleExpectation(StrictModel):
    expected_minutes: float = Field(ge=0, le=48, alias="expectedMinutes")
    expected_usage_rate: float = Field(ge=0, le=1, alias="expectedUsageRate")
    contract_status: Literal["rookie", "expiring", "max", "teamFriendly"] = Field(alias="contractStatus")


class LockerRoomRosterPlayer(StrictModel):
    player_id: int
    name: str
    team: str = ""
    age: int = Field(default=26, ge=18, le=50)
    overall: float = Field(default=74, ge=0, le=100)
    potential: float = Field(default=80, ge=0, le=100)
    actual_minutes: float = Field(default=24, ge=0, le=48, alias="actualMinutes")
    actual_usage_rate: float = Field(default=0.2, ge=0, le=1, alias="actualUsageRate")
    hierarchy_role: LockerRoomHierarchyRole | None = Field(default=None, alias="hierarchyRole")
    role_expectation: RoleExpectation | None = Field(default=None, alias="roleExpectation")
    archetype: PersonalityArchetype | None = None
    personality: PlayerPersonality | None = None


class LockerRoomConflictEvent(StrictModel):
    type: ConflictType
    severity: float = Field(ge=0, le=1)
    remaining_ticks: int = Field(ge=0, alias="remainingTicks")
    affected_player_ids: list[int] = Field(default_factory=list, alias="affectedPlayerIds")
    narrative_tag: str | None = Field(default=None, alias="narrativeTag")
    created_tick: int = Field(default=0, ge=0, alias="createdTick")


class MoraleImpact(StrictModel):
    player_id: int
    morale: float = Field(ge=0, le=1)
    role_satisfaction: float = Field(ge=0, le=1, alias="roleSatisfaction")
    conflict_penalty: float = Field(ge=0, le=1, alias="conflictPenalty")
    contract_security: float = Field(ge=0, le=1, alias="contractSecurity")
    shot_consistency_multiplier: float = Field(alias="shotConsistencyMultiplier")
    injury_probability_multiplier: float = Field(alias="injuryProbabilityMultiplier")
    development_rate_multiplier: float = Field(alias="developmentRateMultiplier")
    trade_demand_probability: float = Field(ge=0, le=1, alias="tradeDemandProbability")


class ChemistryBreakdown(StrictModel):
    average_professionalism: float = Field(ge=0, le=1, alias="averageProfessionalism")
    leadership_impact: float = Field(ge=0, le=1, alias="leadershipImpact")
    role_satisfaction_score: float = Field(ge=0, le=1, alias="roleSatisfactionScore")
    mentor_impact: float = Field(ge=0, le=1, alias="mentorImpact")
    ego_conflict_penalty: float = Field(ge=0, le=1, alias="egoConflictPenalty")
    attribute_boost_multiplier: float = Field(alias="attributeBoostMultiplier")
    clutch_multiplier: float = Field(alias="clutchMultiplier")
    injury_stress_multiplier: float = Field(alias="injuryStressMultiplier")


class LockerRoomStatus(StrictModel):
    profile_id: str
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    chemistry_score: float = Field(ge=0, le=1, alias="chemistryScore")
    morale_trend: Literal["up", "down", "stable"] = Field(alias="moraleTrend")
    conflict_risk: float = Field(ge=0, le=1, alias="conflictRisk")
    mentor_boost_active: bool = Field(alias="mentorBoostActive")
    average_morale: float = Field(ge=0, le=1, alias="averageMorale")
    stress_factor: float = Field(ge=0, alias="stressFactor")
    stale_live_data: bool = Field(alias="staleLiveData")
    captain_player_id: int | None = Field(default=None, alias="captainPlayerId")
    conflicts: list[LockerRoomConflictEvent] = Field(default_factory=list)
    morale: list[MoraleImpact] = Field(default_factory=list)
    breakdown: ChemistryBreakdown


class FranchiseState(StrictModel):
    era: str
    team: str
    cap_space: float
    owner_goal: Literal["win-now", "retool", "rebuild", "contend"] = "win-now"
    roster: list[RosterPlayer]


class TradeProposal(StrictModel):
    from_team: str
    to_team: str
    outgoing_player_ids: list[int] = Field(default_factory=list)
    incoming_player_ids: list[int] = Field(default_factory=list)
    outgoing_asset_value: float = 0.0
    incoming_asset_value: float = 0.0


class TradeEvaluation(StrictModel):
    fairness_score: float
    verdict: Literal["fair", "leans_from_team", "leans_to_team", "unbalanced"]
    rationale: list[str]
    projected_cap_delta: float


class DraftProspect(StrictModel):
    name: str
    age: int
    position: str
    overall: float = Field(ge=0, le=100)
    potential_floor: float = Field(ge=0, le=100)
    potential_ceiling: float = Field(ge=0, le=100)
    scouting_confidence: float = Field(ge=0, le=1)


class DraftClass(StrictModel):
    era: str
    seed: int
    prospects: list[DraftProspect]


class ProgressionResult(StrictModel):
    player_id: int
    before_overall: float
    after_overall: float
    injury_risk: float = Field(ge=0, le=1)


class SeasonOutcome(StrictModel):
    team: str
    wins: int
    losses: int
    playoff_odds: float = Field(ge=0, le=1)
    championship_odds: float = Field(ge=0, le=1)
    pace_adjustment: float


class DynastySnapshot(StrictModel):
    team: str
    seasons: int
    rings: int
    mvps: int
    all_nba: int
    legacy_score: float
    summary: str


class ChemistryCalculateRequest(StrictModel):
    profile_id: str = Field(alias="profileId")
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    roster: list[LockerRoomRosterPlayer] = Field(default_factory=list)
    recent_record: str = Field(default="0-0", alias="recentRecord")
    team_underperforming: bool = Field(default=False, alias="teamUnderperforming")
    seed: int | None = None


class ChemistryCalculateResponse(StrictModel):
    chemistry_score: float = Field(ge=0, le=1, alias="chemistryScore")
    morale_trend: Literal["up", "down", "stable"] = Field(alias="moraleTrend")
    conflict_risk: float = Field(ge=0, le=1, alias="conflictRisk")
    mentor_boost_active: bool = Field(alias="mentorBoostActive")
    breakdown: ChemistryBreakdown


class PersonalityManualUpdate(StrictModel):
    player_id: int = Field(alias="playerId")
    archetype: PersonalityArchetype | None = None
    personality: PlayerPersonality


class PersonalityUpdateRequest(StrictModel):
    profile_id: str = Field(alias="profileId")
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    mode: Literal["auto", "manual"] = "auto"
    roster: list[LockerRoomRosterPlayer] = Field(default_factory=list)
    updates: list[PersonalityManualUpdate] = Field(default_factory=list)
    championships: int = Field(default=0, ge=0)
    mvp_awards: int = Field(default=0, ge=0, alias="mvpAwards")
    contract_disputes: int = Field(default=0, ge=0, alias="contractDisputes")
    public_criticism: int = Field(default=0, ge=0, alias="publicCriticism")
    seed: int | None = None


class PersonalityPlayerState(StrictModel):
    player_id: int = Field(alias="playerId")
    name: str
    archetype: PersonalityArchetype
    personality: PlayerPersonality


class PersonalityUpdateResponse(StrictModel):
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    players: list[PersonalityPlayerState]
    captain_player_id: int | None = Field(default=None, alias="captainPlayerId")
    profile_id: str = Field(alias="profileId")


class ConflictSimulateRequest(StrictModel):
    profile_id: str = Field(alias="profileId")
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    trade_rumor_pressure: float = Field(default=0.5, ge=0, le=1, alias="tradeRumorPressure")
    media_pressure: float = Field(default=0.5, ge=0, le=1, alias="mediaPressure")
    seed: int | None = None


class ConflictSimulateResponse(StrictModel):
    events: list[LockerRoomConflictEvent]
    conflict_risk: float = Field(ge=0, le=1, alias="conflictRisk")
    morale_penalty: float = Field(ge=0, le=1, alias="moralePenalty")
    queue_size: int = Field(ge=0, alias="queueSize")


class MoraleEvaluateRequest(StrictModel):
    profile_id: str = Field(alias="profileId")
    team_id: str = Field(alias="teamId")
    season: str
    era: LockerRoomEra
    team_win_pct: float = Field(default=0.5, ge=0, le=1, alias="teamWinPct")
    chemistry_score: float | None = Field(default=None, ge=0, le=1, alias="chemistryScore")
    team_underperforming: bool = Field(default=False, alias="teamUnderperforming")
    seed: int | None = None


class MoraleEvaluateResponse(StrictModel):
    average_morale: float = Field(ge=0, le=1, alias="averageMorale")
    morale_trend: Literal["up", "down", "stable"] = Field(alias="moraleTrend")
    players: list[MoraleImpact]
    playoff_adjustments: list[dict[str, Any]] = Field(default_factory=list, alias="playoffAdjustments")


class LockerRoomStatusResponse(StrictModel):
    chemistry_score: float = Field(ge=0, le=1, alias="chemistryScore")
    morale_trend: Literal["up", "down", "stable"] = Field(alias="moraleTrend")
    conflict_risk: float = Field(ge=0, le=1, alias="conflictRisk")
    mentor_boost_active: bool = Field(alias="mentorBoostActive")
    status: LockerRoomStatus


class FranchiseOptimizeRequest(StrictModel):
    franchise_state: FranchiseState
    era: str = "modern"
    profile_id: str | None = Field(default=None, alias="profileId")
    team_id: str | int | None = Field(default=None, alias="teamId")
    season: str | None = None
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class FranchiseOptimizeResponse(StrictModel):
    recommended_moves: list[str]
    cap_projection: dict[str, float]
    championship_odds: float
    diagnostics: dict[str, float]
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class TradeEvaluateRequest(StrictModel):
    franchise_state: FranchiseState
    proposal: TradeProposal
    cpu_profile: str = "modern-balanced"
    profile_id: str | None = Field(default=None, alias="profileId")
    team_id: str | int | None = Field(default=None, alias="teamId")
    season: str | None = None
    era: LockerRoomEra | None = None
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class TradeEvaluateResponse(StrictModel):
    evaluation: TradeEvaluation
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class DraftGenerateRequest(StrictModel):
    era: str = "modern"
    season: str = "2025-26"
    class_size: int = Field(default=60, ge=10, le=120)
    seed: int = 42
    include_historical_imports: bool = False
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class DraftGenerateResponse(StrictModel):
    draft_class: DraftClass
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class DraftLotteryRequest(StrictModel):
    season: str = "2025-26"
    teams: list[str] = Field(default_factory=list)
    odds: list[float] = Field(default_factory=list)
    seed: int = 42
    draws: int = Field(default=1, ge=1, le=10000)


class DraftLotteryResponse(StrictModel):
    pick_order: list[str]
    draw_count: int


class ProgressionSimulateRequest(StrictModel):
    players: list[RosterPlayer]
    years: int = Field(default=1, ge=1, le=10)
    seed: int = 42
    profile_id: str | None = Field(default=None, alias="profileId")
    team_id: str | int | None = Field(default=None, alias="teamId")
    season: str | None = None
    era: LockerRoomEra | None = None
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class ProgressionSimulateResponse(StrictModel):
    results: list[ProgressionResult]
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class TeamStrengthInput(StrictModel):
    team: str
    strength: float = Field(ge=0, le=200)


class SeasonSimulateRequest(StrictModel):
    era: str = "modern"
    season: str = "2025-26"
    iterations: int = Field(default=250, ge=1, le=5000)
    seed: int = 42
    team_strengths: list[TeamStrengthInput]
    profile_id: str | None = Field(default=None, alias="profileId")
    team_id: str | int | None = Field(default=None, alias="teamId")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class SeasonSimulateResponse(StrictModel):
    outcomes: list[SeasonOutcome]
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class DynastySeasonInput(StrictModel):
    rings: int = 0
    mvps: int = 0
    all_nba: int = 0
    wins: int = Field(default=0, ge=0, le=82)


class DynastyTrackRequest(StrictModel):
    team: str
    history: list[DynastySeasonInput]
    profile_id: str | None = Field(default=None, alias="profileId")
    team_id: str | int | None = Field(default=None, alias="teamId")
    season: str | None = None
    era: LockerRoomEra | None = None
    finals_appearances_last_6: int = Field(default=0, ge=0, alias="finalsAppearancesLast6")
    early_exit_streak: int = Field(default=0, ge=0, alias="earlyExitStreak")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class DynastyTrackResponse(StrictModel):
    snapshot: DynastySnapshot
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class EraTransitionRequest(StrictModel):
    from_season: str
    to_season: str
    era: str = "modern"
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class EraTransitionResponse(StrictModel):
    previous: EraConfig
    target: EraConfig
    rule_changes: list[str]
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class MCPInvokeRequest(StrictModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPInvokeResponse(StrictModel):
    tool: str
    result: dict[str, Any]


# ---------------------------------------------------------------------------
# CPU AI Personality Modeling Types
# ---------------------------------------------------------------------------


GmArchetype = Literal[
    "aggressive",
    "conservative",
    "rebuild",
    "winNow",
    "analytics",
    "starChaser",
    "smallMarket",
]


class GmPersonality(StrictModel):
    id: str
    archetype: GmArchetype
    risk_tolerance: float = Field(ge=0, le=1)
    trade_frequency: float = Field(ge=0, le=1)
    draft_pick_value_weight: float = Field(ge=0, le=1)
    star_bias_weight: float = Field(ge=0, le=1)
    youth_development_weight: float = Field(ge=0, le=1)
    cap_sensitivity: float = Field(ge=0, le=1)
    loyalty_bias: float = Field(ge=0, le=1)
    media_pressure_sensitivity: float = Field(ge=0, le=1)


class OwnerProfile(StrictModel):
    spending_limit: float = Field(ge=0)
    luxury_tax_tolerance: float = Field(ge=0, le=1)
    patience_level: float = Field(ge=0, le=1)
    championship_demand: float = Field(ge=0, le=1)


class MediaPressureContext(StrictModel):
    fan_sentiment: float = Field(default=0.5, ge=0, le=1)
    media_criticism_index: float = Field(default=0.5, ge=0, le=1)
    recent_playoff_success: float = Field(default=0.5, ge=0, le=1)
    market_size_factor: float = Field(default=0.5, ge=0, le=1)


class EraBehaviorModifier(StrictModel):
    era: str
    trade_aggression_multiplier: float = Field(ge=0)
    salary_cap_volatility: float = Field(ge=0)
    star_movement_probability: float = Field(ge=0, le=1)
    loyalty_bias_boost: float
    spacing_bias_multiplier: float = Field(ge=0)


class TeamAiProfile(StrictModel):
    team_key: str
    season: str
    gm_personality: GmPersonality
    owner_profile: OwnerProfile
    era_modifier: EraBehaviorModifier


class DecisionExplanation(StrictModel):
    summary: str
    factors: dict[str, float]
    triggered_rules: list[str] = Field(default_factory=list)


class NextProfileRecommendation(StrictModel):
    team_key: str
    phase: Literal["regular", "trade_deadline", "offseason"]
    suggested_personality: GmPersonality
    rationale: list[str] = Field(default_factory=list)


class AiDecisionContext(StrictModel):
    team_id: str | int
    era: str = "modern"
    season: str = "2025-26"
    current_record: str = "0-0"
    roster_assets: list[RosterPlayer] = Field(default_factory=list)
    media_context: MediaPressureContext = Field(default_factory=MediaPressureContext)
    owner_profile: OwnerProfile | None = None
    gm_personality: GmPersonality | None = None
    rings_last_6_years: int = Field(default=0, ge=0)
    title_drought_years: int = Field(default=0, ge=0)
    checkpoint: Literal["regular", "trade_deadline", "offseason"] = "regular"
    seed: int = 42


class AiTradeDecisionRequest(StrictModel):
    context: AiDecisionContext
    profile_id: str | None = Field(default=None, alias="profileId")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class AiTradeDecisionResponse(StrictModel):
    team_key: str
    decision: str
    aggressiveness_score: float = Field(ge=0, le=1, alias="aggressivenessScore")
    future_pick_included: bool = Field(alias="futurePickIncluded")
    justification: str
    decision_breakdown: dict[str, float] = Field(alias="decisionBreakdown")
    next_profile_recommendation: NextProfileRecommendation = Field(alias="nextProfileRecommendation")
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class AiDraftDecisionRequest(StrictModel):
    context: AiDecisionContext
    board_strength: float = Field(default=0.5, ge=0, le=1)
    team_need_fit: float = Field(default=0.5, ge=0, le=1)
    profile_id: str | None = Field(default=None, alias="profileId")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class AiDraftDecisionResponse(StrictModel):
    team_key: str
    decision: str
    risk_score: float = Field(ge=0, le=1, alias="riskScore")
    target_profile: str = Field(alias="targetProfile")
    justification: str
    decision_breakdown: dict[str, float] = Field(alias="decisionBreakdown")
    next_profile_recommendation: NextProfileRecommendation = Field(alias="nextProfileRecommendation")
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class AiFreeAgencyDecisionRequest(StrictModel):
    context: AiDecisionContext
    cap_room: float = Field(ge=0)
    market_offer_pressure: float = Field(default=0.5, ge=0, le=1)
    profile_id: str | None = Field(default=None, alias="profileId")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class AiFreeAgencyDecisionResponse(StrictModel):
    team_key: str
    decision: str
    max_offer_guidance: float = Field(ge=0, alias="maxOfferGuidance")
    tax_impact: float = Field(alias="taxImpact")
    justification: str
    decision_breakdown: dict[str, float] = Field(alias="decisionBreakdown")
    next_profile_recommendation: NextProfileRecommendation = Field(alias="nextProfileRecommendation")
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class AiFranchiseDirectionRequest(StrictModel):
    context: AiDecisionContext
    profile_id: str | None = Field(default=None, alias="profileId")
    apply_live_changes: bool = False
    live_operations: list[LiveWriteOperation] = Field(default_factory=list)


class AiFranchiseDirectionResponse(StrictModel):
    team_key: str
    direction: Literal["contender", "pretender", "rebuilder", "tanking", "retooling"]
    confidence: float = Field(ge=0, le=1)
    trigger_factors: list[str] = Field(default_factory=list, alias="triggerFactors")
    justification: str
    decision_breakdown: dict[str, float] = Field(alias="decisionBreakdown")
    next_profile_recommendation: NextProfileRecommendation = Field(alias="nextProfileRecommendation")
    write_operations: list[WriteOperationResult] = Field(default_factory=list)


class AiProfileResponse(StrictModel):
    team_key: str
    season: str
    profile: TeamAiProfile
    required_context_fields: list[str] = Field(default_factory=list)
    capability_flag: str


class AiProfileLookupRequest(StrictModel):
    team_id: str | int
    era: str = "modern"
    season: str = "2025-26"
