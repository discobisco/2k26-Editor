from __future__ import annotations

from dataclasses import dataclass

from .models import TeamDirection
from .world import FranchisePlayer, InjuryStatus, TeamContext


@dataclass(frozen=True)
class PlayerMinuteRecommendation:
    player_id: str
    name: str
    current_minutes: float
    recommended_minutes: int
    delta: int
    role: str
    priority: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RotationPlan:
    strategy: str
    recommendations: tuple[PlayerMinuteRecommendation, ...]
    top_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    total_current_minutes: float
    total_recommended_minutes: int
    priority: int


def rotation_recommendations(context: TeamContext, direction: TeamDirection | None = None):
    from .transactions import recommend_team_transactions

    return tuple(item for item in recommend_team_transactions(context, direction) if item.kind == "rotation")


def build_rotation_plan(context: TeamContext, direction: TeamDirection | None = None) -> RotationPlan:
    direction = direction or _infer_rotation_direction(context)
    injured = {injury.player_id: injury for injury in context.injury_statuses if injury.severity > 0 or injury.games_remaining > 0}
    recommendations = tuple(_player_recommendation(context, player, injured.get(player.player_id), direction) for player in context.roster.players)
    recommendations = tuple(sorted(recommendations, key=lambda item: (item.priority, abs(item.delta), item.recommended_minutes), reverse=True))
    warnings = _rotation_warnings(context, recommendations, direction)
    top_actions = tuple(_action_text(item) for item in recommendations if item.priority >= 65)[:5]
    priority = max((item.priority for item in recommendations), default=0)
    if context.injuries.active_count:
        priority = max(priority, 78)
    return RotationPlan(
        strategy=_strategy_label(direction, context),
        recommendations=recommendations,
        top_actions=top_actions or ("No major rotation changes recommended.",),
        warnings=warnings,
        total_current_minutes=round(sum(player.minutes or 0 for player in context.roster.players), 1),
        total_recommended_minutes=sum(item.recommended_minutes for item in recommendations),
        priority=priority,
    )


def rotation_evidence(context: TeamContext, direction: TeamDirection | None = None) -> dict[str, object]:
    plan = build_rotation_plan(context, direction)
    top = plan.recommendations[0] if plan.recommendations else None
    return {
        "rotation_strategy": plan.strategy,
        "rotation_plan_priority": plan.priority,
        "top_rotation_action": plan.top_actions[0] if plan.top_actions else "",
        "top_rotation_player": top.name if top else "",
        "top_rotation_delta": top.delta if top else 0,
        "rotation_warnings": plan.warnings,
    }


def _player_recommendation(context: TeamContext, player: FranchisePlayer, injury: InjuryStatus | None, direction: TeamDirection) -> PlayerMinuteRecommendation:
    current = float(player.minutes or 0)
    reasons: list[str] = []
    base = _base_minutes(player)
    priority = 35
    role = _role_for_minutes(base)

    if injury is not None:
        recommended = 0 if injury.severity >= 65 or injury.games_remaining >= 5 else max(0, int(base * 0.5))
        reasons.append(f"injury management: {injury.description or 'active injury'}")
        priority = 95
        role = "injured"
    else:
        recommended = base
        if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
            if _is_development_player(player):
                recommended = max(recommended, 26)
                reasons.append("development minutes for young core")
                priority = max(priority, 82)
                role = "development"
            elif _is_veteran(player):
                recommended = min(recommended, 24)
                reasons.append("reduce veteran minutes during rebuild")
                priority = max(priority, 72)
        elif direction is TeamDirection.CONTEND:
            if (player.overall or 0) >= 84:
                recommended = max(recommended, 32)
                reasons.append("contender relies on top rotation player")
                priority = max(priority, 58)
            elif (player.overall or 0) >= 76 and context.injuries.active_count:
                recommended = max(recommended, min(26, int(current + 10)))
                reasons.append("injury replacement minutes")
                priority = max(priority, 78)
                role = "rotation"

        if _morale_minutes_mismatch(player, current):
            recommended = max(recommended, 24)
            reasons.append("morale/minutes mismatch needs role review")
            priority = max(priority, 76)
            if role == "bench":
                role = "rotation"

    recommended = max(0, min(38, int(round(recommended))))
    delta = int(round(recommended - current))
    if abs(delta) >= 8:
        priority = max(priority, 70)
    if not reasons:
        reasons.append("maintain current role")
    if role not in {"injured", "development"}:
        role = _role_for_minutes(recommended)
    return PlayerMinuteRecommendation(player.player_id, player.name or player.player_id, current, recommended, delta, role, priority, tuple(reasons))


def _base_minutes(player: FranchisePlayer) -> int:
    overall = player.overall or 70
    current = player.minutes if player.minutes is not None else 0
    if overall >= 90:
        target = 34
    elif overall >= 84:
        target = 31
    elif overall >= 78:
        target = 26
    elif overall >= 73:
        target = 18
    else:
        target = 10
    if current:
        target = int(round(target * 0.65 + current * 0.35))
    return max(0, min(38, target))


def _rotation_warnings(context: TeamContext, recommendations: tuple[PlayerMinuteRecommendation, ...], direction: TeamDirection) -> tuple[str, ...]:
    warnings: list[str] = []
    if context.injuries.active_count:
        warnings.append(f"{context.injuries.active_count} active injury case(s): rebalance replacement minutes before simming.")
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and any("veteran" in " ".join(item.reasons).lower() for item in recommendations):
        warnings.append("Veteran minutes should be reduced if they block development players.")
    morale_cases = [item.name for item in recommendations if any("morale" in reason.lower() for reason in item.reasons)]
    if morale_cases:
        warnings.append("Morale/minutes mismatch: " + ", ".join(morale_cases[:3]))
    if sum(item.recommended_minutes for item in recommendations) > 255:
        warnings.append("Recommended minutes exceed normal rotation total; trim depth roles manually.")
    return tuple(warnings)


def _action_text(item: PlayerMinuteRecommendation) -> str:
    verb = "increase" if item.delta > 0 else "reduce" if item.delta < 0 else "hold"
    return f"{verb} {item.name} to {item.recommended_minutes} MPG ({item.role})"


def _strategy_label(direction: TeamDirection, context: TeamContext) -> str:
    if context.injuries.active_count:
        return "injury-aware rotation rebalance"
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        return "development-first rotation"
    if direction is TeamDirection.CONTEND:
        return "playoff-ready rotation stability"
    return "role/morale evaluation rotation"


def _is_development_player(player: FranchisePlayer) -> bool:
    return (player.age or 99) <= 24 and (player.potential or player.overall or 0) >= 80


def _is_veteran(player: FranchisePlayer) -> bool:
    return (player.age or 0) >= 31 and (player.minutes or 0) >= 24


def _morale_minutes_mismatch(player: FranchisePlayer, current_minutes: float) -> bool:
    return (player.morale or 50) <= 40 and (player.overall or 0) >= 76 and current_minutes < 24


def _role_for_minutes(minutes: int) -> str:
    if minutes >= 30:
        return "starter"
    if minutes >= 20:
        return "rotation"
    if minutes >= 10:
        return "bench"
    return "reserve"


def _infer_rotation_direction(context: TeamContext) -> TeamDirection:
    if context.record.win_pct >= 0.58 or context.record.expected_win_pct >= 0.58 or context.roster.star_quality >= 88:
        return TeamDirection.CONTEND
    if context.record.win_pct <= 0.35 and context.roster.young_core_count >= 1:
        return TeamDirection.REBUILD
    if context.record.win_pct <= 0.30 and context.roster.star_quality < 82:
        return TeamDirection.TANK
    return TeamDirection.EVALUATE
