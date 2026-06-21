from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RuleSpec:
    field_key: str
    module: str
    function: str


@dataclass(frozen=True)
class RuleValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class ProfileValue:
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class PlayerRuleResult:
    values: dict[str, RuleValue]


@dataclass(frozen=True)
class PlayerProfileResult:
    values: dict[str, ProfileValue]


class MetricRankings:
    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self._rows = tuple(row for row in rows if isinstance(row, dict))
        self._values_by_path: dict[str, tuple[float, ...]] = {}

    def rank(self, value: float, path: str) -> float:
        clean = str(path).removeprefix("!")
        values = self._values_by_path.get(clean)
        if values is None:
            values = tuple(
                sorted(
                    candidate
                    for row in self._rows
                    for candidate in (_row_value(row, clean),)
                    if candidate is not None
                )
            )
            self._values_by_path[clean] = values
        if len(values) > 1:
            below = bisect_left(values, value)
            equal = bisect_right(values, value) - below
            return (below + (equal - 1) / 2) / (len(values) - 1)
        return _score_unit(value)


def _number(source: Any, key: str) -> float | None:
    if source is None:
        return None
    value: Any = None
    if isinstance(source, dict):
        value = source.get(key)
    else:
        value = getattr(source, key, None)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_for_prefix(evidence: Any, prefix: str) -> Any:
    if prefix == "per_game":
        return getattr(evidence, "per_game", {})
    if prefix == "totals":
        return getattr(evidence, "totals", {})
    if prefix == "per_36":
        return getattr(evidence, "per_36", {})
    if prefix == "per_100":
        return getattr(evidence, "per_100", {})
    if prefix == "advanced":
        return getattr(evidence, "advanced", {})
    if prefix == "shooting":
        return getattr(evidence, "shooting", {})
    if prefix == "play_by_play":
        return getattr(evidence, "play_by_play", {})
    if prefix == "team_stats_per_game":
        return getattr(evidence, "team_stats_per_game", {})
    if prefix == "team_stats_per_100":
        return getattr(evidence, "team_stats_per_100", {})
    if prefix == "team_summary":
        return getattr(evidence, "team_summary", {})
    if prefix == "opponent_stats_per_game":
        return getattr(evidence, "opponent_stats_per_game", {})
    if prefix == "opponent_stats_per_100":
        return getattr(evidence, "opponent_stats_per_100", {})
    return getattr(evidence, "source_context", {})


def _path_value(evidence: Any, path: str) -> float | None:
    clean = path.removeprefix("!")
    if "." not in clean:
        return _number(getattr(evidence, "source_context", {}), clean)
    prefix, key = clean.split(".", 1)
    value = _number(_source_for_prefix(evidence, prefix), key)
    if value is not None:
        return value
    if prefix == "per_36" and key.endswith("_per_36_min"):
        per_game_key = f"{key.removesuffix('_per_36_min')}_per_game"
        per_game_value = _number(getattr(evidence, "per_game", {}), per_game_key)
        minutes = _number(getattr(evidence, "per_game", {}), "mp_per_game")
        if per_game_value is not None and minutes is not None and minutes > 0:
            return per_game_value / minutes * 36.0
    return None


def _row_value(row: dict[str, Any], path: str) -> float | None:
    clean = path.removeprefix("!")
    value = _number(row, clean)
    if value is not None:
        return value
    if "." in clean:
        return _number(row, clean.split(".", 1)[1])
    return None


def _metric_rank(value: float, path: str, league_player_rows: Any) -> float:
    if hasattr(league_player_rows, "rank"):
        ranked = league_player_rows.rank(value, path.removeprefix("!"))
        return _score_unit(ranked)
    if isinstance(league_player_rows, Iterable) and not isinstance(league_player_rows, (str, bytes, dict)):
        values = sorted(
            candidate
            for row in league_player_rows
            if isinstance(row, dict)
            for candidate in [_row_value(row, path)]
            if candidate is not None
        )
        if len(values) > 1:
            below = sum(1 for candidate in values if candidate < value)
            equal = sum(1 for candidate in values if candidate == value)
            return _score_unit((below + (equal - 1) / 2) / (len(values) - 1))
    return _score_unit(value)


def _score_unit(value: Any) -> float:
    number = _number({"value": value}, "value")
    if number is None:
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _score_from_parts(evidence: Any, parts: tuple[tuple[str, float], ...], league_player_rows: Any = ()) -> float:
    total = 0.0
    weight_total = 0.0
    for raw_path, raw_weight in parts:
        path = str(raw_path)
        weight = float(raw_weight)
        value = _path_value(evidence, path)
        if value is None:
            continue
        rank = _metric_rank(value, path, league_player_rows)
        if path.startswith("!"):
            rank = 1.0 - rank
        total += rank * weight
        weight_total += weight
    if weight_total <= 0.0:
        return 0.0
    return total / weight_total


def _value_from_stat_range(evidence: Any, stat_path: str, points: tuple[tuple[float, ...], ...], fallback: int) -> int:
    value = _path_value(evidence, stat_path)
    if value is None or not points:
        return fallback
    # Preferred band shape is:
    # (stat_min, stat_mean, stat_median, stat_max, rating_low, rating_high).
    # This keeps the live-game range evidence intact instead of collapsing each
    # band to a single median anchor.  Legacy two-value anchors remain supported
    # only so older rule calls fail soft during this transition.
    first = points[0]
    if len(first) >= 6:
        bands: list[tuple[float, float, float, float, float, float]] = [
            (float(band[0]), float(band[1]), float(band[2]), float(band[3]), float(band[4]), float(band[5]))
            for band in points
            if len(band) >= 6
        ]
        if not bands:
            return fallback
        bands.sort(key=lambda band: (band[0], band[2], band[3]))
        if value <= bands[0][0]:
            return int(round(bands[0][4]))
        if value >= bands[-1][3]:
            return int(round(bands[-1][5]))

        def band_distance(band: tuple[float, float, float, float, float, float]) -> float:
            stat_min, _stat_mean, stat_median, stat_max, _rating_low, _rating_high = band
            width = max(stat_max - stat_min, 1e-9)
            if stat_min <= value <= stat_max:
                return abs(value - stat_median) / width
            if value < stat_min:
                return (stat_min - value) / width + 1.0
            return (value - stat_max) / width + 1.0

        stat_min, _stat_mean, stat_median, stat_max, rating_low, rating_high = min(bands, key=band_distance)
        if stat_max <= stat_min:
            return int(round((rating_low + rating_high) / 2))
        if value <= stat_median:
            ratio = (value - stat_min) / max(stat_median - stat_min, 1e-9)
            return int(round(rating_low + max(0.0, min(1.0, ratio)) * (((rating_low + rating_high) / 2) - rating_low)))
        ratio = (value - stat_median) / max(stat_max - stat_median, 1e-9)
        return int(round(((rating_low + rating_high) / 2) + max(0.0, min(1.0, ratio)) * (rating_high - ((rating_low + rating_high) / 2))))

    ordered = sorted((float(stat), int(rating)) for stat, rating in points)  # legacy median-only anchors
    if value <= ordered[0][0]:
        return ordered[0][1]
    if value >= ordered[-1][0]:
        return ordered[-1][1]
    for (left_stat, left_rating), (right_stat, right_rating) in zip(ordered, ordered[1:]):
        if left_stat <= value <= right_stat:
            if right_stat == left_stat:
                return int(round((left_rating + right_rating) / 2))
            ratio = (value - left_stat) / (right_stat - left_stat)
            return int(round(left_rating + ratio * (right_rating - left_rating)))
    return fallback


def _attribute(
    evidence: Any,
    field_key: str,
    source_rule: str,
    parts: tuple[tuple[str, float], ...],
    *,
    league_player_rows: Any = (),
    range_path: str | None = None,
    range_points: tuple[tuple[float, ...], ...] = (),
) -> dict[str, Any]:
    if range_path is not None and range_points:
        value = _value_from_stat_range(evidence, range_path, range_points, 25)
    else:
        score = _score_from_parts(evidence, parts, league_player_rows)
        value = int(round(25 + score * 74))
    return {
        "value": value,
        "source_rule": source_rule,
        "evidence_keys": tuple(path.removeprefix("!") for path, _weight in parts),
    }


def _attribute_curve(
    evidence: Any,
    field_key: str,
    source_rule: str,
    parts: tuple[tuple[str, float], ...],
    *,
    league_player_rows: Any = (),
) -> dict[str, Any]:
    return _attribute(evidence, field_key, source_rule, parts, league_player_rows=league_player_rows)


def _tendency(
    evidence: Any,
    field_key: str,
    source_rule: str,
    parts: tuple[tuple[str, float], ...],
    *,
    league_player_rows: Any = (),
    range_path: str | None = None,
    range_points: tuple[tuple[float, ...], ...] = (),
) -> dict[str, Any]:
    if range_path is not None and range_points:
        value = _value_from_stat_range(evidence, range_path, range_points, 0)
    else:
        score = _score_from_parts(evidence, parts, league_player_rows)
        value = int(round(score * 100))
    return {
        "value": value,
        "source_rule": source_rule,
        "evidence_keys": tuple(path.removeprefix("!") for path, _weight in parts),
    }


def _tendency_curve(
    evidence: Any,
    field_key: str,
    source_rule: str,
    parts: tuple[tuple[str, float], ...],
    *,
    league_player_rows: Any = (),
) -> dict[str, Any]:
    return _tendency(evidence, field_key, source_rule, parts, league_player_rows=league_player_rows)


def _fixed(field_key: str, value: int | str, evidence_keys: tuple[str, ...], source_rule: str) -> dict[str, Any]:
    return {"value": value, "source_rule": source_rule, "evidence_keys": tuple(evidence_keys)}


def _rule_value(result: dict[str, Any]) -> RuleValue:
    return RuleValue(
        value=result["value"],
        source_rule=str(result["source_rule"]),
        evidence_keys=tuple(str(key) for key in result.get("evidence_keys", ())),
    )


def _profile_value(result: dict[str, Any]) -> ProfileValue:
    return ProfileValue(
        value=result["value"],
        source_rule=str(result["source_rule"]),
        evidence_keys=tuple(str(key) for key in result.get("evidence_keys", ())),
    )

