from __future__ import annotations

from pathlib import Path

from nba2k_editor.mcp_server.adapters.ai_profile_repository import AiProfileRepository
from nba2k_editor.mcp_server.adapters.team_id_resolver import TeamIdResolver
from nba2k_editor.mcp_server.api.v1.models import (
    AiDecisionContext,
    AiTradeDecisionRequest,
    GmPersonality,
    MediaPressureContext,
    OwnerProfile,
    RosterPlayer,
)
from nba2k_editor.mcp_server.domain.cpu_ai_engine import CpuAiEngine
from nba2k_editor.mcp_server.domain.franchise_direction_engine import FranchiseDirectionEngine


def _engine() -> CpuAiEngine:
    data_dir = Path(__file__).resolve().parents[2] / "data" / "ai"
    return CpuAiEngine(
        profile_repository=AiProfileRepository(data_dir=data_dir),
        team_resolver=TeamIdResolver(),
        direction_engine=FranchiseDirectionEngine(),
        default_seed=42,
        cache_max_entries=512,
        cache_ttl_seconds=60,
    )


def _roster() -> list[RosterPlayer]:
    return [
        RosterPlayer(
            player_id=1,
            name="Primary Star",
            team="NYK",
            age=29,
            overall=92,
            potential=93,
            contract_years=3,
            salary=48_000_000,
        ),
        RosterPlayer(
            player_id=2,
            name="Wing 2",
            team="NYK",
            age=25,
            overall=84,
            potential=87,
            contract_years=2,
            salary=24_000_000,
        ),
        RosterPlayer(
            player_id=3,
            name="Young Guard",
            team="NYK",
            age=22,
            overall=79,
            potential=88,
            contract_years=1,
            salary=8_000_000,
        ),
    ]


def _context(
    *,
    gm_personality: GmPersonality,
    owner_profile: OwnerProfile | None = None,
    media_criticism: float = 0.5,
    rings_last_6_years: int = 0,
    title_drought_years: int = 0,
    seed: int = 77,
) -> AiDecisionContext:
    return AiDecisionContext(
        team_id="NYK_2025",
        era="modern",
        season="2025-26",
        current_record="31-25",
        roster_assets=_roster(),
        media_context=MediaPressureContext(
            fan_sentiment=0.48,
            media_criticism_index=media_criticism,
            recent_playoff_success=0.4,
            market_size_factor=0.9,
        ),
        gm_personality=gm_personality,
        owner_profile=owner_profile,
        rings_last_6_years=rings_last_6_years,
        title_drought_years=title_drought_years,
        checkpoint="trade_deadline",
        seed=seed,
    )


def test_archetype_variance_changes_trade_aggressiveness():
    engine = _engine()
    aggressive = GmPersonality(
        id="aggressive",
        archetype="aggressive",
        risk_tolerance=0.82,
        trade_frequency=0.85,
        draft_pick_value_weight=0.25,
        star_bias_weight=0.80,
        youth_development_weight=0.30,
        cap_sensitivity=0.35,
        loyalty_bias=0.20,
        media_pressure_sensitivity=0.70,
    )
    conservative = GmPersonality(
        id="conservative",
        archetype="conservative",
        risk_tolerance=0.25,
        trade_frequency=0.20,
        draft_pick_value_weight=0.85,
        star_bias_weight=0.25,
        youth_development_weight=0.70,
        cap_sensitivity=0.75,
        loyalty_bias=0.70,
        media_pressure_sensitivity=0.35,
    )

    aggressive_result = engine.trade_decision(request=AiTradeDecisionRequest(context=_context(gm_personality=aggressive)))
    conservative_result = engine.trade_decision(request=AiTradeDecisionRequest(context=_context(gm_personality=conservative)))

    assert aggressive_result.aggressiveness_score > conservative_result.aggressiveness_score


def test_owner_tax_tolerance_shifts_aggressiveness_down_when_low():
    engine = _engine()
    gm = GmPersonality(
        id="balanced",
        archetype="winNow",
        risk_tolerance=0.60,
        trade_frequency=0.60,
        draft_pick_value_weight=0.45,
        star_bias_weight=0.60,
        youth_development_weight=0.50,
        cap_sensitivity=0.60,
        loyalty_bias=0.35,
        media_pressure_sensitivity=0.60,
    )
    low_tolerance = OwnerProfile(
        spending_limit=82_000_000,
        luxury_tax_tolerance=0.05,
        patience_level=0.5,
        championship_demand=0.8,
    )
    high_tolerance = OwnerProfile(
        spending_limit=210_000_000,
        luxury_tax_tolerance=0.9,
        patience_level=0.5,
        championship_demand=0.8,
    )

    low_result = engine.trade_decision(
        request=AiTradeDecisionRequest(context=_context(gm_personality=gm, owner_profile=low_tolerance))
    )
    high_result = engine.trade_decision(
        request=AiTradeDecisionRequest(context=_context(gm_personality=gm, owner_profile=high_tolerance))
    )
    assert low_result.aggressiveness_score < high_result.aggressiveness_score


def test_media_pressure_monotonicity_increases_urgency():
    engine = _engine()
    gm = GmPersonality(
        id="analytics",
        archetype="analytics",
        risk_tolerance=0.5,
        trade_frequency=0.45,
        draft_pick_value_weight=0.55,
        star_bias_weight=0.5,
        youth_development_weight=0.55,
        cap_sensitivity=0.55,
        loyalty_bias=0.45,
        media_pressure_sensitivity=0.8,
    )
    low_pressure = engine.trade_decision(
        request=AiTradeDecisionRequest(context=_context(gm_personality=gm, media_criticism=0.2))
    )
    high_pressure = engine.trade_decision(
        request=AiTradeDecisionRequest(context=_context(gm_personality=gm, media_criticism=0.95))
    )
    assert high_pressure.aggressiveness_score > low_pressure.aggressiveness_score


def test_dynasty_and_drought_thresholds_trigger_adjustment():
    engine = _engine()
    gm = GmPersonality(
        id="star",
        archetype="starChaser",
        risk_tolerance=0.75,
        trade_frequency=0.75,
        draft_pick_value_weight=0.3,
        star_bias_weight=0.9,
        youth_development_weight=0.35,
        cap_sensitivity=0.45,
        loyalty_bias=0.25,
        media_pressure_sensitivity=0.7,
    )

    neutral = engine.trade_decision(request=AiTradeDecisionRequest(context=_context(gm_personality=gm)))
    biased = engine.trade_decision(
        request=AiTradeDecisionRequest(
            context=_context(
                gm_personality=gm,
                rings_last_6_years=3,
                title_drought_years=11,
            )
        )
    )
    assert biased.decision_breakdown["dynastyAdjustment"] > neutral.decision_breakdown["dynastyAdjustment"]


def test_seeded_determinism_returns_identical_output():
    engine = _engine()
    gm = GmPersonality(
        id="rebuild",
        archetype="rebuild",
        risk_tolerance=0.55,
        trade_frequency=0.5,
        draft_pick_value_weight=0.7,
        star_bias_weight=0.3,
        youth_development_weight=0.9,
        cap_sensitivity=0.45,
        loyalty_bias=0.4,
        media_pressure_sensitivity=0.5,
    )
    request = AiTradeDecisionRequest(context=_context(gm_personality=gm, seed=1234))
    first = engine.trade_decision(request=request)
    second = engine.trade_decision(request=request)
    assert first.model_dump() == second.model_dump()
