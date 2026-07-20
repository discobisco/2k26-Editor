from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from player_generation_training_data import (
    POSITIONS,
    PoolAnalysisData,
    load_pool_analysis_data,
    sha256_file,
)

DEFAULT_FOLDS = 5
DEFAULT_SEED = "player-generation-phase-2-v1"


def _package_fold(run_id: str, player_index: int, *, n_folds: int, seed: str) -> int:
    payload = f"{seed}\0{run_id}\0{player_index}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") % n_folds


def build_package_grouped_folds(
    data: PoolAnalysisData,
    *,
    n_folds: int = DEFAULT_FOLDS,
    seed: str = DEFAULT_SEED,
) -> np.ndarray:
    """Assign each complete capture-local package to exactly one deterministic fold."""
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")
    if data.package_count == 0:
        raise ValueError("cannot fold an empty package matrix")
    folds = np.asarray(
        [
            _package_fold(
                str(run_id),
                int(player_index),
                n_folds=n_folds,
                seed=seed,
            )
            for run_id, player_index in data.package_keys
        ],
        dtype=np.int64,
    )
    if set(folds.tolist()) != set(range(n_folds)):
        raise ValueError(
            f"deterministic fold assignment did not populate every fold: {sorted(set(folds.tolist()))}"
        )
    return folds


def build_run_sensitivity_folds(data: PoolAnalysisData) -> dict[str, int]:
    """Return a deterministic leave-one-capture-out fold index for sensitivity checks."""
    run_ids = sorted({str(value) for value in data.run_ids.tolist()})
    return {run_id: index for index, run_id in enumerate(run_ids)}


def assert_zero_package_overlap(
    data: PoolAnalysisData,
    folds: np.ndarray,
) -> dict[str, Any]:
    if folds.shape != (data.package_count,):
        raise ValueError("fold array does not align with package rows")
    package_sets: dict[int, set[tuple[str, int]]] = {}
    for index, fold in enumerate(folds.tolist()):
        package_sets.setdefault(int(fold), set()).add(data.package_keys[index])
    overlap_pairs: list[dict[str, Any]] = []
    fold_numbers = sorted(package_sets)
    for left_index, left_fold in enumerate(fold_numbers):
        for right_fold in fold_numbers[left_index + 1 :]:
            overlap = sorted(package_sets[left_fold] & package_sets[right_fold])
            if overlap:
                overlap_pairs.append(
                    {
                        "left_fold": left_fold,
                        "right_fold": right_fold,
                        "packages": overlap,
                    }
                )
    if overlap_pairs:
        raise AssertionError(f"package overlap detected between folds: {overlap_pairs[:1]}")
    return {
        "fold_count": len(package_sets),
        "fold_package_counts": {
            str(fold): len(package_sets[fold]) for fold in fold_numbers
        },
        "overlap_pairs": overlap_pairs,
    }


def _finite(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values)


def _error_metrics(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float]:
    errors = predicted - actual
    mae = float(np.mean(np.abs(errors)))
    rmse = float(math.sqrt(np.mean(errors * errors)))
    bias = float(np.mean(errors))
    return mae, rmse, bias


def evaluate_constant_baseline(
    data: PoolAnalysisData,
    folds: np.ndarray,
) -> list[dict[str, Any]]:
    """Evaluate a position-specific training-fold mean for every exact field."""
    if folds.shape != (data.package_count,):
        raise ValueError("fold array does not align with package rows")
    rows: list[dict[str, Any]] = []
    for fold in sorted(set(int(value) for value in folds.tolist())):
        train_mask = folds != fold
        validation_mask = folds == fold
        for position in POSITIONS:
            position_train = train_mask & (data.positions == position)
            position_validation = validation_mask & (data.positions == position)
            for field_index, field_key in enumerate(data.field_keys):
                train_values = data.field_values[position_train, field_index]
                validation_values = data.field_values[position_validation, field_index]
                train_values = train_values[_finite(train_values)]
                validation_values = validation_values[_finite(validation_values)]
                base = {
                    "baseline": "position_train_mean",
                    "fold": fold,
                    "position": position,
                    "field_type": data.field_types[field_index],
                    "field_key": field_key,
                    "train_count": int(train_values.size),
                    "validation_count": int(validation_values.size),
                    "train_mean": None,
                    "mae": None,
                    "rmse": None,
                    "bias": None,
                    "status": "ok",
                }
                if train_values.size == 0:
                    base["status"] = "no_train_labels"
                    rows.append(base)
                    continue
                if validation_values.size == 0:
                    base["status"] = "no_validation_labels"
                    rows.append(base)
                    continue
                train_mean = float(np.mean(train_values))
                predicted = np.full(validation_values.shape, train_mean, dtype=np.float64)
                mae, rmse, bias = _error_metrics(validation_values, predicted)
                base.update(
                    {
                        "train_mean": train_mean,
                        "mae": mae,
                        "rmse": rmse,
                        "bias": bias,
                    }
                )
                rows.append(base)
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty evaluation artifact: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_prediction_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"missing prediction artifact: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _artifact_summary(predictions_path: Path) -> dict[str, Any]:
    summary_path = predictions_path.parent / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"missing prediction summary: {summary_path}")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _shadow_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    errors = np.abs(predicted - actual)
    return {
        "count": int(actual.size),
        "mae": float(np.mean(errors)),
        "median_absolute_error": float(np.median(errors)),
        "p90_absolute_error": float(np.percentile(errors, 90)),
        "exact_match_rate": float(np.mean(np.rint(predicted) == np.rint(actual))),
        "within_5_rate": float(np.mean(errors <= 5.0)),
        "within_10_rate": float(np.mean(errors <= 10.0)),
    }


def compare_shadow_predictions(
    *,
    learned_predictions_path: Path | str,
    current_predictions_path: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Compare learned/current predictions only on identical package/field/fold rows."""
    learned_path = Path(learned_predictions_path)
    current_path = Path(current_predictions_path)
    learned_summary = _artifact_summary(learned_path)
    current_summary = _artifact_summary(current_path)
    if learned_summary.get("pool_sha256") != current_summary.get("pool_sha256"):
        raise ValueError("learned and current predictions were built from different Pool signatures")
    if learned_summary.get("fold_seed") != current_summary.get("fold_seed"):
        raise ValueError("learned and current predictions use different package-fold seeds")

    def keyed(
        rows: list[dict[str, str]],
        label: str,
        *,
        require_runtime_parity: bool = False,
    ) -> dict[tuple[str, int, str, str], dict[str, str]]:
        result: dict[tuple[str, int, str, str], dict[str, str]] = {}
        for row in rows:
            if require_runtime_parity and str(row["runtime_feature_parity"]).lower() not in {"1", "true", "yes"}:
                continue
            key = (
                str(row["run_id"]),
                int(row["player_index"]),
                str(row["position"]),
                str(row["field_key"]),
            )
            if key in result:
                raise ValueError(f"duplicate {label} prediction row: {key}")
            result[key] = row
        return result

    learned_rows = _read_prediction_rows(learned_path)
    current_rows = _read_prediction_rows(current_path)
    if not current_rows or "runtime_feature_parity" not in current_rows[0]:
        raise ValueError("current prediction artifact is missing the runtime_feature_parity contract")
    learned = keyed(learned_rows, "learned")
    current = keyed(current_rows, "current", require_runtime_parity=True)
    overlap_keys = sorted(set(learned) & set(current))
    comparison_rows: list[dict[str, Any]] = []
    for key in overlap_keys:
        learned_row = learned[key]
        current_row = current[key]
        if int(learned_row["fold"]) != int(current_row["fold"]):
            raise ValueError(f"package fold mismatch for {key}")
        learned_actual = float(learned_row["actual"])
        current_actual = float(current_row["actual"])
        if not math.isclose(learned_actual, current_actual, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"held-out label mismatch for {key}")
        comparison_rows.append(
            {
                "run_id": key[0],
                "player_index": key[1],
                "fold": int(learned_row["fold"]),
                "position": key[2],
                "field_key": key[3],
                "actual": learned_actual,
                "learned": float(learned_row["ridge_final"]),
                "current": float(current_row["current"]),
                "constant_baseline": float(learned_row["constant_baseline"]),
            }
        )

    slot_rows: list[dict[str, Any]] = []
    slots = sorted({(key[3], key[2]) for key in learned})
    for field_key, position in slots:
        selected = [
            row
            for row in comparison_rows
            if row["field_key"] == field_key and row["position"] == position
        ]
        if not selected:
            slot_rows.append(
                {
                    "field_key": field_key,
                    "position": position,
                    "status": "offline_diagnostic_unavailable_no_identical_rows",
                    "validation_count": 0,
                    "learned_mae": "",
                    "learned_p90_absolute_error": "",
                    "current_mae": "",
                    "current_p90_absolute_error": "",
                    "baseline_mae": "",
                    "baseline_p90_absolute_error": "",
                    "beats_current": False,
                    "beats_constant_baseline": False,
                    "passes_both_offline_diagnostics": False,
                }
            )
            continue
        actual = np.asarray([row["actual"] for row in selected], dtype=np.float64)
        learned_values = np.asarray([row["learned"] for row in selected], dtype=np.float64)
        current_values = np.asarray([row["current"] for row in selected], dtype=np.float64)
        baseline_values = np.asarray([row["constant_baseline"] for row in selected], dtype=np.float64)
        learned_metrics = _shadow_metrics(actual, learned_values)
        current_metrics = _shadow_metrics(actual, current_values)
        baseline_metrics = _shadow_metrics(actual, baseline_values)
        beats_current = (
            learned_metrics["mae"] < current_metrics["mae"]
            and learned_metrics["p90_absolute_error"] <= current_metrics["p90_absolute_error"]
        )
        beats_baseline = (
            learned_metrics["mae"] < baseline_metrics["mae"]
            and learned_metrics["p90_absolute_error"] <= baseline_metrics["p90_absolute_error"]
        )
        slot_rows.append(
            {
                "field_key": field_key,
                "position": position,
                "status": (
                    "offline_diagnostic_learned_beats_current"
                    if beats_current
                    else "offline_diagnostic_current_mae_or_tail_is_better"
                ),
                "validation_count": int(actual.size),
                "learned_mae": learned_metrics["mae"],
                "learned_p90_absolute_error": learned_metrics["p90_absolute_error"],
                "current_mae": current_metrics["mae"],
                "current_p90_absolute_error": current_metrics["p90_absolute_error"],
                "baseline_mae": baseline_metrics["mae"],
                "baseline_p90_absolute_error": baseline_metrics["p90_absolute_error"],
                "beats_current": beats_current,
                "beats_constant_baseline": beats_baseline,
                "passes_both_offline_diagnostics": beats_current and beats_baseline,
            }
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "shadow_comparison_predictions.csv", comparison_rows)
    _write_csv(output / "shadow_comparison_slots.csv", slot_rows)
    summary = {
        "pool_sha256": learned_summary["pool_sha256"],
        "fold_seed": learned_summary["fold_seed"],
        "same_pool_signature": True,
        "same_package_folds": True,
        "learned_prediction_count": len(learned),
        "current_prediction_count": len(current),
        "current_unfiltered_prediction_count": len(current_rows),
        "runtime_parity_filter_applied": True,
        "identical_row_count": len(comparison_rows),
        "learned_only_count": len(set(learned) - set(current)),
        "current_only_count": len(set(current) - set(learned)),
        "slot_count": len(slot_rows),
        "evaluated_slot_count": sum(int(row["validation_count"]) > 0 for row in slot_rows),
        "learned_beats_current_slot_count": sum(
            bool(row["beats_current"]) for row in slot_rows
        ),
        "learned_beats_constant_baseline_slot_count": sum(
            bool(row["beats_constant_baseline"]) for row in slot_rows
        ),
        "passes_both_offline_diagnostic_slot_count": sum(
            bool(row["passes_both_offline_diagnostics"]) for row in slot_rows
        ),
        "offline_metrics_are_product_failure_gates": False,
        "simulation_evaluation_status": "not_run",
        "product_verdict": "not_evaluated",
        "production_artifact_written": False,
        "runtime_parity": "proven_for_compared_complete_rows_under_existing_multi_team_rule",
        "fallback_used": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def run_evaluation(
    *,
    pool_path: Path | str | None = None,
    output_dir: Path | str,
    n_folds: int = DEFAULT_FOLDS,
    seed: str = DEFAULT_SEED,
) -> dict[str, Any]:
    data = load_pool_analysis_data(pool_path)
    before_hash = data.pool_sha256
    folds = build_package_grouped_folds(data, n_folds=n_folds, seed=seed)
    overlap = assert_zero_package_overlap(data, folds)
    baseline_rows = evaluate_constant_baseline(data, folds)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "constant_baseline.csv", baseline_rows)
    run_sensitivity = build_run_sensitivity_folds(data)
    (output / "run_sensitivity_folds.json").write_text(
        json.dumps(run_sensitivity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "pool_path": str(data.pool_path),
        "pool_sha256": before_hash,
        "pool_unchanged": True,
        "package_count": data.package_count,
        "capture_count": len(set(data.run_ids.tolist())),
        "field_count": len(data.field_keys),
        "attribute_count": len(data.field_indices("Attribute")),
        "tendency_count": len(data.field_indices("Tendency")),
        "folds": {
            "count": n_folds,
            "seed": seed,
            "package_grouped": True,
            **overlap,
        },
        "baseline": {
            "name": "position_train_mean",
            "row_count": len(baseline_rows),
            "ok_rows": sum(row["status"] == "ok" for row in baseline_rows),
            "unresolved_rows": sum(row["status"] != "ok" for row in baseline_rows),
            "missing_predictions_are_not_scored": True,
        },
        "current_generator_comparison": {
            "status": "unresolved_in_phase_2_slice",
            "reason": "current formula/neighbor output has not yet been adapted to the same held-out package labels",
            "fallback_used": False,
        },
        "runtime_model_eligibility": {
            "status": "not_selected",
            "reason": "source lineage, runtime parity, and role-specific opportunity requirements remain under review",
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    after_hash = sha256_file(data.pool_path)
    if after_hash != before_hash:
        raise RuntimeError("Pool changed during evaluation")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Phase 2 Player Generator evaluation")
    parser.add_argument("--pool", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()
    summary = run_evaluation(
        pool_path=args.pool,
        output_dir=args.output,
        n_folds=args.folds,
        seed=args.seed,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
