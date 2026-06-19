#!/usr/bin/env python3
"""Import Basketball-Reference 2025-26 (season=2026) player/team tables into NBA_DATA_Master.sqlite.

Stdlib-only scraper. It updates the existing workbook-shaped SQLite cache in-place.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import time
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

USER_AGENT = "Mozilla/5.0 (compatible; nba2k-editor-generator/1.0)"
BASE = "https://www.basketball-reference.com"
SEASON = 2026
LEAGUE = "NBA"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"

PLAYER_PAGES = {
    "player_per_game": ("https://www.basketball-reference.com/leagues/NBA_2026_per_game.html", "per_game_stats"),
    "player_totals": ("https://www.basketball-reference.com/leagues/NBA_2026_totals.html", "totals_stats"),
    "player_per_36_min": ("https://www.basketball-reference.com/leagues/NBA_2026_per_minute.html", "per_minute_stats"),
    "player_per_100_poss": ("https://www.basketball-reference.com/leagues/NBA_2026_per_poss.html", "per_poss"),
    "advanced": ("https://www.basketball-reference.com/leagues/NBA_2026_advanced.html", "advanced"),
    "player_shooting": ("https://www.basketball-reference.com/leagues/NBA_2026_shooting.html", "shooting"),
    "player_play_by_play": ("https://www.basketball-reference.com/leagues/NBA_2026_play-by-play.html", "pbp_stats"),
}

LEAGUE_PAGE = "https://www.basketball-reference.com/leagues/NBA_2026.html"
TEAM_TABLES = {
    "team_stats_per_game": "per_game-team",
    "team_totals": "totals-team",
    "team_stats_per_100_pos": "per_poss-team",
    "opponent_stats_per_game": "per_game-opponent",
    "opponent_totals": "totals-opponent",
    "opponent_stats_per_100_poss": "per_poss-opponent",
    "team_summaries": "advanced-team",
}

PLAYER_COMMON = {
    "age": "age",
    "team": "team_name_abbr",
    "pos": "pos",
    "g": "games",
    "gs": "games_started",
}

PLAYER_MAPS: dict[str, dict[str, str]] = {
    "player_per_game": {
        **PLAYER_COMMON,
        "mp_per_game": "mp_per_g",
        "fg_per_game": "fg_per_g",
        "fga_per_game": "fga_per_g",
        "fg_percent": "fg_pct",
        "x3p_per_game": "fg3_per_g",
        "x3pa_per_game": "fg3a_per_g",
        "x3p_percent": "fg3_pct",
        "x2p_per_game": "fg2_per_g",
        "x2pa_per_game": "fg2a_per_g",
        "x2p_percent": "fg2_pct",
        "e_fg_percent": "efg_pct",
        "ft_per_game": "ft_per_g",
        "fta_per_game": "fta_per_g",
        "ft_percent": "ft_pct",
        "orb_per_game": "orb_per_g",
        "drb_per_game": "drb_per_g",
        "trb_per_game": "trb_per_g",
        "ast_per_game": "ast_per_g",
        "stl_per_game": "stl_per_g",
        "blk_per_game": "blk_per_g",
        "tov_per_game": "tov_per_g",
        "pf_per_game": "pf_per_g",
        "pts_per_game": "pts_per_g",
    },
    "player_totals": {
        **PLAYER_COMMON,
        "mp": "mp",
        "fg": "fg",
        "fga": "fga",
        "fg_percent": "fg_pct",
        "x3p": "fg3",
        "x3pa": "fg3a",
        "x3p_percent": "fg3_pct",
        "x2p": "fg2",
        "x2pa": "fg2a",
        "x2p_percent": "fg2_pct",
        "e_fg_percent": "efg_pct",
        "ft": "ft",
        "fta": "fta",
        "ft_percent": "ft_pct",
        "orb": "orb",
        "drb": "drb",
        "trb": "trb",
        "ast": "ast",
        "stl": "stl",
        "blk": "blk",
        "tov": "tov",
        "pf": "pf",
        "pts": "pts",
        "trp_dbl": "trp_dbl",
    },
    "player_per_36_min": {
        **PLAYER_COMMON,
        "mp": "mp",
        "fg_per_36_min": "fg_per_mp",
        "fga_per_36_min": "fga_per_mp",
        "fg_percent": "fg_pct",
        "x3p_per_36_min": "fg3_per_mp",
        "x3pa_per_36_min": "fg3a_per_mp",
        "x3p_percent": "fg3_pct",
        "x2p_per_36_min": "fg2_per_mp",
        "x2pa_per_36_min": "fg2a_per_mp",
        "x2p_percent": "fg2_pct",
        "e_fg_percent": "efg_pct",
        "ft_per_36_min": "ft_per_mp",
        "fta_per_36_min": "fta_per_mp",
        "ft_percent": "ft_pct",
        "orb_per_36_min": "orb_per_mp",
        "drb_per_36_min": "drb_per_mp",
        "trb_per_36_min": "trb_per_mp",
        "ast_per_36_min": "ast_per_mp",
        "stl_per_36_min": "stl_per_mp",
        "blk_per_36_min": "blk_per_mp",
        "tov_per_36_min": "tov_per_mp",
        "pf_per_36_min": "pf_per_mp",
        "pts_per_36_min": "pts_per_mp",
    },
    "player_per_100_poss": {
        **PLAYER_COMMON,
        "mp": "mp",
        "fg_per_100_poss": "fg_per_poss",
        "fga_per_100_poss": "fga_per_poss",
        "fg_percent": "fg_pct",
        "x3p_per_100_poss": "fg3_per_poss",
        "x3pa_per_100_poss": "fg3a_per_poss",
        "x3p_percent": "fg3_pct",
        "x2p_per_100_poss": "fg2_per_poss",
        "x2pa_per_100_poss": "fg2a_per_poss",
        "x2p_percent": "fg2_pct",
        "e_fg_percent": "efg_pct",
        "ft_per_100_poss": "ft_per_poss",
        "fta_per_100_poss": "fta_per_poss",
        "ft_percent": "ft_pct",
        "orb_per_100_poss": "orb_per_poss",
        "drb_per_100_poss": "drb_per_poss",
        "trb_per_100_poss": "trb_per_poss",
        "ast_per_100_poss": "ast_per_poss",
        "stl_per_100_poss": "stl_per_poss",
        "blk_per_100_poss": "blk_per_poss",
        "tov_per_100_poss": "tov_per_poss",
        "pf_per_100_poss": "pf_per_poss",
        "pts_per_100_poss": "pts_per_poss",
        "o_rtg": "off_rtg",
        "d_rtg": "def_rtg",
    },
    "advanced": {
        **PLAYER_COMMON,
        "mp": "mp",
        "per": "per",
        "ts_percent": "ts_pct",
        "x3p_ar": "fg3a_per_fga_pct",
        "f_tr": "fta_per_fga_pct",
        "orb_percent": "orb_pct",
        "drb_percent": "drb_pct",
        "trb_percent": "trb_pct",
        "ast_percent": "ast_pct",
        "stl_percent": "stl_pct",
        "blk_percent": "blk_pct",
        "tov_percent": "tov_pct",
        "usg_percent": "usg_pct",
        "ows": "ows",
        "dws": "dws",
        "ws": "ws",
        "ws_48": "ws_per_48",
        "obpm": "obpm",
        "dbpm": "dbpm",
        "bpm": "bpm",
        "vorp": "vorp",
    },
    "player_shooting": {
        **PLAYER_COMMON,
        "mp": "mp",
        "fg_percent": "fg_pct",
        "avg_dist_fga": "avg_dist",
        "percent_fga_from_x2p_range": "pct_fga_fg2a",
        "percent_fga_from_x0_3_range": "pct_fga_00_03",
        "percent_fga_from_x3_10_range": "pct_fga_03_10",
        "percent_fga_from_x10_16_range": "pct_fga_10_16",
        "percent_fga_from_x16_3p_range": "pct_fga_16_xx",
        "percent_fga_from_x3p_range": "pct_fga_fg3a",
        "fg_percent_from_x2p_range": "fg_pct_fg2a",
        "fg_percent_from_x0_3_range": "fg_pct_00_03",
        "fg_percent_from_x3_10_range": "fg_pct_03_10",
        "fg_percent_from_x10_16_range": "fg_pct_10_16",
        "fg_percent_from_x16_3p_range": "fg_pct_16_xx",
        "fg_percent_from_x3p_range": "fg_pct_fg3a",
        "percent_assisted_x2p_fg": "pct_ast_fg2",
        "percent_assisted_x3p_fg": "pct_ast_fg3",
        "percent_dunks_of_fga": "pct_fga_dunk",
        "num_of_dunks": "fg_dunk",
        "percent_corner_3s_of_3pa": "pct_fg3a_corner3",
        "corner_3_point_percent": "fg_pct_corner3",
        "num_heaves_attempted": "fg3a_heave",
        "num_heaves_made": "fg3_heave",
    },
    "player_play_by_play": {
        **PLAYER_COMMON,
        "mp": "mp",
        "pg_percent": "pct_1",
        "sg_percent": "pct_2",
        "sf_percent": "pct_3",
        "pf_percent": "pct_4",
        "c_percent": "pct_5",
        "on_court_plus_minus_per_100_poss": "plus_minus_on",
        "net_plus_minus_per_100_poss": "plus_minus_net",
        "bad_pass_turnover": "tov_bad_pass",
        "lost_ball_turnover": "tov_lost_ball",
        "shooting_foul_committed": "fouls_shooting",
        "offensive_foul_committed": "fouls_offensive",
        "shooting_foul_drawn": "drawn_shooting",
        "offensive_foul_drawn": "drawn_offensive",
        "points_generated_by_assists": "astd_pts",
        "and1": "and1s",
        "fga_blocked": "own_shots_blk",
    },
}

TEAM_STAT_MAP = {
    "g": "g",
    "mp_per_game": "mp",
    "fg_per_game": "fg",
    "fga_per_game": "fga",
    "fg_percent": "fg_pct",
    "x3p_per_game": "fg3",
    "x3pa_per_game": "fg3a",
    "x3p_percent": "fg3_pct",
    "x2p_per_game": "fg2",
    "x2pa_per_game": "fg2a",
    "x2p_percent": "fg2_pct",
    "ft_per_game": "ft",
    "fta_per_game": "fta",
    "ft_percent": "ft_pct",
    "orb_per_game": "orb",
    "drb_per_game": "drb",
    "trb_per_game": "trb",
    "ast_per_game": "ast",
    "stl_per_game": "stl",
    "blk_per_game": "blk",
    "tov_per_game": "tov",
    "pf_per_game": "pf",
    "pts_per_game": "pts",
}

TEAM_TOTAL_MAP = {k.replace("_per_game", "") if k.endswith("_per_game") else k: v for k, v in TEAM_STAT_MAP.items()}
TEAM_TOTAL_MAP["mp"] = "mp"

TEAM_P100_MAP = {
    "g": "g",
    "mp": "mp",
    "fg_per_100_poss": "fg",
    "fga_per_100_poss": "fga",
    "fg_percent": "fg_pct",
    "x3p_per_100_poss": "fg3",
    "x3pa_per_100_poss": "fg3a",
    "x3p_percent": "fg3_pct",
    "x2p_per_100_poss": "fg2",
    "x2pa_per_100_poss": "fg2a",
    "x2p_percent": "fg2_pct",
    "ft_per_100_poss": "ft",
    "fta_per_100_poss": "fta",
    "ft_percent": "ft_pct",
    "orb_per_100_poss": "orb",
    "drb_per_100_poss": "drb",
    "trb_per_100_poss": "trb",
    "ast_per_100_poss": "ast",
    "stl_per_100_poss": "stl",
    "blk_per_100_poss": "blk",
    "tov_per_100_poss": "tov",
    "pf_per_100_poss": "pf",
    "pts_per_100_poss": "pts",
}

OPP_TEAM_STAT_MAP = {"g": "g", "mp_per_game": "mp"}
for base, stat in [("fg", "fg"), ("fga", "fga"), ("x3p", "fg3"), ("x3pa", "fg3a"), ("x2p", "fg2"), ("x2pa", "fg2a"), ("ft", "ft"), ("fta", "fta"), ("orb", "orb"), ("drb", "drb"), ("trb", "trb"), ("ast", "ast"), ("stl", "stl"), ("blk", "blk"), ("tov", "tov"), ("pf", "pf"), ("pts", "pts")]:
    OPP_TEAM_STAT_MAP[f"opp_{base}_per_game"] = f"opp_{stat}"
OPP_TEAM_STAT_MAP.update(
    {
        "opp_fg_percent": "opp_fg_pct",
        "opp_x3p_percent": "opp_fg3_pct",
        "opp_x2p_percent": "opp_fg2_pct",
        "opp_ft_percent": "opp_ft_pct",
    }
)

OPP_TOTAL_MAP = {"g": "g", "mp": "mp"}
for base, stat in [("fg", "fg"), ("fga", "fga"), ("fg_percent", "fg_pct"), ("x3p", "fg3"), ("x3pa", "fg3a"), ("x3p_percent", "fg3_pct"), ("x2p", "fg2"), ("x2pa", "fg2a"), ("x2p_percent", "fg2_pct"), ("ft", "ft"), ("fta", "fta"), ("ft_percent", "ft_pct"), ("orb", "orb"), ("drb", "drb"), ("trb", "trb"), ("ast", "ast"), ("stl", "stl"), ("blk", "blk"), ("tov", "tov"), ("pf", "pf"), ("pts", "pts")]:
    OPP_TOTAL_MAP[f"opp_{base}"] = f"opp_{stat}"

OPP_P100_MAP = {"g": "g", "mp": "mp"}
for base, stat in [("fg", "fg"), ("fga", "fga"), ("x3p", "fg3"), ("x3pa", "fg3a"), ("x2p", "fg2"), ("x2pa", "fg2a"), ("ft", "ft"), ("fta", "fta"), ("orb", "orb"), ("drb", "drb"), ("trb", "trb"), ("ast", "ast"), ("stl", "stl"), ("blk", "blk"), ("tov", "tov"), ("pf", "pf"), ("pts", "pts")]:
    OPP_P100_MAP[f"opp_{base}_per_100_poss"] = f"opp_{stat}"
OPP_P100_MAP.update(
    {
        "opp_fg_percent": "opp_fg_pct",
        "opp_x3p_percent": "opp_fg3_pct",
        "opp_x2p_percent": "opp_fg2_pct",
        "opp_ft_percent": "opp_ft_pct",
    }
)

TEAM_SUMMARY_MAP = {
    "age": "age",
    "w": "wins",
    "l": "losses",
    "pw": "wins_pyth",
    "pl": "losses_pyth",
    "mov": "mov",
    "sos": "sos",
    "srs": "srs",
    "o_rtg": "off_rtg",
    "d_rtg": "def_rtg",
    "n_rtg": "net_rtg",
    "pace": "pace",
    "f_tr": "fta_per_fga_pct",
    "x3p_ar": "fg3a_per_fga_pct",
    "ts_percent": "ts_pct",
    "e_fg_percent": "efg_pct",
    "tov_percent": "tov_pct",
    "orb_percent": "orb_pct",
    "ft_fga": "ft_rate",
    "opp_e_fg_percent": "opp_efg_pct",
    "opp_tov_percent": "opp_tov_pct",
    "drb_percent": "drb_pct",
    "opp_ft_fga": "opp_ft_rate",
    "arena": "arena_name",
    "attend": "attendance",
    "attend_g": "attendance_per_g",
}

@dataclass
class Cell:
    stat: str
    text: str = ""
    links: list[str] = field(default_factory=list)

@dataclass
class Row:
    cells: dict[str, Cell]
    links: list[str]

class TableParser(HTMLParser):
    def __init__(self, table_id: str):
        super().__init__(convert_charrefs=True)
        self.table_id = table_id
        self.in_table = False
        self.table_depth = 0
        self.in_row = False
        self.row_class = ""
        self.current: Cell | None = None
        self.cells: list[Cell] = []
        self.rows: list[Row] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: v or "" for k, v in attrs}
        if tag == "table" and d.get("id") == self.table_id:
            self.in_table = True
            self.table_depth = 1
            return
        if not self.in_table:
            return
        if tag == "table":
            self.table_depth += 1
        if tag == "tr":
            self.in_row = True
            self.row_class = d.get("class", "")
            self.cells = []
        elif self.in_row and tag in {"th", "td"} and "data-stat" in d:
            self.current = Cell(d["data-stat"])
        elif self.current is not None and tag == "a" and "href" in d:
            self.current.links.append(d["href"])

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.text += data

    def handle_endtag(self, tag: str) -> None:
        if not self.in_table:
            return
        if tag in {"th", "td"} and self.current is not None:
            self.cells.append(self.current)
            self.current = None
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if "thead" not in self.row_class and self.cells:
                by_stat = {cell.stat: cell for cell in self.cells}
                row_links = [link for cell in self.cells for link in cell.links]
                self.rows.append(Row(by_stat, row_links))
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_table = False


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_table(html: str, table_id: str) -> list[Row]:
    parser = TableParser(table_id)
    parser.feed(html)
    return parser.rows


def text(row: Row, stat: str) -> str:
    return row.cells.get(stat, Cell(stat)).text.strip().replace("*", "")


def clean_value(value: str) -> Any:
    value = value.strip().replace(",", "")
    if value in {"", "None"}:
        return None
    if value.endswith("%"):
        value = value[:-1]
    try:
        if any(ch in value for ch in ".eE"):
            return float(value)
        return int(value)
    except ValueError:
        return value


def player_id_from_row(row: Row) -> str | None:
    for link in row.cells.get("name_display", Cell("name_display")).links:
        if link.startswith("/players/") and link.endswith(".html"):
            return Path(link).stem.lower()
    return None


def team_abbr_from_row(row: Row) -> str | None:
    for link in row.links:
        parts = link.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "teams" and parts[2].endswith(".html"):
            return parts[1]
        if len(parts) >= 2 and parts[0] == "teams":
            return parts[1]
    return None


def db_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f"pragma table_info({table})")]


def insert_rows(con: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = db_columns(con, table)
    wanted = [col for col in columns if any(col in row for row in rows)]
    sql = f"insert into {table} ({', '.join(wanted)}) values ({', '.join(['?'] * len(wanted))})"
    values = [[row.get(col) for col in wanted] for row in rows]
    con.executemany(sql, values)


def initialize_empty_database(db_path: Path, schema_source: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return
    source = sqlite3.connect(schema_source)
    dest = sqlite3.connect(db_path)
    try:
        for _, sql in source.execute(
            "select name, sql from sqlite_master where type='table' and sql is not null order by name"
        ):
            dest.execute(sql)
        for table in ("workbook_tables", "workbook_columns"):
            columns = db_columns(source, table)
            select_cols = ", ".join(columns)
            placeholders = ", ".join(["?"] * len(columns))
            rows = source.execute(f"select {select_cols} from {table}").fetchall()
            dest.executemany(f"insert into {table} ({select_cols}) values ({placeholders})", rows)
        dest.commit()
    finally:
        source.close()
        dest.close()


def copy_existing_player_info(con: sqlite3.Connection, schema_source: Path) -> int:
    source = sqlite3.connect(schema_source)
    source.row_factory = sqlite3.Row
    try:
        wanted_ids = [
            row[0]
            for row in con.execute("select distinct player_id from player_season_info where season=?", (SEASON,)).fetchall()
        ]
        if not wanted_ids:
            return 0
        columns = db_columns(con, "player_info")
        quoted_columns = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join(["?"] * len(columns))
        copied = 0
        for player_id in wanted_ids:
            row = source.execute("select * from player_info where player_id=?", (player_id,)).fetchone()
            if row is None:
                continue
            exists = con.execute("select 1 from player_info where player_id=?", (player_id,)).fetchone()
            if exists:
                continue
            con.execute(
                f"insert into player_info ({quoted_columns}) values ({placeholders})",
                [row[col] for col in columns],
            )
            copied += 1
        return copied
    finally:
        source.close()


def build_player_rows(table: str, html: str, table_id: str, con: sqlite3.Connection) -> list[dict[str, Any]]:
    mapping = PLAYER_MAPS[table]
    rows = []
    for row in parse_table(html, table_id):
        player = text(row, "name_display")
        pid = player_id_from_row(row)
        if not player or not pid:
            continue
        if not text(row, "ranker").isdigit():
            continue
        item: dict[str, Any] = {"season": SEASON, "lg": LEAGUE, "player": player, "player_id": pid}
        for col, stat in mapping.items():
            if stat in row.cells:
                item[col] = clean_value(text(row, stat))
        rows.append(item)
    return rows


def prior_experience(con: sqlite3.Connection, player_id: str) -> int:
    row = con.execute(
        "select experience from player_season_info where player_id=? and experience is not null order by season desc limit 1",
        (player_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return 1
    try:
        return int(row[0]) + 1
    except Exception:
        return 1


def build_player_season_info(per_game_rows: list[dict[str, Any]], con: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for row in per_game_rows:
        out.append(
            {
                "season": SEASON,
                "lg": LEAGUE,
                "player": row.get("player"),
                "player_id": row.get("player_id"),
                "age": row.get("age"),
                "team": row.get("team"),
                "pos": row.get("pos"),
                "experience": prior_experience(con, str(row.get("player_id"))),
            }
        )
    return out


def build_team_rows(table: str, html: str, table_id: str) -> list[dict[str, Any]]:
    if table == "team_summaries":
        mapping = TEAM_SUMMARY_MAP
    elif table == "team_stats_per_game":
        mapping = TEAM_STAT_MAP
    elif table == "team_totals":
        mapping = TEAM_TOTAL_MAP
    elif table == "team_stats_per_100_pos":
        mapping = TEAM_P100_MAP
    elif table == "opponent_stats_per_game":
        mapping = OPP_TEAM_STAT_MAP
    elif table == "opponent_totals":
        mapping = OPP_TOTAL_MAP
    elif table == "opponent_stats_per_100_poss":
        mapping = OPP_P100_MAP
    else:
        raise ValueError(table)

    rows = []
    for row in parse_table(html, table_id):
        team = text(row, "team")
        if not team or not text(row, "ranker").isdigit():
            continue
        abbr = team_abbr_from_row(row)
        playoffs = 1 if "*" in row.cells.get("team", Cell("team")).text else 0
        item: dict[str, Any] = {"season": SEASON, "lg": LEAGUE, "team": team, "abbreviation": abbr, "playoffs": playoffs}
        for col, stat in mapping.items():
            if stat in row.cells:
                item[col] = clean_value(text(row, stat))
        rows.append(item)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema-source", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    initialize_empty_database(args.db, args.schema_source)
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    if not args.no_backup:
        backup = args.db.with_suffix(f".pre2026import.{int(time.time())}.bak")
        shutil.copy2(args.db, backup)
        print(f"backup={backup}")

    player_page_html: dict[str, str] = {}
    for table, (url, table_id) in PLAYER_PAGES.items():
        player_page_html[table] = fetch(url)
        print(f"fetched {table} bytes={len(player_page_html[table])}")

    league_html = fetch(LEAGUE_PAGE)
    print(f"fetched league bytes={len(league_html)}")

    with con:
        target_tables = list(PLAYER_PAGES) + ["player_season_info"] + list(TEAM_TABLES) + ["team_abbrev"]
        for table in target_tables:
            con.execute(f"delete from {table} where season=?", (SEASON,))

        per_game_rows: list[dict[str, Any]] | None = None
        for table, (_, table_id) in PLAYER_PAGES.items():
            rows = build_player_rows(table, player_page_html[table], table_id, con)
            insert_rows(con, table, rows)
            print(f"inserted {table} {len(rows)}")
            if table == "player_per_game":
                per_game_rows = rows
        assert per_game_rows is not None
        psi = build_player_season_info(per_game_rows, con)
        insert_rows(con, "player_season_info", psi)
        print(f"inserted player_season_info {len(psi)}")
        copied_info = copy_existing_player_info(con, args.schema_source)
        print(f"copied existing player_info {copied_info}")

        team_summary_rows: list[dict[str, Any]] | None = None
        for table, table_id in TEAM_TABLES.items():
            rows = build_team_rows(table, league_html, table_id)
            insert_rows(con, table, rows)
            print(f"inserted {table} {len(rows)}")
            if table == "team_summaries":
                team_summary_rows = rows
        if team_summary_rows:
            abbrev_rows = [
                {
                    "season": SEASON,
                    "lg": LEAGUE,
                    "team": row.get("team"),
                    "abbreviation": row.get("abbreviation"),
                    "playoffs": row.get("playoffs"),
                }
                for row in team_summary_rows
            ]
            insert_rows(con, "team_abbrev", abbrev_rows)
            print(f"inserted team_abbrev {len(abbrev_rows)}")

    for table in ["player_per_game", "advanced", "player_shooting", "team_summaries", "team_stats_per_game"]:
        count = con.execute(f"select count(*) from {table} where season=?", (SEASON,)).fetchone()[0]
        print(f"count {table} {count}")

if __name__ == "__main__":
    main()
