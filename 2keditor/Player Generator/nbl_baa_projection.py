from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


REFERENCE_CONTEXT_KEY = "nbl_same_season_baa_common_feature_references"
_DEFENSE_FIELDS = frozenset(
    {
        "Attributes/BLOCK", "Attributes/CONTESTSHOT", "Attributes/DEFENSECONSISTENCY",
        "Attributes/HELPDEFENSE", "Attributes/INTERIORDEFENSE", "Attributes/LATERALQUICKNESS",
        "Attributes/PASSPERCEPTION", "Attributes/PERIMETERDEFENSE",
        "Attributes/PICKANDROLLDEFENSEIQ", "Attributes/STEAL",
    }
)
DEFENSIVE_SKILL_FIELD_KEYS = _DEFENSE_FIELDS - {"Attributes/DEFENSECONSISTENCY"}
_REBOUND_FIELDS = frozenset({"Attributes/OFFENSIVEREBOUND", "Attributes/DEFENSEREBOUND"})
_PASSING_FIELDS = frozenset(
    {
        "Attributes/BALLCONTROL", "Attributes/PASSACCURACY",
        "Attributes/PASSIQ", "Attributes/PASSVISION",
    }
)
_MENTAL_FIELDS = frozenset(
    {"Attributes/HUSTLE", "Attributes/OFFENSIVECONSISTENCY"}
)
PROJECTED_FIELD_KEYS = _DEFENSE_FIELDS | _REBOUND_FIELDS | _PASSING_FIELDS | _MENTAL_FIELDS
_TEAM_SUCCESS_FIELDS = _PASSING_FIELDS | _MENTAL_FIELDS
_TEAM_SUCCESS_BLEND_WEIGHT = 0.40
_NEIGHBOR_COUNT = 12
_DISTANCE_FLOOR = 0.05
# No position dimension. The five position features were the largest single term in the
# distance metric -- 40% of the passing distance, 30% of the defensive -- so the label,
# not the player, chose which BAA players an NBL player's ratings were projected from.
_FEATURE_NAMES = (
    "height", "weight", "games_share", "team_defense", "points_share",
    "field_goal_share", "fta_share", "ft_percent", "age",
)
_GROUP_WEIGHTS = {
    # Position carries no weight in the distance metric. It decided which BAA players an
    # NBL player was compared against -- 30% of the defensive distance and 40% of the
    # passing distance -- so the label, not the player, chose the neighbours his ratings
    # were projected from. Its share moves to the body and the box score, which are what
    # the label was standing in for.
    "defense": {"height": 0.35, "weight": 0.20, "games_share": 0.10, "team_defense": 0.35},
    "rebound": {"height": 0.65, "weight": 0.15, "games_share": 0.05, "team_defense": 0.05, "points_share": 0.05, "fta_share": 0.05},
    "passing": {"height": 0.20, "games_share": 0.15, "points_share": 0.20, "field_goal_share": 0.15, "fta_share": 0.10, "ft_percent": 0.20},
    "mental": {"games_share": 0.35, "team_defense": 0.10, "points_share": 0.20, "field_goal_share": 0.10, "fta_share": 0.10, "ft_percent": 0.10, "age": 0.05},
    # Height leads for rebounding, not the position label. The 1947 NBL records 64% of
    # its players with hyphenated positions against the BAA's 29%, and the
    # multi-position fallback takes the higher branch -- so a 6'1" "G-F" was encoded as
    # a pure small forward and matched to 6'6" BAA wings, inheriting their rebound
    # numbers. Rebounding is won by reach, so reach decides who a player is compared to.
}


@dataclass(frozen=True)
class ProjectedFieldValue:
    value: int
    source_rule: str
    evidence_keys: tuple[str, ...]


def make_baa_projection_reference(
    evidence: Any,
    league_rows: Iterable[dict[str, Any]],
    targets: Mapping[str, int],
) -> dict[str, Any]:
    rows = tuple(league_rows)
    return {
        "player_id": str(getattr(evidence, "player_id", "") or "").strip(),
        "team": str(getattr(evidence, "team", "") or "").strip().upper(),
        "features": common_feature_vector(evidence, rows),
        "targets": {str(field): int(value) for field, value in targets.items() if field in PROJECTED_FIELD_KEYS},
    }


def project_nbl_fields(
    evidence: Any,
    league_rows: Iterable[dict[str, Any]],
    current_values: Mapping[str, Any],
) -> dict[str, ProjectedFieldValue]:
    league = str(getattr(evidence, "season_info", {}).get("lg") or "").strip().upper()
    if league != "NBL":
        return {}
    source_context = getattr(evidence, "source_context", {})
    references = source_context.get(REFERENCE_CONTEXT_KEY) if isinstance(source_context, dict) else None
    if not isinstance(references, (tuple, list)) or not references:
        return {}

    source_rows = tuple(
        row
        for row in league_rows
        if str(_source_value(row, "player_season_info.lg", "season_info.lg", "lg") or "").strip().upper() == league
    )
    if not source_rows:
        return {}
    target_features = common_feature_vector(evidence, source_rows)
    team_success_percentile = _team_win_percentile(evidence, source_rows)
    projected: dict[str, ProjectedFieldValue] = {}
    for field_key in PROJECTED_FIELD_KEYS:
        current = current_values.get(field_key)
        current_rule = str(getattr(current, "source_rule", "") or "")
        if current_rule.endswith("_researched_exact_player_override"):
            continue
        candidates: list[tuple[float, int, str, str]] = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            features = reference.get("features")
            targets = reference.get("targets")
            if not isinstance(features, (tuple, list)) or not isinstance(targets, dict):
                continue
            value = targets.get(field_key)
            if not isinstance(value, (int, float)):
                continue
            distance = _feature_distance(field_key, target_features, tuple(float(item) for item in features))
            candidates.append(
                (
                    distance,
                    int(round(value)),
                    str(reference.get("player_id") or "").strip(),
                    str(reference.get("team") or "").strip().upper(),
                )
            )
        if not candidates:
            continue
        nearest = tuple(sorted(candidates, key=lambda item: (item[0], item[2], item[3]))[:_NEIGHBOR_COUNT])
        weighted = tuple((1.0 / (distance + _DISTANCE_FLOOR), value) for distance, value, _player_id, _team in nearest)
        denominator = sum(weight for weight, _value in weighted)
        if denominator <= 0.0:
            continue
        common_feature_value = sum(weight * target for weight, target in weighted) / denominator
        value = common_feature_value
        team_success_keys: tuple[str, ...] = ()
        if field_key in _TEAM_SUCCESS_FIELDS and team_success_percentile is not None:
            reference_values = tuple(sorted(target for _distance, target, _player_id, _team in candidates))
            team_success_value = _linear_percentile(reference_values, team_success_percentile)
            value = (
                (1.0 - _TEAM_SUCCESS_BLEND_WEIGHT) * common_feature_value
                + _TEAM_SUCCESS_BLEND_WEIGHT * team_success_value
            )
            team_win_pct = _team_win_pct(evidence)
            team_success_keys = (
                "team_summary.w",
                "team_summary.l",
                f"raw_common_feature_projection={common_feature_value:.8f}",
                f"team_win_pct={team_win_pct:.8f}",
                f"same_season_nbl_team_win_percentile={team_success_percentile:.8f}",
                f"team_success_reference_value={team_success_value:.8f}",
                "team_success_reference=same-season_BAA_generated_field_distribution",
                f"team_success_blend_weight={_TEAM_SUCCESS_BLEND_WEIGHT:.2f}",
                "mapping=round("
                f"{1.0 - _TEAM_SUCCESS_BLEND_WEIGHT:.2f}*common_feature_projection+"
                f"{_TEAM_SUCCESS_BLEND_WEIGHT:.2f}*team_success_reference_value)",
            )
        value = max(25, min(99, int(round(value))))
        neighbor_proof = tuple(
            f"baa_neighbor={player_id}|{team}|target:{target}|distance:{distance:.8f}"
            for distance, target, player_id, team in nearest[:3]
        )
        projected[field_key] = ProjectedFieldValue(
            value=value,
            source_rule=(
                "nbl_same_season_baa_common_feature_projection_team_success_calibrated"
                if team_success_keys
                else "nbl_same_season_baa_common_feature_projection"
            ),
            evidence_keys=(
                "season_info.lg=NBL",
                "projection_reference=same_season_BAA_generated_field",
                "projection_inputs=only_features_present_in_both_NBL_and_BAA",
                "projection_features=" + ",".join(
                    f"{name}:{feature:.8f}" for name, feature in zip(_FEATURE_NAMES, target_features)
                ),
                "projection_distance_weights=" + ",".join(
                    f"{name}:{weight:.2f}" for name, weight in _weights_for_field(field_key).items()
                ),
                f"projection_neighbor_count={len(nearest)}",
                "projection_method=inverse_distance_weighted_nearest_neighbors",
                *team_success_keys,
                *_source_paths(),
                *neighbor_proof,
            ),
        )
    return projected


def common_feature_vector(source: Any, league_rows: tuple[dict[str, Any], ...]) -> tuple[float, ...]:
    height = _number(_source_value(source, "identity.ht_in_in", "player_info.ht_in_in"))
    weight = _number(_source_value(source, "identity.wt", "player_info.wt"))
    games = _number(_source_value(source, "per_game.g", "player_per_game.g"))
    team_games = _number(_source_value(source, "team_stats_per_game.g"))
    opponent_points = _number(_source_value(source, "opponent_stats_per_game.opp_pts_per_game"))
    points = _number(_source_value(source, "per_game.pts_per_game", "player_per_game.pts_per_game"))
    team_points = _number(_source_value(source, "team_stats_per_game.pts_per_game"))
    field_goals = _number(_source_value(source, "per_game.fg_per_game", "player_per_game.fg_per_game"))
    team_field_goals = _number(_source_value(source, "team_stats_per_game.fg_per_game"))
    free_throw_attempts = _number(_source_value(source, "per_game.fta_per_game", "player_per_game.fta_per_game"))
    team_free_throw_attempts = _number(_source_value(source, "team_stats_per_game.fta_per_game"))
    free_throw_percent = _number(_source_value(source, "per_game.ft_percent", "player_per_game.ft_percent"))
    age = _number(_source_value(source, "season_info.age", "player_season_info.age", "identity.age", "player_info.age"))
    height_population = _population(league_rows, "player_info.ht_in_in", unique_by=None)
    weight_population = _population(league_rows, "player_info.wt", unique_by=None)
    age_population = _population(league_rows, "player_season_info.age", unique_by=None)
    opponent_population = _population(league_rows, "opponent_stats_per_game.opp_pts_per_game", unique_by="team")
    points_share_population = _ratio_population(league_rows, "player_per_game.pts_per_game", "team_stats_per_game.pts_per_game")
    field_goal_share_population = _ratio_population(league_rows, "player_per_game.fg_per_game", "team_stats_per_game.fg_per_game")
    fta_share_population = _ratio_population(league_rows, "player_per_game.fta_per_game", "team_stats_per_game.fta_per_game")
    games_share = games / team_games if games is not None and team_games is not None and team_games > 0.0 else 0.5
    points_share = points / team_points if points is not None and team_points is not None and team_points > 0.0 else None
    field_goal_share = field_goals / team_field_goals if field_goals is not None and team_field_goals is not None and team_field_goals > 0.0 else None
    fta_share = free_throw_attempts / team_free_throw_attempts if free_throw_attempts is not None and team_free_throw_attempts is not None and team_free_throw_attempts > 0.0 else None

    return (
        _span_score(height, height_population),
        _span_score(weight, weight_population),
        _bounded(games_share),
        1.0 - _rank_score(opponent_points, opponent_population),
        _rank_score(points_share, points_share_population),
        _rank_score(field_goal_share, field_goal_share_population),
        _rank_score(fta_share, fta_share_population),
        _bounded(free_throw_percent if free_throw_percent is not None else 0.5),
        _span_score(age, age_population),
    )


def _feature_distance(field_key: str, left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(_FEATURE_NAMES) or len(right) != len(_FEATURE_NAMES):
        return math.inf
    weights = _weights_for_field(field_key)
    distance = 0.0
    feature_index = {name: index for index, name in enumerate(_FEATURE_NAMES)}
    for name, weight in weights.items():
        index = feature_index[name]
        distance += weight * (left[index] - right[index]) ** 2
    return math.sqrt(max(0.0, distance))


def _weights_for_field(field_key: str) -> dict[str, float]:
    if field_key in _REBOUND_FIELDS:
        return _GROUP_WEIGHTS["rebound"]
    if field_key in _PASSING_FIELDS:
        return _GROUP_WEIGHTS["passing"]
    if field_key in _MENTAL_FIELDS:
        return _GROUP_WEIGHTS["mental"]
    return _GROUP_WEIGHTS["defense"]


def _population(
    rows: tuple[dict[str, Any], ...],
    path: str,
    *,
    unique_by: str | None,
) -> tuple[float, ...]:
    values: list[float] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if unique_by is not None:
            identity = str(_source_value(row, unique_by, "player_season_info.team", "team") or f"__ROW_{ordinal}").strip().upper()
            if identity in seen:
                continue
            seen.add(identity)
        value = _number(_source_value(row, path))
        if value is not None:
            values.append(value)
    return tuple(sorted(values))


def _ratio_population(
    rows: tuple[dict[str, Any], ...],
    numerator_path: str,
    denominator_path: str,
) -> tuple[float, ...]:
    values: list[float] = []
    for row in rows:
        numerator = _number(_source_value(row, numerator_path))
        denominator = _number(_source_value(row, denominator_path))
        if numerator is not None and denominator is not None and denominator > 0.0:
            values.append(numerator / denominator)
    return tuple(sorted(values))


def _source_value(source: Any, *paths: str) -> object:
    for path in paths:
        if isinstance(source, dict):
            if path in source and source.get(path) is not None:
                return source.get(path)
            continue
        section, _, field = path.partition(".")
        if not field:
            continue
        mapping = getattr(source, section, None)
        if isinstance(mapping, dict) and mapping.get(field) is not None:
            return mapping.get(field)
        context = getattr(source, "source_context", None)
        if isinstance(context, dict) and context.get(path) is not None:
            return context.get(path)
    return None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _span_score(value: float | None, population: tuple[float, ...]) -> float:
    if value is None or not population:
        return 0.5
    low, high = population[0], population[-1]
    if high <= low:
        return 0.5
    return _bounded((value - low) / (high - low))


def _rank_score(value: float | None, population: tuple[float, ...]) -> float:
    if value is None or not population:
        return 0.5
    left = bisect.bisect_left(population, value)
    right = bisect.bisect_right(population, value)
    return _bounded((left + right + 1.0) / (2.0 * (len(population) + 1.0)))


def _team_win_pct(source: Any) -> float | None:
    wins = _number(_source_value(source, "team_summary.w", "team_summaries.w"))
    losses = _number(_source_value(source, "team_summary.l", "team_summaries.l"))
    if wins is None or losses is None or wins < 0.0 or losses < 0.0 or wins + losses <= 0.0:
        return None
    return wins / (wins + losses)


def _team_win_percentile(source: Any, rows: tuple[dict[str, Any], ...]) -> float | None:
    current = _team_win_pct(source)
    if current is None:
        return None
    team_values: dict[str, float] = {}
    for ordinal, row in enumerate(rows):
        team = str(
            _source_value(row, "player_season_info.team", "season_info.team", "team")
            or f"__ROW_{ordinal}"
        ).strip().upper()
        value = _team_win_pct(row)
        if value is not None:
            team_values.setdefault(team, value)
    population = tuple(sorted(team_values.values()))
    if len(population) < 2:
        return None
    left = bisect.bisect_left(population, current)
    right = bisect.bisect_right(population, current)
    midrank = (left + right - 1.0) / 2.0
    return _bounded(midrank / (len(population) - 1.0))


def _linear_percentile(values: tuple[int, ...], percentile: float) -> float:
    position = _bounded(percentile) * (len(values) - 1)
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _source_paths() -> tuple[str, ...]:
    return (
        "identity.ht_in_in",
        "identity.wt",
        "per_game.g",
        "team_stats_per_game.g",
        "opponent_stats_per_game.opp_pts_per_game",
        "per_game.pts_per_game",
        "team_stats_per_game.pts_per_game",
        "per_game.fg_per_game",
        "team_stats_per_game.fg_per_game",
        "per_game.fta_per_game",
        "team_stats_per_game.fta_per_game",
        "per_game.ft_percent",
        "season_info.age",
        "team_summary.w",
        "team_summary.l",
    )


__all__ = [
    "DEFENSIVE_SKILL_FIELD_KEYS",
    "PROJECTED_FIELD_KEYS",
    "ProjectedFieldValue",
    "REFERENCE_CONTEXT_KEY",
    "common_feature_vector",
    "make_baa_projection_reference",
    "project_nbl_fields",
]
