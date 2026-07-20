from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from player_generation_evaluation import DEFAULT_SEED, build_package_grouped_folds
from player_generation_model_training import PLAYER_MASTER_FEATURES, load_attribute_spike_data
from player_generation_training_data import load_pool_analysis_data, sha256_file

GENERATOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = GENERATOR_DIR.parents[1]
for import_path in (REPO_ROOT, GENERATOR_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TARGET_FIELDS: tuple[str, ...] = (
    "Attributes/3POINT",
    "Attributes/CLOSESHOT",
    "Attributes/PERIMETERDEFENSE",
    "Attributes/PASSACCURACY",
)
TARGET_INPUT_FIELDS: tuple[str, ...] = (
    "Offense / 3pt Shot",
    "Offense / Close Shot",
    "Defense / Perimeter Defense",
    "Offense / Pass Accuracy",
)
def _ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _number(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _target_values(pool_path: Path) -> dict[tuple[str, int], dict[str, float]]:
    with _ro(pool_path) as con:
        rows = con.execute(
            "SELECT run_id,player_index,input_field,value FROM candidate_fields WHERE field_type='Attribute' AND input_field IN (?,?,?,?)",
            TARGET_INPUT_FIELDS,
        )
        values: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
        for row in rows:
            value = _number(row["value"])
            if value is not None:
                field = dict(zip(TARGET_INPUT_FIELDS, TARGET_FIELDS))[str(row["input_field"])]
                values[(str(row["run_id"]), int(row["player_index"]))][field] = value
    return values


def _training_neighbor_model(pool_path: Path, training_keys: set[tuple[str, int]]):
    import stat_neighbor_framework as snf
    field_map = snf._field_key_map()
    requested = set(TARGET_FIELDS)
    fields_by_candidate: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    with _ro(pool_path) as con:
        rows = con.execute(
            "SELECT run_id,player_index,position,field_type,input_field,value FROM candidate_fields WHERE field_type='Attribute' AND input_field IN (?,?,?,?)",
            TARGET_INPUT_FIELDS,
        )
        for row in rows:
            key = (str(row["run_id"]), int(row["player_index"]))
            if key not in training_keys:
                continue
            field_key = field_map.get((str(row["field_type"]), str(row["input_field"])))
            value = snf._float(row["value"])
            if field_key in requested and value is not None:
                fields_by_candidate[(key[0], str(key[1]), str(row["position"]).strip().upper())][field_key] = value
        rows = con.execute("SELECT * FROM candidate_pool")
        by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw_row in rows:
            row = dict(raw_row)
            pos = str(row["position"] or "").strip().upper()
            key = (str(row["run_id"]), str(row["player_index"]), pos)
            fields = fields_by_candidate.get(key, {})
            if not fields:
                continue
            candidate = {
                "run_id": key[0], "player_index": key[1], "player_label": str(row["player_label"] or ""),
                "master_player_id": str(row["master_player_id"] or ""), "position": pos,
                "features": {feature: snf._float(row[feature]) for feature in (*snf.FEATURES, *snf.BODY_FEATURES)},
                "master_features": {feature: snf._float(row.get(f"master_{feature}", row.get(feature))) for feature in (*snf.FEATURES, *snf.BODY_FEATURES)},
                "sim_features": {feature: snf._float(row.get(f"sim_{feature}", row.get(feature))) for feature in (*snf.FEATURES, *snf.BODY_FEATURES)},
                "fields": fields,
            }
            by_position[pos].append(candidate)
    candidates = {pos: tuple(rows) for pos, rows in by_position.items()}
    return snf.StatNeighborModel(path=pool_path, candidates_by_position=candidates, scales_by_position=snf._scale_by_position(candidates))


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float | int]:
    a = np.asarray(actual, dtype=float); p = np.asarray(predicted, dtype=float)
    e = np.abs(a - p)
    return {"count": int(len(a)), "mae": float(e.mean()), "p90_absolute_error": float(np.percentile(e, 90)), "within_5_rate": float((e <= 5).mean())}


def run_current_comparison(output_dir: Path | str, *, pool_path: Path | str | None = None, source_path: Path | str | None = None) -> dict[str, Any]:
    import player_rules
    from stat_neighbor_framework import select_positions_from_evidence

    pool = Path(pool_path) if pool_path else Path(__file__).resolve().parent / "NBA Player Data/player_generation_pool/player_generation_pool.sqlite"
    source = Path(source_path) if source_path else Path(__file__).resolve().parent / "NBA Player Data/NBA_DATA_Master.sqlite"
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    data = load_pool_analysis_data(pool)
    spike_data = load_attribute_spike_data(pool, source_path=source)
    alignment = spike_data.runtime_alignment
    folds = build_package_grouped_folds(data, n_folds=5)
    fold_by_key = {key: int(folds[i]) for i, key in enumerate(data.package_keys)}
    complete_training_keys = {
        key
        for index, key in enumerate(spike_data.package_keys)
        if bool(np.isfinite(spike_data.feature_values[index]).all())
    }
    # Learned/current shadow scoring can only use complete learned-feature rows.
    # Restrict the expensive current-rule reconstruction to that exact contract.
    matches = {
        key: match
        for key, match in alignment.source_matches.items()
        if key in complete_training_keys
    }
    targets = _target_values(pool)
    pool_training_features = {
        key: spike_data.feature_values[index]
        for index, key in enumerate(spike_data.package_keys)
    }
    rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    current_cache: dict[tuple[int, int, str, str, str], dict[str, float]] = {}
    runtime_feature_cache: dict[tuple[int, int, str, str, str], np.ndarray] = {}
    runtime_metadata_cache: dict[tuple[int, int, str, str, str], dict[str, Any]] = {}
    runtime_feature_mismatch_rows: list[dict[str, Any]] = []
    raw_pool_feature_mismatch_rows: list[dict[str, Any]] = []
    parity_recorded: set[tuple[str, int]] = set()
    runtime_feature_parity_by_key: dict[tuple[str, int], bool] = {}
    multi_team_context_package_keys: set[tuple[str, int]] = set()
    parity_counts = {
        column: {"exact": 0, "mismatch": 0, "training_missing": 0, "runtime_missing": 0, "both_missing": 0}
        for column in PLAYER_MASTER_FEATURES
    }
    complete_training_feature_package_count = 0
    complete_training_runtime_exact_package_count = 0
    complete_training_runtime_mismatch_package_count = 0
    complete_non_multi_training_package_count = 0
    complete_non_multi_runtime_exact_package_count = 0
    for fold in range(5):
        validation_keys = {key for key, value in fold_by_key.items() if value == fold}
        training_keys = set(fold_by_key) - validation_keys
        neighbor_model = _training_neighbor_model(pool, training_keys)
        previous_loader = player_rules.load_latest_stat_neighbor_model
        player_rules.load_latest_stat_neighbor_model = lambda model=neighbor_model: model
        try:
            for key, match in matches.items():
                if key not in validation_keys:
                    continue
                cache_key = (fold, match.season, match.player_id, match.team, match.position)
                if cache_key not in current_cache:
                    evidence = alignment.evidence_by_package.get(key)
                    if evidence is None:
                        continue
                    positions = select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
                    result = player_rules.derive_player_rule_values(
                        evidence,
                        positions=positions,
                        league_player_rows=alignment.comparison_rows_by_season[match.season],
                        active_field_keys=set(TARGET_FIELDS),
                    )
                    current_cache[cache_key] = {
                        field: float(result.values[field].value)
                        for field in TARGET_FIELDS if field in result.values and _number(result.values[field].value) is not None
                    }
                    runtime_feature_cache[cache_key] = alignment.runtime_vectors[key]
                    runtime_metadata_cache[cache_key] = {
                        "source_season": match.season,
                        "requested_team": match.team,
                        "evidence_team": str(evidence.team),
                        "multi_team_context": bool(evidence.season_info.get("multi_team_stat_shares")),
                    }
                if key not in parity_recorded:
                    parity_recorded.add(key)
                    training_vector = pool_training_features[key]
                    runtime_vector = runtime_feature_cache[cache_key]
                    raw_pool_vector = alignment.raw_vectors[key]
                    training_complete = bool(np.isfinite(training_vector).all())
                    runtime_complete = bool(np.isfinite(runtime_vector).all())
                    exact_complete = training_complete and runtime_complete and bool(
                        np.allclose(training_vector, runtime_vector, rtol=0.0, atol=1e-9)
                    )
                    runtime_feature_parity_by_key[key] = exact_complete
                    is_multi_team_context = bool(runtime_metadata_cache[cache_key]["multi_team_context"])
                    if is_multi_team_context:
                        multi_team_context_package_keys.add(key)
                    if training_complete:
                        complete_training_feature_package_count += 1
                        if exact_complete:
                            complete_training_runtime_exact_package_count += 1
                        else:
                            complete_training_runtime_mismatch_package_count += 1
                        if not is_multi_team_context:
                            complete_non_multi_training_package_count += 1
                            if exact_complete:
                                complete_non_multi_runtime_exact_package_count += 1
                    for index, column in enumerate(PLAYER_MASTER_FEATURES):
                        training_value = training_vector[index]
                        runtime_value = runtime_vector[index]
                        raw_pool_value = raw_pool_vector[index]
                        if (
                            np.isfinite(raw_pool_value)
                            and np.isfinite(runtime_value)
                            and not np.isclose(raw_pool_value, runtime_value, rtol=0.0, atol=1e-9)
                        ):
                            raw_pool_feature_mismatch_rows.append(
                                {
                                    "run_id": key[0],
                                    "player_index": key[1],
                                    "fold": fold,
                                    **runtime_metadata_cache[cache_key],
                                    "pool_column": column,
                                    "runtime_feature": column.removeprefix("master_"),
                                    "raw_pool_value": float(raw_pool_value),
                                    "runtime_value": float(runtime_value),
                                    "absolute_difference": abs(float(raw_pool_value) - float(runtime_value)),
                                    "alignment_action": "aggregate_multi_team_runtime_override" if is_multi_team_context else "none",
                                }
                            )
                        if not np.isfinite(training_value) and not np.isfinite(runtime_value):
                            parity_counts[column]["both_missing"] += 1
                        elif not np.isfinite(training_value):
                            parity_counts[column]["training_missing"] += 1
                        elif not np.isfinite(runtime_value):
                            parity_counts[column]["runtime_missing"] += 1
                        elif np.isclose(training_value, runtime_value, rtol=0.0, atol=1e-9):
                            parity_counts[column]["exact"] += 1
                        else:
                            parity_counts[column]["mismatch"] += 1
                            runtime_feature_mismatch_rows.append(
                                {
                                    "run_id": key[0],
                                    "player_index": key[1],
                                    "fold": fold,
                                    **runtime_metadata_cache[cache_key],
                                    "pool_column": column,
                                    "runtime_feature": column.removeprefix("master_"),
                                    "training_value": float(training_value),
                                    "runtime_value": float(runtime_value),
                                    "absolute_difference": abs(float(training_value) - float(runtime_value)),
                                }
                            )
                if key not in targets:
                    continue
                predicted = current_cache[cache_key]
                for field, actual in targets[key].items():
                    if field in predicted:
                        prediction_rows.append({"run_id": key[0], "player_index": key[1], "fold": fold, "position": match.position, "field_key": field, "actual": actual, "current": predicted[field], "runtime_feature_parity": runtime_feature_parity_by_key[key]})
        finally:
            player_rules.load_latest_stat_neighbor_model = previous_loader
    for field in TARGET_FIELDS:
        for position in ("PG", "SG", "SF", "PF", "C"):
            selected = [r for r in prediction_rows if r["field_key"] == field and r["position"] == position and r["runtime_feature_parity"]]
            if not selected:
                rows.append({"field_key": field, "position": position, "status": "unresolved_no_exact_source_match", "validation_count": 0, "current_mae": "", "baseline_mae": ""})
                continue
            actual = [float(r["actual"]) for r in selected]
            current = [float(r["current"]) for r in selected]
            baseline_values: list[float] = []
            for item in selected:
                training = [
                    float(row["actual"])
                    for row in prediction_rows
                    if row["field_key"] == field
                    and row["position"] == position
                    and row["runtime_feature_parity"]
                    and fold_by_key[(row["run_id"], int(row["player_index"]))] != int(item["fold"])
                ]
                baseline_values.append(float(np.mean(training)) if training else float(np.mean(actual)))
            cm = _metrics(actual, current); bm = _metrics(actual, baseline_values)
            rows.append({"field_key": field, "position": position, "status": "current_comparator_measured", "validation_count": len(selected), "current_mae": cm["mae"], "current_p90_absolute_error": cm["p90_absolute_error"], "baseline_mae": bm["mae"], "baseline_p90_absolute_error": bm["p90_absolute_error"]})
    with (output / "current_comparison_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (output / "current_comparison_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run_id","player_index","fold","position","field_key","actual","current","runtime_feature_parity"]); writer.writeheader(); writer.writerows(prediction_rows)
    parity_rows = [
        {"pool_column": column, "runtime_feature": column.removeprefix("master_"), **parity_counts[column]}
        for column in PLAYER_MASTER_FEATURES
    ]
    with (output / "runtime_feature_parity.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(parity_rows[0])); writer.writeheader(); writer.writerows(parity_rows)
    if runtime_feature_mismatch_rows:
        with (output / "runtime_feature_mismatches.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(runtime_feature_mismatch_rows[0])); writer.writeheader(); writer.writerows(runtime_feature_mismatch_rows)
    else:
        (output / "runtime_feature_mismatches.csv").write_text(
            "run_id,player_index,fold,source_season,requested_team,evidence_team,multi_team_context,pool_column,runtime_feature,training_value,runtime_value,absolute_difference\n",
            encoding="utf-8",
        )
    if raw_pool_feature_mismatch_rows:
        with (output / "runtime_feature_raw_pool_mismatches.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(raw_pool_feature_mismatch_rows[0]))
            writer.writeheader()
            writer.writerows(raw_pool_feature_mismatch_rows)
    else:
        (output / "runtime_feature_raw_pool_mismatches.csv").write_text(
            "run_id,player_index,fold,source_season,requested_team,evidence_team,multi_team_context,pool_column,runtime_feature,raw_pool_value,runtime_value,absolute_difference,alignment_action\n",
            encoding="utf-8",
        )
    mismatch_package_keys = {
        (str(row["run_id"]), int(row["player_index"])) for row in runtime_feature_mismatch_rows
    }
    raw_mismatch_package_keys = {
        (str(row["run_id"]), int(row["player_index"])) for row in raw_pool_feature_mismatch_rows
    }
    multi_team_raw_mismatch_package_keys = {
        (str(row["run_id"]), int(row["player_index"]))
        for row in raw_pool_feature_mismatch_rows
        if row["multi_team_context"]
    }
    team_key_mismatch_package_keys = {
        (str(row["run_id"]), int(row["player_index"]))
        for row in raw_pool_feature_mismatch_rows
        if row["requested_team"] != row["evidence_team"]
    }
    parity_status = (
        "proven_for_all_complete_exact_source_rows_under_existing_multi_team_rule"
        if complete_training_feature_package_count > 0
        and complete_training_runtime_exact_package_count == complete_training_feature_package_count
        else "unresolved"
    )
    summary = {
        "pool_sha256": data.pool_sha256,
        "pool_unchanged": sha256_file(pool) == data.pool_sha256,
        "package_count": data.package_count,
        "fold_count": 5,
        "fold_seed": DEFAULT_SEED,
        "exact_source_matches": len(alignment.source_matches),
        "comparison_complete_source_matches": len(matches),
        "unresolved_packages": data.package_count - len(alignment.source_matches),
        "context_key_mismatch_count": alignment.context_key_mismatch_count,
        "context_unresolved_count": alignment.context_unresolved_count,
        "prediction_count": len(prediction_rows),
        "runtime_parity_prediction_count": sum(bool(row["runtime_feature_parity"]) for row in prediction_rows),
        "runtime_feature_count": len(PLAYER_MASTER_FEATURES),
        "runtime_parity_package_count": len(parity_recorded),
        "multi_team_context_package_count": len(multi_team_context_package_keys),
        "multi_team_runtime_override_count": len(alignment.multi_team_package_keys),
        "complete_training_feature_package_count": complete_training_feature_package_count,
        "complete_training_runtime_exact_package_count": complete_training_runtime_exact_package_count,
        "complete_training_runtime_mismatch_package_count": complete_training_runtime_mismatch_package_count,
        "complete_non_multi_training_package_count": complete_non_multi_training_package_count,
        "complete_non_multi_runtime_exact_package_count": complete_non_multi_runtime_exact_package_count,
        "raw_pool_runtime_mismatch_cell_count": len(raw_pool_feature_mismatch_rows),
        "raw_pool_runtime_mismatch_package_count": len(raw_mismatch_package_keys),
        "multi_team_raw_pool_mismatch_package_count": len(multi_team_raw_mismatch_package_keys),
        "aligned_runtime_feature_mismatch_cell_count": len(runtime_feature_mismatch_rows),
        "aligned_runtime_feature_mismatch_package_count": len(mismatch_package_keys),
        "team_key_mismatch_package_count": len(team_key_mismatch_package_keys),
        "runtime_feature_parity": parity_status,
        "multi_team_rule": alignment.summary["rule"],
        "current_path": "formula_plus_fold_filtered_neighbor",
        "fallback_used": False,
        "status": "partial_exact_source_match_with_existing_multi_team_rule",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True, type=Path); args = parser.parse_args()
    print(json.dumps(run_current_comparison(args.output), indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
