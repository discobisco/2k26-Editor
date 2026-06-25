from __future__ import annotations

from typing import Any

from .assets import team_asset_breakdown, team_need_summary
from .finances import assess_team_finances
from .models import FranchiseTeam, ImportedSnapshot, ReasonLog, TeamDirection, TeamEvaluation
from .objectives import objective_review_evidence, objectives_from_snapshots, owner_end_season_review
from .transactions import recommend_team_transactions
from .world import TeamContext, build_team_context


def evaluate_team_at_stop(
    *,
    season: int,
    team: FranchiseTeam,
    snapshots: tuple[ImportedSnapshot, ...],
) -> TeamEvaluation:
    """Evaluate owner/GM direction from the current imported franchise world.

    The public facade stays the same, but the decision no longer reads only the
    standings row. It builds a team context from imported standings, expected
    record, roster shape, contracts/cap, draft assets, injuries, and recent
    transactions, then emits explainable owner/GM logs.
    """

    context = build_team_context(season=season, team=team, snapshots=snapshots)
    direction = _classify_direction(context)
    objectives = objectives_from_snapshots(snapshots, season=season, team_id=team.team_id)
    objective_review = owner_end_season_review(context, objectives, direction) if objectives else None
    recommendations = recommend_team_transactions(context, direction)
    actions = tuple(item.message for item in recommendations[:4])
    owner_report = _owner_report(context, direction)
    if objective_review is not None:
        owner_report += f" Directive review: {objective_review.summary}"
    gm_report = _gm_report(context, direction, actions)
    owner_evidence = _shared_evidence(context)
    if objective_review is not None:
        owner_evidence["objective_review"] = objective_review_evidence(objective_review)
    gm_evidence = dict(owner_evidence)
    gm_evidence.update(
        {
            "asset_score": team_asset_breakdown(context).total,
            "cap_space": context.cap.cap_space,
            "transaction_recommendations": tuple(item.kind for item in recommendations),
        }
    )
    action = _action_for_direction(direction, context)
    logs = (
        ReasonLog(season=season, team_id=team.team_id, actor="owner", message=owner_report, action=action, evidence=owner_evidence),
        ReasonLog(season=season, team_id=team.team_id, actor="gm", message=gm_report, action=action, evidence=gm_evidence),
    )
    return TeamEvaluation(team.team_id, direction, owner_report, gm_report, actions, logs)


def _classify_direction(context: TeamContext) -> TeamDirection:
    win_pct = context.record.win_pct
    expected_pct = context.record.expected_win_pct
    star = context.roster.star_quality
    owner = context.team.owner
    pressure = _owner_pressure(context)

    if win_pct >= 0.60 or expected_pct >= 0.60 or (star >= 88 and win_pct >= 0.48):
        return TeamDirection.CONTEND
    if win_pct <= 0.30 and star < 80 and owner.rebuild_tolerance < 45:
        return TeamDirection.TANK
    if win_pct <= 0.36 and (owner.rebuild_tolerance >= 45 or context.draft_assets.future_firsts >= 2 or context.roster.young_core_count >= 1):
        return TeamDirection.REBUILD
    if pressure >= 70 or context.team.gm.aggression + context.team.gm.trade_frequency >= 130:
        return TeamDirection.EVALUATE
    return TeamDirection.EVALUATE


def _owner_report(context: TeamContext, direction: TeamDirection) -> str:
    record = context.record
    finance = assess_team_finances(context)
    if direction is TeamDirection.CONTEND:
        status = f"Owner expects contention at {record.wins}-{record.losses}"
        if record.expected_wins is not None:
            status += f" with {record.expected_wins} expected wins"
        if finance.status == "tax":
            status += "; luxury-tax spending requires a title-level plan"
        if context.injuries.active_count:
            status += f" and {context.injuries.active_count} active injury risk"
        return status + "."
    if direction is TeamDirection.REBUILD:
        return f"Owner can tolerate a reset at {record.wins}-{record.losses}; prioritize draft assets, young-player minutes, and cap flexibility."
    if direction is TeamDirection.TANK:
        return f"Owner is unhappy with {record.wins}-{record.losses}; low rebuild tolerance makes job security and direction clarity urgent."
    return f"Owner is monitoring {record.wins}-{record.losses}; pressure, payroll, morale, and roster fit require another evaluation before spending assets."


def _gm_report(context: TeamContext, direction: TeamDirection, actions: tuple[str, ...]) -> str:
    needs = ", ".join(team_need_summary(context))
    first_action = actions[0] if actions else "Continue evaluation"
    return f"GM classifies {context.team.team_id} as {direction.value}; needs: {needs}; first action: {first_action}"


def _shared_evidence(context: TeamContext) -> dict[str, Any]:
    return {
        "wins": context.record.wins,
        "losses": context.record.losses,
        "win_pct": round(context.record.win_pct, 3),
        "expected_wins": context.record.expected_wins,
        "expected_win_pct": round(context.record.expected_win_pct, 3),
        "market_pressure": context.record.market_pressure,
        "owner_pressure": _owner_pressure(context),
        "roster_average_age": context.roster.average_age,
        "star_quality": context.roster.star_quality,
        "top_two_quality": context.roster.top_two_quality,
        "average_morale": context.roster.average_morale,
        "development_score": context.roster.development_score,
        "active_injuries": context.injuries.active_count,
        "injury_severity": context.injuries.total_severity,
        "payroll": context.cap.payroll,
        "salary_cap": context.cap.salary_cap,
        "luxury_tax_line": context.cap.luxury_tax_line,
        "luxury_tax_overage": context.cap.luxury_tax_overage,
        "future_firsts": context.draft_assets.future_firsts,
        "draft_pick_value": context.draft_assets.pick_value,
        "recent_transactions": context.recent_transactions.count,
    }


def _owner_pressure(context: TeamContext) -> int:
    owner = context.team.owner
    standings_pressure = max(0, owner.championship_expectations - owner.patience)
    market_pressure = max(0, context.record.market_pressure - 50) * owner.market_pressure_sensitivity / 100
    tax_pressure = 15 if context.cap.is_tax_team and owner.spending_willingness < 50 else 0
    return int(round(min(100, standings_pressure + market_pressure + tax_pressure)))


def _action_for_direction(direction: TeamDirection, context: TeamContext) -> str:
    if direction is TeamDirection.CONTEND:
        return "championship_push" if not context.injuries.active_count else "injury_aware_championship_push"
    if direction is TeamDirection.REBUILD:
        return "rebuild_evaluation"
    if direction is TeamDirection.TANK:
        return "ownership_concern"
    return "trade_market_scan"
