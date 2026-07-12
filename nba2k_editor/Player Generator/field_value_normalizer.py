from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class NormalizedFieldValue:
    value: int
    source_rule: str
    evidence_keys: tuple[str, ...]


_TEAM_PER100_TOTAL_FEATURES: dict[str, str] = {
    "pts_per100": "team_points",
    "fga_per100": "team_fga",
    "x3pa_per100": "team_3pa",
    "fta_per100": "team_fta",
    "ast_per100": "team_ast",
    "orb_per100": "team_orb",
    "drb_per100": "team_drb",
    "stl_per100": "team_stl",
    "blk_per100": "team_blk",
    "tov_per100": "team_tov",
    "pf_per100": "team_pf",
}

_EPSILON = 1.0e-9
_ATTRIBUTE_LOWER_IS_BETTER_FEATURES: frozenset[str] = frozenset({
    "tov_percent",
    "tov_per100",
    "pf_per100",
})


def normalize_field_value(
    *,
    field_key: str,
    value: float | int,
    initial_match_2k_features: dict[str, float | None],
    initial_match_master_features: dict[str, float | None],
    domain_master_feature_rows: Iterable[dict[str, float | None]],
    feature_names: Iterable[str],
    source_rule: str,
    evidence_keys: Iterable[str],
    league_feature_baselines: dict[str, float] | None = None,
) -> NormalizedFieldValue:
    """Adjust a neighbor-selected 2K field by its match's 2K-vs-master stat deviation.

    Attributes compare the initial match's 2K stat features to that same player's
    master stat features after league normalization. Tendencies compare the same
    pair after team-context normalization. The incoming value remains the exact
    2K attribute/tendency value selected by the neighbor model; this only moves
    that value by the same-stat bounded percent difference between the matched player's 2K stat output
    and that same player's master stat value.
    """

    section = _section(field_key)
    rounded_value = int(round(float(value)))
    if section not in {"Attributes", "Tendencies"}:
        return NormalizedFieldValue(value=rounded_value, source_rule=source_rule, evidence_keys=tuple(evidence_keys))

    features = tuple(str(feature) for feature in feature_names if str(feature).strip())
    if section == "Attributes":
        baselines = league_feature_baselines if league_feature_baselines is not None else _league_feature_baselines(domain_master_feature_rows, features)
    else:
        baselines = {}
    deltas: list[float] = []
    used_features: list[str] = []
    unit_aligned_features: list[str] = []
    inverse_features: list[str] = []
    for feature in features:
        two_k_value, master_value, unit_aligned = _normalized_feature_pair(
            section,
            feature,
            initial_match_2k_features,
            initial_match_master_features,
            baselines,
        )
        if two_k_value is None or master_value is None or not _finite(two_k_value) or not _finite(master_value):
            continue
        denominator = max(abs(two_k_value), abs(master_value))
        if denominator <= _EPSILON:
            continue
        delta = (master_value - two_k_value) / denominator
        if section == "Attributes" and _lower_is_better_feature(feature):
            delta *= -1.0
            inverse_features.append(feature)
        deltas.append(delta)
        used_features.append(feature)
        if unit_aligned:
            unit_aligned_features.append(feature)

    if not deltas:
        return NormalizedFieldValue(value=_clamp_field_value(section, rounded_value), source_rule=source_rule, evidence_keys=tuple(evidence_keys))

    percent_delta = mean(deltas)
    adjusted = _clamp_field_value(section, int(round(float(value) * (1.0 + percent_delta))))
    return NormalizedFieldValue(
        value=adjusted,
        source_rule=f"{source_rule}_match_deviation_adjusted",
        evidence_keys=(
            *tuple(evidence_keys),
            f"normalization={'league' if section == 'Attributes' else 'team'}",
            f"match_2k_to_master_percent_delta={percent_delta:.6f}",
            "normalized_features=" + ",".join(used_features),
            *(
                ("unit_aligned_features=" + ",".join(unit_aligned_features),)
                if unit_aligned_features
                else ()
            ),
            *(
                ("inverse_delta_features=" + ",".join(inverse_features),)
                if inverse_features
                else ()
            ),
        ),
    )


def _league_feature_baselines(rows: Iterable[dict[str, float | None]], features: tuple[str, ...]) -> dict[str, float]:
    values: dict[str, list[float]] = {feature: [] for feature in features}
    for row in rows:
        for feature in features:
            value = _float(row.get(feature))
            if value is not None and _finite(value) and abs(value) > _EPSILON:
                values[feature].append(value)
    return {feature: mean(feature_values) for feature, feature_values in values.items() if feature_values and abs(mean(feature_values)) > _EPSILON}


def build_league_feature_baselines(rows: Iterable[dict[str, float | None]], features: Iterable[str]) -> dict[str, float]:
    return _league_feature_baselines(rows, tuple(str(feature) for feature in features if str(feature).strip()))


def _normalized_feature_pair(
    section: str,
    feature: str,
    two_k_row: dict[str, float | None],
    master_row: dict[str, float | None],
    league_baselines: dict[str, float],
) -> tuple[float | None, float | None, bool]:
    if section == "Attributes":
        two_k_value = _float(two_k_row.get(feature))
        master_value = _float(master_row.get(feature))
        two_k_value, master_value, unit_aligned = _align_percent_units(feature, two_k_value, master_value)
        baseline = league_baselines.get(feature)
        if baseline not in (None, 0.0):
            two_k_value = None if two_k_value is None else two_k_value / baseline
            master_value = None if master_value is None else master_value / baseline
        return two_k_value, master_value, unit_aligned

    two_k_value = _team_normalized_feature_value(feature, two_k_row)
    master_value = _team_normalized_feature_value(feature, master_row)
    two_k_value, master_value, unit_aligned = _align_percent_units(feature, two_k_value, master_value)
    return two_k_value, master_value, unit_aligned


def _team_normalized_feature_value(feature: str, row: dict[str, float | None]) -> float | None:
    value = _float(row.get(feature))
    if value is None:
        return None
    team_rate = _team_per100_rate(row, _TEAM_PER100_TOTAL_FEATURES.get(feature))
    return value if team_rate in (None, 0.0) else value / team_rate


def _align_percent_units(feature: str, left: float | None, right: float | None) -> tuple[float | None, float | None, bool]:
    if left is None or right is None or not _percent_point_feature(feature):
        return left, right, False
    left_abs = abs(left)
    right_abs = abs(right)
    if left_abs <= 1.0 < right_abs <= 100.0:
        return left * 100.0, right, True
    if right_abs <= 1.0 < left_abs <= 100.0:
        return left, right * 100.0, True
    return left, right, False


def _percent_point_feature(feature: str) -> bool:
    key = str(feature).lower()
    if key in {"fg_pct", "x3p_pct", "e_fg_percent", "ft_pct", "ts_percent", "x3p_ar", "f_tr"}:
        return False
    return key.endswith("_percent") or key.startswith("percent_")


def _lower_is_better_feature(feature: str) -> bool:
    return str(feature).lower() in _ATTRIBUTE_LOWER_IS_BETTER_FEATURES


def _team_per100_rate(row: dict[str, float | None], total_feature: str | None) -> float | None:
    if not total_feature:
        return None
    total = _float(row.get(total_feature))
    possessions = _float(row.get("team_poss"))
    if total is None or possessions in (None, 0.0):
        return None
    return total * 100.0 / possessions


def _section(field_key: object) -> str:
    return str(field_key or "").split("/", 1)[0].strip()


def _clamp_field_value(section: str, value: int) -> int:
    if section == "Attributes":
        return max(25, min(99, value))
    if section == "Tendencies":
        return max(0, min(100, value))
    return value


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


__all__ = ["NormalizedFieldValue", "build_league_feature_baselines", "normalize_field_value"]
