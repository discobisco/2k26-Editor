from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "current_active_stat_extractor_runs"
DEFAULT_ATTRIBUTE_OUT = REPO_ROOT / "nba2k_editor" / "Player Generator" / "Attribute Maps"
DEFAULT_TENDENCY_OUT = REPO_ROOT / "nba2k_editor" / "Player Generator" / "Tendency Maps"
POSITIONS = ("PG", "SG", "SF", "PF", "C")
IDENTITY_COLUMNS = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
STAT_IDENTITY_COLUMNS = {*IDENTITY_COLUMNS, "current_year_stat_id"}
ATTRIBUTE_BINS = ((25, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 99.000001))
TENDENCY_BINS = ((0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 100.000001))
COUNTING_STATS = {
    "Points": "PTS",
    "Assists": "AST",
    "Blocks": "BLK",
    "Fouls": "PF",
    "Steals": "STL",
    "Turnovers": "TOV",
    "Defensive Rebounds": "DREB",
    "Offensive Rebounds": "ORB",
    "Field Goals Attempted": "FGA",
    "Field Goals Made": "FGM",
    "Free Throws Attempted": "FTA",
    "Free Throws Made": "FTM",
    "Three Pointers Attempted": "3PA",
    "Three Pointers Made": "3PM",
    "Total +/-": "+/-",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text or text.lower().startswith("err:"):
        return None
    try:
        return float(text)
    except Exception:
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sx = math.sqrt(sum(x * x for x in dx))
    sy = math.sqrt(sum(y * y for y in dy))
    if sx <= 0 or sy <= 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


def norm_pos(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "POINT GUARD": "PG",
        "SHOOTING GUARD": "SG",
        "SMALL FORWARD": "SF",
        "POWER FORWARD": "PF",
        "CENTER": "C",
        "CENTRE": "C",
    }
    return aliases.get(text, text)


def position_values(primary: Any, secondary: Any = "") -> tuple[str, ...]:
    out: list[str] = []
    for raw in (primary, secondary):
        pos = norm_pos(raw)
        if pos in POSITIONS and pos not in out:
            out.append(pos)
    return tuple(out)


def run_source_dir(run_dir: Path) -> Path:
    nested = run_dir / "current_active_attr_tendency_range_map" / "source_data"
    if nested.is_dir():
        return nested
    return run_dir


def source_paths(run_dir: Path) -> dict[str, Path]:
    sd = run_source_dir(run_dir)
    return {
        "stats": sd / "current_active_player_stats.csv",
        "attributes": sd / "current_active_player_attributes.csv",
        "tendencies": sd / "current_active_player_tendencies.csv",
    }


def discover_runs(runs_root: Path, requested: Iterable[str] | None = None) -> list[Path]:
    if requested:
        runs = [runs_root / r if not str(r).startswith("/") else Path(r) for r in requested]
    else:
        runs = sorted(runs_root.glob("run_*"))
    valid: list[Path] = []
    for run in runs:
        paths = source_paths(run)
        if all(path.is_file() for path in paths.values()):
            valid.append(run)
    return valid


def load_positions(path: Path | None) -> dict[tuple[str, str], tuple[str, ...]]:
    if path is None or not path.is_file():
        return {}
    rows = read_csv(path)
    out: dict[tuple[str, str], tuple[str, ...]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or row.get("run") or "").strip()
        player_index = str(row.get("player_index") or "").strip()
        if not run_id or not player_index:
            continue
        primary = row.get("primary_position") or row.get("position") or row.get("Position") or row.get("Vitals/POSITION") or row.get("POSITION")
        secondary = row.get("secondary_position") or row.get("Secondary Position") or row.get("Vitals/SECONDARYPOSITION") or row.get("SECONDARYPOSITION")
        positions = position_values(primary, secondary)
        if positions:
            out[(run_id, player_index)] = positions
    return out


def positions_from_row(row: dict[str, str]) -> tuple[str, ...]:
    primary = row.get("primary_position") or row.get("position") or row.get("Position") or row.get("Vitals/POSITION") or row.get("POSITION")
    secondary = row.get("secondary_position") or row.get("Secondary Position") or row.get("Vitals/SECONDARYPOSITION") or row.get("SECONDARYPOSITION")
    return position_values(primary, secondary)


def stat_features(row: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    gp = num(row.get("Games Played")) or 0.0
    gs = num(row.get("Games Started")) or 0.0
    minutes = num(row.get("Minutes")) or 0.0
    if gp > 0:
        out["GP"] = gp
        out["GS"] = gs
        out["GS%"] = gs / gp * 100.0
        out["MP/g"] = minutes / gp
    if minutes > 0:
        out["Minutes"] = minutes
    raw: dict[str, float] = {}
    for col, short in COUNTING_STATS.items():
        v = num(row.get(col))
        if v is None:
            continue
        raw[short] = v
        out[short] = v
        if gp > 0:
            out[f"{short}/g"] = v / gp
        if minutes > 0:
            out[f"{short}/36"] = v / minutes * 36.0
    for col, value in row.items():
        if col in STAT_IDENTITY_COLUMNS or col in COUNTING_STATS:
            continue
        v = num(value)
        if v is not None:
            out[col] = v
    fgm, fga = raw.get("FGM"), raw.get("FGA")
    tpm, tpa = raw.get("3PM"), raw.get("3PA")
    ftm, fta = raw.get("FTM"), raw.get("FTA")
    pts = raw.get("PTS")
    if fgm is not None and fga and fga > 0:
        out["FG%"] = fgm / fga * 100.0
    if tpm is not None and tpa and tpa > 0:
        out["3P%"] = tpm / tpa * 100.0
    if ftm is not None and fta and fta > 0:
        out["FT%"] = ftm / fta * 100.0
    if tpa is not None and fga and fga > 0:
        out["3PAr"] = tpa / fga * 100.0
    if fta is not None and fga and fga > 0:
        out["FTr"] = fta / fga * 100.0
    if pts is not None and fga and fga > 0:
        out["PTS/FGA"] = pts / fga
    if fgm is not None and tpm is not None and fga and fga > 0:
        out["eFG%"] = (fgm + 0.5 * tpm) / fga * 100.0
    if pts is not None and fga is not None and fta is not None and (2 * (fga + 0.44 * fta)) > 0:
        out["TS%"] = pts / (2 * (fga + 0.44 * fta)) * 100.0
    dreb, oreb = raw.get("DREB"), raw.get("ORB")
    if dreb is not None and oreb is not None:
        reb = dreb + oreb
        out["REB"] = reb
        if gp > 0:
            out["REB/g"] = reb / gp
        if minutes > 0:
            out["REB/36"] = reb / minutes * 36.0
    return out


def value_columns(rows: list[dict[str, str]], identity: set[str]) -> list[str]:
    if not rows:
        return []
    return [col for col in rows[0] if col not in identity]


def stat_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"players": 0, "mean": "", "median": "", "min": "", "max": ""}
    return {
        "players": len(values),
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


def bin_label(kind: str, lo: float, hi: float) -> str:
    if kind == "attribute" and hi >= 99:
        return f"{int(lo)}-99"
    if kind == "tendency" and hi >= 100:
        return f"{int(lo)}-100"
    return f"{int(lo)}-{int(hi)}"


def collect_samples(runs: list[Path], positions: dict[tuple[str, str], tuple[str, ...]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    attr_samples: list[dict[str, Any]] = []
    tend_samples: list[dict[str, Any]] = []
    stat_samples: list[dict[str, Any]] = []
    missing_positions: list[dict[str, Any]] = []
    for run in runs:
        run_id = run.name
        paths = source_paths(run)
        stats = read_csv(paths["stats"])
        attrs = read_csv(paths["attributes"])
        tends = read_csv(paths["tendencies"])
        stat_by_player = {str(row.get("player_index", "")): row for row in stats}
        attr_by_player = {str(row.get("player_index", "")): row for row in attrs}
        tend_by_player = {str(row.get("player_index", "")): row for row in tends}
        players = sorted(set(stat_by_player) & set(attr_by_player) & set(tend_by_player), key=lambda x: int(x) if x.isdigit() else x)
        attr_fields = value_columns(attrs, IDENTITY_COLUMNS)
        tend_fields = value_columns(tends, IDENTITY_COLUMNS)
        for player_index in players:
            stat_row = stat_by_player[player_index]
            pos = positions.get((run_id, player_index)) or positions_from_row(stat_row) or positions_from_row(attr_by_player[player_index]) or positions_from_row(tend_by_player[player_index])
            if not pos:
                missing_positions.append({
                    "run_id": run_id,
                    "player_index": player_index,
                    "current_year_stat_id": stat_row.get("current_year_stat_id", ""),
                    "team_index": stat_row.get("team_index", ""),
                    "roster_slot": stat_row.get("roster_slot", ""),
                    "primary_position": "",
                    "secondary_position": "",
                })
                continue
            features = stat_features(stat_row)
            for p in pos:
                for stat, value in features.items():
                    stat_samples.append({"run_id": run_id, "player_index": player_index, "position": p, "stat": stat, "value": value})
                for field in attr_fields:
                    value = num(attr_by_player[player_index].get(field))
                    if value is not None:
                        attr_samples.append({"run_id": run_id, "player_index": player_index, "position": p, "field": field, "value": value, "stats": features})
                for field in tend_fields:
                    value = num(tend_by_player[player_index].get(field))
                    if value is not None:
                        tend_samples.append({"run_id": run_id, "player_index": player_index, "position": p, "field": field, "value": value, "stats": features})
    return attr_samples, tend_samples, stat_samples, missing_positions


def distribution_rows(samples: list[dict[str, Any]], kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bins = ATTRIBUTE_BINS if kind == "attribute" else TENDENCY_BINS
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    bin_grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for sample in samples:
        key = (sample["position"], sample["field"])
        value = float(sample["value"])
        grouped[key].append(value)
        for lo, hi in bins:
            if lo <= value < hi:
                bin_grouped[(sample["position"], sample["field"], bin_label(kind, lo, hi))].append(value)
                break
    out: list[dict[str, Any]] = []
    for (position, field), vals in sorted(grouped.items()):
        s = stat_summary(vals)
        out.append({"kind": kind, "position": position, "field": field, **s})
    bin_out: list[dict[str, Any]] = []
    for position in POSITIONS:
        fields = sorted({field for pos, field in grouped if pos == position})
        for field in fields:
            for lo, hi in bins:
                label = bin_label(kind, lo, hi)
                vals = bin_grouped.get((position, field, label), [])
                s = stat_summary(vals)
                bin_out.append({"kind": kind, "position": position, "field": field, "game_value_range": label, **s})
    return out, bin_out


def correlation_rows(samples: list[dict[str, Any]], kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_position_field: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        by_position_field[(sample["position"], sample["field"])].append(sample)
    best_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for (position, field), rows in sorted(by_position_field.items()):
        stat_names = sorted({stat for row in rows for stat in row["stats"]})
        best: dict[str, Any] | None = None
        for stat in stat_names:
            xs: list[float] = []
            ys: list[float] = []
            for row in rows:
                stat_value = row["stats"].get(stat)
                if stat_value is None:
                    continue
                xs.append(float(row["value"]))
                ys.append(float(stat_value))
            r = pearson(xs, ys)
            if r is None:
                continue
            rec = {"kind": kind, "position": position, "field": field, "stat": stat, "r": r, "abs_r": abs(r), "n": len(xs)}
            all_rows.append(rec)
            if best is None or (rec["abs_r"], rec["n"]) > (best["abs_r"], best["n"]):
                best = rec
        if best is not None:
            best_rows.append(best)
    return best_rows, all_rows


def mapped_stat_bin_rows(samples: list[dict[str, Any]], best_rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    bins = ATTRIBUTE_BINS if kind == "attribute" else TENDENCY_BINS
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        by_key[(sample["position"], sample["field"])].append(sample)
    out: list[dict[str, Any]] = []
    for best in best_rows:
        position = str(best["position"])
        field = str(best["field"])
        stat = str(best["stat"])
        rows = by_key[(position, field)]
        for lo, hi in bins:
            label = bin_label(kind, lo, hi)
            vals: list[float] = []
            for row in rows:
                value = float(row["value"])
                if not (lo <= value < hi):
                    continue
                stat_value = row["stats"].get(stat)
                if stat_value is not None:
                    vals.append(float(stat_value))
            s = stat_summary(vals)
            out.append({
                "kind": kind,
                "position": position,
                "field": field,
                "best_stat": stat,
                "r": best["r"],
                "n": best["n"],
                "game_value_range": label,
                "stat_players": s["players"],
                "stat_mean": s["mean"],
                "stat_median": s["median"],
                "stat_min": s["min"],
                "stat_max": s["max"],
            })
    return out


def write_outputs(out_dir: Path, kind: str, samples: list[dict[str, Any]], missing_positions: list[dict[str, Any]], run_ids: list[str]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dist, dist_bins = distribution_rows(samples, kind)
    best, all_corr = correlation_rows(samples, kind)
    mapped_bins = mapped_stat_bin_rows(samples, best, kind)
    write_csv(out_dir / f"{kind}_position_distribution_summary.csv", dist, ["kind", "position", "field", "players", "mean", "median", "min", "max"])
    write_csv(out_dir / f"{kind}_position_distribution_bins.csv", dist_bins, ["kind", "position", "field", "game_value_range", "players", "mean", "median", "min", "max"])
    write_csv(out_dir / f"{kind}_best_stat_by_position.csv", best, ["kind", "position", "field", "stat", "r", "abs_r", "n"])
    write_csv(out_dir / f"{kind}_all_stat_correlations_by_position.csv", all_corr, ["kind", "position", "field", "stat", "r", "abs_r", "n"])
    write_csv(out_dir / f"{kind}_mapped_stat_bins_by_position.csv", mapped_bins, ["kind", "position", "field", "best_stat", "r", "n", "game_value_range", "stat_players", "stat_mean", "stat_median", "stat_min", "stat_max"])
    manifest = {
        "kind": kind,
        "runs": run_ids,
        "positions": POSITIONS,
        "samples": len(samples),
        "distribution_rows": len(dist),
        "distribution_bin_rows": len(dist_bins),
        "best_stat_rows": len(best),
        "all_correlation_rows": len(all_corr),
        "mapped_stat_bin_rows": len(mapped_bins),
        "missing_position_rows": len(missing_positions),
        "join_policy": "run_id + player_index only; player names are not used",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    md = [
        f"# {kind.title()} position map",
        "",
        f"Runs: {', '.join(run_ids)}",
        "Join policy: `run_id + player_index`; player names are not used.",
        "Players with both primary and secondary positions are included in both position buckets.",
        "",
        "## Outputs",
        f"- `{kind}_position_distribution_summary.csv`",
        f"- `{kind}_position_distribution_bins.csv`",
        f"- `{kind}_best_stat_by_position.csv`",
        f"- `{kind}_all_stat_correlations_by_position.csv`",
        f"- `{kind}_mapped_stat_bins_by_position.csv`",
        "",
        "## Counts",
        json.dumps(manifest, indent=2),
    ]
    (out_dir / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return manifest


def write_position_template(path: Path, missing: list[dict[str, Any]]) -> None:
    write_csv(path, missing, ["run_id", "player_index", "current_year_stat_id", "team_index", "roster_slot", "primary_position", "secondary_position"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build position-specific attribute/tendency maps from active export runs.")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--runs", nargs="*", default=("run_001", "run_002", "run_003", "run_004"))
    parser.add_argument("--positions-csv", type=Path, default=None, help="CSV keyed by run_id,player_index with primary_position and optional secondary_position.")
    parser.add_argument("--attribute-out", type=Path, default=DEFAULT_ATTRIBUTE_OUT)
    parser.add_argument("--tendency-out", type=Path, default=DEFAULT_TENDENCY_OUT)
    parser.add_argument("--write-position-template", type=Path, default=DEFAULT_ATTRIBUTE_OUT / "missing_position_template.csv")
    parser.add_argument("--allow-missing-positions", action="store_true", help="Skip players with no position. Default is to fail after writing a template.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runs = discover_runs(args.runs_root, args.runs)
    if not runs:
        raise SystemExit(f"no valid runs found under {args.runs_root}")
    positions = load_positions(args.positions_csv)
    attr_samples, tend_samples, _stat_samples, missing = collect_samples(runs, positions)
    if missing and not args.allow_missing_positions:
        write_position_template(args.write_position_template, missing)
        raise SystemExit(
            "missing position metadata for "
            f"{len(missing)} run/player rows; wrote template: {args.write_position_template}. "
            "Provide --positions-csv or rerun with --allow-missing-positions to skip them."
        )
    run_ids = [run.name for run in runs]
    attr_manifest = write_outputs(args.attribute_out, "attribute", attr_samples, missing, run_ids)
    tend_manifest = write_outputs(args.tendency_out, "tendency", tend_samples, missing, run_ids)
    print(json.dumps({"attribute": attr_manifest, "tendency": tend_manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
