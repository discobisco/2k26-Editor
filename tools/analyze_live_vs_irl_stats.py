from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "outputs"
LIVE_STATS_CSV = OUT_DIR / "current_active_player_stats.csv"
DB_PATH = REPO_ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
SEASON = 1947
COMPARISON_CSV = OUT_DIR / "live_vs_irl_1947_stats_comparison.csv"
METRICS_CSV = OUT_DIR / "live_vs_irl_1947_stats_metrics.csv"
PLAYER_ERROR_CSV = OUT_DIR / "live_vs_irl_1947_player_error_ranking.csv"
REPORT_MD = OUT_DIR / "live_vs_irl_1947_stats_analysis.md"
REPORT_JSON = OUT_DIR / "live_vs_irl_1947_stats_analysis.json"

FIELD_MAP = {
    "Games Played": "g",
    "Games Started": "gs",
    "Minutes": "mp",
    "Assists": "ast",
    "Blocks": "blk",
    "Double Doubles": None,
    "Fouls": "pf",
    "Steals": "stl",
    "Total +/-": None,
    "Triple Doubles": "trp_dbl",
    "Turnovers": "tov",
    "Defensive Rebounds": "drb",
    "Offensive Rebounds": "orb",
    "Rebounds": "trb",
    "Field Goals Attempted": "fga",
    "Field Goals Made": "fg",
    "Free Throws Attempted": "fta",
    "Free Throws Made": "ft",
    "Points": "pts",
    "Three Pointers Attempted": "x3pa",
    "Three Pointers Made": "x3p",
}


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if text == "" or text.lower().startswith("err:"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def load_live_rows() -> list[dict[str, str]]:
    with LIVE_STATS_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_irl_totals() -> dict[str, dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM player_totals WHERE season = ?", (SEASON,)).fetchall()
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_player[str(row["player"]).strip()].append(dict(row))
    selected: dict[str, dict[str, Any]] = {}
    for player, player_rows in by_player.items():
        aggregate = [row for row in player_rows if str(row.get("team") or "").upper().endswith("TM")]
        if aggregate:
            selected[player] = aggregate[0]
        elif len(player_rows) == 1:
            selected[player] = player_rows[0]
        else:
            # No aggregate row but multiple teams: preserve the first deterministic row and flag team row count.
            selected[player] = sorted(player_rows, key=lambda row: str(row.get("team") or ""))[0]
        selected[player]["_source_row_count"] = len(player_rows)
    return selected


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    live_rows = load_live_rows()
    irl_by_player = load_irl_totals()

    comparison_rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    per_field: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    skipped_missing: dict[str, int] = defaultdict(int)
    unsupported_fields = [field for field, irl in FIELD_MAP.items() if irl is None]

    for live in live_rows:
        player = str(live.get("player_label") or "").strip()
        irl = irl_by_player.get(player)
        if not irl:
            unmatched.append(player)
            continue
        for live_field, irl_field in FIELD_MAP.items():
            if irl_field is None:
                continue
            live_value = num(live.get(live_field))
            irl_value = num(irl.get(irl_field))
            if irl_value is None and irl_field in {"x3p", "x3pa"} and SEASON < 1980:
                irl_value = 0.0
            if live_value is None or irl_value is None:
                skipped_missing[live_field] += 1
                continue
            diff = live_value - irl_value
            abs_diff = abs(diff)
            pct_diff = None if irl_value == 0 else diff / irl_value * 100.0
            row = {
                "player": player,
                "live_team_slot": live.get("team_slot"),
                "live_team_label": live.get("team_label"),
                "player_index": live.get("player_index"),
                "irl_team": irl.get("team"),
                "irl_row_count": irl.get("_source_row_count"),
                "field": live_field,
                "irl_column": irl_field,
                "live_value": live_value,
                "irl_value": irl_value,
                "diff_live_minus_irl": diff,
                "abs_diff": abs_diff,
                "pct_diff": pct_diff,
            }
            comparison_rows.append(row)
            per_field[live_field].append((live_value, irl_value, player))

    metrics: list[dict[str, Any]] = []
    for field, pairs in sorted(per_field.items()):
        live_values = [p[0] for p in pairs]
        irl_values = [p[1] for p in pairs]
        diffs = [live - irl for live, irl, _player in pairs]
        abs_diffs = [abs(value) for value in diffs]
        pct_diffs = [abs(live - irl) / abs(irl) * 100.0 for live, irl, _player in pairs if irl != 0]
        exact = sum(1 for d in diffs if abs(d) < 1e-9)
        metrics.append({
            "field": field,
            "n": len(pairs),
            "exact_matches": exact,
            "exact_match_rate": exact / len(pairs) if pairs else None,
            "live_mean": statistics.mean(live_values) if live_values else None,
            "irl_mean": statistics.mean(irl_values) if irl_values else None,
            "mean_signed_error": statistics.mean(diffs) if diffs else None,
            "mae": statistics.mean(abs_diffs) if abs_diffs else None,
            "rmse": math.sqrt(statistics.mean([d * d for d in diffs])) if diffs else None,
            "median_abs_error": statistics.median(abs_diffs) if abs_diffs else None,
            "mean_abs_pct_error": statistics.mean(pct_diffs) if pct_diffs else None,
            "pearson_r": pearson(live_values, irl_values),
            "missing_or_uncomparable_rows": skipped_missing.get(field, 0),
        })

    player_errors: dict[str, dict[str, Any]] = {}
    for row in comparison_rows:
        player = row["player"]
        bucket = player_errors.setdefault(player, {
            "player": player,
            "live_team_label": row["live_team_label"],
            "irl_team": row["irl_team"],
            "fields_compared": 0,
            "sum_abs_scaled_error": 0.0,
            "sum_abs_error": 0.0,
            "max_abs_error": 0.0,
            "max_abs_error_field": "",
        })
        bucket["fields_compared"] += 1
        abs_diff = float(row["abs_diff"])
        irl_value = abs(float(row["irl_value"]))
        bucket["sum_abs_error"] += abs_diff
        bucket["sum_abs_scaled_error"] += abs_diff / max(irl_value, 1.0)
        if abs_diff > bucket["max_abs_error"]:
            bucket["max_abs_error"] = abs_diff
            bucket["max_abs_error_field"] = row["field"]
    player_error_rows = []
    for bucket in player_errors.values():
        n = bucket["fields_compared"]
        bucket["mean_abs_error"] = bucket["sum_abs_error"] / n if n else None
        bucket["mean_abs_scaled_error"] = bucket["sum_abs_scaled_error"] / n if n else None
        player_error_rows.append(bucket)
    player_error_rows.sort(key=lambda row: (row["mean_abs_scaled_error"] or 0), reverse=True)

    with COMPARISON_CSV.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(comparison_rows[0].keys()) if comparison_rows else []
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    with METRICS_CSV.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(metrics[0].keys()) if metrics else []
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metrics)

    with PLAYER_ERROR_CSV.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(player_error_rows[0].keys()) if player_error_rows else []
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(player_error_rows)

    top_bad_fields = sorted(metrics, key=lambda row: (row["mean_abs_pct_error"] is None, -(row["mean_abs_pct_error"] or 0)))[:8]
    top_correlated = sorted([m for m in metrics if m["pearson_r"] is not None], key=lambda row: row["pearson_r"], reverse=True)[:8]
    low_correlated = sorted([m for m in metrics if m["pearson_r"] is not None], key=lambda row: row["pearson_r"])[:8]

    report = {
        "season": SEASON,
        "live_rows": len(live_rows),
        "matched_players": len(player_errors),
        "unmatched_players": unmatched,
        "comparison_points": len(comparison_rows),
        "unsupported_live_fields": unsupported_fields,
        "metrics": metrics,
        "top_player_errors": player_error_rows[:25],
        "files": {
            "comparison_csv": str(COMPARISON_CSV),
            "metrics_csv": str(METRICS_CSV),
            "player_error_csv": str(PLAYER_ERROR_CSV),
            "report_md": str(REPORT_MD),
            "report_json": str(REPORT_JSON),
        },
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def fmt(value: Any, digits: int = 3) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        return str(value)

    lines = [
        "# Live NBA2K stats vs IRL 1946-47 totals",
        "",
        f"Live source: `{LIVE_STATS_CSV}`",
        f"IRL source: `{DB_PATH}` / `player_totals` season `{SEASON}`",
        f"Live active rows: {len(live_rows)}",
        f"Matched players: {len(player_errors)}",
        f"Unmatched players: {len(unmatched)}",
        f"Comparable player-field points: {len(comparison_rows)}",
        "",
        "Fields skipped as not directly available in the 1947 IRL totals source: " + ", ".join(unsupported_fields) + ".",
        "Rows with missing IRL values were excluded per field, so sparse-era unavailable fields like minutes, starts, steals, blocks, turnovers, and rebounds have low/no coverage.",
        "For multi-team IRL players, aggregate `2TM`/`3TM` rows were used when present.",
        "",
        "## Per-field metrics",
        "",
        "| Field | n | exact | live mean | IRL mean | mean err | MAE | RMSE | MAPE | r |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        lines.append(
            f"| {row['field']} | {row['n']} | {row['exact_matches']} | {fmt(row['live_mean'], 2)} | {fmt(row['irl_mean'], 2)} | "
            f"{fmt(row['mean_signed_error'], 2)} | {fmt(row['mae'], 2)} | {fmt(row['rmse'], 2)} | {fmt(row['mean_abs_pct_error'], 1)}% | {fmt(row['pearson_r'], 3)} |"
        )
    lines.extend([
        "",
        "## Worst player-level mismatches by normalized absolute error",
        "",
        "| Player | Live team | IRL team | fields | mean scaled abs err | max abs err | max field |",
        "|---|---|---|---:|---:|---:|---|",
    ])
    for row in player_error_rows[:20]:
        lines.append(
            f"| {row['player']} | {row['live_team_label']} | {row['irl_team']} | {row['fields_compared']} | "
            f"{fmt(row['mean_abs_scaled_error'], 3)} | {fmt(row['max_abs_error'], 1)} | {row['max_abs_error_field']} |"
        )
    lines.extend([
        "",
        "## Highest field MAPE",
        "",
    ])
    for row in top_bad_fields:
        lines.append(f"- {row['field']}: MAPE {fmt(row['mean_abs_pct_error'], 1)}%, MAE {fmt(row['mae'], 2)}, r {fmt(row['pearson_r'], 3)}, n {row['n']}")
    lines.extend([
        "",
        "## Correlation extremes",
        "",
        "Highest:",
    ])
    for row in top_correlated:
        lines.append(f"- {row['field']}: r {fmt(row['pearson_r'], 3)}, MAE {fmt(row['mae'], 2)}, n {row['n']}")
    lines.append("Lowest:")
    for row in low_correlated:
        lines.append(f"- {row['field']}: r {fmt(row['pearson_r'], 3)}, MAE {fmt(row['mae'], 2)}, n {row['n']}")
    lines.extend([
        "",
        "## Output files",
        "",
        f"- Comparison rows: `{COMPARISON_CSV}`",
        f"- Field metrics: `{METRICS_CSV}`",
        f"- Player error ranking: `{PLAYER_ERROR_CSV}`",
        f"- JSON report: `{REPORT_JSON}`",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "live_rows": len(live_rows),
        "matched_players": len(player_errors),
        "unmatched_players": len(unmatched),
        "comparison_points": len(comparison_rows),
        "metrics_csv": str(METRICS_CSV),
        "player_error_csv": str(PLAYER_ERROR_CSV),
        "report_md": str(REPORT_MD),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
