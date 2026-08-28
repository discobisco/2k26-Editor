"""Capture and rebuild the Player Generator pool from game-offset-backed data.

Pool package identity is ``(snapshot/run, player_index)``. Player names are not
identity, matching evidence, features, or model inputs. Derived pool columns may
only be calculated from values captured through current game offsets.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

POSITIONS = ("PG", "SG", "SF", "PF", "C")
SEASON_GAMES = 82.0
_GENERATOR_DIR = Path(__file__).resolve().parent
_SOURCE_ROOT = _GENERATOR_DIR / "NBA Player Data"
_PLAYER_POOL_DIR = _SOURCE_ROOT / "player_generation_pool"
POOL_SQLITE = _PLAYER_POOL_DIR / "player_generation_pool.sqlite"
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
    "games_started",
    "mp_per_game",
    "ast_percent",
    "stl_percent",
    "blk_percent",
    "tov_percent",
    "usg_percent",

    "team_points",
    "team_pa",
    "team_poss",
    "team_games",
    "team_fgm",
    "team_fga",
    "team_3pm",
    "team_3pa",
    "team_ftm",
    "team_fta",
    "team_ast",
    "team_orb",
    "team_drb",
    "team_stl",
    "team_blk",
    "team_tov",
    "team_pf",
    "opp_fgm",
    "opp_fga",
    "opp_3pm",
    "opp_3pa",
    "team_o_rtg",
    "team_d_rtg",
    "team_n_rtg",

    "team_ts_percent",
    "team_x3p_ar",
    "team_e_fg_percent",
    "team_tov_percent",
    "team_opp_e_fg_percent",
)
VITAL_COLUMNS = ("height_inches", "height_cm", "weight_pounds", "weight_kg")


def pool_database_path() -> Path:
    return POOL_SQLITE


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
            tendency_rows INTEGER NOT NULL,
            team_stat_rows INTEGER NOT NULL DEFAULT 0
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
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(pool_export_snapshots)")}
    if "team_stat_rows" not in columns:
        connection.execute("ALTER TABLE pool_export_snapshots ADD COLUMN team_stat_rows INTEGER NOT NULL DEFAULT 0")


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


def pool_source_ids() -> tuple[str, ...]:
    return stored_pool_snapshot_ids()


def source_signature(snapshot_ids: Sequence[str]) -> dict[str, Any]:
    signature: dict[str, Any] = {}
    if snapshot_ids and POOL_SQLITE.is_file():
        with sqlite3.connect(POOL_SQLITE) as connection:
            _ensure_pool_export_tables(connection)
            for snapshot_id in snapshot_ids:
                row = connection.execute(
                    "SELECT created_at, stats_rows, attribute_rows, tendency_rows, team_stat_rows FROM pool_export_snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    signature[f"snapshot/{snapshot_id}"] = {
                        "created_at": str(row[0]),
                        "stats_rows": int(row[1]),
                        "attribute_rows": int(row[2]),
                        "tendency_rows": int(row[3]),
                        "team_stat_rows": int(row[4]),
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


def _pool_is_current(snapshot_ids: Sequence[str]) -> bool:
    manifest = _pool_manifest_values(pool_database_path())
    if not manifest:
        return False
    if json.loads(manifest.get("source_snapshots", "[]")) != list(snapshot_ids):
        return False
    return json.loads(manifest.get("snapshot_signature", "{}")) == source_signature(snapshot_ids)


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
    games = as_float(stats.get("Games Played"))
    games_started = as_float(stats.get("Games Started"))
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
        "games": games,
        "games_started": games_started,
        "mp_per_game": safe_div(minutes, games),
    }


def _team_stat_value(stats: Dict[str, str], *keys: str) -> Optional[float]:
    for key in keys:
        value = as_float(stats.get(key))
        if value is not None:
            return value
    return None


def live_team_features(stats: Dict[str, str]) -> Dict[str, Optional[float]]:
    points = _team_stat_value(stats, "POINTS")
    allowed = _team_stat_value(stats, "PA")
    possessions = _team_stat_value(stats, "POSS")
    made = _team_stat_value(stats, "MADE")
    attempted = _team_stat_value(stats, "ATTEMPTED")
    threes_made = _team_stat_value(stats, "3POINTMADE", "3PT_MADE")
    threes_attempted = _team_stat_value(stats, "3POINTATTEMPTED", "3PT_ATTEMPTED")
    free_throw_made = _team_stat_value(stats, "FREETHROWMADE", "FREE_THROWS_MADE")
    free_throw_attempted = _team_stat_value(stats, "FREETHROWATTEMPTED", "FREE_THROWS_ATTEMPTED")
    turnovers = _team_stat_value(stats, "TURNOVER")
    offensive_rebounds = _team_stat_value(stats, "OFFENSIVEREBOUNDS", "OFFENSIVE_REBOUNDS")
    defensive_rebounds = _team_stat_value(stats, "DEFENSEREBOUNDS", "DEFENSIVE_REBOUNDS")
    assists = _team_stat_value(stats, "ASSISTS")
    steals = _team_stat_value(stats, "STEALS")
    blocks = _team_stat_value(stats, "BLOCKS")
    fouls = _team_stat_value(stats, "FOUL")
    opp_made = _team_stat_value(stats, "OFGM")
    opp_attempted = _team_stat_value(stats, "OFGA")
    opp_threes_made = _team_stat_value(stats, "O3PM")
    opp_threes_attempted = _team_stat_value(stats, "O3PA")
    return {
        "team_points": points,
        "team_pa": allowed,
        "team_poss": possessions,
        "team_games": SEASON_GAMES,
        "team_fgm": made,
        "team_fga": attempted,
        "team_3pm": threes_made,
        "team_3pa": threes_attempted,
        "team_ftm": free_throw_made,
        "team_fta": free_throw_attempted,
        "team_ast": assists,
        "team_orb": offensive_rebounds,
        "team_drb": defensive_rebounds,
        "team_stl": steals,
        "team_blk": blocks,
        "team_tov": turnovers,
        "team_pf": fouls,
        "opp_fgm": opp_made,
        "opp_fga": opp_attempted,
        "opp_3pm": opp_threes_made,
        "opp_3pa": opp_threes_attempted,
        "team_o_rtg": None if possessions in (None, 0) or points is None else points * 100.0 / possessions,
        "team_d_rtg": None if possessions in (None, 0) or allowed is None else allowed * 100.0 / possessions,
        "team_n_rtg": None if possessions in (None, 0) or points is None or allowed is None else (points - allowed) * 100.0 / possessions,
        "team_ts_percent": safe_div(points, None if attempted is None or free_throw_attempted is None else 2.0 * (attempted + 0.44 * free_throw_attempted)),
        "team_x3p_ar": safe_div(threes_attempted, attempted),
        "team_e_fg_percent": safe_div((made or 0.0) + 0.5 * (threes_made or 0.0), attempted),
        "team_tov_percent": safe_div(turnovers, possessions),
        "team_opp_e_fg_percent": safe_div((opp_made or 0.0) + 0.5 * (opp_threes_made or 0.0), opp_attempted),
    }


def live_player_team_features(stats: Dict[str, str], team: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    minutes = as_float(stats.get("Minutes"))
    fgm = as_float(stats.get("Field Goals Made"))
    fga = as_float(stats.get("Field Goals Attempted"))
    fta = as_float(stats.get("Free Throws Attempted"))
    ast = as_float(stats.get("Assists"))
    stl = as_float(stats.get("Steals"))
    blk = as_float(stats.get("Blocks"))
    tov = as_float(stats.get("Turnovers"))
    pf = as_float(stats.get("Fouls"))
    team_games = team.get("team_games")
    team_minutes = None if team_games is None else float(team_games) * 240.0
    team_player_minutes = None if team_minutes in (None, 0) else team_minutes / 5.0
    team_possessions = team.get("team_poss")
    team_fgm = team.get("team_fgm")
    team_fga = team.get("team_fga")
    team_fta = team.get("team_fta")
    team_tov = team.get("team_tov")
    opp_fga = team.get("opp_fga")
    opp_3pa = team.get("opp_3pa")
    return {
        "ast_percent": safe_div(ast, None if minutes in (None, 0) or team_minutes in (None, 0) or team_fgm is None or fgm is None else ((minutes / (team_minutes / 5.0)) * team_fgm) - fgm),
        "stl_percent": None if stl is None or minutes in (None, 0) or team_player_minutes in (None, 0) or team_possessions in (None, 0) else stl * team_player_minutes / (minutes * team_possessions),
        "blk_percent": None if blk is None or minutes in (None, 0) or team_player_minutes in (None, 0) or opp_fga is None or opp_3pa is None or opp_fga == opp_3pa else blk * team_player_minutes / (minutes * (opp_fga - opp_3pa)),
        "tov_percent": safe_div(tov, None if fga is None or fta is None or tov is None else fga + 0.44 * fta + tov),
        "usg_percent": None if minutes in (None, 0) or team_player_minutes in (None, 0) or team_fga is None or team_fta is None or team_tov is None else safe_div((fga or 0.0) + 0.44 * (fta or 0.0) + (tov or 0.0), minutes * (team_fga + 0.44 * team_fta + team_tov) / team_player_minutes),
    }


def live_vitals(stats: Dict[str, str]) -> Dict[str, Optional[float]]:
    height_inches = as_float(stats.get("height_inches"))
    height_cm = as_float(stats.get("height_cm"))
    if height_inches is None and height_cm is not None:
        height_inches = height_cm / 2.54
    if height_cm is None and height_inches is not None:
        height_cm = height_inches * 2.54
    weight_pounds = as_float(stats.get("weight_pounds") or stats.get("weight"))
    weight_kg = as_float(stats.get("weight_kg"))
    if weight_pounds is None and weight_kg is not None:
        weight_pounds = weight_kg / 0.45359237
    if weight_kg is None and weight_pounds is not None:
        weight_kg = weight_pounds * 0.45359237

    return {
        "height_inches": None if height_inches is None else round(float(height_inches), 4),
        "height_cm": None if height_cm is None else round(float(height_cm), 4),
        "weight_pounds": None if weight_pounds is None else round(float(weight_pounds), 4),
        "weight_kg": None if weight_kg is None else round(float(weight_kg), 4),
    }


def _feature_columns_sql() -> str:
    columns = (f'"{column}" REAL' for column in (*VITAL_COLUMNS, *FEATURES))
    return ",\n                ".join(columns)


def _candidate_pool_insert_sql() -> str:
    columns = (
        "run_id",
        "player_index",
        "position",
        *VITAL_COLUMNS,
        *FEATURES,
    )
    quoted = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO candidate_pool ({quoted}) VALUES ({placeholders})"


def _candidate_pool_values(row: dict[str, Any]) -> tuple[Any, ...]:
    feature_payload = row.get("features", {}) if isinstance(row.get("features"), dict) else {}
    vital_payload = row.get("vitals", {}) if isinstance(row.get("vitals"), dict) else {}
    return (
        row.get("run_id"),
        row.get("player_index"),
        row.get("position"),
        *(vital_payload.get(column, row.get(column)) for column in VITAL_COLUMNS),
        *(feature_payload.get(feature, row.get(feature)) for feature in FEATURES),
    )


def _stored_snapshot_rows(snapshot_id: str) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]], dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    if not POOL_SQLITE.is_file():
        raise FileNotFoundError(f"missing player pool SQL: {POOL_SQLITE}")
    with sqlite3.connect(POOL_SQLITE) as connection:
        _ensure_pool_export_tables(connection)
        rows = connection.execute(
            "SELECT row_type, row_json FROM pool_export_rows WHERE snapshot_id = ? ORDER BY rowid",
            (snapshot_id,),
        ).fetchall()
    by_type: dict[str, dict[int, dict[str, str]]] = {"stats": {}, "attributes": {}, "tendencies": {}, "team_stats": {}}
    for row_type, row_json in rows:
        payload = {str(key): str(value) for key, value in json.loads(str(row_json)).items()}
        bucket = by_type.get(str(row_type))
        if bucket is None:
            continue
        if str(row_type) == "team_stats":
            bucket[int(payload["team_index"])] = payload
        else:
            bucket[int(payload["player_index"])] = payload
    return by_type["stats"], by_type["attributes"], by_type["tendencies"], by_type["team_stats"]


def load_candidates(snapshot_ids: Sequence[str] | None = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    candidates: List[Dict[str, Any]] = []
    fieldnames: list[str] = []
    for run_id in tuple(snapshot_ids or pool_source_ids()):
        stats_rows, attrs_rows, tends_rows, team_rows = _stored_snapshot_rows(run_id)
        if not fieldnames and attrs_rows and tends_rows:
            attr_fields = [c for c in next(iter(attrs_rows.values())).keys() if c not in BASE_COLS]
            tend_fields = [c for c in next(iter(tends_rows.values())).keys() if c not in BASE_COLS]
            fieldnames = [f"Attribute::{c}" for c in attr_fields] + [f"Tendency::{c}" for c in tend_fields]
        for idx, stats in stats_rows.items():
            positions = parse_positions(stats.get("primary_position"))
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
            team_index = int(stats.get("team_index") or -1)
            live = live_features(stats)
            team_all_features = live_team_features(team_rows.get(team_index, {}))
            team_features = {key: value for key, value in team_all_features.items() if value is not None}
            player_team_features = {key: value for key, value in live_player_team_features(stats, team_all_features).items() if value is not None}
            features = {**live, **team_features, **player_team_features}
            vitals = live_vitals(stats)
            for pos in positions:
                candidates.append({
                    "run_id": run_id,
                    "player_index": idx,
                    "position": pos,
                    "features": features,
                    "vitals": vitals,
                    "fields": fields,
                })
    return candidates, fieldnames


def write_pool_database(
    *,
    snapshot_ids: Sequence[str],
    candidates: Sequence[Dict[str, Any]],
    fieldnames: Sequence[str],
) -> dict[str, Any]:
    db_path = pool_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    signature = source_signature(snapshot_ids)
    feature_columns_sql = _feature_columns_sql()
    insert_sql = _candidate_pool_insert_sql()
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            f"""
            DROP TABLE IF EXISTS pool_runs;
            DROP TABLE IF EXISTS candidate_pool;
            DROP TABLE IF EXISTS candidate_fields;
            DROP TABLE IF EXISTS pool_manifest;
            CREATE TABLE pool_runs (
                run_id TEXT PRIMARY KEY
            );
            CREATE TABLE candidate_pool (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
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
        connection.executemany("INSERT INTO pool_runs VALUES (?)", ((snapshot_id,) for snapshot_id in snapshot_ids))
        for candidate in candidates:
            connection.execute(insert_sql, _candidate_pool_values(candidate))
            for field_key, value in candidate["fields"].items():
                field_type, input_field = field_key.split("::", 1)
                connection.execute(
                    "INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)",
                    (candidate["run_id"], int(candidate["player_index"]), candidate["position"], field_type, input_field, float(value)),
                )
        manifest = {
            "source_snapshots": json.dumps(list(snapshot_ids)),
            "snapshot_signature": json.dumps(signature, sort_keys=True),
            "data_contract": "game-offset-derived inputs to exact captured fields",
            "features": json.dumps(list(FEATURES)),
            "vital_columns": json.dumps(list(VITAL_COLUMNS)),
            "candidate_rows": str(len({(c["run_id"], c["player_index"]) for c in candidates})),
            "candidate_position_rows": str(len(candidates)),
            "fieldnames": json.dumps(list(fieldnames)),
        }
        connection.executemany("INSERT INTO pool_manifest VALUES (?, ?)", manifest.items())
        connection.commit()
    return {
        "pool_db": str(db_path),
        "source_snapshots": list(snapshot_ids),
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


def capture_active_roster_pool_rows(model: Any, *, progress_callback: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded_teams = sorted(model.loaded_items.get("Teams", {}).values(), key=lambda item: int(item.index))
    active_teams = loaded_teams[:30]
    team_slots = {int(team.index): slot for slot, team in enumerate(active_teams)}
    players = sorted(
        model.player_roster_slot_items_for_team_items(active_teams),
        key=lambda row: (
            team_slots[int(row[1]["team_index"])],
            int(row[1]["team_slot"]),
            int(row[0].index),
        ),
    )
    team_stat_entries = list(model.grouped_fields("Teams").get("Team Stats Edit", {}).get("Teams", ()))
    grouped = model.grouped_fields("Players")
    season_id_entries = list(grouped.get("Stats", {}).get("Season IDs", ()))
    stat_detail_entries = [
        entry
        for entry in season_id_entries
        if model.is_player_selected_stat_detail_entry(entry)
    ]
    current_stat_selector = next(
        (
            entry
            for entry in season_id_entries
            if model.is_player_season_id_selector_entry(entry)
            and str(entry.normalized_name).upper() == "CURRENTYEARSTATID"
        ),
        None,
    )
    player_entries = [
        entry
        for section_groups in grouped.values()
        for group_entries in section_groups.values()
        for entry in group_entries
    ]
    position_entries = {
        str(entry.normalized_name).upper(): entry
        for entry in player_entries
        if str(entry.normalized_name).upper() in {"POSITION", "SECONDARYPOSITION"}
    }
    vital_entries = {
        str(entry.normalized_name).upper(): entry
        for entry in player_entries
        if str(entry.normalized_name).upper()
        in {"HEIGHT", "WEIGHT", "WEIGHTKG", "PLAYTYPE1", "PLAYTYPE2", "PLAYTYPE3", "PLAYTYPE4"}
    }
    attribute_entries = [entry for group_entries in grouped.get("Attributes", {}).values() for entry in group_entries]
    tendency_entries = [entry for group_entries in grouped.get("Tendencies", {}).values() for entry in group_entries]
    stats_rows: list[dict[str, Any]] = []
    attribute_rows: list[dict[str, Any]] = []
    tendency_rows: list[dict[str, Any]] = []
    team_stat_rows: list[dict[str, Any]] = []
    total_units = max(1, len(players) * 3 + len(loaded_teams[:30]) + 1)
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
    for team_slot, team in enumerate(active_teams):
        team_row: dict[str, Any] = {"team_slot": team_slot, "team_index": team.index, "team_label": team.label}
        for entry in team_stat_entries:
            team_row[str(entry.normalized_name)] = _display(model.read_entry_value(entry, index=team.index))
        team_stat_rows.append(team_row)
        completed_units += 1
        emit_progress(f"Captured team stats for {team_slot + 1}/{len(loaded_teams[:30])} loaded teams...")

    for progress_slot, (player, placement) in enumerate(players, start=1):
        team_index = int(placement["team_index"])
        team_slot = team_slots[team_index]
        roster_slot = int(placement["team_slot"])
        identity = {
            "team_slot": team_slot,
            "team_index": team_index,
            "team_label": str(placement["team_label"]),
            "roster_slot": roster_slot,
            "player_index": player.index,
            "player_label": player.label,
        }
        stat_row: dict[str, Any] = dict(identity)
        for column, normalized_name in (("primary_position", "POSITION"), ("secondary_position", "SECONDARYPOSITION")):
            entry = position_entries.get(normalized_name)
            stat_row[column] = "" if entry is None else _display(model.read_entry_value_for_item(entry, player))
        if current_stat_selector is None:
            stat_id = None
            current_stat_selector_name = None
        else:
            current_stat_value = model.read_entry_value_for_item(current_stat_selector, player)
            stat_row[current_stat_selector.display_name] = _display(current_stat_value)
            stat_id = _raw_int(current_stat_value)
            current_stat_selector_name = current_stat_selector.display_name
        height_entry = vital_entries.get("HEIGHT")
        weight_entry = vital_entries.get("WEIGHT")
        weight_kg_entry = vital_entries.get("WEIGHTKG")
        stat_row["height_inches"] = "" if height_entry is None else _display(model.read_entry_value_for_item(height_entry, player))
        stat_row["weight_pounds"] = "" if weight_entry is None else _display(model.read_entry_value_for_item(weight_entry, player))
        stat_row["weight_kg"] = "" if weight_kg_entry is None else _display(model.read_entry_value_for_item(weight_kg_entry, player))
        for play_type_number in range(1, 5):
            entry = vital_entries.get(f"PLAYTYPE{play_type_number}")
            stat_row[f"play_type_{play_type_number}"] = (
                "" if entry is None else _display(model.read_entry_value_for_item(entry, player))
            )
        valid_current_stat_slot = isinstance(current_stat_selector_name, str) and isinstance(stat_id, int) and 0 < stat_id < 0xFFFF
        if valid_current_stat_slot:
            for entry in stat_detail_entries:
                stat_row[entry.display_name] = _display(
                    model.read_entry_value_for_item(
                        entry,
                        player,
                        stat_selector=current_stat_selector_name,
                    )
                )
        else:
            for entry in stat_detail_entries:
                stat_row[entry.display_name] = ""
        stats_rows.append(stat_row)
        completed_units += 1
        emit_progress(f"Captured stats for {progress_slot}/{len(players)} loaded team-slot players...")

        attribute_row: dict[str, Any] = dict(identity)
        for entry in attribute_entries:
            attribute_row[f"{entry.group} / {entry.display_name}"] = _display(model.read_entry_value_for_item(entry, player))
        attribute_rows.append(attribute_row)
        completed_units += 1
        emit_progress(f"Captured attributes for {progress_slot}/{len(players)} loaded team-slot players...")

        tendency_row: dict[str, Any] = dict(identity)
        for entry in tendency_entries:
            tendency_row[f"{entry.group} / {entry.display_name}"] = _display(model.read_entry_value_for_item(entry, player))
        tendency_rows.append(tendency_row)
        completed_units += 1
        emit_progress(f"Captured tendencies for {progress_slot}/{len(players)} loaded team-slot players...")
    return stats_rows, attribute_rows, tendency_rows, team_stat_rows


def add_current_roster_to_player_generation_pool(model: Any, *, season: int = 2026, progress_callback: Any | None = None) -> dict[str, Any]:
    stats_rows, attribute_rows, tendency_rows, team_stat_rows = capture_active_roster_pool_rows(
        model,
        progress_callback=progress_callback,
    )
    if not stats_rows:
        return {
            "status": "No loaded roster rows were captured. Load Players and Teams before adding the current roster.",
            "pool_db": str(pool_database_path()),
            "candidate_rows": 0,
            "candidate_position_rows": 0,
            "added_snapshot_id": "",
            "added_stats_rows": 0,
            "added_attribute_rows": 0,
            "added_tendency_rows": 0,
            "added_team_stat_rows": 0,
            "sync_required": False,
        }
    total_units = max(1, len(stats_rows) * 3 + len(team_stat_rows) + 1)
    if progress_callback is not None:
        progress_callback(max(0, total_units - 1), total_units, "Writing current roster snapshot to Pool SQL...")
    with _connect_pool() as connection:
        _ensure_pool_export_tables(connection)
        snapshot_id = _next_snapshot_id(connection)
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO pool_export_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, int(season), created_at, "editor_active_roster", len(stats_rows), len(attribute_rows), len(tendency_rows), len(team_stat_rows)),
        )
        for row_type, rows in (("stats", stats_rows), ("attributes", attribute_rows), ("tendencies", tendency_rows), ("team_stats", team_stat_rows)):
            connection.executemany(
                "INSERT INTO pool_export_rows VALUES (?, ?, ?)",
                ((snapshot_id, row_type, json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in rows),
            )
        connection.commit()
    if progress_callback is not None:
        progress_callback(total_units, total_units, "Added current roster snapshot to Pool SQL.")
    manifest = _pool_manifest_values(pool_database_path())
    return {
        "status": "Current roster snapshot added. Run Sync Player Pool SQL to rebuild offset-backed Pool columns.",
        "pool_db": str(pool_database_path()),
        "candidate_rows": int(manifest.get("candidate_rows", "0")),
        "candidate_position_rows": int(manifest.get("candidate_position_rows", "0")),
        "added_snapshot_id": snapshot_id,
        "added_stats_rows": len(stats_rows),
        "added_attribute_rows": len(attribute_rows),
        "added_tendency_rows": len(tendency_rows),
        "added_team_stat_rows": len(team_stat_rows),
        "sync_required": True,
    }


def sync_player_generation_pool(*, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    """Rebuild derived Pool tables exclusively from game-offset-backed captures."""
    total_steps = 3

    def emit_progress(step: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0, min(total_steps, step)), total_steps, message)

    emit_progress(0, "Checking player pool sources...")
    snapshot_ids = pool_source_ids()
    if not snapshot_ids:
        raise FileNotFoundError("no player pool snapshots found; use Add Current Roster to Pool SQL from the editor")
    if not force and _pool_is_current(snapshot_ids):
        manifest = _pool_manifest_values(pool_database_path())
        emit_progress(total_steps, "Player generation pool already current.")
        return {
            "status": "Player generation pool already current.",
            "pool_db": str(pool_database_path()),
            "source_snapshots": json.loads(manifest.get("source_snapshots", "[]")),
            "candidate_rows": int(manifest.get("candidate_rows", "0")),
            "candidate_position_rows": int(manifest.get("candidate_position_rows", "0")),
        }

    emit_progress(1, f"Loading {len(snapshot_ids)} player pool snapshot(s)...")
    candidates, fieldnames = load_candidates(snapshot_ids)

    manifest = {
        "pool_sqlite": str(pool_database_path()),
        "source_snapshots": list(snapshot_ids),
        "rule": "game-offset-derived inputs to exact captured field outputs",
        "features": list(FEATURES),
        "vital_columns": list(VITAL_COLUMNS),
        "candidate_rows": len({(c["run_id"], c["player_index"]) for c in candidates}),
        "candidate_position_rows": len(candidates),
        "candidate_rows_by_position": {pos: sum(1 for c in candidates if c["position"] == pos) for pos in POSITIONS},
        "status": f"Rebuilt player generation pool from {len(snapshot_ids)} snapshots.",
    }
    emit_progress(2, "Writing offset-backed player pool SQLite...")
    pool_manifest = write_pool_database(
        snapshot_ids=snapshot_ids,
        candidates=candidates,
        fieldnames=fieldnames,
    )
    manifest["pool_summary"] = pool_manifest
    emit_progress(total_steps, "Player pool SQL sync complete.")
    return manifest


def ensure_player_generation_pool_current(*, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    return sync_player_generation_pool(force=force, progress_callback=progress_callback)

