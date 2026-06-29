"""Player Generator empirical pool and position-neighbor model workflow.

This module owns the editor-side workflow that turns complete 2K export runs
(stats + attributes + tendencies) into a reusable SQL-backed candidate pool and
the latest position-neighbor model artifact consumed by player_rules.py.

Core contract:
- 2K exported sim stats are the link between 2K field packages and IRL stats.
- Compare PG only to PG, SG only to SG, SF only to SF, PF only to PF, C only to C.
- No position weights and no cross-position blending.
- NBA Master SQL provides IRL target stats/positions.
- 2K run exports provide sim-output stats plus actual 2K attributes/tendencies to transfer.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from game_port import _person_name_keys

POSITIONS = ("PG", "SG", "SF", "PF", "C")
_GENERATOR_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _GENERATOR_DIR.parents[1]
_SOURCE_ROOT = _GENERATOR_DIR / "NBA Player Data"
_PLAYER_POOL_DIR = _SOURCE_ROOT / "player_generation_pool"
RUNS_DIR = Path("outputs/current_active_stat_extractor_runs/Pull from DATA runs")
OUTPUT_DIR = _PLAYER_POOL_DIR
MASTER_SQLITE = _SOURCE_ROOT / "NBA_DATA_Master.sqlite"
POOL_SQLITE = _PLAYER_POOL_DIR / "player_generation_pool.sqlite"
OUT_PREFIX = "POSITION_STAT_NEIGHBOR_MODEL_"
MERGED_MODEL_SQLITE = OUTPUT_DIR / "POSITION_STAT_NEIGHBOR_MODEL.sqlite"
REQUIRED_RUN_FILES = ("current_active_player_stats.csv", "current_active_player_attributes.csv", "current_active_player_tendencies.csv")
BASE_COLS = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
FEATURES = (
    "pts_per36",
    "fga_per36",
    "fg_pct",
    "x3pa_per36",
    "x3p_pct",
    "e_fg_percent",
    "fta_per36",
    "ft_pct",
    "ast_per36",
    "orb_per36",
    "drb_per36",
    "stl_per36",
    "blk_per36",
    "tov_per36",
    "pf_per36",
    "games",
    "mp_per_game",
    "pts_per100",
    "fga_per100",
    "x3pa_per100",
    "fta_per100",
    "ast_per100",
    "orb_per100",
    "drb_per100",
    "trb_per100",
    "stl_per100",
    "blk_per100",
    "tov_per100",
    "pf_per100",
    "player_o_rtg",
    "player_d_rtg",
    "per",
    "ts_percent",
    "x3p_ar",
    "f_tr",
    "orb_percent",
    "drb_percent",
    "trb_percent",
    "ast_percent",
    "stl_percent",
    "blk_percent",
    "tov_percent",
    "usg_percent",
    "ows",
    "dws",
    "ws",
    "ws_48",
    "obpm",
    "dbpm",
    "bpm",
    "vorp",
    "avg_dist_fga",
    "percent_fga_from_x2p_range",
    "percent_fga_from_x0_3_range",
    "percent_fga_from_x3_10_range",
    "percent_fga_from_x10_16_range",
    "percent_fga_from_x16_3p_range",
    "percent_fga_from_x3p_range",
    "fg_percent_from_x2p_range",
    "fg_percent_from_x0_3_range",
    "fg_percent_from_x3_10_range",
    "fg_percent_from_x10_16_range",
    "fg_percent_from_x16_3p_range",
    "fg_percent_from_x3p_range",
    "percent_assisted_x2p_fg",
    "percent_assisted_x3p_fg",
    "percent_dunks_of_fga",
    "num_of_dunks",
    "percent_corner_3s_of_3pa",
    "corner_3_point_percent",
    "team_o_rtg",
    "team_d_rtg",
    "team_n_rtg",
    "team_pace",
    "team_srs",
    "team_ts_percent",
    "team_x3p_ar",
    "team_e_fg_percent",
    "team_tov_percent",
    "team_orb_percent",
    "team_drb_percent",
    "team_opp_e_fg_percent",
    "all_star",
    "all_nba",
    "all_defense",
    "award_share",
    "mvp_share",
    "dpoy_share",
    "all_team_vote_share",
)
VITAL_COLUMNS = ("height_inches", "height_cm", "weight_pounds", "weight_kg")
REQUIRED_LIVE_STAT_FIELDS = {
    "Assists",
    "Blocks",
    "Defensive Rebounds",
    "Field Goals Attempted",
    "Field Goals Made",
    "Fouls",
    "Free Throws Attempted",
    "Free Throws Made",
    "Minutes",
    "Offensive Rebounds",
    "Points",
    "Steals",
    "Three Pointers Attempted",
    "Three Pointers Made",
    "Turnovers",
}
@dataclass(frozen=True)
class PlayerGenerationPoolRequest:
    root: Path = _REPO_ROOT
    force: bool = False

    def normalized(self) -> "PlayerGenerationPoolRequest":
        return PlayerGenerationPoolRequest(root=Path(self.root).resolve(), force=bool(self.force))


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def player_pool_dir() -> Path:
    return _PLAYER_POOL_DIR


def pool_database_path(root: Path | None = None) -> Path:
    _ = root
    return POOL_SQLITE


def position_stat_neighbor_model_path(sources: Sequence[str]) -> Path:
    _ = sources
    return MERGED_MODEL_SQLITE


def complete_run_ids(root: Path | None = None) -> tuple[str, ...]:
    project_root = _REPO_ROOT if root is None else Path(root).resolve()
    base = project_root / RUNS_DIR
    rows: list[tuple[int, str]] = []
    for path in base.iterdir() if base.exists() else ():
        if path.is_dir() and path.name.startswith("run_"):
            suffix = path.name.split("_", 1)[-1]
            if suffix.isdigit() and all((path / name).is_file() for name in REQUIRED_RUN_FILES):
                rows.append((int(suffix), path.name))
    return tuple(name for _num, name in sorted(rows))


def run_file_signature(root: Path, runs: Sequence[str]) -> dict[str, dict[str, float | int]]:
    project_root = Path(root).resolve()
    signature: dict[str, dict[str, float | int]] = {}
    for run_id in runs:
        run_dir = project_root / RUNS_DIR / run_id
        for name in REQUIRED_RUN_FILES:
            stat = (run_dir / name).stat()
            signature[f"{run_id}/{name}"] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
    return signature


def _connect_pool() -> sqlite3.Connection:
    POOL_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(POOL_SQLITE)


def _ensure_pool_export_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pool_export_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            season INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            stats_rows INTEGER NOT NULL,
            attribute_rows INTEGER NOT NULL,
            tendency_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pool_export_rows (
            snapshot_id TEXT NOT NULL,
            row_type TEXT NOT NULL,
            row_json TEXT NOT NULL,
            FOREIGN KEY(snapshot_id) REFERENCES pool_export_snapshots(snapshot_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pool_export_rows_snapshot_type ON pool_export_rows(snapshot_id, row_type);
        """
    )


def stored_pool_snapshot_ids() -> tuple[str, ...]:
    if not POOL_SQLITE.is_file():
        return ()
    with sqlite3.connect(POOL_SQLITE) as connection:
        _ensure_pool_export_tables(connection)
        rows = connection.execute("SELECT snapshot_id FROM pool_export_snapshots ORDER BY created_at, snapshot_id").fetchall()
    return tuple(str(row[0]) for row in rows)


def _next_snapshot_id(connection: sqlite3.Connection) -> str:
    _ensure_pool_export_tables(connection)
    rows = connection.execute("SELECT snapshot_id FROM pool_export_snapshots WHERE snapshot_id LIKE 'editor_capture_%'").fetchall()
    numbers = []
    for (snapshot_id,) in rows:
        suffix = str(snapshot_id).rsplit("_", 1)[-1]
        if suffix.isdigit():
            numbers.append(int(suffix))
    return f"editor_capture_{max(numbers, default=0) + 1:03d}"


def pool_source_ids(root: Path | None = None) -> tuple[str, ...]:
    return (*complete_run_ids(root), *stored_pool_snapshot_ids())


def source_signature(root: Path, sources: Sequence[str]) -> dict[str, Any]:
    signature: dict[str, Any] = {}
    run_sources = [source for source in sources if str(source).startswith("run_")]
    if run_sources:
        signature.update(run_file_signature(root, run_sources))
    snapshot_sources = [source for source in sources if not str(source).startswith("run_")]
    if snapshot_sources and POOL_SQLITE.is_file():
        with sqlite3.connect(POOL_SQLITE) as connection:
            _ensure_pool_export_tables(connection)
            for snapshot_id in snapshot_sources:
                row = connection.execute(
                    "SELECT created_at, stats_rows, attribute_rows, tendency_rows FROM pool_export_snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    signature[f"snapshot/{snapshot_id}"] = {
                        "created_at": str(row[0]),
                        "stats_rows": int(row[1]),
                        "attribute_rows": int(row[2]),
                        "tendency_rows": int(row[3]),
                    }
    return signature


def _pool_manifest_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    with sqlite3.connect(path) as connection:
        try:
            rows = connection.execute("SELECT key, value FROM pool_manifest").fetchall()
        except sqlite3.Error:
            return {}
    return {str(key): str(value) for key, value in rows}


def _pool_is_current(root: Path, sources: Sequence[str]) -> bool:
    manifest = _pool_manifest_values(pool_database_path())
    if not manifest:
        return False
    if json.loads(manifest.get("source_runs", "[]")) != list(sources):
        return False
    return json.loads(manifest.get("run_file_signature", "{}")) == source_signature(root, sources)


def as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        value = float(v)
        return None if math.isnan(value) else value
    s = str(v).strip()
    if not s or s.upper() in {"NA", "NAN", "NULL", "NONE"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_div(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d is None or d == 0:
        return None
    return n / d


def per36(total: Optional[float], minutes: Optional[float]) -> Optional[float]:
    r = safe_div(total, minutes)
    return None if r is None else r * 36.0


def parse_positions(pos_text: object) -> tuple[str, ...]:
    text = str(pos_text or "").upper()
    compact = re.sub(r"[^A-Z]+", "", text)
    position_map = {
        "G": ("PG", "SG"),
        "GF": ("SG", "SF"),
        "FG": ("SF", "SG"),
        "F": ("SF", "PF"),
        "FC": ("PF", "C"),
        "CF": ("C", "PF"),
    }
    mapped = position_map.get(compact)
    if mapped:
        return mapped
    found = []
    for pos in POSITIONS:
        if re.search(rf"\b{pos}\b", text):
            found.append(pos)
    return tuple(dict.fromkeys(p for p in found if p in POSITIONS))


def live_features(stats: Dict[str, str]) -> Dict[str, Optional[float]]:
    minutes = as_float(stats.get("Minutes"))
    return {
        "pts_per36": per36(as_float(stats.get("Points")), minutes),
        "fga_per36": per36(as_float(stats.get("Field Goals Attempted")), minutes),
        "fg_pct": safe_div(as_float(stats.get("Field Goals Made")), as_float(stats.get("Field Goals Attempted"))),
        "x3pa_per36": per36(as_float(stats.get("Three Pointers Attempted")), minutes),
        "x3p_pct": safe_div(as_float(stats.get("Three Pointers Made")), as_float(stats.get("Three Pointers Attempted"))),
        "e_fg_percent": safe_div((as_float(stats.get("Field Goals Made")) or 0.0) + 0.5 * (as_float(stats.get("Three Pointers Made")) or 0.0), as_float(stats.get("Field Goals Attempted"))),
        "fta_per36": per36(as_float(stats.get("Free Throws Attempted")), minutes),
        "ft_pct": safe_div(as_float(stats.get("Free Throws Made")), as_float(stats.get("Free Throws Attempted"))),
        "ast_per36": per36(as_float(stats.get("Assists")), minutes),
        "orb_per36": per36(as_float(stats.get("Offensive Rebounds")), minutes),
        "drb_per36": per36(as_float(stats.get("Defensive Rebounds")), minutes),
        "stl_per36": per36(as_float(stats.get("Steals")), minutes),
        "blk_per36": per36(as_float(stats.get("Blocks")), minutes),
        "tov_per36": per36(as_float(stats.get("Turnovers")), minutes),
        "pf_per36": per36(as_float(stats.get("Fouls")), minutes),
        "games": as_float(stats.get("Games") or stats.get("G")),
        "mp_per_game": None,
    }


def live_vitals(stats: Dict[str, str], master: Dict[str, Any]) -> Dict[str, Optional[float]]:
    height_inches = as_float(stats.get("height_inches"))
    height_cm = as_float(stats.get("height_cm"))
    if height_inches is None and height_cm is not None:
        height_inches = height_cm / 2.54
    if height_cm is None and height_inches is not None:
        height_cm = height_inches * 2.54
    if height_inches is None:
        height_inches = as_float(master.get("height_inches"))
        if height_inches is not None:
            height_cm = height_inches * 2.54

    weight_pounds = as_float(stats.get("weight_pounds") or stats.get("weight"))
    weight_kg = as_float(stats.get("weight_kg"))
    if weight_pounds is None and weight_kg is not None:
        weight_pounds = weight_kg / 0.45359237
    if weight_kg is None and weight_pounds is not None:
        weight_kg = weight_pounds * 0.45359237
    if weight_pounds is None:
        weight_pounds = as_float(master.get("weight_pounds"))
        if weight_pounds is not None:
            weight_kg = weight_pounds * 0.45359237

    return {
        "height_inches": None if height_inches is None else round(float(height_inches), 4),
        "height_cm": None if height_cm is None else round(float(height_cm), 4),
        "weight_pounds": None if weight_pounds is None else round(float(weight_pounds), 4),
        "weight_kg": None if weight_kg is None else round(float(weight_kg), 4),
    }


def _feature_columns_sql() -> str:
    return ",\n                ".join(f'"{column}" REAL' for column in (*VITAL_COLUMNS, *FEATURES))


def _candidate_pool_insert_sql() -> str:
    columns = ("run_id", "player_index", "player_label", "master_player", "master_player_id", "position", *VITAL_COLUMNS, *FEATURES)
    quoted = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO candidate_pool ({quoted}) VALUES ({placeholders})"


def _candidate_pool_values(row: dict[str, Any]) -> tuple[Any, ...]:
    feature_payload = row.get("features", {}) if isinstance(row.get("features"), dict) else {}
    vital_payload = row.get("vitals", {}) if isinstance(row.get("vitals"), dict) else {}
    return (
        row.get("run_id"),
        row.get("player_index"),
        row.get("player_label"),
        row.get("master_player"),
        row.get("master_player_id"),
        row.get("position"),
        *(vital_payload.get(column, row.get(column)) for column in VITAL_COLUMNS),
        *(feature_payload.get(feature, row.get(feature)) for feature in FEATURES),
    )


def _table_name(connection: sqlite3.Connection, sheet: str) -> str:
    row = connection.execute("SELECT table_name FROM workbook_tables WHERE sheet_name = ?", (sheet,)).fetchone()
    if row is None:
        raise KeyError(f"workbook sheet not found: {sheet}")
    return str(row[0])


def _sheet_rows(connection: sqlite3.Connection, sheet: str) -> list[dict[str, Any]]:
    table = _table_name(connection, sheet)
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def _player_team_key(row: dict[str, Any]) -> tuple[int, str, str]:
    return (int(row.get("season") or 0), str(row.get("player_id") or "").strip().upper(), str(row.get("team") or row.get("tm") or "").strip().upper())


@lru_cache(maxsize=1)
def _master_feature_index() -> dict[str, tuple[dict[str, Any], ...]]:
    if not MASTER_SQLITE.is_file():
        return {}
    with sqlite3.connect(MASTER_SQLITE) as connection:
        player_info = {str(row.get("player_id") or "").strip().upper(): row for row in _sheet_rows(connection, "Player Info")}
        season_rows = _sheet_rows(connection, "Player Season Info")
        per_game = {_player_team_key(row): row for row in _sheet_rows(connection, "Player Per Game")}
        per_36 = {_player_team_key(row): row for row in _sheet_rows(connection, "Player Per 36 min")}
        per_100 = {_player_team_key(row): row for row in _sheet_rows(connection, "Player Per 100 Poss")}
        advanced = {_player_team_key(row): row for row in _sheet_rows(connection, "Advanced")}
        shooting = {_player_team_key(row): row for row in _sheet_rows(connection, "Player Shooting")}
        team_summary = {(int(row.get("season") or 0), str(row.get("abbreviation") or "").strip().upper()): row for row in _sheet_rows(connection, "Team Summaries")}
        all_star = {(int(row.get("season") or 0), str(row.get("player_id") or "").strip().upper()) for row in _sheet_rows(connection, "All Star Selections")}
        all_teams = _sheet_rows(connection, "All Teams")
        award_rows = _sheet_rows(connection, "Player Award Shares")
        vote_rows = _sheet_rows(connection, "All team Voting")

    all_team_context: dict[tuple[int, str], dict[str, float]] = {}
    for row in all_teams:
        key = (int(row.get("season") or 0), str(row.get("player_id") or "").strip().upper())
        typ = str(row.get("type") or "").upper()
        number = as_float(row.get("number_tm")) or 0.0
        if "NBA" in typ:
            all_team_context.setdefault(key, {})["all_nba"] = max(all_team_context.setdefault(key, {}).get("all_nba", 0.0), max(1.0, 4.0 - number))
        if "DEF" in typ:
            all_team_context.setdefault(key, {})["all_defense"] = max(all_team_context.setdefault(key, {}).get("all_defense", 0.0), max(1.0, 3.0 - number))

    award_context: dict[tuple[int, str], dict[str, float]] = {}
    for row in award_rows:
        key = (int(row.get("season") or 0), str(row.get("player_id") or "").strip().upper())
        share = as_float(row.get("share"))
        if share is None:
            continue
        bucket = award_context.setdefault(key, {})
        bucket["award_share"] = max(bucket.get("award_share", 0.0), share)
        award = str(row.get("award") or "").upper()
        if "MVP" in award and "FINAL" not in award:
            bucket["mvp_share"] = max(bucket.get("mvp_share", 0.0), share)
        if "DPOY" in award or "DEFENSIVE" in award:
            bucket["dpoy_share"] = max(bucket.get("dpoy_share", 0.0), share)
    for row in vote_rows:
        key = (int(row.get("season") or 0), str(row.get("player_id") or "").strip().upper())
        share = as_float(row.get("share"))
        if share is not None:
            award_context.setdefault(key, {})["all_team_vote_share"] = max(award_context.setdefault(key, {}).get("all_team_vote_share", 0.0), share)

    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in season_rows:
        season = int(row.get("season") or 0)
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if not season or not player_id or not team or (len(team) == 3 and team[0].isdigit() and team[1:] == "TM"):
            continue
        key = (season, player_id, team)
        identity = player_info.get(player_id, {})
        features = _sql_feature_values(
            identity=identity,
            per_game=per_game.get(key, {}),
            per_36=per_36.get(key, {}),
            per_100=per_100.get(key, {}),
            advanced=advanced.get(key, {}),
            shooting=shooting.get(key, {}),
            team_summary=team_summary.get((season, team), {}),
            awards={
                "all_star": 1.0 if (season, player_id) in all_star else None,
                **all_team_context.get((season, player_id), {}),
                **award_context.get((season, player_id), {}),
            },
        )
        positions = parse_positions(row.get("pos") or identity.get("pos"))
        candidate = {
            "player": row.get("player") or identity.get("player") or player_id,
            "player_id": player_id,
            "season": season,
            "team": team,
            "positions": positions,
            "features": features,
        }
        for name_key in _person_name_keys(candidate["player"], player_id):
            by_name.setdefault(name_key, []).append(candidate)
    return {key: tuple(rows) for key, rows in by_name.items()}


def _sql_feature_values(*, identity: dict[str, Any], per_game: dict[str, Any], per_36: dict[str, Any], per_100: dict[str, Any], advanced: dict[str, Any], shooting: dict[str, Any], team_summary: dict[str, Any], awards: dict[str, Any]) -> dict[str, Optional[float]]:
    def per36(per36_col: str, per_game_col: str) -> Optional[float]:
        direct = as_float(per_36.get(per36_col))
        if direct is not None:
            return direct
        per_game_value = as_float(per_game.get(per_game_col))
        minutes = as_float(per_game.get("mp_per_game"))
        if per_game_value is None:
            return None
        if minutes in (None, 0):
            return per_game_value
        return per_game_value * 36.0 / minutes

    values: dict[str, Optional[float]] = {
        "pts_per36": per36("pts_per_36_min", "pts_per_game"),
        "fga_per36": per36("fga_per_36_min", "fga_per_game"),
        "fg_pct": as_float(per_game.get("fg_percent")),
        "x3pa_per36": per36("x3pa_per_36_min", "x3pa_per_game"),
        "x3p_pct": as_float(per_game.get("x3p_percent")),
        "e_fg_percent": as_float(per_100.get("e_fg_percent")) or as_float(per_game.get("e_fg_percent")),
        "fta_per36": per36("fta_per_36_min", "fta_per_game"),
        "ft_pct": as_float(per_game.get("ft_percent")),
        "ast_per36": per36("ast_per_36_min", "ast_per_game"),
        "orb_per36": per36("orb_per_36_min", "orb_per_game"),
        "drb_per36": per36("drb_per_36_min", "drb_per_game"),
        "stl_per36": per36("stl_per_36_min", "stl_per_game"),
        "blk_per36": per36("blk_per_36_min", "blk_per_game"),
        "tov_per36": per36("tov_per_36_min", "tov_per_game"),
        "pf_per36": per36("pf_per_36_min", "pf_per_game"),
        "games": as_float(per_game.get("g")),
        "mp_per_game": as_float(per_game.get("mp_per_game")),
        "pts_per100": as_float(per_100.get("pts_per_100_poss")),
        "fga_per100": as_float(per_100.get("fga_per_100_poss")),
        "x3pa_per100": as_float(per_100.get("x3pa_per_100_poss")),
        "fta_per100": as_float(per_100.get("fta_per_100_poss")),
        "ast_per100": as_float(per_100.get("ast_per_100_poss")),
        "orb_per100": as_float(per_100.get("orb_per_100_poss")),
        "drb_per100": as_float(per_100.get("drb_per_100_poss")),
        "trb_per100": as_float(per_100.get("trb_per_100_poss")),
        "stl_per100": as_float(per_100.get("stl_per_100_poss")),
        "blk_per100": as_float(per_100.get("blk_per_100_poss")),
        "tov_per100": as_float(per_100.get("tov_per_100_poss")),
        "pf_per100": as_float(per_100.get("pf_per_100_poss")),
        "player_o_rtg": as_float(per_100.get("o_rtg")),
        "player_d_rtg": as_float(per_100.get("d_rtg")),
        "height_inches": as_float(identity.get("ht_in_in")),
        "weight_pounds": as_float(identity.get("wt")),
    }
    for column in (
        "per", "ts_percent", "x3p_ar", "f_tr", "orb_percent", "drb_percent", "trb_percent", "ast_percent", "stl_percent", "blk_percent", "tov_percent", "usg_percent", "ows", "dws", "ws", "ws_48", "obpm", "dbpm", "bpm", "vorp",
    ):
        values[column] = as_float(advanced.get(column))
    for column in (
        "avg_dist_fga", "percent_fga_from_x2p_range", "percent_fga_from_x0_3_range", "percent_fga_from_x3_10_range", "percent_fga_from_x10_16_range", "percent_fga_from_x16_3p_range", "percent_fga_from_x3p_range", "fg_percent_from_x2p_range", "fg_percent_from_x0_3_range", "fg_percent_from_x3_10_range", "fg_percent_from_x10_16_range", "fg_percent_from_x16_3p_range", "fg_percent_from_x3p_range", "percent_assisted_x2p_fg", "percent_assisted_x3p_fg", "percent_dunks_of_fga", "num_of_dunks", "percent_corner_3s_of_3pa", "corner_3_point_percent",
    ):
        values[column] = as_float(shooting.get(column))
    for source, target in (
        ("o_rtg", "team_o_rtg"), ("d_rtg", "team_d_rtg"), ("n_rtg", "team_n_rtg"), ("pace", "team_pace"), ("srs", "team_srs"), ("ts_percent", "team_ts_percent"), ("x3p_ar", "team_x3p_ar"), ("e_fg_percent", "team_e_fg_percent"), ("tov_percent", "team_tov_percent"), ("orb_percent", "team_orb_percent"), ("drb_percent", "team_drb_percent"), ("opp_e_fg_percent", "team_opp_e_fg_percent"),
    ):
        values[target] = as_float(team_summary.get(source))
    for column in ("all_star", "all_nba", "all_defense", "award_share", "mvp_share", "dpoy_share", "all_team_vote_share"):
        values[column] = as_float(awards.get(column))
    return values


def _master_features_for_live(stats: dict[str, str], positions: tuple[str, ...]) -> dict[str, Any]:
    index = _master_feature_index()
    matches: list[dict[str, Any]] = []
    for name_key in _person_name_keys(stats.get("player_label")):
        matches.extend(index.get(name_key, ()))
    if positions:
        matches = [row for row in matches if not row.get("positions") or set(positions).intersection(row.get("positions", ())) ]
    if not matches:
        return {}
    live = live_features(stats)
    scored: list[tuple[float, dict[str, Any]]] = []
    scales = {feature: (0.0, 1.0) for feature in FEATURES}
    for row in matches:
        dist, common = _feature_distance(live, row["features"], scales, features=("pts_per36", "fga_per36", "fg_pct", "x3pa_per36", "x3p_pct", "fta_per36", "ft_pct", "ast_per36", "orb_per36", "drb_per36", "stl_per36", "blk_per36", "tov_per36", "pf_per36"))
        if dist is not None and common >= 3:
            scored.append((dist, row))
    if scored:
        return min(scored, key=lambda item: item[0])[1]
    return matches[0]


def _feature_distance(a: dict[str, Optional[float]], b: dict[str, Optional[float]], scales: dict[str, tuple[float, float]], *, features: tuple[str, ...]) -> tuple[Optional[float], int]:
    parts: list[float] = []
    for feature in features:
        av = a.get(feature)
        bv = b.get(feature)
        if av is None or bv is None:
            continue
        scale = scales.get(feature, (0.0, 1.0))[1] or 1.0
        parts.append(((float(av) - float(bv)) / scale) ** 2)
    if not parts:
        return None, 0
    return math.sqrt(sum(parts) / len(parts)), len(parts)


def _stored_snapshot_rows(snapshot_id: str) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    if not POOL_SQLITE.is_file():
        raise FileNotFoundError(f"missing player pool SQL: {POOL_SQLITE}")
    with sqlite3.connect(POOL_SQLITE) as connection:
        _ensure_pool_export_tables(connection)
        rows = connection.execute(
            "SELECT row_type, row_json FROM pool_export_rows WHERE snapshot_id = ? ORDER BY rowid",
            (snapshot_id,),
        ).fetchall()
    by_type: dict[str, dict[int, dict[str, str]]] = {"stats": {}, "attributes": {}, "tendencies": {}}
    for row_type, row_json in rows:
        payload = {str(key): str(value) for key, value in json.loads(str(row_json)).items()}
        player_index = int(payload["player_index"])
        by_type[str(row_type)][player_index] = payload
    return by_type["stats"], by_type["attributes"], by_type["tendencies"]


def _source_export_rows(root: Path, source_id: str) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    if source_id.startswith("run_"):
        run_dir = root / RUNS_DIR / source_id
        return (
            {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_stats.csv")},
            {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_attributes.csv")},
            {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_tendencies.csv")},
        )
    return _stored_snapshot_rows(source_id)


def load_candidates(root: Path, runs: Sequence[str] | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    candidates: List[Dict[str, Any]] = []
    match_rows: List[Dict[str, Any]] = []
    fieldnames: list[str] = []
    for run_id in tuple(runs or pool_source_ids(root)):
        stats_rows, attrs_rows, tends_rows = _source_export_rows(root, run_id)
        if not fieldnames and attrs_rows and tends_rows:
            attr_fields = [c for c in next(iter(attrs_rows.values())).keys() if c not in BASE_COLS]
            tend_fields = [c for c in next(iter(tends_rows.values())).keys() if c not in BASE_COLS]
            fieldnames = [f"Attribute::{c}" for c in attr_fields] + [f"Tendency::{c}" for c in tend_fields]
        for idx, stats in stats_rows.items():
            label = stats.get("player_label", "")
            positions = parse_positions(stats.get("primary_position"))
            match_rows.append({
                "run_id": run_id,
                "player_index": idx,
                "live_player_label": label,
                "matched": bool(positions),
                "master_player": label,
                "master_player_id": str(idx),
                "positions": ";".join(positions),
            })
            if not positions:
                continue
            fields: Dict[str, float] = {}
            for col, val in attrs_rows.get(idx, {}).items():
                if col in BASE_COLS:
                    continue
                v = as_float(val)
                if v is not None:
                    fields[f"Attribute::{col}"] = v
            for col, val in tends_rows.get(idx, {}).items():
                if col in BASE_COLS:
                    continue
                v = as_float(val)
                if v is not None:
                    fields[f"Tendency::{col}"] = v
            master = _master_features_for_live(stats, positions)
            feats = {**live_features(stats), **(master.get("features") or {})}
            vitals = live_vitals(stats, {"height_inches": feats.get("height_inches"), "weight_pounds": feats.get("weight_pounds")})
            features_with_body = {**feats, "height_inches": vitals.get("height_inches"), "weight_pounds": vitals.get("weight_pounds")}
            master_player = str(master.get("player") or label)
            master_player_id = str(master.get("player_id") or idx)
            for pos in positions:
                candidates.append({
                    "run_id": run_id,
                    "player_index": idx,
                    "player_label": label,
                    "master_player": master_player,
                    "master_player_id": master_player_id,
                    "position": pos,
                    "features": features_with_body,
                    "vitals": vitals,
                    "fields": fields,
                })
    return candidates, match_rows, fieldnames



def _create_model_manifest_table(connection: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    connection.execute("DROP TABLE IF EXISTS model_manifest")
    connection.execute("CREATE TABLE model_manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO model_manifest VALUES (?, ?)",
        ((str(key), json.dumps(value) if isinstance(value, (dict, list, tuple)) else str(value)) for key, value in manifest.items()),
    )


def write_model_database(
    model_path: Path,
    *,
    manifest: dict[str, Any],
    candidate_rows: Sequence[dict[str, Any]],
    match_rows: Sequence[dict[str, Any]],
    neighbor_rows: Sequence[dict[str, Any]],
    suggestion_rows: Sequence[dict[str, Any]],
) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if model_path.exists():
        model_path.unlink()
    feature_columns_sql = _feature_columns_sql()
    insert_sql = _candidate_pool_insert_sql()
    with sqlite3.connect(model_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            f"""
            CREATE TABLE candidate_pool (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                player_label TEXT NOT NULL,
                master_player TEXT NOT NULL,
                master_player_id TEXT NOT NULL,
                position TEXT NOT NULL,
                {feature_columns_sql}
            );
            CREATE TABLE player_name_matches (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                live_player_label TEXT NOT NULL,
                matched INTEGER NOT NULL,
                master_player TEXT NOT NULL,
                master_player_id TEXT NOT NULL,
                positions TEXT NOT NULL
            );
            CREATE TABLE irl_to_2k_neighbors (
                target_player TEXT NOT NULL,
                target_player_id TEXT NOT NULL,
                target_team TEXT NOT NULL,
                position TEXT NOT NULL,
                neighbor_rank INTEGER NOT NULL,
                distance REAL NOT NULL,
                common_features INTEGER NOT NULL,
                neighbor_run_id TEXT NOT NULL,
                neighbor_player_index INTEGER NOT NULL,
                neighbor_live_label TEXT NOT NULL,
                neighbor_master_player TEXT NOT NULL,
                neighbor_master_player_id TEXT NOT NULL
            );
            CREATE TABLE suggested_field_values (
                target_player TEXT NOT NULL,
                target_player_id TEXT NOT NULL,
                target_team TEXT NOT NULL,
                position TEXT NOT NULL,
                Type TEXT NOT NULL,
                "Input Field" TEXT NOT NULL,
                suggested_top1 INTEGER NOT NULL,
                suggested_top5_median REAL NOT NULL,
                neighbor_count INTEGER NOT NULL,
                top_neighbor TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            insert_sql,
            (_candidate_pool_values(row) for row in candidate_rows),
        )
        connection.executemany(
            "INSERT INTO player_name_matches VALUES (?, ?, ?, ?, ?, ?, ?)",
            ((row.get("run_id"), row.get("player_index"), row.get("live_player_label"), 1 if row.get("matched") in (True, "True", "true", 1, "1") else 0, row.get("master_player"), row.get("master_player_id"), row.get("positions")) for row in match_rows),
        )
        connection.executemany(
            "INSERT INTO irl_to_2k_neighbors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((row.get("target_player"), row.get("target_player_id"), row.get("target_team"), row.get("position"), row.get("neighbor_rank"), row.get("distance"), row.get("common_features"), row.get("neighbor_run_id"), row.get("neighbor_player_index"), row.get("neighbor_live_label"), row.get("neighbor_master_player"), row.get("neighbor_master_player_id")) for row in neighbor_rows),
        )
        connection.executemany(
            "INSERT INTO suggested_field_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((row.get("target_player"), row.get("target_player_id"), row.get("target_team"), row.get("position"), row.get("Type"), row.get("Input Field"), row.get("suggested_top1"), row.get("suggested_top5_median"), row.get("neighbor_count"), row.get("top_neighbor")) for row in suggestion_rows),
        )
        _create_model_manifest_table(connection, manifest)
        connection.execute("CREATE INDEX idx_suggested_target ON suggested_field_values(target_player_id, target_team, position)")
        connection.execute("CREATE INDEX idx_suggested_field ON suggested_field_values(Type, \"Input Field\")")
        connection.commit()


def write_pool_database(
    root: Path,
    *,
    runs: Sequence[str],
    candidates: Sequence[Dict[str, Any]],
    match_rows: Sequence[Dict[str, Any]],
    fieldnames: Sequence[str],
    model_path: Path,
) -> dict[str, Any]:
    db_path = pool_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    signature = source_signature(root, runs)
    feature_columns_sql = _feature_columns_sql()
    insert_sql = _candidate_pool_insert_sql()
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            f"""
            DROP TABLE IF EXISTS pool_runs;
            DROP TABLE IF EXISTS player_name_matches;
            DROP TABLE IF EXISTS candidate_pool;
            DROP TABLE IF EXISTS candidate_fields;
            DROP TABLE IF EXISTS pool_manifest;
            CREATE TABLE pool_runs (
                run_id TEXT PRIMARY KEY,
                run_path TEXT NOT NULL,
                stats_path TEXT NOT NULL,
                attributes_path TEXT NOT NULL,
                tendencies_path TEXT NOT NULL
            );
            CREATE TABLE player_name_matches (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                live_player_label TEXT NOT NULL,
                matched INTEGER NOT NULL,
                master_player TEXT NOT NULL,
                master_player_id TEXT NOT NULL,
                positions TEXT NOT NULL
            );
            CREATE TABLE candidate_pool (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                player_label TEXT NOT NULL,
                master_player TEXT NOT NULL,
                master_player_id TEXT NOT NULL,
                position TEXT NOT NULL,
                {feature_columns_sql}
            );
            CREATE TABLE candidate_fields (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                position TEXT NOT NULL,
                field_type TEXT NOT NULL,
                input_field TEXT NOT NULL,
                value REAL NOT NULL
            );
            CREATE TABLE pool_manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        for run_id in runs:
            if str(run_id).startswith("run_"):
                run_dir = root / RUNS_DIR / run_id
                values = (
                    run_id,
                    str(run_dir),
                    str(run_dir / "current_active_player_stats.csv"),
                    str(run_dir / "current_active_player_attributes.csv"),
                    str(run_dir / "current_active_player_tendencies.csv"),
                )
            else:
                values = (run_id, str(POOL_SQLITE), "pool_export_rows:stats", "pool_export_rows:attributes", "pool_export_rows:tendencies")
            connection.execute("INSERT INTO pool_runs VALUES (?, ?, ?, ?, ?)", values)
        connection.executemany(
            "INSERT INTO player_name_matches VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    row["run_id"],
                    int(row["player_index"]),
                    row["live_player_label"],
                    1 if row["matched"] else 0,
                    row["master_player"],
                    row["master_player_id"],
                    row["positions"],
                )
                for row in match_rows
            ),
        )
        for candidate in candidates:
            connection.execute(insert_sql, _candidate_pool_values(candidate))
            for field_key, value in candidate["fields"].items():
                field_type, input_field = field_key.split("::", 1)
                connection.execute(
                    "INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)",
                    (candidate["run_id"], int(candidate["player_index"]), candidate["position"], field_type, input_field, float(value)),
                )
        manifest = {
            "source_runs": json.dumps(list(runs)),
            "run_file_signature": json.dumps(signature, sort_keys=True),
            "model_path": str(model_path),
            "candidate_rows": str(len({(c["run_id"], c["player_index"]) for c in candidates})),
            "candidate_position_rows": str(len(candidates)),
            "fieldnames": json.dumps(list(fieldnames)),
        }
        connection.executemany("INSERT INTO pool_manifest VALUES (?, ?)", manifest.items())
        connection.commit()
    return {
        "pool_db": str(db_path),
        "source_runs": list(runs),
        "candidate_rows": int(manifest["candidate_rows"]),
        "candidate_position_rows": int(manifest["candidate_position_rows"]),
    }


def _display(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("display_value", ""))


def _raw_int(value: dict[str, Any] | None) -> int | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("raw_value")
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def capture_active_roster_pool_rows(model: Any, *, progress_callback: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded_players = sorted(model.loaded_items.get("Players", {}).values(), key=lambda item: int(item.index))
    if not loaded_players:
        raise RuntimeError("no loaded Players; load the editor player list before adding the current roster to Pool SQL")
    loaded_teams = sorted(model.loaded_items.get("Teams", {}).values(), key=lambda item: int(item.index))
    if not loaded_teams:
        raise RuntimeError("no loaded Teams; load Teams before adding the current roster to Pool SQL")
    players_by_address = {int(player.address): player for player in loaded_players}
    team_player_entries = sorted(
        (
            (int(str(entry.normalized_name).replace("PLAYER", "")), entry)
            for entry in model.grouped_fields("Teams").get("Team Players", {}).get("Team Players", ())
            if str(entry.normalized_name).startswith("PLAYER") and str(entry.normalized_name).replace("PLAYER", "").isdigit()
        ),
        key=lambda item: item[0],
    )[:15]
    players: list[tuple[Any, Any, int, int]] = []
    for team_slot, team in enumerate(loaded_teams[:30]):
        for roster_slot, entry in team_player_entries:
            player_pointer = _raw_int(model.read_entry_value(entry, index=team.index))
            if not player_pointer:
                continue
            player = players_by_address.get(int(player_pointer))
            if player is not None:
                players.append((player, team, team_slot, roster_slot))
    if not players:
        raise RuntimeError("no loaded Players found in loaded Teams player slots")
    grouped = model.grouped_fields("Players")
    season_id_entries = list(grouped.get("Stats", {}).get("Season IDs", ()))
    stat_id_entries = [entry for entry in season_id_entries if model.is_player_season_id_selector_entry(entry)]
    stat_detail_entries = [
        entry
        for entry in season_id_entries
        if model.is_player_selected_stat_detail_entry(entry) and entry.display_name in REQUIRED_LIVE_STAT_FIELDS
    ]
    if not stat_detail_entries:
        raise RuntimeError("no selected stat detail fields found in Players / Stats / Season IDs")
    position_entries = {
        str(entry.normalized_name).upper(): entry
        for section_groups in grouped.values()
        for group_entries in section_groups.values()
        for entry in group_entries
        if str(entry.normalized_name).upper() in {"POSITION", "SECONDARYPOSITION"}
    }
    vital_entries = {
        str(entry.normalized_name).upper(): entry
        for section_groups in grouped.values()
        for group_entries in section_groups.values()
        for entry in group_entries
        if str(entry.normalized_name).upper() in {"HEIGHT", "WEIGHT", "WEIGHTKG"}
    }
    attribute_entries = [entry for group_entries in grouped.get("Attributes", {}).values() for entry in group_entries]
    tendency_entries = [entry for group_entries in grouped.get("Tendencies", {}).values() for entry in group_entries]
    if not attribute_entries:
        raise RuntimeError("no Players / Attributes fields found")
    if not tendency_entries:
        raise RuntimeError("no Players / Tendencies fields found")
    selector = "Current Year Stat ID"
    stats_rows: list[dict[str, Any]] = []
    attribute_rows: list[dict[str, Any]] = []
    tendency_rows: list[dict[str, Any]] = []
    total_units = max(1, len(players) * 3 + 1)
    completed_units = 0
    last_progress_percent = -1

    def emit_progress(message: str, *, force: bool = False) -> None:
        nonlocal last_progress_percent
        if progress_callback is None:
            return
        percent = int(completed_units * 100 / total_units)
        if force or percent != last_progress_percent:
            last_progress_percent = percent
            progress_callback(completed_units, total_units, message)

    emit_progress(f"Capturing 0/{len(players)} loaded team-slot players into Pool SQL...", force=True)
    for progress_slot, (player, team, team_slot, roster_slot) in enumerate(players, start=1):
        identity = {
            "team_slot": team_slot,
            "team_index": team.index,
            "team_label": team.label,
            "roster_slot": roster_slot,
            "player_index": player.index,
            "player_label": player.label,
        }
        stat_row: dict[str, Any] = dict(identity)
        for column, normalized_name in (("primary_position", "POSITION"), ("secondary_position", "SECONDARYPOSITION")):
            entry = position_entries.get(normalized_name)
            stat_row[column] = "" if entry is None else _display(model.read_entry_value(entry, index=player.index))
        stat_id = None
        for entry in stat_id_entries:
            if entry.display_name == selector or entry.normalized_name == "CURRENTYEARSTATID":
                stat_id = _raw_int(model.read_entry_value(entry, index=player.index))
                break
        stat_row["current_year_stat_id"] = "" if stat_id is None else stat_id
        height_entry = vital_entries.get("HEIGHT")
        weight_entry = vital_entries.get("WEIGHT")
        weight_kg_entry = vital_entries.get("WEIGHTKG")
        stat_row["height_inches"] = "" if height_entry is None else _display(model.read_entry_value(height_entry, index=player.index))
        stat_row["weight_pounds"] = "" if weight_entry is None else _display(model.read_entry_value(weight_entry, index=player.index))
        stat_row["weight_kg"] = "" if weight_kg_entry is None else _display(model.read_entry_value(weight_kg_entry, index=player.index))
        if stat_id is not None and stat_id > 0 and stat_id != 0xFFFF:
            for entry in stat_detail_entries:
                stat_row[entry.display_name] = _display(model.read_entry_value(entry, index=player.index, stat_selector=selector))
        else:
            for entry in stat_detail_entries:
                stat_row[entry.display_name] = ""
        stats_rows.append(stat_row)
        completed_units += 1
        emit_progress(f"Captured stats for {progress_slot}/{len(players)} loaded team-slot players...")

        attribute_row: dict[str, Any] = dict(identity)
        for entry in attribute_entries:
            attribute_row[f"{entry.group} / {entry.display_name}"] = _display(model.read_entry_value(entry, index=player.index))
        attribute_rows.append(attribute_row)
        completed_units += 1
        emit_progress(f"Captured attributes for {progress_slot}/{len(players)} loaded team-slot players...")

        tendency_row: dict[str, Any] = dict(identity)
        for entry in tendency_entries:
            tendency_row[f"{entry.group} / {entry.display_name}"] = _display(model.read_entry_value(entry, index=player.index))
        tendency_rows.append(tendency_row)
        completed_units += 1
        emit_progress(f"Captured tendencies for {progress_slot}/{len(players)} loaded team-slot players...")
    return stats_rows, attribute_rows, tendency_rows


def add_current_roster_to_player_generation_pool(model: Any, *, season: int = 2026, progress_callback: Any | None = None) -> dict[str, Any]:
    stats_rows, attribute_rows, tendency_rows = capture_active_roster_pool_rows(model, progress_callback=progress_callback)
    total_units = max(1, len(stats_rows) * 3 + 1)
    if progress_callback is not None:
        progress_callback(max(0, total_units - 1), total_units, "Writing current roster snapshot to Pool SQL...")
    with _connect_pool() as connection:
        _ensure_pool_export_tables(connection)
        snapshot_id = _next_snapshot_id(connection)
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO pool_export_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, int(season), created_at, "editor_active_roster", len(stats_rows), len(attribute_rows), len(tendency_rows)),
        )
        for row_type, rows in (("stats", stats_rows), ("attributes", attribute_rows), ("tendencies", tendency_rows)):
            connection.executemany(
                "INSERT INTO pool_export_rows VALUES (?, ?, ?)",
                ((snapshot_id, row_type, json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in rows),
            )
        connection.commit()
    if progress_callback is not None:
        progress_callback(total_units, total_units, "Added current roster snapshot to Pool SQL.")
    manifest = _pool_manifest_values(pool_database_path())
    return {
        "status": "Current roster snapshot added. Run Sync Player Pool SQL to rebuild the neighbor model when needed.",
        "pool_db": str(pool_database_path()),
        "output_dir": manifest.get("model_path") or manifest.get("model_dir", ""),
        "candidate_rows": int(manifest.get("candidate_rows", "0")),
        "candidate_position_rows": int(manifest.get("candidate_position_rows", "0")),
        "added_snapshot_id": snapshot_id,
        "added_stats_rows": len(stats_rows),
        "added_attribute_rows": len(attribute_rows),
        "added_tendency_rows": len(tendency_rows),
        "sync_required": True,
    }


def sync_player_generation_pool(request: PlayerGenerationPoolRequest | None = None, *, progress_callback: Any | None = None) -> dict[str, Any]:
    """Ensure the Player Generator SQL pool and latest neighbor artifact match complete run exports."""
    total_steps = 4

    def emit_progress(step: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0, min(total_steps, step)), total_steps, message)

    emit_progress(0, "Checking player pool sources...")
    normalized = (request or PlayerGenerationPoolRequest()).normalized()
    root = normalized.root
    force = normalized.force
    runs = pool_source_ids(root)
    if not runs:
        raise FileNotFoundError("no player pool sources found; use Add Current Roster to Pool SQL from the editor")
    if not force and _pool_is_current(root, runs):
        manifest = _pool_manifest_values(pool_database_path())
        emit_progress(total_steps, "Player generation pool already current.")
        return {
            "status": "Player generation pool already current.",
            "pool_db": str(pool_database_path()),
            "output_dir": manifest.get("model_path") or manifest.get("model_dir", ""),
            "source_runs": json.loads(manifest.get("source_runs", "[]")),
            "candidate_rows": int(manifest.get("candidate_rows", "0")),
            "candidate_position_rows": int(manifest.get("candidate_position_rows", "0")),
        }

    model_path = position_stat_neighbor_model_path(runs).resolve()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    emit_progress(1, f"Loading {len(runs)} player pool source(s)...")
    candidates, match_rows, fieldnames = load_candidates(root, runs)
    emit_progress(2, "Preparing candidate model rows...")
    candidate_rows = []
    for c in candidates:
        row = {
            "run_id": c["run_id"],
            "player_index": c["player_index"],
            "player_label": c["player_label"],
            "master_player": c["master_player"],
            "master_player_id": c["master_player_id"],
            "position": c["position"],
        }
        for column in VITAL_COLUMNS:
            row[column] = c.get("vitals", {}).get(column)
        for feat in FEATURES:
            row[feat] = c["features"].get(feat)
        candidate_rows.append(row)

    manifest = {
        "output_dir": str(model_path),
        "model_sqlite": str(model_path),
        "pool_sqlite": str(pool_database_path()),
        "source_runs": [str((root / RUNS_DIR / run).resolve()) for run in runs],
        "rule": "same-position stat-profile neighbors only; no position weights; no cross-position blending",
        "features": list(FEATURES),
        "vital_columns": list(VITAL_COLUMNS),
        "live_rows": len(match_rows),
        "matched_live_rows": sum(1 for r in match_rows if r["matched"]),
        "candidate_rows": len({(c["run_id"], c["player_index"]) for c in candidates}),
        "candidate_position_rows": len(candidates),
        "candidate_rows_by_position": {pos: sum(1 for c in candidates if c["position"] == pos) for pos in POSITIONS},
        "created_files": [model_path.name],
        "status": f"Rebuilt player generation pool from {len(runs)} runs.",
    }
    emit_progress(3, "Writing player pool SQLite...")
    write_model_database(
        model_path,
        manifest=manifest,
        candidate_rows=candidate_rows,
        match_rows=match_rows,
        neighbor_rows=(),
        suggestion_rows=(),
    )
    pool_manifest = write_pool_database(
        root,
        runs=runs,
        candidates=candidates,
        match_rows=match_rows,
        fieldnames=fieldnames,
        model_path=model_path,
    )
    manifest["pool_summary"] = pool_manifest
    emit_progress(total_steps, "Player pool SQL sync complete.")
    return manifest


def ensure_player_generation_pool_current(*, root: Path | None = None, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    return sync_player_generation_pool(PlayerGenerationPoolRequest(root=_REPO_ROOT if root is None else Path(root), force=force), progress_callback=progress_callback)


def build_position_stat_neighbor_model(root: Path, *, force: bool = False) -> dict[str, Any]:
    """Backward-compatible API for old callers; program workflow uses sync_player_generation_pool."""
    return ensure_player_generation_pool_current(root=root, force=force)


def next_output_dir(root: Path) -> Path:
    base = root / OUTPUT_DIR
    nums = []
    for p in base.iterdir() if base.exists() else []:
        if p.is_dir() and p.name.startswith(OUT_PREFIX):
            suffix = p.name[len(OUT_PREFIX):]
            if suffix.isdigit():
                nums.append(int(suffix))
    return base / f"{OUT_PREFIX}{max(nums, default=0) + 1:03d}"

