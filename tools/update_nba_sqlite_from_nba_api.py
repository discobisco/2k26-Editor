#!/usr/bin/env python3
"""Incrementally update NBA API archive SQLite tables.

Stdlib-only. Pulls NBA Stats API game logs and PlayByPlayV3 data into the
large `nba.sqlite` archive shipped beside the Player Generator data.

Why a v3 table instead of forcing everything into the legacy play_by_play table:
NBA Stats `playbyplayv2` currently returns `{}` for tested historical games,
while `playbyplayv3` returns richer action rows with text subtype fields instead
of the old numeric action-type taxonomy. Keep that source data lossless in a
new `play_by_play_v3` table, and keep the existing legacy `play_by_play` table
untouched.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "nba.sqlite"
STATS_BASE = "https://stats.nba.com/stats"
NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

GAME_COLUMNS = (
    "season_id", "team_id_home", "team_abbreviation_home", "team_name_home", "game_id", "game_date",
    "matchup_home", "wl_home", "min", "fgm_home", "fga_home", "fg_pct_home", "fg3m_home", "fg3a_home",
    "fg3_pct_home", "ftm_home", "fta_home", "ft_pct_home", "oreb_home", "dreb_home", "reb_home",
    "ast_home", "stl_home", "blk_home", "tov_home", "pf_home", "pts_home", "plus_minus_home",
    "video_available_home", "team_id_away", "team_abbreviation_away", "team_name_away", "matchup_away",
    "wl_away", "fgm_away", "fga_away", "fg_pct_away", "fg3m_away", "fg3a_away", "fg3_pct_away",
    "ftm_away", "fta_away", "ft_pct_away", "oreb_away", "dreb_away", "reb_away", "ast_away",
    "stl_away", "blk_away", "tov_away", "pf_away", "pts_away", "plus_minus_away", "video_available_away",
    "season_type",
)

PBP_V3_COLUMNS = (
    "game_id", "season_id", "season", "season_type", "game_date", "action_number", "action_id", "period",
    "clock", "team_id", "team_tricode", "person_id", "player_name", "player_name_i", "x_legacy", "y_legacy",
    "shot_distance", "shot_result", "is_field_goal", "score_home", "score_away", "points_total", "location",
    "description", "action_type", "sub_type", "video_available", "shot_value", "raw_json",
)


def nba_get(endpoint: str, params: dict[str, Any], *, timeout: int = 30, attempts: int = 4) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{STATS_BASE}/{endpoint}?{query}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=NBA_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network/API transient
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(2.0 * attempt, 8.0))
    raise RuntimeError(f"NBA API request failed after {attempts} attempts: {url}: {last_error}")


def first_result_set(data: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    sets = data.get("resultSets") or data.get("resultSet") or []
    if isinstance(sets, dict):
        sets = [sets]
    if not sets:
        return [], []
    first = sets[0]
    return list(first.get("headers") or []), list(first.get("rowSet") or [])


def dict_rows(headers: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(headers, row)) for row in rows]


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("CREATE INDEX IF NOT EXISTS idx_game_game_id ON game(game_id)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS play_by_play_v3 (
            game_id TEXT NOT NULL,
            season_id TEXT,
            season INTEGER,
            season_type TEXT,
            game_date TEXT,
            action_number INTEGER NOT NULL,
            action_id INTEGER,
            period INTEGER,
            clock TEXT,
            team_id TEXT,
            team_tricode TEXT,
            person_id TEXT,
            player_name TEXT,
            player_name_i TEXT,
            x_legacy INTEGER,
            y_legacy INTEGER,
            shot_distance INTEGER,
            shot_result TEXT,
            is_field_goal INTEGER,
            score_home TEXT,
            score_away TEXT,
            points_total INTEGER,
            location TEXT,
            description TEXT,
            action_type TEXT,
            sub_type TEXT,
            video_available INTEGER,
            shot_value INTEGER,
            raw_json TEXT,
            PRIMARY KEY (game_id, action_number, action_id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_pbp_v3_season ON play_by_play_v3(season_id, season_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pbp_v3_player ON play_by_play_v3(person_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pbp_v3_action ON play_by_play_v3(action_type, sub_type)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS nba_api_ingest_log (
            season TEXT NOT NULL,
            season_type TEXT NOT NULL,
            game_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            game_rows INTEGER NOT NULL DEFAULT 0,
            pbp_v3_rows INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (season, season_type, game_id)
        )
        """
    )
    con.commit()


def fetch_game_rows(season: str, season_type: str) -> list[dict[str, Any]]:
    data = nba_get(
        "leaguegamefinder",
        {
            "LeagueID": "00",
            "Season": season,
            "SeasonType": season_type,
        },
    )
    headers, rows = first_result_set(data)
    return dict_rows(headers, rows)


def game_record_from_team_rows(game_id: str, rows: list[dict[str, Any]], season_type: str) -> dict[str, Any] | None:
    if len(rows) < 2:
        return None
    home = next((row for row in rows if " vs. " in str(row.get("MATCHUP", ""))), None)
    away = next((row for row in rows if " @ " in str(row.get("MATCHUP", ""))), None)
    if home is None or away is None:
        return None
    return {
        "season_id": home.get("SEASON_ID"),
        "team_id_home": home.get("TEAM_ID"),
        "team_abbreviation_home": home.get("TEAM_ABBREVIATION"),
        "team_name_home": home.get("TEAM_NAME"),
        "game_id": game_id,
        "game_date": home.get("GAME_DATE"),
        "matchup_home": home.get("MATCHUP"),
        "wl_home": home.get("WL"),
        "min": home.get("MIN"),
        "fgm_home": home.get("FGM"),
        "fga_home": home.get("FGA"),
        "fg_pct_home": home.get("FG_PCT"),
        "fg3m_home": home.get("FG3M"),
        "fg3a_home": home.get("FG3A"),
        "fg3_pct_home": home.get("FG3_PCT"),
        "ftm_home": home.get("FTM"),
        "fta_home": home.get("FTA"),
        "ft_pct_home": home.get("FT_PCT"),
        "oreb_home": home.get("OREB"),
        "dreb_home": home.get("DREB"),
        "reb_home": home.get("REB"),
        "ast_home": home.get("AST"),
        "stl_home": home.get("STL"),
        "blk_home": home.get("BLK"),
        "tov_home": home.get("TOV"),
        "pf_home": home.get("PF"),
        "pts_home": home.get("PTS"),
        "plus_minus_home": home.get("PLUS_MINUS"),
        "video_available_home": None,
        "team_id_away": away.get("TEAM_ID"),
        "team_abbreviation_away": away.get("TEAM_ABBREVIATION"),
        "team_name_away": away.get("TEAM_NAME"),
        "matchup_away": away.get("MATCHUP"),
        "wl_away": away.get("WL"),
        "fgm_away": away.get("FGM"),
        "fga_away": away.get("FGA"),
        "fg_pct_away": away.get("FG_PCT"),
        "fg3m_away": away.get("FG3M"),
        "fg3a_away": away.get("FG3A"),
        "fg3_pct_away": away.get("FG3_PCT"),
        "ftm_away": away.get("FTM"),
        "fta_away": away.get("FTA"),
        "ft_pct_away": away.get("FT_PCT"),
        "oreb_away": away.get("OREB"),
        "dreb_away": away.get("DREB"),
        "reb_away": away.get("REB"),
        "ast_away": away.get("AST"),
        "stl_away": away.get("STL"),
        "blk_away": away.get("BLK"),
        "tov_away": away.get("TOV"),
        "pf_away": away.get("PF"),
        "pts_away": away.get("PTS"),
        "plus_minus_away": away.get("PLUS_MINUS"),
        "video_available_away": None,
        "season_type": season_type,
    }


def upsert_game(con: sqlite3.Connection, record: dict[str, Any]) -> None:
    # The shipped archive has no uniqueness constraint on game.game_id and may
    # contain duplicate imported rows. Replace the targeted game atomically
    # instead of relying on ON CONFLICT.
    con.execute("DELETE FROM game WHERE game_id = ?", (record.get("game_id"),))
    columns = [col for col in GAME_COLUMNS if col in record]
    quoted = ", ".join(f'"{col}"' for col in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f'INSERT INTO game ({quoted}) VALUES ({placeholders})'
    con.execute(sql, [record.get(col) for col in columns])


def fetch_pbp_v3(game_id: str) -> list[dict[str, Any]]:
    data = nba_get("playbyplayv3", {"GameID": game_id, "StartPeriod": 0, "EndPeriod": 14})
    return list(((data.get("game") or {}).get("actions") or []))


def pbp_record(action: dict[str, Any], *, game_id: str, season_id: str, season: str, season_type: str, game_date: str | None) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "season_id": season_id,
        "season": int(season.split("-")[0]) + 1,
        "season_type": season_type,
        "game_date": game_date,
        "action_number": action.get("actionNumber"),
        "action_id": action.get("actionId"),
        "period": action.get("period"),
        "clock": action.get("clock"),
        "team_id": action.get("teamId"),
        "team_tricode": action.get("teamTricode"),
        "person_id": action.get("personId"),
        "player_name": action.get("playerName"),
        "player_name_i": action.get("playerNameI"),
        "x_legacy": action.get("xLegacy"),
        "y_legacy": action.get("yLegacy"),
        "shot_distance": action.get("shotDistance"),
        "shot_result": action.get("shotResult"),
        "is_field_goal": action.get("isFieldGoal"),
        "score_home": action.get("scoreHome"),
        "score_away": action.get("scoreAway"),
        "points_total": action.get("pointsTotal"),
        "location": action.get("location"),
        "description": action.get("description"),
        "action_type": action.get("actionType"),
        "sub_type": action.get("subType"),
        "video_available": action.get("videoAvailable"),
        "shot_value": action.get("shotValue"),
        "raw_json": json.dumps(action, separators=(",", ":"), ensure_ascii=False),
    }


def replace_pbp_v3(con: sqlite3.Connection, records: list[dict[str, Any]], game_id: str) -> None:
    con.execute("DELETE FROM play_by_play_v3 WHERE game_id = ?", (game_id,))
    if not records:
        return
    columns = list(PBP_V3_COLUMNS)
    quoted = ", ".join(f'"{col}"' for col in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f'INSERT OR REPLACE INTO play_by_play_v3 ({quoted}) VALUES ({placeholders})'
    con.executemany(sql, ([record.get(col) for col in columns] for record in records))


def grouped_by_game(team_rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in team_rows:
        grouped.setdefault(str(row.get("GAME_ID")), []).append(row)
    return grouped


def update_season(con: sqlite3.Connection, *, season: str, season_type: str, delay: float, limit_games: int | None, skip_existing: bool) -> tuple[int, int, int]:
    team_rows = fetch_game_rows(season, season_type)
    games = grouped_by_game(team_rows)
    ordered_game_ids = sorted(games)
    if limit_games is not None:
        ordered_game_ids = ordered_game_ids[:limit_games]
    season_id = str(team_rows[0].get("SEASON_ID")) if team_rows else ""
    print(f"{season} {season_type}: fetched {len(team_rows)} team-game rows -> {len(games)} games; processing {len(ordered_game_ids)}")
    game_count = 0
    pbp_games = 0
    pbp_rows = 0
    for idx, game_id in enumerate(ordered_game_ids, start=1):
        if skip_existing:
            existing = con.execute(
                "SELECT pbp_v3_rows FROM nba_api_ingest_log WHERE season=? AND season_type=? AND game_id=?",
                (season, season_type, game_id),
            ).fetchone()
            if existing and int(existing[0] or 0) > 0:
                continue
        record = game_record_from_team_rows(game_id, games[game_id], season_type)
        if record is None:
            print(f"WARN missing home/away pair for {game_id}", file=sys.stderr)
            continue
        upsert_game(con, record)
        game_count += 1
        actions = fetch_pbp_v3(game_id)
        pbp_records = [
            pbp_record(action, game_id=game_id, season_id=season_id, season=season, season_type=season_type, game_date=record.get("game_date"))
            for action in actions
            if action.get("actionNumber") is not None
        ]
        replace_pbp_v3(con, pbp_records, game_id)
        pbp_games += 1
        pbp_rows += len(pbp_records)
        con.execute(
            """
            INSERT INTO nba_api_ingest_log(season, season_type, game_id, game_rows, pbp_v3_rows)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(season, season_type, game_id) DO UPDATE SET
                fetched_at=CURRENT_TIMESTAMP,
                game_rows=excluded.game_rows,
                pbp_v3_rows=excluded.pbp_v3_rows
            """,
            (season, season_type, game_id, len(pbp_records)),
        )
        con.commit()
        if idx == 1 or idx % 25 == 0 or idx == len(ordered_game_ids):
            print(f"  {idx}/{len(ordered_game_ids)} {game_id}: pbp_v3_rows={len(pbp_records)}")
        if delay:
            time.sleep(delay)
    return game_count, pbp_games, pbp_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--season", action="append", required=True, help="NBA season label, e.g. 2023-24. Repeatable.")
    parser.add_argument("--season-type", action="append", choices=["Regular Season", "Playoffs"], help="Repeatable. Defaults to Regular Season.")
    parser.add_argument("--delay", type=float, default=0.6, help="Delay between per-game PBP requests.")
    parser.add_argument("--limit-games", type=int, default=None, help="Debug/test: process only first N games per season/type.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip games already logged with nonzero PBP rows.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = args.db.expanduser().resolve()
    if not db.is_file():
        raise FileNotFoundError(db)
    con = sqlite3.connect(db)
    try:
        ensure_schema(con)
        totals = [0, 0, 0]
        season_types = args.season_type or ["Regular Season"]
        for season in args.season:
            for season_type in season_types:
                game_count, pbp_games, pbp_rows = update_season(
                    con,
                    season=season,
                    season_type=season_type,
                    delay=args.delay,
                    limit_games=args.limit_games,
                    skip_existing=args.skip_existing,
                )
                totals[0] += game_count
                totals[1] += pbp_games
                totals[2] += pbp_rows
        print(f"DONE game_rows_upserted={totals[0]} pbp_games={totals[1]} pbp_v3_rows={totals[2]}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
