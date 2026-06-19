from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
LIVE_STATS_CSV = OUT / "current_active_player_stats.csv"
DB_PATH = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"
SEASON = 1947
TOLERANCE = 0.01

PAIR_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_pairs_1947_within_001.csv"
SUMMARY_CSV = OUT / "live_fg_pct_nearby_irl_fg_pct_summary_1947_within_001.csv"


def num(value: Any) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text or text.lower().startswith("err:"):
            return None
        return float(text)
    except Exception:
        return None


def load_live_players() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(LIVE_STATS_CSV.open(newline="", encoding="utf-8")):
        fgm = num(row.get("Field Goals Made"))
        fga = num(row.get("Field Goals Attempted"))
        gp = num(row.get("Games Played"))
        if fgm is None or fga is None or fga <= 0:
            continue
        rows.append(
            {
                "live_player": str(row.get("player_label") or "").strip(),
                "live_team": row.get("team_label"),
                "live_player_index": row.get("player_index"),
                "live_games_played": gp,
                "live_fgm": fgm,
                "live_fga": fga,
                "live_fg_percent": fgm / fga,
            }
        )
    return rows


def load_irl_players() -> list[dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    db_rows = con.execute("SELECT * FROM player_totals WHERE season = ?", (SEASON,)).fetchall()
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db_rows:
        by_player[str(row["player"]).strip()].append(dict(row))

    selected: list[dict[str, Any]] = []
    for player, player_rows in by_player.items():
        aggregate = [row for row in player_rows if str(row.get("team") or "").upper().endswith("TM")]
        if aggregate:
            row = aggregate[0]
        elif len(player_rows) == 1:
            row = player_rows[0]
        else:
            row = sorted(player_rows, key=lambda value: str(value.get("team") or ""))[0]
        fg_percent = num(row.get("fg_percent"))
        fga = num(row.get("fga"))
        if fg_percent is None or fga is None or fga <= 0:
            continue
        selected.append(
            {
                "irl_player": player,
                "irl_team": row.get("team"),
                "irl_games": num(row.get("g")),
                "irl_fgm": num(row.get("fg")),
                "irl_fga": fga,
                "irl_fg_percent": fg_percent,
                "irl_source_row_count": len(player_rows),
            }
        )
    return selected


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    live_players = load_live_players()
    irl_players = load_irl_players()

    pair_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for live in live_players:
        matches = []
        live_pct = float(live["live_fg_percent"])
        for irl in irl_players:
            irl_pct = float(irl["irl_fg_percent"])
            diff = live_pct - irl_pct
            abs_diff = abs(diff)
            if abs_diff <= TOLERANCE:
                pair_rows.append(
                    {
                        **live,
                        **irl,
                        "fg_percent_diff_live_minus_irl": diff,
                        "abs_fg_percent_diff": abs_diff,
                        "within_tolerance": int(abs_diff <= TOLERANCE),
                    }
                )
                matches.append((abs_diff, irl))
        matches.sort(key=lambda item: (item[0], str(item[1]["irl_player"])))
        summary_rows.append(
            {
                **live,
                "match_count": len(matches),
                "closest_irl_players": "; ".join(
                    f"{match[1]['irl_player']} ({float(match[1]['irl_fg_percent']):.3f}, diff {match[0]:.3f})"
                    for match in matches[:12]
                ),
            }
        )

    pair_rows.sort(key=lambda row: (str(row["live_player"]), float(row["abs_fg_percent_diff"]), str(row["irl_player"])))
    summary_rows.sort(key=lambda row: str(row["live_player"]))

    pair_fields = [
        "live_player",
        "live_team",
        "live_player_index",
        "live_games_played",
        "live_fgm",
        "live_fga",
        "live_fg_percent",
        "irl_player",
        "irl_team",
        "irl_games",
        "irl_fgm",
        "irl_fga",
        "irl_fg_percent",
        "fg_percent_diff_live_minus_irl",
        "abs_fg_percent_diff",
        "irl_source_row_count",
        "within_tolerance",
    ]
    with PAIR_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=pair_fields)
        writer.writeheader()
        writer.writerows(pair_rows)

    summary_fields = [
        "live_player",
        "live_team",
        "live_player_index",
        "live_games_played",
        "live_fgm",
        "live_fga",
        "live_fg_percent",
        "match_count",
        "closest_irl_players",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    bob_pairs = [row for row in pair_rows if row["live_player"] == "Bob Feerick"][:12]
    print(f"live players: {len(live_players)}")
    print(f"IRL players with FG%: {len(irl_players)}")
    print(f"pair rows within +/- {TOLERANCE:.3f}: {len(pair_rows)}")
    print(f"summary rows: {len(summary_rows)}")
    print(f"pairs csv: {PAIR_CSV}")
    print(f"summary csv: {SUMMARY_CSV}")
    print("Bob Feerick first matches:")
    for row in bob_pairs:
        print(
            f"  live {float(row['live_fg_percent']):.3f} -> "
            f"{row['irl_player']} {float(row['irl_fg_percent']):.3f} "
            f"diff {float(row['abs_fg_percent_diff']):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
