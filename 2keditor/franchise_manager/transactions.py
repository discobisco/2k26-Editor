from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assets import team_asset_breakdown, team_need_summary
from .finances import assess_team_finances
from .models import TeamDirection
from .world import TeamContext


@dataclass(frozen=True)
class TransactionRecommendation:
    kind: str
    priority: int
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


def recommend_team_transactions(context: TeamContext, direction: TeamDirection | None = None) -> tuple[TransactionRecommendation, ...]:
    direction = direction or infer_transaction_direction(context)
    assets = team_asset_breakdown(context)
    finance = assess_team_finances(context)
    needs = team_need_summary(context)
    recommendations: list[TransactionRecommendation] = []

    if direction is TeamDirection.CONTEND:
        trade_message = "Explore veteran upgrade without damaging the long-term core."
        if context.injuries.active_count:
            trade_message = "Explore veteran injury insurance before the next playoff push."
        if finance.status == "tax":
            trade_message += " Keep luxury tax and owner approval attached to every offer."
        trade_evidence = {"needs": needs, "asset_score": assets.total, "luxury_tax_overage": finance.luxury_tax_overage}
        _add_trade_score_evidence(context, direction, trade_evidence)
        recommendations.append(TransactionRecommendation("trade", 90, trade_message, trade_evidence))
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        trade_evidence = {"future_firsts": context.draft_assets.future_firsts, "veteran_core_count": context.roster.veteran_core_count, "asset_score": assets.total}
        _add_trade_score_evidence(context, direction, trade_evidence)
        recommendations.append(TransactionRecommendation("trade", 95, "Shop veterans and expensive non-core contracts for picks or younger players.", trade_evidence))
    else:
        trade_evidence = {"needs": needs, "asset_score": assets.total}
        _add_trade_score_evidence(context, direction, trade_evidence)
        recommendations.append(TransactionRecommendation("trade", 65, "Scan trade market for positional weaknesses before committing assets.", trade_evidence))

    if finance.status == "cap_space":
        fa_message = "Rank free agents who fit the team timeline; cap room can be used aggressively."
    elif finance.status == "tax":
        fa_message = "Use minimums, exceptions, and buyout targets; avoid new long salary unless it changes the title odds."
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        fa_message = "Avoid long veteran deals; use short contracts to preserve flexibility."
    else:
        fa_message = "Build a free-agent shortlist for depth and expiring-value contracts."
    fa_evidence = {"cap_space": finance.cap_space, "finance_status": finance.status}
    _add_free_agency_evidence(context, direction, fa_evidence)
    recommendations.append(TransactionRecommendation("free_agency", 70, fa_message, fa_evidence))

    young_underplayed = [player for player in context.roster.players if (player.age or 99) <= 24 and (player.potential or 0) >= 80 and (player.minutes or 0) < 22]
    if young_underplayed:
        names = ", ".join(player.name or player.player_id for player in young_underplayed[:3])
        rotation_evidence_data = {"players": [player.player_id for player in young_underplayed]}
        _add_rotation_evidence(context, direction, rotation_evidence_data)
        recommendations.append(TransactionRecommendation("rotation", 80, f"Open rotation minutes for development candidates: {names}.", rotation_evidence_data))
    elif context.injuries.active_count:
        rotation_evidence_data = {"active_injuries": context.injuries.active_count}
        _add_rotation_evidence(context, direction, rotation_evidence_data)
        recommendations.append(TransactionRecommendation("rotation", 75, "Rebalance minutes around active injuries before applying progression/regression.", rotation_evidence_data))
    else:
        rotation_evidence_data = {"average_morale": context.roster.average_morale}
        _add_rotation_evidence(context, direction, rotation_evidence_data)
        recommendations.append(TransactionRecommendation("rotation", 50, "Maintain current rotation but monitor morale and role/minutes alignment.", rotation_evidence_data))

    if context.draft_assets.future_firsts >= 2:
        draft_message = "Use surplus firsts as trade optionality or build a draft board around team needs."
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        draft_message = "Acquire more first-round equity before the draft room locks."
    else:
        draft_message = "Protect remaining draft equity unless the move meaningfully raises the ceiling."
    recommendations.append(TransactionRecommendation("draft", 60, draft_message, {"future_firsts": context.draft_assets.future_firsts, "pick_value": context.draft_assets.pick_value}))

    return tuple(sorted(recommendations, key=lambda item: item.priority, reverse=True))


def _add_trade_score_evidence(context: TeamContext, direction: TeamDirection, evidence: dict[str, Any]) -> None:
    from .trades import rank_trade_proposals

    ranked = rank_trade_proposals(context, direction=direction)
    if not ranked:
        return
    top = ranked[0]
    evidence.update(
        {
            "top_trade_label": top.package.label,
            "top_trade_score": top.acceptance_score,
            "top_trade_decision": top.decision,
            "top_trade_cap_legal": top.cap_legal,
            "top_trade_value_margin": top.evidence.get("value_margin", 0),
        }
    )


def _add_free_agency_evidence(context: TeamContext, direction: TeamDirection, evidence: dict[str, Any]) -> None:
    from .free_agency import free_agency_plan

    plan = free_agency_plan(context, direction=direction)
    evidence.update(
        {
            "free_agency_strategy": plan.strategy,
            "estimated_cap_space_after_top_offer": plan.cap_space_after_top_offer,
            "top_free_agent_target": plan.ranked_targets[0].target.player.name if plan.ranked_targets else "",
            "top_free_agent_fit_score": plan.ranked_targets[0].fit_score if plan.ranked_targets else 0,
            "free_agency_warnings": plan.warnings,
        }
    )


def _add_rotation_evidence(context: TeamContext, direction: TeamDirection, evidence: dict[str, Any]) -> None:
    from .rotation import rotation_evidence

    evidence.update(rotation_evidence(context, direction))


def infer_transaction_direction(context: TeamContext) -> TeamDirection:
    if context.record.win_pct >= 0.58 or context.record.expected_win_pct >= 0.58 or context.roster.star_quality >= 88:
        return TeamDirection.CONTEND
    if context.record.win_pct <= 0.35 and context.roster.young_core_count >= 1:
        return TeamDirection.REBUILD
    if context.record.win_pct <= 0.30 and context.roster.star_quality < 82:
        return TeamDirection.TANK
    return TeamDirection.EVALUATE
