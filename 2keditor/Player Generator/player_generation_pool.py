"""Capture and rebuild the Player Generator pool from game-offset-backed data.

Pool package identity is ``(snapshot/run, player_index)``. Player names are not
identity, matching evidence, features, or model inputs. Derived pool columns may
only be calculated from values captured through current game offsets.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
VITAL_COLUMNS = (
    "height_inches",
    "height_cm",
    "weight_pounds",
    "weight_kg",
    "wingspan_inches",
    "wingspan_cm",
    "age",
    "years_pro",
)

# Bumped whenever the derived candidate_* schema changes (feature/vital columns,
# play-type table). A stored pool whose fingerprint no longer matches is rebuilt
# from the immutable raw snapshots instead of being extended in place.
POOL_SCHEMA_VERSION = 3

PLAY_TYPE_SLOTS = (1, 2, 3, 4)
_ABSENT_PLAY_TYPE = {"", "NONE", "N/A", "NA", "--"}

# Player Vitals offsets captured verbatim for every package. Version-specific
# names are all listed; grouped_fields only yields the ones the loaded game
# exposes, so unused aliases are harmless.
_CAPTURED_VITAL_ENTRY_NAMES = {
    "HEIGHT",
    "WEIGHT",
    "WEIGHTKG",
    "WINGSPAN",
    "WINGSPANCM",
    "STANDINGREACH",
    "AGE",
    "YEARSPRO",
    "BIRTHDAY",
    "BIRTHMONTH",
    "PLAYTYPE1",
    "PLAYTYPE2",
    "PLAYTYPE3",
    "PLAYTYPE4",
}


class PoolCaptureError(RuntimeError):
    """Raised when a roster capture is incomplete.

    The run is rejected as a whole; nothing is written to the pool. The message
    lists every missing field so a partial capture can never become a package.
    """


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


def _schema_fingerprint() -> str:
    """Identity of the derived candidate_* schema.

    A stored pool whose fingerprint differs (new feature/vital column, play-type
    table, schema-version bump) is rebuilt from the immutable raw snapshots
    rather than extended in place.
    """

    return json.dumps(
        {"version": POOL_SCHEMA_VERSION, "vitals": list(VITAL_COLUMNS), "features": list(FEATURES)},
        sort_keys=True,
    )


_SNAPSHOT_ROW_TYPES = ("stats", "attributes", "tendencies", "team_stats")


def _content_hash_from_row_json(rows_by_type: dict[str, Sequence[str]]) -> str:
    """Order-independent hash of a run's raw captured rows.

    Identifies a byte-identical recapture of the same roster. Excludes the
    snapshot timestamp and any derived data — only the captured field values.
    """

    digest = hashlib.sha256()
    for row_type in _SNAPSHOT_ROW_TYPES:
        digest.update(row_type.encode("utf-8"))
        for row_json in sorted(rows_by_type.get(row_type, ())):
            digest.update(b"\x1f")
            digest.update(str(row_json).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _capture_content_hash(
    stats_rows: Sequence[dict[str, Any]],
    attribute_rows: Sequence[dict[str, Any]],
    tendency_rows: Sequence[dict[str, Any]],
    team_stat_rows: Sequence[dict[str, Any]],
) -> str:
    return _content_hash_from_row_json(
        {
            "stats": [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in stats_rows],
            "attributes": [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in attribute_rows],
            "tendencies": [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in tendency_rows],
            "team_stats": [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in team_stat_rows],
        }
    )


def _snapshot_content_hash(connection: sqlite3.Connection, snapshot_id: str) -> str:
    by_type: dict[str, list[str]] = {}
    for row_type, row_json in connection.execute(
        "SELECT row_type, row_json FROM pool_export_rows WHERE snapshot_id = ?",
        (snapshot_id,),
    ):
        by_type.setdefault(str(row_type), []).append(str(row_json))
    return _content_hash_from_row_json(by_type)


def _snapshot_counts(connection: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT created_at, stats_rows, attribute_rows, tendency_rows, team_stat_rows "
        "FROM pool_export_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()
    if row is None:
        return {"created_at": "", "stats_rows": 0, "attribute_rows": 0, "tendency_rows": 0, "team_stat_rows": 0}
    return {
        "created_at": str(row[0]),
        "stats_rows": int(row[1]),
        "attribute_rows": int(row[2]),
        "tendency_rows": int(row[3]),
        "team_stat_rows": int(row[4]),
    }


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


def live_vitals(stats: Dict[str, str], season: Optional[int] = None) -> Dict[str, Optional[float]]:
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

    wingspan_inches = as_float(stats.get("wingspan_inches"))
    wingspan_cm = as_float(stats.get("wingspan_cm"))
    if wingspan_inches is None and wingspan_cm is not None:
        wingspan_inches = wingspan_cm / 2.54
    if wingspan_cm is None and wingspan_inches is not None:
        wingspan_cm = wingspan_inches * 2.54

    return {
        "height_inches": None if height_inches is None else round(float(height_inches), 4),
        "height_cm": None if height_cm is None else round(float(height_cm), 4),
        "weight_pounds": None if weight_pounds is None else round(float(weight_pounds), 4),
        "weight_kg": None if weight_kg is None else round(float(weight_kg), 4),
        "wingspan_inches": None if wingspan_inches is None else round(float(wingspan_inches), 4),
        "wingspan_cm": None if wingspan_cm is None else round(float(wingspan_cm), 4),
        "age": _normalized_age(stats, season),
        "years_pro": as_float(stats.get("years_pro")),
    }


#: The AGE offset does not carry an age in a retail roster -- it carries the player's
#: birth year, stored one below the true year (Devin Booker, born 1996, reads 1995).
#: Editor-authored players carry a real age there instead, because the editor writes
#: one. The pool therefore sees both units and normalizes to an age; the raw capture in
#: ``pool_export_rows`` stays verbatim. See ``_AGE_AS_BIRTH_YEAR_THRESHOLD``.
_AGE_AS_BIRTH_YEAR_THRESHOLD = 100.0
_AGE_BIRTH_YEAR_BIAS = 1


def _normalized_age(stats: dict[str, Any], season: Optional[int] = None) -> float | None:
    """Return a player age in years, whichever unit the AGE field was written in."""
    raw = as_float(stats.get("age"))
    if raw is None or raw < _AGE_AS_BIRTH_YEAR_THRESHOLD:
        return raw
    if season is None:
        return None
    return float(season) - (float(raw) + _AGE_BIRTH_YEAR_BIAS)


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


def _rows_by_index(rows: Sequence[Dict[str, Any]], key: str) -> dict[int, Dict[str, Any]]:
    out: dict[int, Dict[str, Any]] = {}
    for row in rows:
        try:
            out[int(row[key])] = dict(row)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _snapshot_play_types(stats: Dict[str, Any]) -> tuple[tuple[int, str], ...]:
    out: list[tuple[int, str]] = []
    for slot in PLAY_TYPE_SLOTS:
        label = str(stats.get(f"play_type_{slot}") or "").strip()
        if not label or label.upper() in _ABSENT_PLAY_TYPE:
            continue
        out.append((slot, label))
    return tuple(out)


def _candidates_from_rows(
    run_id: str,
    stats_by_index: dict[int, Dict[str, Any]],
    attrs_by_index: dict[int, Dict[str, Any]],
    tends_by_index: dict[int, Dict[str, Any]],
    team_by_index: dict[int, Dict[str, Any]],
    *,
    season: Optional[int] = None,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for idx, stats in stats_by_index.items():
        positions = parse_positions(stats.get("primary_position"))
        if not positions:
            continue
        attribute_row = attrs_by_index.get(idx, {})
        # Snapshots captured before the floor-value guard existed still carry blank
        # roster templates; keep them out of the derived pool on every rebuild.
        if _is_floor_value_attribute_row(
            attribute_row, tuple(key for key in attribute_row if key not in BASE_COLS)
        ):
            continue
        fields: Dict[str, float] = {}
        for col, val in attribute_row.items():
            if col in BASE_COLS:
                continue
            v = as_float(val)
            if v is not None:
                fields[f"Attribute::{col}"] = v
        for col, val in tends_by_index.get(idx, {}).items():
            if col in BASE_COLS:
                continue
            v = as_float(val)
            if v is not None:
                fields[f"Tendency::{col}"] = v
        team_index = int(as_float(stats.get("team_index")) or -1)
        live = live_features(stats)
        team_all_features = live_team_features(team_by_index.get(team_index, {}))
        team_features = {key: value for key, value in team_all_features.items() if value is not None}
        player_team_features = {
            key: value for key, value in live_player_team_features(stats, team_all_features).items() if value is not None
        }
        features = {**live, **team_features, **player_team_features}
        vitals = live_vitals(stats, season)
        play_types = _snapshot_play_types(stats)
        for pos in positions:
            candidates.append(
                {
                    "run_id": run_id,
                    "player_index": idx,
                    "position": pos,
                    "features": features,
                    "vitals": vitals,
                    "fields": fields,
                    "play_types": play_types,
                }
            )
    return candidates


def _snapshot_candidates(run_id: str) -> List[Dict[str, Any]]:
    stats_rows, attrs_rows, tends_rows, team_rows = _stored_snapshot_rows(run_id)
    return _candidates_from_rows(
        run_id, stats_rows, attrs_rows, tends_rows, team_rows, season=_snapshot_season(run_id)
    )


def _snapshot_season(run_id: str) -> Optional[int]:
    """Season the snapshot was captured for; needed to read a birth year as an age."""
    with sqlite3.connect(POOL_SQLITE) as connection:
        row = connection.execute(
            "SELECT season FROM pool_export_snapshots WHERE snapshot_id = ?", (run_id,)
        ).fetchone()
    return None if row is None or row[0] is None else int(row[0])


_CANDIDATE_TABLE_SQL = (
    "DROP TABLE IF EXISTS pool_runs",
    "DROP TABLE IF EXISTS candidate_pool",
    "DROP TABLE IF EXISTS candidate_fields",
    "DROP TABLE IF EXISTS candidate_play_types",
)


def _ensure_pool_tables(connection: sqlite3.Connection) -> None:
    _ensure_pool_export_tables(connection)
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS pool_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT '',
            stats_rows INTEGER NOT NULL DEFAULT 0,
            attribute_rows INTEGER NOT NULL DEFAULT 0,
            tendency_rows INTEGER NOT NULL DEFAULT 0,
            team_stat_rows INTEGER NOT NULL DEFAULT 0,
            candidate_position_rows INTEGER NOT NULL DEFAULT 0,
            play_type_rows INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS candidate_pool (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            position TEXT NOT NULL,
            {_feature_columns_sql()}
        );
        CREATE TABLE IF NOT EXISTS candidate_fields (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            position TEXT NOT NULL,
            field_type TEXT NOT NULL,
            input_field TEXT NOT NULL,
            value REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidate_play_types (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            position TEXT NOT NULL,
            slot INTEGER NOT NULL,
            play_type TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pool_manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_candidate_pool_run ON candidate_pool(run_id);
        CREATE INDEX IF NOT EXISTS idx_candidate_fields_run ON candidate_fields(run_id);
        CREATE INDEX IF NOT EXISTS idx_candidate_play_types_run ON candidate_play_types(run_id);
        """
    )


def _pool_schema_matches(connection: sqlite3.Connection) -> bool:
    try:
        row = connection.execute("SELECT value FROM pool_manifest WHERE key = 'schema_fingerprint'").fetchone()
    except sqlite3.Error:
        return False
    return row is not None and str(row[0]) == _schema_fingerprint()


def _reset_candidate_tables(connection: sqlite3.Connection) -> None:
    for statement in _CANDIDATE_TABLE_SQL:
        connection.execute(statement)
    _ensure_pool_tables(connection)


def _write_run_candidates(
    connection: sqlite3.Connection,
    run_id: str,
    candidates: Sequence[Dict[str, Any]],
    counts: dict[str, Any],
) -> int:
    connection.execute("DELETE FROM candidate_pool WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM candidate_fields WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM candidate_play_types WHERE run_id = ?", (run_id,))
    insert_sql = _candidate_pool_insert_sql()
    play_type_rows = 0
    for candidate in candidates:
        connection.execute(insert_sql, _candidate_pool_values(candidate))
        player_index = int(candidate["player_index"])
        for field_key, value in candidate["fields"].items():
            field_type, input_field = field_key.split("::", 1)
            connection.execute(
                "INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, player_index, candidate["position"], field_type, input_field, float(value)),
            )
        for slot, label in candidate.get("play_types", ()):
            connection.execute(
                "INSERT INTO candidate_play_types VALUES (?, ?, ?, ?, ?)",
                (run_id, player_index, candidate["position"], int(slot), str(label)),
            )
            play_type_rows += 1
    connection.execute(
        "INSERT OR REPLACE INTO pool_runs "
        "(run_id, created_at, stats_rows, attribute_rows, tendency_rows, team_stat_rows, candidate_position_rows, play_type_rows) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            str(counts.get("created_at", "")),
            int(counts.get("stats_rows", 0)),
            int(counts.get("attribute_rows", 0)),
            int(counts.get("tendency_rows", 0)),
            int(counts.get("team_stat_rows", 0)),
            len(candidates),
            play_type_rows,
        ),
    )
    return play_type_rows


def _refresh_pool_manifest(connection: sqlite3.Connection) -> dict[str, int | list[str]]:
    runs = [str(row[0]) for row in connection.execute("SELECT run_id FROM pool_runs ORDER BY created_at, run_id")]
    position_rows = int(connection.execute("SELECT COUNT(*) FROM candidate_pool").fetchone()[0])
    player_rows = int(
        connection.execute("SELECT COUNT(*) FROM (SELECT DISTINCT run_id, player_index FROM candidate_pool)").fetchone()[0]
    )
    play_type_rows = int(connection.execute("SELECT COUNT(*) FROM candidate_play_types").fetchone()[0])
    by_position = {
        pos: int(connection.execute("SELECT COUNT(*) FROM candidate_pool WHERE position = ?", (pos,)).fetchone()[0])
        for pos in POSITIONS
    }
    manifest = {
        "schema_fingerprint": _schema_fingerprint(),
        "schema_version": str(POOL_SCHEMA_VERSION),
        "data_contract": "game-offset-derived inputs to exact captured fields",
        "features": json.dumps(list(FEATURES)),
        "vital_columns": json.dumps(list(VITAL_COLUMNS)),
        "source_snapshots": json.dumps(runs),
        "candidate_rows": str(player_rows),
        "candidate_position_rows": str(position_rows),
        "candidate_rows_by_position": json.dumps(by_position),
        "play_type_rows": str(play_type_rows),
    }
    connection.execute("DELETE FROM pool_manifest")
    connection.executemany("INSERT INTO pool_manifest VALUES (?, ?)", manifest.items())
    return {
        "source_snapshots": runs,
        "candidate_rows": player_rows,
        "candidate_position_rows": position_rows,
        "play_type_rows": play_type_rows,
        "candidate_rows_by_position": by_position,
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


#: Blank roster-slot templates carry every attribute at the rating floor. The Pool is a
#: calibration source, so a block of floor values pulls every field-exact target it
#: feeds -- eleven "A Z" slots were captured alongside the 329 real players in
#: editor_capture_002 before this filter existed.
#:
#: Matching the label alone is not enough: retail rosters ship the same template under
#: other names ("AD ABC" put four 5'4"/350lb centers into editor_capture_005), so the
#: label is only a fast path and ``_is_floor_value_attribute_row`` is the real guard.
_EMPTY_ROSTER_SLOT_LABELS = frozenset({"a z", "az", "ad abc", "adabc"})

#: Every attribute of a template slot sits at the rating floor; only Potential varies
#: (40-42 across the templates seen). A real fringe player is nowhere near this -- the
#: weakest player in editor_capture_005 had 4 of 52 attributes at the floor.
_FLOOR_ATTRIBUTE_RATING = 25.0
_FLOOR_SIGNATURE_EXEMPT_FIELDS = frozenset({"Misc / Potential"})


def _is_empty_roster_slot(player: Any) -> bool:
    label = " ".join(str(getattr(player, "label", "") or "").split()).strip().lower()
    return label in _EMPTY_ROSTER_SLOT_LABELS


def _is_floor_value_attribute_row(attribute_row: dict[str, Any], attribute_field_names: tuple[str, ...]) -> bool:
    """True when every gradeable attribute sits at the floor -- a blank roster template."""
    graded = 0
    for name in attribute_field_names:
        if name in _FLOOR_SIGNATURE_EXEMPT_FIELDS:
            continue
        value = as_float(attribute_row.get(name))
        if value is None:
            continue
        if value != _FLOOR_ATTRIBUTE_RATING:
            return False
        graded += 1
    return graded > 0


def capture_active_roster_pool_rows(model: Any, *, progress_callback: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded_teams = sorted(model.loaded_items.get("Teams", {}).values(), key=lambda item: int(item.index))
    active_teams = loaded_teams[:30]
    team_slots = {int(team.index): slot for slot, team in enumerate(active_teams)}
    players = sorted(
        (
            row
            for row in model.player_roster_slot_items_for_team_items(active_teams)
            if not _is_empty_roster_slot(row[0])
        ),
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
        if str(entry.normalized_name).upper() in _CAPTURED_VITAL_ENTRY_NAMES
    }
    attribute_entries = [entry for group_entries in grouped.get("Attributes", {}).values() for entry in group_entries]
    tendency_entries = [entry for group_entries in grouped.get("Tendencies", {}).values() for entry in group_entries]
    attribute_field_names = tuple(f"{entry.group} / {entry.display_name}" for entry in attribute_entries)
    tendency_field_names = tuple(f"{entry.group} / {entry.display_name}" for entry in tendency_entries)
    team_stat_field_names = tuple(str(entry.normalized_name) for entry in team_stat_entries)
    stat_detail_field_names = tuple(entry.display_name for entry in stat_detail_entries)
    if not attribute_entries or not tendency_entries:
        raise PoolCaptureError(
            "player layout exposes no "
            + ("Attributes" if not attribute_entries else "Tendencies")
            + " for the loaded game version; load Players before capturing"
        )
    if not team_stat_entries:
        raise PoolCaptureError("team layout exposes no Team Stats Edit fields; load Teams before capturing")
    if current_stat_selector is None:
        raise PoolCaptureError("player layout exposes no CURRENTYEARSTATID selector; cannot resolve season stats")
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
        def _vital(name: str, _player: Any = player) -> str:
            entry = vital_entries.get(name)
            return "" if entry is None else _display(model.read_entry_value_for_item(entry, _player))

        stat_row["height_inches"] = _vital("HEIGHT")
        stat_row["weight_pounds"] = _vital("WEIGHT")
        stat_row["weight_kg"] = _vital("WEIGHTKG")
        stat_row["wingspan_inches"] = _vital("WINGSPAN")
        stat_row["wingspan_cm"] = _vital("WINGSPANCM")
        stat_row["standing_reach"] = _vital("STANDINGREACH")
        stat_row["age"] = _vital("AGE")
        stat_row["years_pro"] = _vital("YEARSPRO")
        stat_row["birth_day"] = _vital("BIRTHDAY")
        stat_row["birth_month"] = _vital("BIRTHMONTH")
        for play_type_number in PLAY_TYPE_SLOTS:
            stat_row[f"play_type_{play_type_number}"] = _vital(f"PLAYTYPE{play_type_number}")
        valid_current_stat_slot = isinstance(current_stat_selector_name, str) and isinstance(stat_id, int) and 0 < stat_id < 0xFFFF
        stat_row["stat_slot_valid"] = "1" if valid_current_stat_slot else "0"
        for entry in stat_detail_entries:
            stat_row[entry.display_name] = (
                _display(
                    model.read_entry_value_for_item(entry, player, stat_selector=current_stat_selector_name)
                )
                if valid_current_stat_slot
                else ""
            )
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

    stats_rows, attribute_rows, tendency_rows = _drop_floor_value_slots(
        stats_rows, attribute_rows, tendency_rows, attribute_field_names
    )

    _validate_capture(
        stats_rows=stats_rows,
        attribute_rows=attribute_rows,
        tendency_rows=tendency_rows,
        team_stat_rows=team_stat_rows,
        team_indices={int(team.index) for team in active_teams},
        attribute_field_names=attribute_field_names,
        tendency_field_names=tendency_field_names,
        team_stat_field_names=team_stat_field_names,
        stat_detail_field_names=stat_detail_field_names,
    )
    return stats_rows, attribute_rows, tendency_rows, team_stat_rows


def _drop_floor_value_slots(
    stats_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
    tendency_rows: list[dict[str, Any]],
    attribute_field_names: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop blank roster templates the label fast path did not catch.

    Runs on the three per-player row lists together so they stay index-aligned for
    ``_validate_capture``.
    """
    dropped = {
        int(row["player_index"])
        for row in attribute_rows
        if _is_floor_value_attribute_row(row, attribute_field_names)
    }
    if not dropped:
        return stats_rows, attribute_rows, tendency_rows
    keep = lambda rows: [row for row in rows if int(row["player_index"]) not in dropped]
    return keep(stats_rows), keep(attribute_rows), keep(tendency_rows)


_REQUIRED_STAT_DETAIL_FIELDS = (
    "Games Played",
    "Minutes",
    "Points",
    "Field Goals Attempted",
    "Field Goals Made",
    "Free Throws Attempted",
    "Free Throws Made",
    "Assists",
    "Offensive Rebounds",
    "Defensive Rebounds",
    "Steals",
    "Blocks",
    "Turnovers",
    "Fouls",
)


def _validate_capture(
    *,
    stats_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
    tendency_rows: list[dict[str, Any]],
    team_stat_rows: list[dict[str, Any]],
    team_indices: set[int],
    attribute_field_names: tuple[str, ...],
    tendency_field_names: tuple[str, ...],
    team_stat_field_names: tuple[str, ...],
    stat_detail_field_names: tuple[str, ...],
) -> None:
    problems: list[str] = []
    if not stats_rows:
        raise PoolCaptureError("no roster-slot players were captured; load Players and Teams before capturing")
    if not team_stat_rows:
        problems.append("no team stat rows captured")

    for team_row in team_stat_rows:
        label = str(team_row.get("team_label") or team_row.get("team_index"))
        missing = [name for name in team_stat_field_names if not str(team_row.get(name, "")).strip()]
        if missing:
            problems.append(f"team {label}: empty team stats {missing}")

    missing_detail = [name for name in _REQUIRED_STAT_DETAIL_FIELDS if name not in stat_detail_field_names]
    if missing_detail:
        problems.append(f"stat-detail layout is missing required fields {missing_detail}")

    attr_by_index = {int(row.get("player_index")): row for row in attribute_rows}
    tend_by_index = {int(row.get("player_index")): row for row in tendency_rows}
    for stat_row in stats_rows:
        index = int(stat_row.get("player_index"))
        label = str(stat_row.get("player_label") or index)
        if not parse_positions(stat_row.get("primary_position")):
            problems.append(f"{label}: primary position {stat_row.get('primary_position')!r} does not resolve to PG/SG/SF/PF/C")
        team_index = _int_or_none(stat_row.get("team_index"))
        if team_index is None or team_index not in team_indices:
            problems.append(f"{label}: team_index {stat_row.get('team_index')!r} has no captured team stat row")
        attr_row = attr_by_index.get(index)
        if attr_row is None:
            problems.append(f"{label}: no attribute row captured")
        else:
            empty = [name for name in attribute_field_names if not str(attr_row.get(name, "")).strip()]
            if empty:
                problems.append(f"{label}: {len(empty)} empty attributes ({empty[:5]}{'...' if len(empty) > 5 else ''})")
        tend_row = tend_by_index.get(index)
        if tend_row is None:
            problems.append(f"{label}: no tendency row captured")
        else:
            empty = [name for name in tendency_field_names if not str(tend_row.get(name, "")).strip()]
            if empty:
                problems.append(f"{label}: {len(empty)} empty tendencies ({empty[:5]}{'...' if len(empty) > 5 else ''})")
        if str(stat_row.get("stat_slot_valid")) == "1":
            empty_stats = [name for name in _REQUIRED_STAT_DETAIL_FIELDS if not str(stat_row.get(name, "")).strip()]
            if empty_stats:
                problems.append(f"{label}: stat slot marked valid but season stats empty {empty_stats}")

    if problems:
        raise PoolCaptureError(
            f"roster capture incomplete ({len(problems)} problem(s)); run rejected:\n  - "
            + "\n  - ".join(problems[:60])
            + ("" if len(problems) <= 60 else f"\n  ... and {len(problems) - 60} more")
        )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def add_current_roster_to_player_generation_pool(model: Any, *, season: int = 2026, progress_callback: Any | None = None) -> dict[str, Any]:
    """Capture the loaded roster and append its derived rows as one run.

    The capture is validated as a whole (``PoolCaptureError`` on any gap) before
    anything is written. The new run's ``candidate_*`` rows are built and inserted
    in the same call: there is no separate rebuild step, and existing runs are
    left untouched unless the derived schema changed.
    """

    stats_rows, attribute_rows, tendency_rows, team_stat_rows = capture_active_roster_pool_rows(
        model,
        progress_callback=progress_callback,
    )
    total_units = max(1, len(stats_rows) * 3 + len(team_stat_rows) + 2)
    if progress_callback is not None:
        progress_callback(max(0, total_units - 2), total_units, "Writing current roster run to Pool SQL...")

    stats_by_index = _rows_by_index(stats_rows, "player_index")
    attrs_by_index = _rows_by_index(attribute_rows, "player_index")
    tends_by_index = _rows_by_index(tendency_rows, "player_index")
    team_by_index = _rows_by_index(team_stat_rows, "team_index")
    content_hash = _capture_content_hash(stats_rows, attribute_rows, tendency_rows, team_stat_rows)

    with _connect_pool() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        _ensure_pool_tables(connection)

        for existing_id in [str(row[0]) for row in connection.execute("SELECT snapshot_id FROM pool_export_snapshots")]:
            if _snapshot_content_hash(connection, existing_id) == content_hash:
                summary = _refresh_pool_manifest(connection)
                connection.commit()
                if progress_callback is not None:
                    progress_callback(total_units, total_units, f"Capture identical to run {existing_id}; not added.")
                return {
                    "status": f"Capture is identical to existing run {existing_id}; nothing added.",
                    "pool_db": str(pool_database_path()),
                    "candidate_rows": int(summary["candidate_rows"]),
                    "candidate_position_rows": int(summary["candidate_position_rows"]),
                    "added_snapshot_id": "",
                    "duplicate_of": existing_id,
                    "added_stats_rows": 0,
                    "added_attribute_rows": 0,
                    "added_tendency_rows": 0,
                    "added_team_stat_rows": 0,
                    "added_play_type_rows": 0,
                    "rebuilt_all_runs": False,
                    "sync_required": False,
                }

        rebuilt_all = not _pool_schema_matches(connection)
        if rebuilt_all:
            _reset_candidate_tables(connection)

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

        run_counts = {
            "created_at": created_at,
            "stats_rows": len(stats_rows),
            "attribute_rows": len(attribute_rows),
            "tendency_rows": len(tendency_rows),
            "team_stat_rows": len(team_stat_rows),
        }
        candidates = _candidates_from_rows(
            snapshot_id, stats_by_index, attrs_by_index, tends_by_index, team_by_index, season=int(season)
        )
        if not candidates:
            raise PoolCaptureError("capture produced no position candidates; run rejected")
        added_play_type_rows = _write_run_candidates(connection, snapshot_id, candidates, run_counts)

        if rebuilt_all:
            existing = [
                str(row[0])
                for row in connection.execute("SELECT snapshot_id FROM pool_export_snapshots WHERE snapshot_id <> ?", (snapshot_id,))
            ]
            for other in existing:
                other_candidates = _snapshot_candidates(other)
                if other_candidates:
                    _write_run_candidates(connection, other, other_candidates, _snapshot_counts(connection, other))

        summary = _refresh_pool_manifest(connection)
        connection.commit()

    if progress_callback is not None:
        progress_callback(total_units, total_units, "Added current roster run to Pool SQL.")
    return {
        "status": (
            f"Added run {snapshot_id}: {len(stats_rows)} players, {added_play_type_rows} play-type rows. "
            + ("Derived schema changed — all runs rebuilt." if rebuilt_all else "Existing runs unchanged.")
        ),
        "pool_db": str(pool_database_path()),
        "candidate_rows": int(summary["candidate_rows"]),
        "candidate_position_rows": int(summary["candidate_position_rows"]),
        "added_snapshot_id": snapshot_id,
        "added_stats_rows": len(stats_rows),
        "added_attribute_rows": len(attribute_rows),
        "added_tendency_rows": len(tendency_rows),
        "added_team_stat_rows": len(team_stat_rows),
        "added_play_type_rows": added_play_type_rows,
        "rebuilt_all_runs": rebuilt_all,
        "sync_required": False,
    }


def sync_player_generation_pool(*, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    """Bring the derived ``candidate_*`` tables level with the stored raw runs.

    Normal path: add any snapshot whose ``run_id`` is not present yet. ``force``
    (or a changed derived schema) drops and rebuilds every run's derived rows
    from the immutable raw snapshots. Raw ``pool_export_*`` data is never touched.
    """

    total_steps = 3

    def emit_progress(step: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0, min(total_steps, step)), total_steps, message)

    emit_progress(0, "Checking player pool sources...")
    snapshot_ids = stored_pool_snapshot_ids()
    if not snapshot_ids:
        raise FileNotFoundError("no player pool snapshots found; use Add Current Roster to Pool SQL from the editor")

    with _connect_pool() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        _ensure_pool_tables(connection)
        full_rebuild = force or not _pool_schema_matches(connection)
        if full_rebuild:
            _reset_candidate_tables(connection)
            pending = list(snapshot_ids)
        else:
            present = {str(row[0]) for row in connection.execute("SELECT run_id FROM pool_runs")}
            pending = [snapshot_id for snapshot_id in snapshot_ids if snapshot_id not in present]

        if not pending:
            summary = _refresh_pool_manifest(connection)
            connection.commit()
            emit_progress(total_steps, "Player generation pool already current.")
            return {
                "status": "Player generation pool already current.",
                "pool_db": str(pool_database_path()),
                "source_snapshots": summary["source_snapshots"],
                "candidate_rows": int(summary["candidate_rows"]),
                "candidate_position_rows": int(summary["candidate_position_rows"]),
                "play_type_rows": int(summary["play_type_rows"]),
            }

        empty_runs: list[str] = []
        for index, run_id in enumerate(pending, start=1):
            emit_progress(1, f"Adding run {index}/{len(pending)} ({run_id})...")
            candidates = _snapshot_candidates(run_id)
            if not candidates:
                empty_runs.append(run_id)
                continue
            _write_run_candidates(connection, run_id, candidates, _snapshot_counts(connection, run_id))

        emit_progress(2, "Refreshing pool manifest...")
        summary = _refresh_pool_manifest(connection)
        connection.commit()

    emit_progress(total_steps, "Player pool SQL sync complete.")
    status = (
        f"{'Rebuilt' if full_rebuild else 'Added'} {len(pending) - len(empty_runs)} run(s); "
        f"{summary['candidate_position_rows']} position rows, {summary['play_type_rows']} play-type rows."
    )
    if empty_runs:
        status += f" WARNING: {len(empty_runs)} run(s) produced no candidates: {empty_runs}"
    return {
        "status": status,
        "pool_db": str(pool_database_path()),
        "source_snapshots": summary["source_snapshots"],
        "candidate_rows": int(summary["candidate_rows"]),
        "candidate_position_rows": int(summary["candidate_position_rows"]),
        "candidate_rows_by_position": summary["candidate_rows_by_position"],
        "play_type_rows": int(summary["play_type_rows"]),
        "empty_runs": empty_runs,
        "full_rebuild": full_rebuild,
    }


def ensure_player_generation_pool_current(*, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    return sync_player_generation_pool(force=force, progress_callback=progress_callback)

