from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from player_generation_evaluation import DEFAULT_SEED, build_package_grouped_folds
from player_generation_master_bridge import (
    PLAYER_FEATURE_RUNTIME_SOURCES,
    PLAYER_MASTER_FEATURES,
    PLAYER_RUNTIME_FEATURES,
    RuntimeFeatureAlignment,
    default_source_path,
    load_runtime_feature_alignment,
    runtime_player_feature_vector,
)
from player_generation_training_data import (
    POSITIONS,
    classify_candidate_pool_columns,
    default_pool_path,
    sha256_file,
)

MODEL_FAMILY = "standardized_ridge_v1"
FOLD_SEED = DEFAULT_SEED
MIN_TRAIN_ROWS = 100
RIDGE_ALPHA = 1.0
ATTRIBUTE_MIN = 25.0
ATTRIBUTE_MAX = 99.0

# Representative Attribute spike: shooting, creation, defense, and passing.
# Direct-owned durability/stamina/free-throw fields are intentionally absent.
SPIKE_ATTRIBUTES: tuple[str, ...] = (
    "Offense / 3pt Shot",
    "Offense / Close Shot",
    "Defense / Perimeter Defense",
    "Offense / Pass Accuracy",
)


@dataclass(frozen=True)
class AttributeSpikeData:
    pool_path: Path
    pool_sha256: str
    package_keys: tuple[tuple[str, int], ...]
    positions: np.ndarray
    feature_columns: tuple[str, ...]
    feature_values: np.ndarray
    target_input_fields: tuple[str, ...]
    target_values: np.ndarray
    column_lineage: dict[str, str]
    runtime_alignment: RuntimeFeatureAlignment

    @property
    def package_count(self) -> int:
        return len(self.package_keys)


class ModelTrainingError(RuntimeError):
    pass


def _read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing player generation pool: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _float_or_nan(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _field_key(input_field: str) -> str:
    # Candidate field keys are authored normalized names. Keep this resolver
    # local and explicit for the spike; no display-name heuristic is used.
    aliases = {
        "Offense / 3pt Shot": "Attributes/3POINT",
        "Offense / Close Shot": "Attributes/CLOSESHOT",
        "Defense / Perimeter Defense": "Attributes/PERIMETERDEFENSE",
        "Offense / Pass Accuracy": "Attributes/PASSACCURACY",
    }
    try:
        return aliases[input_field]
    except KeyError as exc:
        raise ModelTrainingError(f"spike target is not explicitly authored: {input_field}") from exc


def load_attribute_spike_data(
    pool_path: Path | str | None = None,
    *,
    source_path: Path | str | None = None,
    target_input_fields: Sequence[str] = SPIKE_ATTRIBUTES,
) -> AttributeSpikeData:
    path = Path(pool_path) if pool_path is not None else default_pool_path()
    before_hash = sha256_file(path)
    with _read_only_connection(path) as connection:
        table_info = list(connection.execute("PRAGMA table_info(candidate_pool)"))
        columns = tuple(str(row[1]) for row in table_info)
        lineage = classify_candidate_pool_columns(columns)
        feature_columns = tuple(str(column) for column in PLAYER_MASTER_FEATURES)
        missing = sorted(set(feature_columns) - set(columns))
        if missing:
            raise ModelTrainingError(f"missing source feature columns: {missing}")
        invalid = [column for column in feature_columns if lineage.get(column) != "source_feature_candidate_not_analysis_outcome"]
        if invalid:
            raise ModelTrainingError(f"feature lineage is not source-only: {invalid}")

        quoted_features = ", ".join(f'"{column}"' for column in feature_columns)
        rows = list(connection.execute(
            f"SELECT run_id, player_index, position, {quoted_features} FROM candidate_pool ORDER BY run_id, player_index"
        ))
        package_keys = tuple((str(row["run_id"]), int(row["player_index"])) for row in rows)
        if len(package_keys) != len(set(package_keys)):
            raise ModelTrainingError("candidate_pool contains duplicate package keys")
        positions = np.asarray([str(row["position"]).strip().upper() for row in rows], dtype=object)
        invalid_positions = sorted(set(positions.tolist()) - set(POSITIONS))
        if invalid_positions:
            raise ModelTrainingError(f"unsupported positions: {invalid_positions}")
        feature_values = np.asarray(
            [[_float_or_nan(row[column]) for column in feature_columns] for row in rows],
            dtype=np.float64,
        )

        target_fields = tuple(str(field) for field in target_input_fields)
        target_values = np.full((len(rows), len(target_fields)), np.nan, dtype=np.float64)
        package_index = {key: index for index, key in enumerate(package_keys)}
        placeholders = ", ".join("?" for _ in target_fields)
        target_rows = connection.execute(
            f"""
            SELECT run_id, player_index, field_type, input_field, value
            FROM candidate_fields
            WHERE field_type = 'Attribute' AND input_field IN ({placeholders})
            ORDER BY run_id, player_index, input_field
            """,
            target_fields,
        )
        target_index = {field: index for index, field in enumerate(target_fields)}
        for row in target_rows:
            key = (str(row["run_id"]), int(row["player_index"]))
            row_index = package_index.get(key)
            field_index = target_index.get(str(row["input_field"]))
            if row_index is None or field_index is None:
                continue
            target_values[row_index, field_index] = _float_or_nan(row["value"])

    alignment = load_runtime_feature_alignment(path, source_path or default_source_path())
    for key in alignment.multi_team_package_keys:
        row_index = package_index.get(key)
        if row_index is not None:
            feature_values[row_index] = alignment.aligned_vectors[key]

    after_hash = sha256_file(path)
    if before_hash != after_hash:
        raise ModelTrainingError("Pool changed during read-only model-matrix load")
    return AttributeSpikeData(
        pool_path=path,
        pool_sha256=before_hash,
        package_keys=package_keys,
        positions=positions,
        feature_columns=feature_columns,
        feature_values=feature_values,
        target_input_fields=target_fields,
        target_values=target_values,
        column_lineage={column: lineage[column] for column in feature_columns},
        runtime_alignment=alignment,
    )


def _complete_rows(features: np.ndarray, target: np.ndarray) -> np.ndarray:
    return np.isfinite(target) & np.isfinite(features).all(axis=1)


def _fit_ridge(features: np.ndarray, target: np.ndarray, alpha: float = RIDGE_ALPHA) -> dict[str, np.ndarray]:
    if len(features) == 0:
        raise ModelTrainingError("cannot fit ridge model with zero rows")
    mean = np.mean(features, axis=0)
    scale = np.std(features, axis=0)
    scale = np.where(scale > 0.0, scale, 1.0)
    normalized = (features - mean) / scale
    design = np.column_stack((np.ones(len(normalized)), normalized))
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    gram = design.T @ design + alpha * penalty
    rhs = design.T @ target
    try:
        coefficients = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError as exc:
        raise ModelTrainingError(f"ridge solve failed: {exc}") from exc
    return {"feature_mean": mean, "feature_scale": scale, "coefficients": coefficients}


def _predict(model: dict[str, np.ndarray], features: np.ndarray) -> np.ndarray:
    normalized = (features - model["feature_mean"]) / model["feature_scale"]
    design = np.column_stack((np.ones(len(normalized)), normalized))
    return design @ model["coefficients"]


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    errors = np.abs(predicted - actual)
    return {
        "count": int(len(actual)),
        "mae": float(np.mean(errors)),
        "median_absolute_error": float(np.median(errors)),
        "p90_absolute_error": float(np.percentile(errors, 90)),
        "exact_match_rate": float(np.mean(np.rint(predicted) == np.rint(actual))),
        "within_5_rate": float(np.mean(errors <= 5.0)),
        "within_10_rate": float(np.mean(errors <= 10.0)),
        "prediction_min": float(np.min(predicted)),
        "prediction_max": float(np.max(predicted)),
    }


def _package_folds(data: AttributeSpikeData, n_folds: int = 5) -> np.ndarray:
    return build_package_grouped_folds(
        data,  # type: ignore[arg-type] - the shared fold owner needs package_count/package_keys only.
        n_folds=n_folds,
        seed=FOLD_SEED,
    )


def _csv_write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    values = list(rows)
    if not values:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(values[0].keys()))
        writer.writeheader()
        writer.writerows(values)


def run_attribute_spike(
    output_dir: Path | str,
    *,
    pool_path: Path | str | None = None,
    source_path: Path | str | None = None,
    n_folds: int = 5,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = load_attribute_spike_data(pool_path, source_path=source_path)
    folds = _package_folds(data, n_folds=n_folds)
    if not np.array_equal(folds, _package_folds(data, n_folds=n_folds)):
        raise ModelTrainingError("fold assignment is not deterministic")

    model_family = {
        "name": MODEL_FAMILY,
        "algorithm": "standardized ridge regression",
        "dependency": "NumPy only",
        "alpha": RIDGE_ALPHA,
        "deterministic": True,
        "missing_data_policy": "complete-feature rows only; no imputation; missing labels are not scored",
        "feature_order": list(data.feature_columns),
        "feature_lineage": data.column_lineage,
        "feature_runtime_sources": PLAYER_FEATURE_RUNTIME_SOURCES,
        "team_features_excluded": True,
        "sim_features_excluded": True,
        "runtime_parity": "proven for all complete training rows after applying the existing aggregate multi-team player rule in the read-only derivative view",
        "multi_team_rule": data.runtime_alignment.summary["rule"],
    }
    (output / "model_family_decision.json").write_text(json.dumps(model_family, indent=2, sort_keys=True), encoding="utf-8")

    result_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for target_index, target_field in enumerate(data.target_input_fields):
        target_key = _field_key(target_field)
        target = data.target_values[:, target_index]
        for position in POSITIONS:
            fold_predictions: list[tuple[int, str, float, float, float]] = []
            fold_metrics: list[dict[str, Any]] = []
            for fold in range(n_folds):
                train_mask = (data.positions == position) & (folds != fold)
                validation_mask = (data.positions == position) & (folds == fold)
                train_complete = train_mask & _complete_rows(data.feature_values, target)
                validation_complete = validation_mask & _complete_rows(data.feature_values, target)
                train_count = int(train_complete.sum())
                validation_count = int(validation_complete.sum())
                if train_count < MIN_TRAIN_ROWS or validation_count == 0:
                    fold_rows.append({
                        "field_key": target_key,
                        "position": position,
                        "fold": fold,
                        "train_count": train_count,
                        "validation_count": validation_count,
                        "status": "insufficient_train_or_validation_rows",
                    })
                    continue
                model = _fit_ridge(data.feature_values[train_complete], target[train_complete])
                ridge_raw = _predict(model, data.feature_values[validation_complete])
                ridge_final = np.rint(np.clip(ridge_raw, ATTRIBUTE_MIN, ATTRIBUTE_MAX))
                baseline_value = float(np.mean(target[train_complete]))
                baseline = np.full(validation_count, baseline_value, dtype=np.float64)
                actual = target[validation_complete]
                ridge_raw_metrics = _metrics(actual, ridge_raw)
                ridge_final_metrics = _metrics(actual, ridge_final)
                baseline_metrics = _metrics(actual, baseline)
                fold_metrics.append({
                    "fold": fold,
                    "train_count": train_count,
                    "validation_count": validation_count,
                    "ridge_raw": ridge_raw_metrics,
                    "ridge": ridge_final_metrics,
                    "constant_baseline": baseline_metrics,
                })
                indices = np.flatnonzero(validation_complete)
                for local_index, row_index in enumerate(indices):
                    fold_predictions.append((
                        fold,
                        str(data.package_keys[row_index][0]),
                        float(actual[local_index]),
                        float(ridge_raw[local_index]),
                        float(baseline[local_index]),
                    ))
                    prediction_rows.append({
                        "field_key": target_key,
                        "position": position,
                        "fold": fold,
                        "run_id": data.package_keys[row_index][0],
                        "player_index": data.package_keys[row_index][1],
                        "actual": float(actual[local_index]),
                        "ridge_raw": float(ridge_raw[local_index]),
                        "ridge_final": float(ridge_final[local_index]),
                        "constant_baseline": float(baseline[local_index]),
                    })
            if fold_predictions:
                actual = np.asarray([row[2] for row in fold_predictions], dtype=np.float64)
                ridge_raw = np.asarray([row[3] for row in fold_predictions], dtype=np.float64)
                ridge_final = np.rint(np.clip(ridge_raw, ATTRIBUTE_MIN, ATTRIBUTE_MAX))
                baseline = np.asarray([row[4] for row in fold_predictions], dtype=np.float64)
                ridge_raw_metrics = _metrics(actual, ridge_raw)
                ridge_metrics = _metrics(actual, ridge_final)
                baseline_metrics = _metrics(actual, baseline)
                beats_constant_baseline_diagnostic = (
                    ridge_metrics["mae"] < baseline_metrics["mae"]
                    and ridge_metrics["p90_absolute_error"] <= baseline_metrics["p90_absolute_error"]
                )
                run_mae = []
                for run_id in sorted({row[1] for row in fold_predictions}):
                    run_actual = np.asarray([row[2] for row in fold_predictions if row[1] == run_id], dtype=np.float64)
                    run_ridge_raw = np.asarray([row[3] for row in fold_predictions if row[1] == run_id], dtype=np.float64)
                    run_ridge = np.rint(np.clip(run_ridge_raw, ATTRIBUTE_MIN, ATTRIBUTE_MAX))
                    run_mae.append(float(np.mean(np.abs(run_ridge - run_actual))) )
                result_rows.append({
                    "field_key": target_key,
                    "position": position,
                    "status": "offline_diagnostic_complete",
                    "feature_count": len(data.feature_columns),
                    "validation_count": len(fold_predictions),
                    "fold_count": len(fold_metrics),
                    "ridge_mae": ridge_metrics["mae"],
                    "ridge_raw_mae": ridge_raw_metrics["mae"],
                    "ridge_median_absolute_error": ridge_metrics["median_absolute_error"],
                    "ridge_p90_absolute_error": ridge_metrics["p90_absolute_error"],
                    "baseline_mae": baseline_metrics["mae"],
                    "baseline_p90_absolute_error": baseline_metrics["p90_absolute_error"],
                    "beats_constant_baseline_diagnostic": beats_constant_baseline_diagnostic,
                    "ridge_within_5_rate": ridge_metrics["within_5_rate"],
                    "ridge_within_10_rate": ridge_metrics["within_10_rate"],
                    "ridge_prediction_min": ridge_metrics["prediction_min"],
                    "ridge_prediction_max": ridge_metrics["prediction_max"],
                    "run_holdout_mae_min": min(run_mae),
                    "run_holdout_mae_max": max(run_mae),
                    "current_comparator": "reported_separately_as_offline_diagnostic",
                })
            else:
                result_rows.append({
                    "field_key": target_key,
                    "position": position,
                    "status": "insufficient_complete_training_or_validation_rows",
                    "feature_count": len(data.feature_columns),
                    "validation_count": 0,
                    "fold_count": 0,
                    "ridge_mae": "",
                    "ridge_raw_mae": "",
                    "ridge_median_absolute_error": "",
                    "ridge_p90_absolute_error": "",
                    "baseline_mae": "",
                    "baseline_p90_absolute_error": "",
                    "beats_constant_baseline_diagnostic": "",
                    "ridge_within_5_rate": "",
                    "ridge_within_10_rate": "",
                    "ridge_prediction_min": "",
                    "ridge_prediction_max": "",
                    "run_holdout_mae_min": "",
                    "run_holdout_mae_max": "",
                    "current_comparator": "not_evaluated_without_complete_training_rows",
                })
            for fold_metric in fold_metrics:
                fold_rows.append({
                    "field_key": target_key,
                    "position": position,
                    "fold": fold_metric["fold"],
                    "train_count": fold_metric["train_count"],
                    "validation_count": fold_metric["validation_count"],
                    "ridge_mae": fold_metric["ridge"]["mae"],
                    "ridge_raw_mae": fold_metric["ridge_raw"]["mae"],
                    "ridge_p90_absolute_error": fold_metric["ridge"]["p90_absolute_error"],
                    "baseline_mae": fold_metric["constant_baseline"]["mae"],
                    "baseline_p90_absolute_error": fold_metric["constant_baseline"]["p90_absolute_error"],
                    "status": "ok",
                })

    _csv_write(output / "attribute_spike_results.csv", result_rows)
    _csv_write(output / "attribute_spike_fold_results.csv", fold_rows)
    _csv_write(output / "attribute_spike_predictions.csv", prediction_rows)
    summary = {
        "model_family": MODEL_FAMILY,
        "pool_path": str(data.pool_path),
        "pool_sha256": data.pool_sha256,
        "pool_unchanged": sha256_file(data.pool_path) == data.pool_sha256,
        "package_count": data.package_count,
        "fold_count": n_folds,
        "fold_seed": FOLD_SEED,
        "target_count": len(data.target_input_fields),
        "target_fields": [_field_key(field) for field in data.target_input_fields],
        "feature_count": len(data.feature_columns),
        "feature_columns": list(data.feature_columns),
        "feature_policy": "player-level master source features only; team/live overlays excluded; sim and identity columns excluded",
        "runtime_feature_alignment": data.runtime_alignment.summary,
        "complete_feature_row_count": int(np.isfinite(data.feature_values).all(axis=1).sum()),
        "result_row_count": len(result_rows),
        "evaluated_row_count": sum(1 for row in result_rows if row["validation_count"]),
        "status_counts": {
            "offline_diagnostic_complete": sum(
                1 for row in result_rows if row["status"] == "offline_diagnostic_complete"
            ),
            "insufficient_complete_training_or_validation_rows": sum(
                1 for row in result_rows if row["status"] == "insufficient_complete_training_or_validation_rows"
            ),
        },
        "offline_diagnostic_only": True,
        "simulation_evaluation_status": "not_run",
        "product_verdict": "not_evaluated",
        "production_artifact_written": False,
        "direct_fields_excluded": ["durability", "stamina", "free_throw"],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic Phase 3 Attribute model-family spike")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pool", type=Path, default=None)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()
    summary = run_attribute_spike(args.output, pool_path=args.pool, source_path=args.source, n_folds=args.folds)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
