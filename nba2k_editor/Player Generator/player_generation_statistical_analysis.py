from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from player_generation_training_data import (
    BASELINE_RUN_ID,
    POSITIONS,
    PoolAnalysisData,
    load_pool_analysis_data,
)

MIN_SAMPLE_DEFAULT = 30
DECISION_CONTEXT_CONTRACT: dict[str, object] = {
    "field_roles": {
        "Tendency": "context-gated probability that an applicable action is selected",
        "Attribute": "execution quality after an action is selected",
    },
    "verified_sequential_examples": [
        "called-play branch: coach selects playbook plays for a target player from that player's Play Types 1-4",
        "no-set-play ballhandler evaluates applicable pass, drive, and shoot choices",
        "pass decisions depend on pass/open-man/drive/shoot Tendencies plus teammate openness and Touches",
        "drive/ISO decisions can depend on defender quality and matchup-specific ISO Tendencies",
    ],
    "available_pool_context": [
        "capture-local team membership",
        "complete captured roster Attributes and Tendencies",
        "season aggregate player box-score totals",
        "season aggregate team totals",
        "Play Types 1-4 for editor_capture_027 onward",
        "player makes and attempts needed to separate shooting opportunity from shooting execution",
        "team aggregate shooting/rebounding fields available only after exact key-semantic verification",
    ],
    "missing_event_context": [
        "actual touches",
        "openness at decision time",
        "selected action event",
        "pass target event",
        "current ballhandler decision branch",
        "defender matchup at decision time",
    ],
    "missing_historical_context": [
        "Play Types 1-4 are absent from editor_capture_001 through editor_capture_026 and from candidate columns",
        "event-level shot quality, shot selection, and rebound opportunity are absent from all captures",
    ],
    "role_specific_rules": {
        "shooting": "FG% and 3PT% are downstream ratios; analyze makes and attempts separately and do not map either percentage directly to a shooting Attribute",
        "rebounding": "rebound Attributes are relative league/roster signals; analyze rank/percentile and opportunity, including verified team/league missed-shot environment",
    },
    "missing_context_policy": "unresolved_missing_event_context; never fabricate an aggregate proxy",
}


@dataclass(frozen=True)
class Association:
    scope: str
    position: str
    field_type: str
    field_key: str
    stat_source: str
    stat_key: str
    method: str
    n: int
    coefficient: float | None
    p_value: float | None
    q_value: float | None
    status: str

    def as_row(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "position": self.position,
            "field_type": self.field_type,
            "field_key": self.field_key,
            "stat_source": self.stat_source,
            "stat_key": self.stat_key,
            "method": self.method,
            "n": self.n,
            "coefficient": self.coefficient,
            "p_value": self.p_value,
            "q_value": self.q_value,
            "status": self.status,
        }


@dataclass(frozen=True)
class Dependence:
    scope: str
    position: str
    left_type: str
    left_field: str
    right_type: str
    right_field: str
    n: int
    coefficient: float | None
    p_value: float | None
    q_value: float | None
    status: str

    def as_row(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "position": self.position,
            "left_type": self.left_type,
            "left_field": self.left_field,
            "right_type": self.right_type,
            "right_field": self.right_field,
            "n": self.n,
            "coefficient": self.coefficient,
            "p_value": self.p_value,
            "q_value": self.q_value,
            "status": self.status,
        }


def _rank_vector(values: np.ndarray) -> np.ndarray:
    result = np.full(values.shape, np.nan, dtype=np.float64)
    finite_indices = np.flatnonzero(np.isfinite(values))
    if finite_indices.size == 0:
        return result
    finite_values = values[finite_indices]
    order = np.argsort(finite_values, kind="mergesort")
    sorted_values = finite_values[order]
    sorted_ranks = np.empty(sorted_values.size, dtype=np.float64)
    start = 0
    while start < sorted_values.size:
        stop = start + 1
        while stop < sorted_values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        sorted_ranks[start:stop] = (start + stop - 1) / 2.0 + 1.0
        start = stop
    ranks = np.empty(sorted_values.size, dtype=np.float64)
    ranks[order] = sorted_ranks
    result[finite_indices] = ranks
    return result


def _rank_matrix(values: np.ndarray) -> np.ndarray:
    ranked = np.full(values.shape, np.nan, dtype=np.float64)
    for column in range(values.shape[1]):
        ranked[:, column] = _rank_vector(values[:, column])
    return ranked


def _normal_approximation_p(coefficient: float, n: int, controls: int = 0) -> float:
    if n <= controls + 3:
        return 1.0
    bounded = min(1.0 - 1e-15, max(-1.0 + 1e-15, coefficient))
    z_value = math.atanh(bounded) * math.sqrt(max(1.0, n - controls - 3.0))
    return math.erfc(abs(z_value) / math.sqrt(2.0))


def _correlation(
    left: np.ndarray,
    right: np.ndarray,
    *,
    min_sample: int,
) -> tuple[int, float | None, float | None, str]:
    mask = np.isfinite(left) & np.isfinite(right)
    n = int(mask.sum())
    if n == 0:
        return n, None, None, "no_complete_rows"
    if n < min_sample:
        return n, None, None, "below_min_sample"
    x = left[mask]
    y = right[mask]
    x = x - float(np.mean(x))
    y = y - float(np.mean(y))
    denominator = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    if denominator == 0.0:
        return n, None, None, "constant"
    coefficient = float(np.dot(x, y) / denominator)
    coefficient = max(-1.0, min(1.0, coefficient))
    return n, coefficient, _normal_approximation_p(coefficient, n), "ok"


def _partial_correlation_minutes(
    left: np.ndarray,
    right: np.ndarray,
    minutes: np.ndarray,
    *,
    min_sample: int,
) -> tuple[int, float | None, float | None, str]:
    mask = np.isfinite(left) & np.isfinite(right) & np.isfinite(minutes)
    n = int(mask.sum())
    if n == 0:
        return n, None, None, "no_complete_rows"
    if n < min_sample:
        return n, None, None, "below_min_sample"
    x = left[mask]
    y = right[mask]
    z = minutes[mask]
    design = np.column_stack((np.ones(n, dtype=np.float64), z))
    x_residual = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
    y_residual = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    denominator = float(
        np.sqrt(np.dot(x_residual, x_residual) * np.dot(y_residual, y_residual))
    )
    if denominator == 0.0:
        return n, None, None, "constant_after_minutes"
    coefficient = float(np.dot(x_residual, y_residual) / denominator)
    coefficient = max(-1.0, min(1.0, coefficient))
    return n, coefficient, _normal_approximation_p(coefficient, n, controls=1), "ok"


def _with_fdr(rows: Sequence[Association]) -> list[Association]:
    valid = [
        (index, float(row.p_value))
        for index, row in enumerate(rows)
        if row.status == "ok" and row.p_value is not None
    ]
    q_values: dict[int, float] = {}
    if valid:
        ordered = sorted(valid, key=lambda item: (item[1], item[0]))
        total = len(ordered)
        running = 1.0
        for rank in range(total, 0, -1):
            index, p_value = ordered[rank - 1]
            running = min(running, p_value * total / rank)
            q_values[index] = min(1.0, running)
    return [
        Association(
            scope=row.scope,
            position=row.position,
            field_type=row.field_type,
            field_key=row.field_key,
            stat_source=row.stat_source,
            stat_key=row.stat_key,
            method=row.method,
            n=row.n,
            coefficient=row.coefficient,
            p_value=row.p_value,
            q_value=q_values.get(index),
            status=row.status,
        )
        for index, row in enumerate(rows)
    ]


def _dependencies_with_fdr(rows: Sequence[Dependence]) -> list[Dependence]:
    valid = [
        (index, float(row.p_value))
        for index, row in enumerate(rows)
        if row.status == "ok" and row.p_value is not None
    ]
    q_values: dict[int, float] = {}
    if valid:
        ordered = sorted(valid, key=lambda item: (item[1], item[0]))
        total = len(ordered)
        running = 1.0
        for rank in range(total, 0, -1):
            index, p_value = ordered[rank - 1]
            running = min(running, p_value * total / rank)
            q_values[index] = min(1.0, running)
    return [
        Dependence(
            scope=row.scope,
            position=row.position,
            left_type=row.left_type,
            left_field=row.left_field,
            right_type=row.right_type,
            right_field=row.right_field,
            n=row.n,
            coefficient=row.coefficient,
            p_value=row.p_value,
            q_value=q_values.get(index),
            status=row.status,
        )
        for index, row in enumerate(rows)
    ]


def _position_masks(base_mask: np.ndarray, positions: np.ndarray, include_all: bool) -> Iterable[tuple[str, np.ndarray]]:
    if include_all:
        yield "ALL", base_mask.copy()
    for position in POSITIONS:
        yield position, base_mask & (positions == position)


def analyze_associations(
    data: PoolAnalysisData,
    *,
    min_sample: int = MIN_SAMPLE_DEFAULT,
) -> tuple[list[Association], list[Association], list[dict[str, object]]]:
    observational_rows: list[Association] = []
    baseline_rows: list[Association] = []
    exposure_rows: list[dict[str, object]] = []

    observational_mask = ~data.baseline_mask
    for position, mask in _position_masks(observational_mask, data.positions, include_all=False):
        field_ranks = _rank_matrix(data.field_values[mask, :])
        sim_ranks = _rank_matrix(data.sim_values[mask, :])
        raw_ranks = _rank_matrix(data.raw_values[mask, :])
        minute_ranks = _rank_vector(data.minutes[mask])

        for field_index, field_key in enumerate(data.field_keys):
            field_type = data.field_types[field_index]
            field_values = field_ranks[:, field_index]
            n, coefficient, p_value, status = _correlation(
                field_values, minute_ranks, min_sample=min_sample
            )
            observational_rows.append(
                Association(
                    "observational_26",
                    position,
                    field_type,
                    field_key,
                    "raw_exposure",
                    "Minutes",
                    "marginal_position_rank_correlation",
                    n,
                    coefficient,
                    p_value,
                    None,
                    status,
                )
            )
            for stat_index, stat_key in enumerate(data.raw_stat_names):
                stat_values = raw_ranks[:, stat_index]
                n, coefficient, p_value, status = _correlation(
                    field_values, stat_values, min_sample=min_sample
                )
                observational_rows.append(
                    Association(
                        "observational_26",
                        position,
                        field_type,
                        field_key,
                        "raw_total",
                        stat_key,
                        "marginal_position_rank_correlation",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )
                n, coefficient, p_value, status = _partial_correlation_minutes(
                    field_values,
                    stat_values,
                    minute_ranks,
                    min_sample=min_sample,
                )
                observational_rows.append(
                    Association(
                        "observational_26",
                        position,
                        field_type,
                        field_key,
                        "raw_total",
                        stat_key,
                        "marginal_position_rank_partial_minutes",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )
            for stat_index, stat_key in enumerate(data.sim_stat_names):
                n, coefficient, p_value, status = _correlation(
                    field_values, sim_ranks[:, stat_index], min_sample=min_sample
                )
                observational_rows.append(
                    Association(
                        "observational_26",
                        position,
                        field_type,
                        field_key,
                        "sim_derived",
                        stat_key,
                        "marginal_position_rank_correlation",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )

        for stat_index, stat_key in enumerate(data.raw_stat_names):
            n, coefficient, p_value, status = _correlation(
                minute_ranks, raw_ranks[:, stat_index], min_sample=min_sample
            )
            exposure_rows.append(
                {
                    "scope": "observational_26",
                    "position": position,
                    "exposure": "Minutes",
                    "raw_stat": stat_key,
                    "method": "marginal_position_rank_correlation",
                    "n": n,
                    "coefficient": coefficient,
                    "p_value": p_value,
                    "status": status,
                }
            )

    tendency_indices = data.field_indices("Tendency")
    for position, mask in _position_masks(data.baseline_mask, data.positions, include_all=True):
        field_ranks = _rank_matrix(data.field_values[mask, :])
        sim_ranks = _rank_matrix(data.sim_values[mask, :])
        raw_ranks = _rank_matrix(data.raw_values[mask, :])
        minute_ranks = _rank_vector(data.minutes[mask])
        for field_index in tendency_indices:
            field_key = data.field_keys[field_index]
            field_values = field_ranks[:, field_index]
            n, coefficient, p_value, status = _correlation(
                field_values, minute_ranks, min_sample=min_sample
            )
            baseline_rows.append(
                Association(
                    "run_26_all_99_attribute_baseline",
                    position,
                    "Tendency",
                    field_key,
                    "raw_exposure",
                    "Minutes",
                    "marginal_position_rank_correlation",
                    n,
                    coefficient,
                    p_value,
                    None,
                    status,
                )
            )
            for stat_index, stat_key in enumerate(data.raw_stat_names):
                stat_values = raw_ranks[:, stat_index]
                n, coefficient, p_value, status = _correlation(
                    field_values, stat_values, min_sample=min_sample
                )
                baseline_rows.append(
                    Association(
                        "run_26_all_99_attribute_baseline",
                        position,
                        "Tendency",
                        field_key,
                        "raw_total",
                        stat_key,
                        "marginal_position_rank_correlation",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )
                n, coefficient, p_value, status = _partial_correlation_minutes(
                    field_values,
                    stat_values,
                    minute_ranks,
                    min_sample=min_sample,
                )
                baseline_rows.append(
                    Association(
                        "run_26_all_99_attribute_baseline",
                        position,
                        "Tendency",
                        field_key,
                        "raw_total",
                        stat_key,
                        "marginal_position_rank_partial_minutes",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )
            for stat_index, stat_key in enumerate(data.sim_stat_names):
                n, coefficient, p_value, status = _correlation(
                    field_values, sim_ranks[:, stat_index], min_sample=min_sample
                )
                baseline_rows.append(
                    Association(
                        "run_26_all_99_attribute_baseline",
                        position,
                        "Tendency",
                        field_key,
                        "sim_derived",
                        stat_key,
                        "marginal_position_rank_correlation",
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )

    return _with_fdr(observational_rows), _with_fdr(baseline_rows), exposure_rows


def analyze_field_dependencies(
    data: PoolAnalysisData,
    *,
    min_sample: int = MIN_SAMPLE_DEFAULT,
) -> list[Dependence]:
    rows: list[Dependence] = []
    observational_mask = ~data.baseline_mask
    for position, mask in _position_masks(observational_mask, data.positions, include_all=False):
        ranked = _rank_matrix(data.field_values[mask, :])
        for left_index in range(len(data.field_keys)):
            for right_index in range(left_index + 1, len(data.field_keys)):
                n, coefficient, p_value, status = _correlation(
                    ranked[:, left_index],
                    ranked[:, right_index],
                    min_sample=min_sample,
                )
                rows.append(
                    Dependence(
                        "observational_26",
                        position,
                        data.field_types[left_index],
                        data.field_keys[left_index],
                        data.field_types[right_index],
                        data.field_keys[right_index],
                        n,
                        coefficient,
                        p_value,
                        None,
                        status,
                    )
                )
    return _dependencies_with_fdr(rows)


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty analysis artifact: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _status_counts(rows: Sequence[Association] | Sequence[Dependence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return dict(sorted(counts.items()))


def _top_associations(rows: Sequence[Association], limit: int = 25) -> list[dict[str, object]]:
    eligible = [row for row in rows if row.status == "ok" and row.coefficient is not None]
    eligible.sort(
        key=lambda row: (
            -abs(row.coefficient if row.coefficient is not None else 0.0),
            row.position,
            row.field_key,
            row.stat_key,
            row.method,
        )
    )
    return [row.as_row() for row in eligible[:limit]]


def run_analysis(
    *,
    pool_path: Path | str | None = None,
    output_dir: Path | str,
    min_sample: int = MIN_SAMPLE_DEFAULT,
) -> dict[str, object]:
    if min_sample < 3:
        raise ValueError("min_sample must be at least 3")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = load_pool_analysis_data(pool_path)

    observational, baseline, exposure = analyze_associations(data, min_sample=min_sample)
    dependencies = analyze_field_dependencies(data, min_sample=min_sample)

    observational_rows = [row.as_row() for row in observational]
    baseline_rows = [row.as_row() for row in baseline]
    dependency_rows = [row.as_row() for row in dependencies]
    _write_csv(output / "observational_field_stat_associations.csv", observational_rows)
    _write_csv(output / "run_26_tendency_stat_baseline.csv", baseline_rows)
    _write_csv(output / "field_dependence.csv", dependency_rows)
    _write_csv(output / "minutes_raw_stat_exposure.csv", exposure)

    lineage_path = output / "candidate_pool_column_lineage.json"
    lineage_path.write_text(
        json.dumps(dict(sorted(data.column_lineage.items())), indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "decision_context_contract.json").write_text(
        json.dumps(DECISION_CONTEXT_CONTRACT, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary: dict[str, object] = {
        "pool_path": str(data.pool_path),
        "pool_sha256": data.pool_sha256,
        "package_count": data.package_count,
        "capture_count": len(set(data.run_ids.tolist())),
        "baseline_run_id": BASELINE_RUN_ID,
        "baseline_package_count": int(data.baseline_mask.sum()),
        "observational_package_count": int((~data.baseline_mask).sum()),
        "position_counts": {
            position: int(np.sum(data.positions == position)) for position in POSITIONS
        },
        "field_count": len(data.field_keys),
        "attribute_count": len(data.field_indices("Attribute")),
        "tendency_count": len(data.field_indices("Tendency")),
        "candidate_pool_column_count": len(data.column_lineage),
        "sim_stat_count": len(data.sim_stat_names),
        "sim_stats_with_any_value": int(
            sum(np.isfinite(data.sim_values[:, i]).any() for i in range(len(data.sim_stat_names)))
        ),
        "package_aligned_minutes_count": int(np.isfinite(data.minutes).sum()),
        "min_sample": min_sample,
        "p_value_method": "Fisher-z normal approximation on position-ranked values",
        "fdr_method": "Benjamini-Hochberg per artifact",
        "association_interpretation": "marginal reduced-form covariance screen; not a direct game effect",
        "decision_context_contract": DECISION_CONTEXT_CONTRACT,
        "observational_association_rows": len(observational),
        "observational_status_counts": _status_counts(observational),
        "baseline_association_rows": len(baseline),
        "baseline_status_counts": _status_counts(baseline),
        "field_dependence_rows": len(dependencies),
        "field_dependence_status_counts": _status_counts(dependencies),
        "minutes_exposure_rows": len(exposure),
        "top_observational_associations": _top_associations(observational),
        "top_run_26_tendency_associations": _top_associations(baseline),
        "baseline_protocol": {
            "starting_attributes": 99,
            "base_roster_tendencies_manually_changed": False,
            "role": "separately reported Tendency/action-frequency screen under controlled high starting execution quality",
            "not_controlled": [
                "touches",
                "action eligibility and branch ordering",
                "teammate choices and openness",
                "opponents and defender matchups",
            ],
            "pool_rows_modified": False,
        },
        "limitations": [
            "Every association in this artifact is marginal/reduced-form and does not establish causality or reproduce the game's sequential decision checks.",
            "Tendencies select context-applicable actions; Attributes determine execution quality after selection. Cross-role covariance is not a direct effect.",
            "The Pool has no event-level touches, openness, selected-action, pass-target, current-branch, or defender-matchup observations; conditional effects requiring them remain unresolved.",
            "FG% and 3PT% are downstream makes-over-attempts ratios; shooting Attribute evidence must separate attempt opportunity, shot mix, and execution.",
            "Rebound totals are opportunity-sensitive and relative to league/roster context; higher team/league FG% can shrink the missed-shot rebound pool.",
            "Run 26 does not estimate within-run starting-Attribute slopes because intended starting Attributes were fixed at 99.",

            "Attribute-by-Tendency incremental interaction tests are not included in this first executable slice.",
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only marginal Minutes-aware Attribute/Tendency screening of the Player Generation Pool."
    )
    parser.add_argument("--pool", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-sample", type=int, default=MIN_SAMPLE_DEFAULT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_analysis(
        pool_path=args.pool,
        output_dir=args.output,
        min_sample=args.min_sample,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
