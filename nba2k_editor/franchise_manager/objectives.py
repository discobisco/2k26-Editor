from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import ImportedDataKind, ImportedSnapshot, TeamDirection
from .world import TeamContext, latest_payload


@dataclass(frozen=True)
class ObjectiveDirective:
    team_id: str
    season: int
    objective_type: str
    priority: str = "secondary"
    target: dict[str, Any] = field(default_factory=dict)
    status: str = "open"
    description: str = ""
    source: str = "owner"


@dataclass(frozen=True)
class ObjectiveProgress:
    directive: ObjectiveDirective
    status: str
    progress: float
    target_value: float
    actual_value: float
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OwnerReview:
    results: tuple[ObjectiveProgress, ...]
    passed_primary: int
    failed_primary: int
    passed_secondary: int
    failed_secondary: int
    firing_risk: int
    budget_delta: int
    morale_delta: int
    summary: str


def assign_preseason_directives(context: TeamContext, direction: TeamDirection | None = None) -> tuple[ObjectiveDirective, ...]:
    direction = direction or _infer_objective_direction(context)
    season = context.season
    team_id = context.team.team_id
    owner = context.team.owner
    directives: list[ObjectiveDirective] = []
    if direction is TeamDirection.CONTEND:
        directives.append(ObjectiveDirective(team_id, season, "make_playoffs", "primary", {"min_wins": 45}, description="Make the playoffs with the current core."))
        if context.cap.is_tax_team or owner.spending_willingness < 55:
            directives.append(ObjectiveDirective(team_id, season, "manage_luxury_tax", "secondary", {"max_tax_overage": 0 if owner.spending_willingness < 50 else 15_000_000}, description="Keep tax exposure aligned with owner budget."))
        directives.append(ObjectiveDirective(team_id, season, "protect_star_health", "secondary", {"max_rotation_games_lost": 30}, description="Manage star injury risk before playoffs."))
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        directives.append(ObjectiveDirective(team_id, season, "develop_young_core", "primary", {"min_young_core": 2}, description="Establish a young core with real rotation minutes."))
        directives.append(ObjectiveDirective(team_id, season, "acquire_first_round_pick", "secondary", {"min_future_firsts": 2}, description="Add or preserve future first-round equity."))
        directives.append(ObjectiveDirective(team_id, season, "preserve_cap_flexibility", "secondary", {"min_cap_space_or_expiring": 25_000_000}, description="Avoid long-term payroll traps."))
    else:
        directives.append(ObjectiveDirective(team_id, season, "finish_above_expected", "primary", {"min_win_delta": 0}, description="Meet or beat expected record."))
        directives.append(ObjectiveDirective(team_id, season, "stabilize_morale", "secondary", {"min_average_morale": 50}, description="Avoid role and morale collapse."))
    return tuple(directives)


def objectives_from_snapshots(snapshots: tuple[ImportedSnapshot, ...], *, season: int, team_id: str) -> tuple[ObjectiveDirective, ...]:
    payload = latest_payload(snapshots, ImportedDataKind.OBJECTIVES) or {}
    directives = []
    for row in _rows_from_payload(payload):
        directive = objective_from_payload(row)
        if directive.season not in (0, season):
            continue
        if directive.team_id and directive.team_id != team_id:
            continue
        directives.append(directive if directive.team_id else ObjectiveDirective(team_id, season, directive.objective_type, directive.priority, directive.target, directive.status, directive.description, directive.source))
    return tuple(directives)


def evaluate_objective_progress(context: TeamContext, objectives: Iterable[ObjectiveDirective]) -> tuple[ObjectiveProgress, ...]:
    return tuple(_evaluate_one(context, objective) for objective in objectives)


def owner_end_season_review(context: TeamContext, objectives: Iterable[ObjectiveDirective], direction: TeamDirection | None = None) -> OwnerReview:
    direction = direction or _infer_objective_direction(context)
    results = evaluate_objective_progress(context, tuple(objectives))
    passed_primary = sum(1 for item in results if item.directive.priority == "primary" and item.status == "passed")
    failed_primary = sum(1 for item in results if item.directive.priority == "primary" and item.status == "failed")
    passed_secondary = sum(1 for item in results if item.directive.priority != "primary" and item.status == "passed")
    failed_secondary = sum(1 for item in results if item.directive.priority != "primary" and item.status == "failed")
    owner = context.team.owner
    pressure = max(0, context.record.market_pressure - 50) * owner.market_pressure_sensitivity / 100
    risk = owner.firing_threshold + failed_primary * 35 + failed_secondary * 12 - passed_primary * 18 - passed_secondary * 6
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and owner.rebuild_tolerance >= 65:
        risk -= 12
    risk += int(round(pressure))
    firing_risk = max(0, min(100, int(round(risk))))
    budget_delta = passed_primary * 8_000_000 + passed_secondary * 3_000_000 - failed_primary * 10_000_000 - failed_secondary * 4_000_000
    morale_delta = passed_primary * 4 + passed_secondary * 1 - failed_primary * 5 - failed_secondary * 2
    if failed_primary:
        summary = f"Owner review: failed primary directive; firing risk {firing_risk}%."
    elif passed_primary and not failed_secondary:
        summary = f"Owner review: directives passed; budget confidence improves by ${budget_delta:,}."
    else:
        summary = f"Owner review: mixed directive results; firing risk {firing_risk}%."
    return OwnerReview(results, passed_primary, failed_primary, passed_secondary, failed_secondary, firing_risk, budget_delta, morale_delta, summary)


def objective_review_evidence(review: OwnerReview) -> dict[str, Any]:
    return {
        "passed_primary": review.passed_primary,
        "failed_primary": review.failed_primary,
        "passed_secondary": review.passed_secondary,
        "failed_secondary": review.failed_secondary,
        "firing_risk": review.firing_risk,
        "budget_delta": review.budget_delta,
        "morale_delta": review.morale_delta,
        "summary": review.summary,
        "results": [
            {
                "objective_type": item.directive.objective_type,
                "priority": item.directive.priority,
                "status": item.status,
                "progress": item.progress,
                "actual": item.actual_value,
                "target": item.target_value,
                "summary": item.summary,
            }
            for item in review.results
        ],
    }


def objective_to_payload(objective: ObjectiveDirective | dict[str, Any]) -> dict[str, Any]:
    if isinstance(objective, ObjectiveDirective):
        return {
            "team_id": objective.team_id,
            "season": objective.season,
            "objective_type": objective.objective_type,
            "priority": objective.priority,
            "target": dict(objective.target),
            "status": objective.status,
            "description": objective.description,
            "source": objective.source,
        }
    return dict(objective)


def objective_from_payload(payload: dict[str, Any]) -> ObjectiveDirective:
    target = payload.get("target") or payload.get("target_json") or {}
    if not isinstance(target, dict):
        target = {}
    return ObjectiveDirective(
        team_id=str(payload.get("team_id") or payload.get("team") or ""),
        season=_int_value(payload.get("season"), 0),
        objective_type=str(payload.get("objective_type") or payload.get("type") or ""),
        priority=str(payload.get("priority") or payload.get("importance") or "secondary"),
        target=target,
        status=str(payload.get("status") or "open"),
        description=str(payload.get("description") or payload.get("label") or ""),
        source=str(payload.get("source") or "owner"),
    )


def _evaluate_one(context: TeamContext, objective: ObjectiveDirective) -> ObjectiveProgress:
    kind = objective.objective_type
    target = objective.target
    if kind == "make_playoffs":
        target_value = float(target.get("min_wins", 45))
        actual = float(context.record.wins)
        return _progress(objective, actual, target_value, actual >= target_value, f"{context.record.wins} wins vs {int(target_value)} target")
    if kind == "manage_luxury_tax":
        target_value = float(target.get("max_tax_overage", 0))
        actual = float(context.cap.luxury_tax_overage)
        return _progress(objective, max(0.0, target_value - actual), target_value, actual <= target_value, f"${int(actual):,} tax overage vs ${int(target_value):,} max", inverse_actual=actual)
    if kind == "develop_young_core":
        target_value = float(target.get("min_young_core", 2))
        actual = float(context.roster.young_core_count)
        return _progress(objective, actual, target_value, actual >= target_value, f"{int(actual)} young core players vs {int(target_value)} target")
    if kind == "acquire_first_round_pick":
        target_value = float(target.get("min_future_firsts", 2))
        actual = float(context.draft_assets.future_firsts)
        return _progress(objective, actual, target_value, actual >= target_value, f"{int(actual)} future firsts vs {int(target_value)} target")
    if kind == "preserve_cap_flexibility":
        target_value = float(target.get("min_cap_space_or_expiring", 25_000_000))
        actual = float(max(context.cap.cap_space, context.cap.expiring_salary))
        return _progress(objective, actual, target_value, actual >= target_value, f"${int(actual):,} flexibility vs ${int(target_value):,} target")
    if kind == "finish_above_expected":
        target_value = float(target.get("min_win_delta", 0))
        actual = float(context.record.wins - (context.record.expected_wins or context.record.wins))
        return _progress(objective, actual, target_value, actual >= target_value, f"{actual:+.0f} wins vs expected")
    if kind == "stabilize_morale":
        target_value = float(target.get("min_average_morale", 50))
        actual = float(context.roster.average_morale)
        return _progress(objective, actual, target_value, actual >= target_value, f"{actual:.1f} morale vs {target_value:.0f} target")
    if kind == "protect_star_health":
        target_value = float(target.get("max_rotation_games_lost", 30))
        actual = float(context.injuries.rotation_games_lost)
        return _progress(objective, max(0.0, target_value - actual), target_value, actual <= target_value, f"{int(actual)} rotation games lost vs {int(target_value)} max", inverse_actual=actual)
    return ObjectiveProgress(objective, "open", 0.0, 0.0, 0.0, "Objective type is not implemented.", {"objective_type": kind})


def _progress(objective: ObjectiveDirective, actual_for_progress: float, target_value: float, passed: bool, summary: str, *, inverse_actual: float | None = None) -> ObjectiveProgress:
    denominator = abs(target_value) if target_value else 1.0
    progress = max(0.0, min(1.0, actual_for_progress / denominator))
    actual_value = actual_for_progress if inverse_actual is None else inverse_actual
    return ObjectiveProgress(objective, "passed" if passed else "failed", round(progress, 3), target_value, actual_value, summary, {"target": objective.target})


def _rows_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = payload.get("objectives") or payload.get("directives") or payload.get("rows") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    return tuple(dict(row) for row in rows if isinstance(row, dict))


def _infer_objective_direction(context: TeamContext) -> TeamDirection:
    if context.record.win_pct >= 0.58 or context.record.expected_win_pct >= 0.58 or context.roster.star_quality >= 88:
        return TeamDirection.CONTEND
    if context.record.win_pct <= 0.35 and context.roster.young_core_count >= 1:
        return TeamDirection.REBUILD
    if context.record.win_pct <= 0.30 and context.roster.star_quality < 82:
        return TeamDirection.TANK
    return TeamDirection.EVALUATE


def _int_value(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(round(float(str(value).replace(",", ""))))
    except ValueError:
        return default
