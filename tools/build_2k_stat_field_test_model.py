#!/usr/bin/env python3
"""Build a testable fact-first NBA2K stat -> attribute/tendency mapping model.

Inputs:
- outputs/current_active_stat_extractor_runs/STAT_BUCKETS_TO_FIELD_VALUES_FROM_4_GAME_RUNS_RELATION_CLEANED_003.csv
- outputs/current_active_stat_extractor_runs/run_001..run_004/current_active_player_{stats,attributes,tendencies}.csv

The model is intentionally standalone and artifact-first. It does not wire production
Player Generator formulas. It creates a run-scoped output folder with:
- model_knots.csv: fitted stat->field calibration knots trained on all runs
- holdout_predictions.csv: leave-one-run-out predictions for testing
- field_metrics.csv: field-level test metrics
- manifest.json / README.md
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RUNS = ("run_001", "run_002", "run_003", "run_004")
MAPPING_REL = Path("outputs/current_active_stat_extractor_runs/STAT_BUCKETS_TO_FIELD_VALUES_FROM_4_GAME_RUNS_RELATION_CLEANED_003.csv")
REVIEW_REL = Path("outputs/current_active_stat_extractor_runs/STAT_BUCKETS_TO_FIELD_VALUES_FROM_4_GAME_RUNS_RELATION_REVIEW_003.csv")
RUNS_DIR = Path("outputs/current_active_stat_extractor_runs")
OUT_PREFIX = "WORKING_STAT_TO_FIELD_TEST_MODEL_"
BASE_COLS = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}

STAT_TOTAL_COLUMN = {
    "Assists": "Assists",
    "Blocks": "Blocks",
    "Fouls": "Fouls",
    "Steals": "Steals",
    "Defensive Rebounds": "Defensive Rebounds",
    "Offensive Rebounds": "Offensive Rebounds",
    "Field Goals Attempted": "Field Goals Attempted",
    "Three Pointers Attempted": "Three Pointers Attempted",
}
RATE_COLUMNS = {
    "FG%": ("Field Goals Made", "Field Goals Attempted"),
    "FT%": ("Free Throws Made", "Free Throws Attempted"),
    "3P%": ("Three Pointers Made", "Three Pointers Attempted"),
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if math.isnan(float(v)):
            return None
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def base_stat_name(mapped_stat: str, basis: str) -> str:
    if basis == "per_36" and mapped_stat.endswith(" Per 36"):
        return mapped_stat[: -len(" Per 36")]
    if basis == "per_game" and mapped_stat.endswith(" Per Game"):
        return mapped_stat[: -len(" Per Game")]
    return mapped_stat


def feature_value(stats_row: Dict[str, str], mapped_stat: str, basis: str) -> Optional[float]:
    if basis == "rate":
        cols = RATE_COLUMNS.get(mapped_stat)
        if not cols:
            return None
        return safe_div(as_float(stats_row.get(cols[0])), as_float(stats_row.get(cols[1])))

    base = base_stat_name(mapped_stat, basis)
    col = STAT_TOTAL_COLUMN.get(base)
    if not col:
        return None
    total = as_float(stats_row.get(col))
    if basis == "total":
        return total
    if basis == "per_game":
        return safe_div(total, as_float(stats_row.get("Games Played")))
    if basis == "per_36":
        minutes = as_float(stats_row.get("Minutes"))
        if minutes is None or minutes == 0 or total is None:
            return None
        return total / minutes * 36.0
    return None


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def rmse(errors: Sequence[float]) -> Optional[float]:
    if not errors:
        return None
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def sorted_median(vals: Sequence[float]) -> float:
    return float(median(vals))


def fit_knots(points: Sequence[Tuple[float, float]], *, max_knots: int = 9, monotonic: bool = False, direction: str = "increasing") -> List[Dict[str, Any]]:
    clean = sorted((float(x), float(y)) for x, y in points if x is not None and y is not None and math.isfinite(x) and math.isfinite(y))
    if not clean:
        return []

    # Collapse exact stat-value duplicates first so repeated players/runs do not create fake knot density.
    by_x: Dict[float, List[float]] = defaultdict(list)
    for x, y in clean:
        by_x[x].append(y)
    collapsed = [(x, sorted_median(ys), len(ys)) for x, ys in sorted(by_x.items())]

    if len(collapsed) <= max_knots:
        knots = [{"x": x, "y": y, "rows": n} for x, y, n in collapsed]
    else:
        bin_size = max(1, math.ceil(len(collapsed) / max_knots))
        knots = []
        for i in range(0, len(collapsed), bin_size):
            chunk = collapsed[i : i + bin_size]
            xs = []
            ys = []
            rows = 0
            for x, y, n in chunk:
                xs.extend([x] * n)
                ys.extend([y] * n)
                rows += n
            knots.append({"x": sorted_median(xs), "y": sorted_median(ys), "rows": rows})

    # Data-first monotonic smoothing is only applied where the reviewed relation says monotonic TRUE.
    if monotonic and knots:
        if direction == "decreasing":
            running = knots[0]["y"]
            for k in knots:
                running = min(running, k["y"])
                k["y"] = running
        else:
            running = knots[0]["y"]
            for k in knots:
                running = max(running, k["y"])
                k["y"] = running

    return knots


def predict_from_knots(x: float, knots: Sequence[Dict[str, Any]]) -> Optional[float]:
    if x is None or not knots:
        return None
    if len(knots) == 1:
        return float(knots[0]["y"])
    if x <= knots[0]["x"]:
        return float(knots[0]["y"])
    if x >= knots[-1]["x"]:
        return float(knots[-1]["y"])
    for left, right in zip(knots, knots[1:]):
        lx = float(left["x"])
        rx = float(right["x"])
        if lx <= x <= rx:
            if rx == lx:
                return float(right["y"])
            t = (x - lx) / (rx - lx)
            return float(left["y"]) + t * (float(right["y"]) - float(left["y"]))
    return float(knots[-1]["y"])


def next_output_dir(root: Path) -> Path:
    base = root / RUNS_DIR
    existing = []
    if base.exists():
        for p in base.iterdir():
            if p.is_dir() and p.name.startswith(OUT_PREFIX):
                suffix = p.name[len(OUT_PREFIX) :]
                if suffix.isdigit():
                    existing.append(int(suffix))
    n = (max(existing) + 1) if existing else 1
    return base / f"{OUT_PREFIX}{n:03d}"


def load_model_specs(root: Path) -> List[Dict[str, Any]]:
    rows = read_csv(root / MAPPING_REL)
    specs = []
    seen = set()
    for r in rows:
        key = (r["Input Field"], r["Type"], r["Mapped Stat"], r["Stat Basis"])
        if key in seen:
            continue
        seen.add(key)
        specs.append(
            {
                "field": r["Input Field"],
                "type": r["Type"],
                "mapped_stat": r["Mapped Stat"],
                "basis": r["Stat Basis"],
                "direction": r.get("Direction", "").strip() or "increasing",
                "monotonic": str(r.get("Monotonic", "")).strip().upper() == "TRUE",
                "relation_decision": r.get("Relation Decision", ""),
                "relation_reason": r.get("Relation Reason", ""),
            }
        )
    return specs


def write_model_scope(root: Path, out_dir: Path) -> Dict[str, Any]:
    review_rows = read_csv(root / REVIEW_REL)
    scope_rows = []
    decision_counts: Dict[str, int] = defaultdict(int)
    for r in review_rows:
        decision = r.get("Relation Decision", "").strip()
        decision_counts[decision] += 1
        scope_rows.append(
            {
                "Input Field": r.get("Input Field", ""),
                "Type": r.get("Type", ""),
                "Model Status": "modeled" if decision in {"keep", "change"} else "not_modeled",
                "Relation Decision": decision,
                "Target Mapped Stat": r.get("Target Mapped Stat", ""),
                "Target Stat Basis": r.get("Target Stat Basis", ""),
                "Relation Reason": r.get("Relation Reason", ""),
                "Output Player Rows": r.get("Output Player Rows", ""),
                "Monotonic": r.get("Monotonic", ""),
            }
        )
    write_csv(
        out_dir / "model_scope.csv",
        scope_rows,
        [
            "Input Field",
            "Type",
            "Model Status",
            "Relation Decision",
            "Target Mapped Stat",
            "Target Stat Basis",
            "Relation Reason",
            "Output Player Rows",
            "Monotonic",
        ],
    )
    return {
        "reviewed_fields": len(scope_rows),
        "decision_counts": dict(sorted(decision_counts.items())),
        "modeled_fields_from_review": sum(1 for r in scope_rows if r["Model Status"] == "modeled"),
        "not_modeled_fields_from_review": sum(1 for r in scope_rows if r["Model Status"] == "not_modeled"),
    }


def load_run_rows(root: Path, run_id: str) -> Dict[int, Dict[str, Any]]:
    run_dir = root / RUNS_DIR / run_id
    stats = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_stats.csv")}
    attrs = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_attributes.csv")}
    tends = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_tendencies.csv")}
    joined: Dict[int, Dict[str, Any]] = {}
    for idx, srow in stats.items():
        joined[idx] = {
            "run_id": run_id,
            "player_index": idx,
            "player_label": srow.get("player_label", ""),
            "team_label": srow.get("team_label", ""),
            "stats": srow,
            "attributes": attrs.get(idx, {}),
            "tendencies": tends.get(idx, {}),
        }
    return joined


def actual_field_value(joined_row: Dict[str, Any], field: str, field_type: str) -> Optional[float]:
    source = joined_row["attributes"] if field_type == "Attribute" else joined_row["tendencies"]
    return as_float(source.get(field))


def build_samples(root: Path, specs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    specs_by_field: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for spec in specs:
        specs_by_field[(spec["field"], spec["type"])].append(spec)

    samples = []
    for run_id in RUNS:
        rows = load_run_rows(root, run_id)
        for _, joined in rows.items():
            for (field, field_type), field_specs in specs_by_field.items():
                y = actual_field_value(joined, field, field_type)
                if y is None:
                    continue
                feature_values = []
                for spec in field_specs:
                    x = feature_value(joined["stats"], spec["mapped_stat"], spec["basis"])
                    feature_values.append(
                        {
                            "mapped_stat": spec["mapped_stat"],
                            "basis": spec["basis"],
                            "x": x,
                        }
                    )
                if any(f["x"] is not None for f in feature_values):
                    samples.append(
                        {
                            "run_id": run_id,
                            "player_index": joined["player_index"],
                            "player_label": joined["player_label"],
                            "team_label": joined["team_label"],
                            "field": field,
                            "type": field_type,
                            "actual": y,
                            "features": feature_values,
                        }
                    )
    return samples


def train_calibrators(samples: Sequence[Dict[str, Any]], specs: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    points: Dict[Tuple[str, str, str], List[Tuple[float, float]]] = defaultdict(list)
    spec_lookup = {(s["field"], s["mapped_stat"], s["basis"]): s for s in specs}
    for sample in samples:
        for f in sample["features"]:
            if f["x"] is None:
                continue
            points[(sample["field"], f["mapped_stat"], f["basis"])].append((float(f["x"]), float(sample["actual"])))
    calibrators = {}
    for key, pts in points.items():
        spec = spec_lookup[key]
        calibrators[key] = fit_knots(pts, monotonic=spec["monotonic"], direction=spec["direction"])
    return calibrators


def predict_sample(sample: Dict[str, Any], calibrators: Dict[Tuple[str, str, str], List[Dict[str, Any]]]) -> Tuple[Optional[float], List[str]]:
    preds = []
    source_values = []
    for f in sample["features"]:
        x = f["x"]
        source_values.append(f"{f['mapped_stat']}[{f['basis']}]={'' if x is None else round(float(x), 6)}")
        if x is None:
            continue
        knots = calibrators.get((sample["field"], f["mapped_stat"], f["basis"]), [])
        p = predict_from_knots(float(x), knots)
        if p is not None:
            preds.append(float(p))
    if not preds:
        return None, source_values
    return sorted_median(preds), source_values


def build_holdout_predictions(samples: Sequence[Dict[str, Any]], specs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for holdout_run in RUNS:
        train = [s for s in samples if s["run_id"] != holdout_run]
        test = [s for s in samples if s["run_id"] == holdout_run]
        calibrators = train_calibrators(train, specs)
        for sample in test:
            pred, source_values = predict_sample(sample, calibrators)
            if pred is None:
                continue
            pred_round = int(round(pred))
            actual = float(sample["actual"])
            out.append(
                {
                    "holdout_run": holdout_run,
                    "player_index": sample["player_index"],
                    "player_label": sample["player_label"],
                    "team_label": sample["team_label"],
                    "Input Field": sample["field"],
                    "Type": sample["type"],
                    "actual_value": int(round(actual)),
                    "predicted_value": pred_round,
                    "raw_predicted_value": round(pred, 4),
                    "abs_error": abs(pred_round - actual),
                    "signed_error": pred_round - actual,
                    "source_values": "; ".join(source_values),
                }
            )
    return out


def build_metrics(preds: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    by_field: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in preds:
        by_field[(r["Input Field"], r["Type"])].append(r)
    rows = []
    for (field, typ), vals in sorted(by_field.items()):
        actuals = [float(v["actual_value"]) for v in vals]
        predictions = [float(v["predicted_value"]) for v in vals]
        errors = [float(v["abs_error"]) for v in vals]
        signed = [float(v["signed_error"]) for v in vals]
        corr = pearson(actuals, predictions)
        rows.append(
            {
                "Input Field": field,
                "Type": typ,
                "tested_rows": len(vals),
                "mae": round(sum(errors) / len(errors), 4),
                "rmse": round(rmse(errors) or 0.0, 4),
                "median_abs_error": round(sorted_median(errors), 4),
                "bias_signed_error": round(sum(signed) / len(signed), 4),
                "within_5_pct": round(100.0 * sum(e <= 5 for e in errors) / len(errors), 2),
                "within_10_pct": round(100.0 * sum(e <= 10 for e in errors) / len(errors), 2),
                "actual_min": min(actuals),
                "actual_max": max(actuals),
                "predicted_min": min(predictions),
                "predicted_max": max(predictions),
                "pearson_actual_predicted": "" if corr is None else round(corr, 4),
            }
        )
    all_errors = [float(v["abs_error"]) for v in preds]
    all_signed = [float(v["signed_error"]) for v in preds]
    summary = {
        "tested_prediction_rows": len(preds),
        "tested_fields": len(by_field),
        "overall_mae": round(sum(all_errors) / len(all_errors), 4) if all_errors else None,
        "overall_rmse": round(rmse(all_errors) or 0.0, 4) if all_errors else None,
        "overall_median_abs_error": round(sorted_median(all_errors), 4) if all_errors else None,
        "overall_bias_signed_error": round(sum(all_signed) / len(all_signed), 4) if all_signed else None,
        "overall_within_5_pct": round(100.0 * sum(e <= 5 for e in all_errors) / len(all_errors), 2) if all_errors else None,
        "overall_within_10_pct": round(100.0 * sum(e <= 10 for e in all_errors) / len(all_errors), 2) if all_errors else None,
    }
    return rows, summary


def write_model_knots(out_dir: Path, samples: Sequence[Dict[str, Any]], specs: Sequence[Dict[str, Any]]) -> int:
    calibrators = train_calibrators(samples, specs)
    spec_lookup = {(s["field"], s["mapped_stat"], s["basis"]): s for s in specs}
    rows = []
    for key, knots in sorted(calibrators.items()):
        field, mapped_stat, basis = key
        spec = spec_lookup[key]
        for i, knot in enumerate(knots, start=1):
            rows.append(
                {
                    "Input Field": field,
                    "Type": spec["type"],
                    "Mapped Stat": mapped_stat,
                    "Stat Basis": basis,
                    "Relation Decision": spec["relation_decision"],
                    "Direction": spec["direction"],
                    "Monotonic": spec["monotonic"],
                    "knot_index": i,
                    "stat_value": round(float(knot["x"]), 8),
                    "field_value_median": round(float(knot["y"]), 4),
                    "training_rows": int(knot["rows"]),
                    "Relation Reason": spec["relation_reason"],
                }
            )
    write_csv(
        out_dir / "model_knots.csv",
        rows,
        [
            "Input Field",
            "Type",
            "Mapped Stat",
            "Stat Basis",
            "Relation Decision",
            "Direction",
            "Monotonic",
            "knot_index",
            "stat_value",
            "field_value_median",
            "training_rows",
            "Relation Reason",
        ],
    )
    return len(rows)


def write_readme(out_dir: Path, manifest: Dict[str, Any]) -> None:
    text = f"""# Working 2K stat -> field test model

This is a standalone test model built from the four current-active game-side exports and the relation-cleaned semantic map.

## Files

- `model_scope.csv` — reviewed fields with modeled/not-modeled status.
- `model_knots.csv` — trained stat-to-field calibration knots using all four runs.
- `holdout_predictions.csv` — leave-one-run-out predictions by player/field.
- `field_metrics.csv` — field-level test metrics.
- `manifest.json` — source lineage and summary metrics.

## Scope

- Reviewed fields: {manifest['scope_summary']['reviewed_fields']}.
- Fields modeled: {manifest['modeled_fields']}.
- Not-modeled fields: {manifest['scope_summary']['not_modeled_fields_from_review']}.
- Prediction rows tested: {manifest['holdout_summary']['tested_prediction_rows']}.
- Overall MAE: {manifest['holdout_summary']['overall_mae']}.
- Overall within 10: {manifest['holdout_summary']['overall_within_10_pct']}%.

## Contract

This does not modify Player Generator runtime formulas. It is the working model artifact for testing and calibration. The model uses only reviewed `keep/change` relations from `STAT_BUCKETS_TO_FIELD_VALUES_FROM_4_GAME_RUNS_RELATION_CLEANED_003.csv` and four actual run exports joined by `run_id + player_index`.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--out-dir", default=None, help="Output directory. Defaults to next WORKING_STAT_TO_FIELD_TEST_MODEL_### folder.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else next_output_dir(root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = load_model_specs(root)
    scope_summary = write_model_scope(root, out_dir)
    samples = build_samples(root, specs)
    holdout = build_holdout_predictions(samples, specs)
    metrics_rows, holdout_summary = build_metrics(holdout)
    knot_count = write_model_knots(out_dir, samples, specs)

    write_csv(
        out_dir / "holdout_predictions.csv",
        holdout,
        [
            "holdout_run",
            "player_index",
            "player_label",
            "team_label",
            "Input Field",
            "Type",
            "actual_value",
            "predicted_value",
            "raw_predicted_value",
            "abs_error",
            "signed_error",
            "source_values",
        ],
    )
    write_csv(
        out_dir / "field_metrics.csv",
        metrics_rows,
        [
            "Input Field",
            "Type",
            "tested_rows",
            "mae",
            "rmse",
            "median_abs_error",
            "bias_signed_error",
            "within_5_pct",
            "within_10_pct",
            "actual_min",
            "actual_max",
            "predicted_min",
            "predicted_max",
            "pearson_actual_predicted",
        ],
    )

    manifest = {
        "output_dir": str(out_dir),
        "source_mapping": str((root / MAPPING_REL).resolve()),
        "source_runs": [str((root / RUNS_DIR / r).resolve()) for r in RUNS],
        "modeled_fields": len({(s["field"], s["type"]) for s in specs}),
        "modeled_stat_relations": len(specs),
        "training_sample_rows": len(samples),
        "model_knot_rows": knot_count,
        "scope_summary": scope_summary,
        "holdout_summary": holdout_summary,
        "algorithm": "per-field/per-stat piecewise median calibration; median-combine multi-stat fields; leave-one-run-out testing",
        "no_runtime_wiring": True,
        "created_files": [
            "README.md",
            "model_scope.csv",
            "model_knots.csv",
            "holdout_predictions.csv",
            "field_metrics.csv",
            "manifest.json",
        ],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    write_readme(out_dir, manifest)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
