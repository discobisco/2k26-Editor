from __future__ import annotations

from pathlib import Path

from nba2k_editor.mcp_server.adapters.ai_profile_repository import AiProfileRepository
from nba2k_editor.mcp_server.adapters.team_id_resolver import TeamIdResolver
from nba2k_editor.mcp_server.api.v1.models import (
    AiDecisionContext,
    AiTradeDecisionRequest,
    MediaPressureContext,
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


def _request(*, gm_override=None) -> AiTradeDecisionRequest:
    context = AiDecisionContext(
        team_id="ATL_2025",
        era="modern",
        season="2025-26",
        current_record="20-36",
        roster_assets=[
            RosterPlayer(
                player_id=1,
                name="Guard A",
                team="ATL",
                age=24,
                overall=80,
                potential=86,
                contract_years=2,
                salary=17_000_000,
            ),
            RosterPlayer(
                player_id=2,
                name="Forward B",
                team="ATL",
                age=31,
                overall=84,
                potential=84,
                contract_years=1,
                salary=27_000_000,
            ),
        ],
        media_context=MediaPressureContext(
            fan_sentiment=0.35,
            media_criticism_index=0.88,
            recent_playoff_success=0.2,
            market_size_factor=0.55,
        ),
        checkpoint="offseason",
        rings_last_6_years=0,
        title_drought_years=12,
        seed=909,
        gm_personality=gm_override,
    )
    return AiTradeDecisionRequest(context=context)


def test_profile_drift_is_request_driven_not_server_persisted():
    engine = _engine()

    initial = engine.trade_decision(request=_request())
    suggested = initial.next_profile_recommendation.suggested_personality

    # Stateless behavior: same request returns same recommendation.
    repeated = engine.trade_decision(request=_request())
    assert repeated.next_profile_recommendation.suggested_personality.model_dump() == suggested.model_dump()

    # Caller-managed drift: passing the prior suggested profile changes the next recommendation.
    with_override = engine.trade_decision(request=_request(gm_override=suggested))
    assert (
        with_override.next_profile_recommendation.suggested_personality.trade_frequency
        != repeated.next_profile_recommendation.suggested_personality.trade_frequency
    )
