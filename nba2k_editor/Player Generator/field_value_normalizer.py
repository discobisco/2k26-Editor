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
) -> NormalizedFieldValue:
    """Adjust a neighbor-selected 2K field by its match's 2K-vs-master stat deviation.

    Attributes compare the initial match's 2K stat features to that same player's
    master stat features after league normalization. Tendencies compare the same
    pair after team-context normalization. The incoming value remains the exact
    2K attribute/tendency value selected by the neighbor model; this only moves
    that value by the percent that the matched player's 2K stat output is off
    from the matched player's master stat value.
    """

    section = _section(field_key)
    rounded_value = int(round(float(value)))
    if section not in {"Attributes", "Tendencies"}:
        return NormalizedFieldValue(value=rounded_value, source_rule=source_rule, evidence_keys=tuple(evidence_keys))

    features = tuple(str(feature) for feature in feature_names if str(feature).strip())
    baselines = _league_feature_baselines(domain_master_feature_rows, features) if section == "Attributes" else {}
    deltas: list[float] = []
    used_features: list[str] = []
    for feature in features:
        two_k_value = _normalized_feature_value(section, feature, initial_match_2k_features, baselines)
        master_value = _normalized_feature_value(section, feature, initial_match_master_features, baselines)
        if two_k_value is None or master_value is None or not _finite(two_k_value) or not _finite(master_value):
            continue
        denominator = abs(two_k_value)
        if denominator <= _EPSILON:
            continue
        deltas.append((master_value - two_k_value) / denominator)
        used_features.append(feature)

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


def _normalized_feature_value(
    section: str,
    feature: str,
    row: dict[str, float | None],
    league_baselines: dict[str, float],
) -> float | None:
    value = _float(row.get(feature))
    if value is None:
        return None
    if section == "Attributes":
        baseline = league_baselines.get(feature)
        return value if baseline in (None, 0.0) else value / baseline
    team_rate = _team_per100_rate(row, _TEAM_PER100_TOTAL_FEATURES.get(feature))
    return value if team_rate in (None, 0.0) else value / team_rate


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


__all__ = ["NormalizedFieldValue", "normalize_field_value"]
