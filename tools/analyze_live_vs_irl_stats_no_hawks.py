from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
LIVE_STATS_CSV = OUT / "current_active_player_stats.csv"
DB_PATH = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
SEASON = 1947
EXCLUDED_TEAM_LABELS = {"Atlanta Hawks"}
PER_GAME_COMPARISON_CSV = OUT / "live_vs_irl_1947_stats_comparison_no_hawks_per_game.csv"
PER_GAME_METRICS_CSV = OUT / "live_vs_irl_1947_stats_metrics_no_hawks_per_game.csv"
PLAYER_ERROR_CSV = OUT / "live_vs_irl_1947_player_error_ranking_no_hawks_per_game.csv"
EXACT_MATCHES_CSV = OUT / "live_vs_irl_1947_exact_matches_no_hawks_per_game.csv"
REPORT_MD = OUT / "live_vs_irl_1947_stats_analysis_no_hawks_per_game.md"
REPORT_JSON = OUT / "live_vs_irl_1947_stats_analysis_no_hawks_per_game.json"

FIELD_MAP = {
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

PERCENT_FIELD_MAP = {
    "Field Goal %": ("Field Goals Made", "Field Goals Attempted", "fg_percent"),
    "Free Throw %": ("Free Throws Made", "Free Throws Attempted", "ft_percent"),
}

# These live/game and IRL values are season totals. The comparison is per-game
# only: live total / live Games Played vs IRL total / IRL g. Games Played is
# used only as the denominator and is not itself compared. Percentage fields are
# compared directly as made / attempted vs the IRL percentage column.
PER_GAME_FIELDS = {field for field, column in FIELD_MAP.items() if column is not None}


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text or text.lower().startswith("err:"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def safe_pct(made: float | None, attempted: float | None) -> float | None:
    if made is None or attempted is None or attempted <= 0:
        return None
    return made / attempted


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
            selected[player] = sorted(player_rows, key=lambda row: str(row.get("team") or ""))[0]
        selected[player]["_source_row_count"] = len(player_rows)
    return selected


def build_per_game_comparison_rows(live_rows: list[dict[str, str]], irl_by_player: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    skipped_missing: dict[str, int] = defaultdict(int)
    unmatched_names: list[str] = []
    no_comparable_names: list[str] = []
    for live in live_rows:
        player = str(live.get("player_label") or "").strip()
        irl = irl_by_player.get(player)
        if not irl:
            unmatched_names.append(player)
            continue
        before_count = len(rows)
        live_games = num(live.get("Games Played"))
        irl_games = num(irl.get("g"))
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
            live_games = num(live.get("Games Played"))
            irl_games = num(irl.get("g"))
            if live_field in PER_GAME_FIELDS:
                if live_games is None or live_games <= 0 or irl_games is None or irl_games <= 0:
                    skipped_missing[live_field] += 1
                    continue
                compared_live = live_value / live_games
                compared_irl = irl_value / irl_games
            else:
                continue
            diff = compared_live - compared_irl
            exact_match = abs(diff) < 1e-12
            rows.append(
                {
                    "player": player,
                    "live_team_slot": live.get("team_slot"),
                    "live_team_label": live.get("team_label"),
                    "player_index": live.get("player_index"),
                    "irl_team": irl.get("team"),
                    "irl_row_count": irl.get("_source_row_count"),
                    "field": live_field,
                    "irl_column": irl_field,
                    "live_raw_value": live_value,
                    "irl_raw_value": irl_value,
                    "live_games_played": live_games,
                    "irl_games_played": irl_games,
                    "live_compared_value": compared_live,
                    "irl_compared_value": compared_irl,
                    "diff_live_minus_irl": diff,
                    "abs_diff": abs(diff),
                    "exact_match": int(exact_match),
                    "pct_diff": None if compared_irl == 0 else diff / compared_irl * 100.0,
                    "comparison_mode": "per_game_actual_gp",
                }
            )
        for percent_field, (live_made_field, live_attempted_field, irl_percent_field) in PERCENT_FIELD_MAP.items():
            live_made = num(live.get(live_made_field))
            live_attempted = num(live.get(live_attempted_field))
            live_percent = safe_pct(live_made, live_attempted)
            irl_percent = num(irl.get(irl_percent_field))
            if live_percent is None or irl_percent is None:
                skipped_missing[percent_field] += 1
                continue
            diff = live_percent - irl_percent
            exact_match = abs(diff) < 1e-12
            rows.append(
                {
                    "player": player,
                    "live_team_slot": live.get("team_slot"),
                    "live_team_label": live.get("team_label"),
                    "player_index": live.get("player_index"),
                    "irl_team": irl.get("team"),
                    "irl_row_count": irl.get("_source_row_count"),
                    "field": percent_field,
                    "irl_column": irl_percent_field,
                    "live_raw_value": live_percent,
                    "irl_raw_value": irl_percent,
                    "live_games_played": live_games,
                    "irl_games_played": irl_games,
                    "live_compared_value": live_percent,
                    "irl_compared_value": irl_percent,
                    "diff_live_minus_irl": diff,
                    "abs_diff": abs(diff),
                    "exact_match": int(exact_match),
                    "pct_diff": None if irl_percent == 0 else diff / irl_percent * 100.0,
                    "comparison_mode": "percentage",
                }
            )
        if len(rows) == before_count:
            no_comparable_names.append(player)
    return rows, skipped_missing, unmatched_names, no_comparable_names


def metrics_from_rows(rows: list[dict[str, Any]], skipped_missing: dict[str, int]) -> list[dict[str, Any]]:
    per_field: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for row in rows:
        per_field[str(row["field"])].append((float(row["live_compared_value"]), float(row["irl_compared_value"]), str(row["player"])))
    metrics: list[dict[str, Any]] = []
    for field, pairs in sorted(per_field.items()):
        live_values = [p[0] for p in pairs]
        irl_values = [p[1] for p in pairs]
        diffs = [live - irl for live, irl, _player in pairs]
        abs_diffs = [abs(value) for value in diffs]
        pct_diffs = [abs(live - irl) / abs(irl) * 100.0 for live, irl, _player in pairs if irl != 0]
        exact = sum(1 for d in diffs if abs(d) < 1e-9)
        metrics.append(
            {
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
            }
        )
    return metrics


def player_errors_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        player = str(row["player"])
        bucket = buckets.setdefault(
            player,
            {
                "player": player,
                "live_team_label": row["live_team_label"],
                "irl_team": row["irl_team"],
                "fields_compared": 0,
                "sum_abs_scaled_error": 0.0,
                "sum_abs_error": 0.0,
                "max_abs_error": 0.0,
                "max_abs_error_field": "",
            },
        )
        bucket["fields_compared"] += 1
        abs_diff = float(row["abs_diff"])
        irl_value = abs(float(row["irl_compared_value"]))
        bucket["sum_abs_error"] += abs_diff
        bucket["sum_abs_scaled_error"] += abs_diff / max(irl_value, 1.0)
        if abs_diff > bucket["max_abs_error"]:
            bucket["max_abs_error"] = abs_diff
            bucket["max_abs_error_field"] = row["field"]
    player_rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        n = bucket["fields_compared"]
        bucket["mean_abs_error"] = bucket["sum_abs_error"] / n if n else None
        bucket["mean_abs_scaled_error"] = bucket["sum_abs_scaled_error"] / n if n else None
        player_rows.append(bucket)
    player_rows.sort(key=lambda row: row["mean_abs_scaled_error"] or 0, reverse=True)
    return player_rows


def exact_matches_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact_rows = [row for row in rows if int(row.get("exact_match") or 0) == 1]
    return sorted(exact_rows, key=lambda row: (str(row["field"]), str(row["player"])))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def main() -> int:
    all_live_rows = list(csv.DictReader(LIVE_STATS_CSV.open(newline="", encoding="utf-8")))
    live_rows = [row for row in all_live_rows if row.get("team_label") not in EXCLUDED_TEAM_LABELS]
    excluded_rows = [row for row in all_live_rows if row.get("team_label") in EXCLUDED_TEAM_LABELS]
    irl_by_player = load_irl_totals()

    per_game_rows, per_game_skipped, per_game_unmatched, per_game_no_comparable = build_per_game_comparison_rows(live_rows, irl_by_player)
    per_game_metrics = metrics_from_rows(per_game_rows, per_game_skipped)
    player_errors = player_errors_from_rows(per_game_rows)
    exact_matches = exact_matches_from_rows(per_game_rows)

    write_csv(PER_GAME_COMPARISON_CSV, per_game_rows)
    write_csv(PER_GAME_METRICS_CSV, per_game_metrics)
    write_csv(PLAYER_ERROR_CSV, player_errors)
    write_csv(EXACT_MATCHES_CSV, exact_matches)

    lines = [
        "# Live NBA2K stats vs IRL 1946-47 totals — Hawks excluded",
        "",
        f"Excluded live teams: {', '.join(sorted(EXCLUDED_TEAM_LABELS))}",
        "Primary table below compares counting stats per game: live total / live GP vs IRL total / IRL GP.",
        "FG% and FT% are derived from live makes/attempts and compared directly to IRL percentage columns.",
        "Games Played is used only as the denominator and is not compared as a stat.",
        "",
        f"Live active rows before filter: {len(all_live_rows)}",
        f"Excluded Hawks rows: {len(excluded_rows)}",
        f"Live active rows after filter: {len(live_rows)}",
        f"Matched players with comparable fields: {len(player_errors)}",
        f"No comparable stat row after filtering: {len(per_game_no_comparable)}",
        f"Unmatched names in IRL DB: {len(per_game_unmatched)}",
        f"Comparable player-field points: {len(per_game_rows)}",
        f"Exact player-field points: {len(exact_matches)}",
        "",
        "## Per-game field metrics",
        "",
        "| Field | n | exact | live mean | IRL mean | mean err | MAE | RMSE | MAPE | r |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in per_game_metrics:
        lines.append(
            f"| {row['field']} | {row['n']} | {row['exact_matches']} | {fmt(row['live_mean'], 3)} | {fmt(row['irl_mean'], 3)} | "
            f"{fmt(row['mean_signed_error'], 3)} | {fmt(row['mae'], 3)} | {fmt(row['rmse'], 3)} | {fmt(row['mean_abs_pct_error'], 1)}% | {fmt(row['pearson_r'], 3)} |"
        )
    lines.extend(
        [
            "",
            "## Worst player-level mismatches, per-game",
            "",
            "| Player | Live team | IRL team | fields | mean scaled abs err | max abs err | max field |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in player_errors[:20]:
        lines.append(
            f"| {row['player']} | {row['live_team_label']} | {row['irl_team']} | {row['fields_compared']} | "
            f"{fmt(row['mean_abs_scaled_error'], 3)} | {fmt(row['max_abs_error'], 3)} | {row['max_abs_error_field']} |"
        )
    lines.extend(
        [
            "",
            "## Output files",
            "",
            f"- Per-game comparison rows: `{PER_GAME_COMPARISON_CSV}`",
            f"- Per-game metrics: `{PER_GAME_METRICS_CSV}`",
            f"- Player error ranking: `{PLAYER_ERROR_CSV}`",
            f"- Exact matches: `{EXACT_MATCHES_CSV}`",
            f"- JSON report: `{REPORT_JSON}`",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "excluded_team_labels": sorted(EXCLUDED_TEAM_LABELS),
                "comparison_mode": "per_game_only",
                "per_game_denominator": "actual player games played: live Games Played and IRL g",
                "games_played_field_mode": "denominator_only_not_compared",
                "live_rows_before_filter": len(all_live_rows),
                "excluded_rows": len(excluded_rows),
                "live_rows_after_filter": len(live_rows),
                "matched_players_with_comparable_fields": len(player_errors),
                "no_comparable_names": per_game_no_comparable,
                "unmatched_names": per_game_unmatched,
                "comparison_points": len(per_game_rows),
                "exact_match_points": len(exact_matches),
                "per_game_metrics": per_game_metrics,
                "exact_matches": exact_matches,
                "top_player_errors_per_game": player_errors[:25],
                "files": {
                    "per_game_comparison_csv": str(PER_GAME_COMPARISON_CSV),
                    "per_game_metrics_csv": str(PER_GAME_METRICS_CSV),
                    "player_error_csv": str(PLAYER_ERROR_CSV),
                    "exact_matches_csv": str(EXACT_MATCHES_CSV),
                    "report_md": str(REPORT_MD),
                    "report_json": str(REPORT_JSON),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "excluded_rows": len(excluded_rows),
                "live_rows_after_filter": len(live_rows),
                "matched_players_with_comparable_fields": len(player_errors),
                "comparison_points_per_game": len(per_game_rows),
                "exact_match_points": len(exact_matches),
                "report_md": str(REPORT_MD),
                "per_game_metrics_csv": str(PER_GAME_METRICS_CSV),
                "exact_matches_csv": str(EXACT_MATCHES_CSV),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
