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
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
REQUIRED_RUN_FILES = ("current_active_player_stats.csv", "current_active_player_attributes.csv", "current_active_player_tendencies.csv")
BASE_COLS = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
FEATURES = (
    "pts_per36",
    "fga_per36",
    "fg_pct",
    "x3pa_per36",
    "x3p_pct",
    "fta_per36",
    "ft_pct",
    "ast_per36",
    "orb_per36",
    "drb_per36",
    "stl_per36",
    "blk_per36",
    "tov_per36",
    "pf_per36",
)
BODY_FEATURES = ("height_inches", "weight_pounds")
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
_NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}


@dataclass(frozen=True)
class PlayerGenerationPoolRequest:
    season: int = 2026
    root: Path = _REPO_ROOT
    force: bool = False

    def normalized(self) -> "PlayerGenerationPoolRequest":
        return PlayerGenerationPoolRequest(season=int(self.season), root=Path(self.root).resolve(), force=bool(self.force))


def ascii_name_text(value: object) -> str:
    from game_port import _ascii_name_text

    return _ascii_name_text(value)


def identity(value: object) -> str:
    from game_port import _identity

    return _identity(value)


def name_tokens(value: object) -> tuple[str, ...]:
    from game_port import _name_tokens

    return _name_tokens(value)


def person_name_keys(*values: object) -> tuple[str, ...]:
    from game_port import _person_name_keys

    return _person_name_keys(*values)


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




def player_pool_dir() -> Path:
    return _PLAYER_POOL_DIR

def pool_database_path(root: Path | None = None) -> Path:
    _ = root  # kept for compatibility with existing callers; the pool belongs to Player Generator data.
    return POOL_SQLITE


def position_stat_neighbor_model_path(sources: Sequence[str]) -> Path:
    model_number = len(tuple(sources))
    return OUTPUT_DIR / f"{OUT_PREFIX}{model_number:03d}.sqlite"


def complete_run_ids(root: Path | None = None) -> tuple[str, ...]:
    project_root = _REPO_ROOT if root is None else Path(root).resolve()
    base = project_root / RUNS_DIR
    rows: list[tuple[int, str]] = []
    for path in base.iterdir() if base.exists() else ():
        if not path.is_dir() or not path.name.startswith("run_"):
            continue
        suffix = path.name.split("_", 1)[-1]
        if not suffix.isdigit():
            continue
        if all((path / name).is_file() for name in REQUIRED_RUN_FILES):
            rows.append((int(suffix), path.name))
    return tuple(name for _num, name in sorted(rows))


def run_file_signature(root: Path, runs: Sequence[str]) -> dict[str, dict[str, float | int]]:
    project_root = Path(root).resolve()
    signature: dict[str, dict[str, float | int]] = {}
    for run_id in runs:
        run_dir = project_root / RUNS_DIR / run_id
        for name in REQUIRED_RUN_FILES:
            path = run_dir / name
            stat = path.stat()
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
                    "SELECT season, created_at, stats_rows, attribute_rows, tendency_rows FROM pool_export_snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    signature[f"snapshot/{snapshot_id}"] = {
                        "season": int(row[0]),
                        "created_at": str(row[1]),
                        "stats_rows": int(row[2]),
                        "attribute_rows": int(row[3]),
                        "tendency_rows": int(row[4]),
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


def _pool_is_current(root: Path, season: int, sources: Sequence[str]) -> bool:
    manifest = _pool_manifest_values(pool_database_path())
    if not manifest:
        return False
    if manifest.get("season") != str(season):
        return False
    if json.loads(manifest.get("source_runs", "[]")) != list(sources):
        return False
    if json.loads(manifest.get("run_file_signature", "{}")) != source_signature(root, sources):
        return False
    model_path = Path(manifest.get("model_path") or manifest.get("model_dir", ""))
    try:
        model_path.relative_to(OUTPUT_DIR)
    except ValueError:
        return False
    return model_path.is_file() and model_path.suffix == ".sqlite"


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


def median_float(vals: Sequence[float]) -> float:
    return float(median(vals))


def is_aggregate_team(team: object) -> bool:
    value = str(team or "").upper()
    return value == "TOT" or bool(re.fullmatch(r"\dTM", value))


def row_get(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def select_player_rows(rows: List[sqlite3.Row]) -> Dict[str, sqlite3.Row]:
    by_player: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_player[str(row["player_id"])].append(row)
    selected: Dict[str, sqlite3.Row] = {}
    for pid, group in by_player.items():
        aggregate = [r for r in group if is_aggregate_team(row_get(r, "team"))]
        candidates = aggregate or group
        selected[pid] = max(candidates, key=lambda r: (as_float(row_get(r, "g")) or 0, as_float(row_get(r, "mp")) or as_float(row_get(r, "mp_per_game")) or 0))
    return selected


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


def positions_from_pbp(pbp: Optional[Dict[str, Any]], fallback_pos: object) -> tuple[str, ...]:
    if pbp:
        out = []
        for pos, col in [("PG", "pg_percent"), ("SG", "sg_percent"), ("SF", "sf_percent"), ("PF", "pf_percent"), ("C", "c_percent")]:
            if (as_float(pbp.get(col)) or 0.0) > 0:
                out.append(pos)
        if out:
            return tuple(out)
    return parse_positions(fallback_pos)


def load_master(root: Path, season: int) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    _ = root
    con = sqlite3.connect(MASTER_SQLITE)
    con.row_factory = sqlite3.Row
    tables = {}
    for table in ["player_season_info", "player_per_game", "player_per_36_min", "advanced", "player_play_by_play"]:
        rows = con.execute(f"select * from {table} where season = ?", (season,)).fetchall()
        tables[table] = {pid: dict(row) for pid, row in select_player_rows(rows).items()}
    info_rows = con.execute("select * from player_info").fetchall()
    tables["player_info"] = {str(row["player_id"]): dict(row) for row in info_rows}
    players: Dict[str, Dict[str, Any]] = {}
    key_index: Dict[str, List[Dict[str, Any]]] = {}
    player_ids = set().union(*(set(tables[table].keys()) for table in ("player_season_info", "player_per_game", "player_per_36_min", "advanced", "player_play_by_play")))
    for pid in sorted(player_ids):
        pg = tables["player_per_game"].get(pid, {})
        p36 = tables["player_per_36_min"].get(pid, {})
        info = tables["player_season_info"].get(pid, {})
        adv = tables["advanced"].get(pid, {})
        pbp = tables["player_play_by_play"].get(pid, {})
        identity = tables["player_info"].get(pid, {})
        name = pg.get("player") or info.get("player") or identity.get("player") or pid
        def master_per36(per36_col: str, per_game_col: str) -> Optional[float]:
            direct = as_float(p36.get(per36_col))
            if direct is not None:
                return direct
            per_game_value = as_float(pg.get(per_game_col))
            mpg = as_float(pg.get("mp_per_game"))
            return None if per_game_value is None or mpg in (None, 0) else per_game_value * 36.0 / mpg

        features = {
            "pts_per36": master_per36("pts_per_36_min", "pts_per_game"),
            "fga_per36": master_per36("fga_per_36_min", "fga_per_game"),
            "fg_pct": as_float(pg.get("fg_percent")),
            "x3pa_per36": master_per36("x3pa_per_36_min", "x3pa_per_game"),
            "x3p_pct": as_float(pg.get("x3p_percent")),
            "fta_per36": master_per36("fta_per_36_min", "fta_per_game"),
            "ft_pct": as_float(pg.get("ft_percent")),
            "ast_per36": master_per36("ast_per_36_min", "ast_per_game"),
            "orb_per36": master_per36("orb_per_36_min", "orb_per_game"),
            "drb_per36": master_per36("drb_per_36_min", "drb_per_game"),
            "stl_per36": master_per36("stl_per_36_min", "stl_per_game"),
            "blk_per36": master_per36("blk_per_36_min", "blk_per_game"),
            "tov_per36": master_per36("tov_per_36_min", "tov_per_game"),
            "pf_per36": master_per36("pf_per_36_min", "pf_per_game"),
            "height_inches": as_float(identity.get("ht_in_in")),
            "weight_pounds": as_float(identity.get("wt")),
        }
        positions = positions_from_pbp(pbp, info.get("pos") or pg.get("pos"))
        row = {
            "player_id": pid,
            "player": name,
            "team": pg.get("team") or info.get("team") or "",
            "positions": positions,
            "features": features,
            "games": as_float(pg.get("g")),
            "minutes_per_game": as_float(pg.get("mp_per_game")),
            "height_inches": as_float(identity.get("ht_in_in")),
            "weight_pounds": as_float(identity.get("wt")),
        }
        players[pid] = row
        for key in person_name_keys(name):
            key_index.setdefault(key, []).append(row)
    con.close()
    return players, key_index


def live_features(stats: Dict[str, str]) -> Dict[str, Optional[float]]:
    minutes = as_float(stats.get("Minutes"))
    return {
        "pts_per36": per36(as_float(stats.get("Points")), minutes),
        "fga_per36": per36(as_float(stats.get("Field Goals Attempted")), minutes),
        "fg_pct": safe_div(as_float(stats.get("Field Goals Made")), as_float(stats.get("Field Goals Attempted"))),
        "x3pa_per36": per36(as_float(stats.get("Three Pointers Attempted")), minutes),
        "x3p_pct": safe_div(as_float(stats.get("Three Pointers Made")), as_float(stats.get("Three Pointers Attempted"))),
        "fta_per36": per36(as_float(stats.get("Free Throws Attempted")), minutes),
        "ft_pct": safe_div(as_float(stats.get("Free Throws Made")), as_float(stats.get("Free Throws Attempted"))),
        "ast_per36": per36(as_float(stats.get("Assists")), minutes),
        "orb_per36": per36(as_float(stats.get("Offensive Rebounds")), minutes),
        "drb_per36": per36(as_float(stats.get("Defensive Rebounds")), minutes),
        "stl_per36": per36(as_float(stats.get("Steals")), minutes),
        "blk_per36": per36(as_float(stats.get("Blocks")), minutes),
        "tov_per36": per36(as_float(stats.get("Turnovers")), minutes),
        "pf_per36": per36(as_float(stats.get("Fouls")), minutes),
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


def match_live_player(label: str, key_index: Dict[str, List[Dict[str, Any]]], vitals: Dict[str, Optional[float]] | None = None) -> Optional[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for key in person_name_keys(label):
        for row in key_index.get(key, ()):
            pid = str(row.get("player_id") or "")
            if pid in seen:
                continue
            seen.add(pid)
            candidates.append(row)
    tokens = tuple(token for token in name_tokens(label) if token not in _NAME_SUFFIXES)
    if len(tokens) == 2:
        for key in person_name_keys(f"{tokens[1]} {tokens[0]}"):
            for row in key_index.get(key, ()):
                pid = str(row.get("player_id") or "")
                if pid in seen:
                    continue
                seen.add(pid)
                candidates.append(row)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda row: _vital_match_distance(vitals or {}, row))


def _vital_match_distance(live: Dict[str, Optional[float]], master: Dict[str, Any]) -> tuple[float, int, str]:
    parts: list[float] = []
    live_height = as_float(live.get("height_inches"))
    master_height = as_float(master.get("height_inches"))
    if live_height is not None and master_height is not None:
        parts.append(((live_height - master_height) / 2.0) ** 2)
    live_weight = as_float(live.get("weight_pounds"))
    master_weight = as_float(master.get("weight_pounds"))
    if live_weight is not None and master_weight is not None:
        parts.append(((live_weight - master_weight) / 12.0) ** 2)
    if not parts:
        return (0.0, 0, str(master.get("player_id") or ""))
    return (math.sqrt(sum(parts) / len(parts)), -len(parts), str(master.get("player_id") or ""))


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


def load_candidates(root: Path, key_index: Dict[str, List[Dict[str, Any]]], runs: Sequence[str] | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
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
            match_vitals = live_vitals(stats, {})
            master = match_live_player(label, key_index, match_vitals)
            match_rows.append({
                "run_id": run_id,
                "player_index": idx,
                "live_player_label": label,
                "matched": master is not None,
                "master_player": "" if master is None else master["player"],
                "master_player_id": "" if master is None else master["player_id"],
                "positions": "" if master is None else ";".join(master["positions"]),
            })
            if master is None or not master["positions"]:
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
            feats = live_features(stats)
            vitals = live_vitals(stats, master)
            features_with_body = {**feats, "height_inches": vitals.get("height_inches"), "weight_pounds": vitals.get("weight_pounds")}
            for pos in master["positions"]:
                candidates.append({
                    "run_id": run_id,
                    "player_index": idx,
                    "player_label": label,
                    "master_player": master["player"],
                    "master_player_id": master["player_id"],
                    "position": pos,
                    "features": features_with_body,
                    "vitals": vitals,
                    "fields": fields,
                })
    return candidates, match_rows, fieldnames


def scale_by_position(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Tuple[float, float]]]:
    out: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for pos in POSITIONS:
        rows = [c for c in candidates if c["position"] == pos]
        pos_scales = {}
        for feat in (*FEATURES, *BODY_FEATURES):
            vals = sorted(float(c["features"][feat]) for c in rows if c["features"].get(feat) is not None and math.isfinite(float(c["features"][feat])))
            if not vals:
                pos_scales[feat] = (0.0, 1.0)
                continue
            med = median_float(vals)
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
            scale = math.sqrt(var) or 1.0
            pos_scales[feat] = (med, scale)
        out[pos] = pos_scales
    return out


def distance(a: Dict[str, Optional[float]], b: Dict[str, Optional[float]], scales: Dict[str, Tuple[float, float]], features: Sequence[str] = FEATURES) -> Tuple[Optional[float], int]:
    parts = []
    for feat in features:
        av = a.get(feat)
        bv = b.get(feat)
        if av is None or bv is None:
            continue
        scale = scales.get(feat, (0.0, 1.0))[1] or 1.0
        parts.append(((float(av) - float(bv)) / scale) ** 2)
    if len(parts) < min(6, len(tuple(features))):
        return None, len(parts)
    return math.sqrt(sum(parts) / len(parts)), len(parts)


def nearest_neighbors(target_features: Dict[str, Optional[float]], pos: str, candidates_by_pos: Dict[str, List[Dict[str, Any]]], scales: Dict[str, Dict[str, Tuple[float, float]]], *, features: Sequence[str] = FEATURES, exclude_player_id: str = "", exclude_run: str = "", k: int = 10) -> List[Dict[str, Any]]:
    rows = []
    for c in candidates_by_pos.get(pos, []):
        if exclude_player_id and c["master_player_id"] == exclude_player_id:
            continue
        if exclude_run and c["run_id"] == exclude_run:
            continue
        dist, common = distance(target_features, c["features"], scales[pos], features)
        if dist is None:
            continue
        rows.append({"candidate": c, "distance": dist, "common_features": common})
    rows.sort(key=lambda r: r["distance"])
    return rows[:k]


def features_for_field(field_key: str) -> tuple[str, ...]:
    key = identity(field_key)
    if "3PT" in key or "3POINT" in key or "THREE" in key:
        return ("x3pa_per36", "x3p_pct", "fga_per36", "pts_per36")
    if "FREE" in key or "FOUL" in key or "DRAW" in key:
        return ("fta_per36", "ft_pct", "pts_per36")
    if "PASS" in key or "ASSIST" in key or "VISION" in key or "TOUCH" in key:
        return ("ast_per36", "tov_per36")
    if "REBOUND" in key or "BOXOUT" in key or "PUTBACK" in key:
        return ("orb_per36", "drb_per36", "height_inches", "weight_pounds")
    if "STEAL" in key or "INTERCEPT" in key:
        return ("stl_per36", "pf_per36")
    if "BLOCK" in key or "INTERIORDEFENSE" in key or "HELPDEFENSE" in key:
        return ("blk_per36", "pf_per36", "drb_per36", "height_inches", "weight_pounds")
    if "DUNK" in key or "LAYUP" in key or "CLOSE" in key or "POST" in key:
        return ("pts_per36", "fga_per36", "fg_pct", "fta_per36", "height_inches", "weight_pounds")
    if "SHOT" in key or "JUMPER" in key or "MIDRANGE" in key or "FADE" in key:
        return ("pts_per36", "fga_per36", "fg_pct")
    if "BALL" in key or "HANDLE" in key:
        return ("ast_per36", "tov_per36", "pts_per36")
    if "DEFENSE" in key or "LATERAL" in key:
        return ("stl_per36", "blk_per36", "pf_per36")
    return FEATURES


def build_irl_neighbors(master_players: Dict[str, Dict[str, Any]], candidates: List[Dict[str, Any]], scales: Dict[str, Dict[str, Tuple[float, float]]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_pos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        by_pos[c["position"]].append(c)
    neighbor_rows: List[Dict[str, Any]] = []
    suggestion_rows: List[Dict[str, Any]] = []
    fields_by_features_by_pos: dict[str, dict[tuple[str, ...], list[str]]] = {}
    for pos, pos_candidates in by_pos.items():
        all_fields = sorted(set().union(*(set(c["fields"].keys()) for c in pos_candidates))) if pos_candidates else []
        grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for field_key in all_fields:
            grouped[features_for_field(field_key)].append(field_key)
        fields_by_features_by_pos[pos] = grouped
    for player in master_players.values():
        for pos in player["positions"]:
            neigh = nearest_neighbors(player["features"], pos, by_pos, scales, k=10)
            for rank, n in enumerate(neigh, 1):
                c = n["candidate"]
                neighbor_rows.append({
                    "target_player": player["player"],
                    "target_player_id": player["player_id"],
                    "target_team": player["team"],
                    "position": pos,
                    "neighbor_rank": rank,
                    "distance": round(n["distance"], 6),
                    "common_features": n["common_features"],
                    "neighbor_run_id": c["run_id"],
                    "neighbor_player_index": c["player_index"],
                    "neighbor_live_label": c["player_label"],
                    "neighbor_master_player": c["master_player"],
                    "neighbor_master_player_id": c["master_player_id"],
                })
            if not fields_by_features_by_pos.get(pos):
                continue
            for section_features, field_keys in fields_by_features_by_pos.get(pos, {}).items():
                section_neighbors = nearest_neighbors(player["features"], pos, by_pos, scales, features=section_features, k=5)
                top5 = [n["candidate"] for n in section_neighbors]
                if not top5:
                    continue
                for field_key in field_keys:
                    vals = [float(c["fields"][field_key]) for c in top5 if field_key in c["fields"]]
                    if not vals:
                        continue
                    kind, field = field_key.split("::", 1)
                    top_with_field = next((c for c in top5 if field_key in c["fields"]), top5[0])
                    suggestion_rows.append({
                        "target_player": player["player"],
                        "target_player_id": player["player_id"],
                        "target_team": player["team"],
                        "position": pos,
                        "Type": kind,
                        "Input Field": field,
                        "suggested_top1": int(round(top_with_field["fields"].get(field_key, median_float(vals)))),
                        "suggested_top5_median": round(median_float(vals), 4),
                        "neighbor_count": len(vals),
                        "top_neighbor": top_with_field["player_label"],
                    })
    return neighbor_rows, suggestion_rows



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
    with sqlite3.connect(model_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE candidate_pool (
                run_id TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                player_label TEXT NOT NULL,
                master_player TEXT NOT NULL,
                master_player_id TEXT NOT NULL,
                position TEXT NOT NULL,
                height_inches REAL,
                height_cm REAL,
                weight_pounds REAL,
                weight_kg REAL,
                pts_per36 REAL,
                fga_per36 REAL,
                fg_pct REAL,
                x3pa_per36 REAL,
                x3p_pct REAL,
                fta_per36 REAL,
                ft_pct REAL,
                ast_per36 REAL,
                orb_per36 REAL,
                drb_per36 REAL,
                stl_per36 REAL,
                blk_per36 REAL,
                tov_per36 REAL,
                pf_per36 REAL
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
            "INSERT INTO candidate_pool VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((row.get("run_id"), row.get("player_index"), row.get("player_label"), row.get("master_player"), row.get("master_player_id"), row.get("position"), *(row.get(column) for column in VITAL_COLUMNS), *(row.get(feature) for feature in FEATURES)) for row in candidate_rows),
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
    season: int,
    runs: Sequence[str],
    candidates: Sequence[Dict[str, Any]],
    match_rows: Sequence[Dict[str, Any]],
    fieldnames: Sequence[str],
    model_path: Path,
) -> dict[str, Any]:
    db_path = pool_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    signature = source_signature(root, runs)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
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
                height_inches REAL,
                height_cm REAL,
                weight_pounds REAL,
                weight_kg REAL,
                pts_per36 REAL,
                fga_per36 REAL,
                fg_pct REAL,
                x3pa_per36 REAL,
                x3p_pct REAL,
                fta_per36 REAL,
                ft_pct REAL,
                ast_per36 REAL,
                orb_per36 REAL,
                drb_per36 REAL,
                stl_per36 REAL,
                blk_per36 REAL,
                tov_per36 REAL,
                pf_per36 REAL
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
            features = candidate["features"]
            connection.execute(
                """
                INSERT INTO candidate_pool VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["run_id"],
                    int(candidate["player_index"]),
                    candidate["player_label"],
                    candidate["master_player"],
                    candidate["master_player_id"],
                    candidate["position"],
                    *(candidate.get("vitals", {}).get(column) for column in VITAL_COLUMNS),
                    *(features.get(feature) for feature in FEATURES),
                ),
            )
            for field_key, value in candidate["fields"].items():
                field_type, input_field = field_key.split("::", 1)
                connection.execute(
                    "INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)",
                    (candidate["run_id"], int(candidate["player_index"]), candidate["position"], field_type, input_field, float(value)),
                )
        manifest = {
            "season": str(season),
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
        if str(entry.normalized_name).upper() in {"HEIGHTCM", "WEIGHT", "WEIGHTKG"}
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
        height_cm_entry = vital_entries.get("HEIGHTCM")
        weight_entry = vital_entries.get("WEIGHT")
        weight_kg_entry = vital_entries.get("WEIGHTKG")
        stat_row["height_cm"] = "" if height_cm_entry is None else _display(model.read_entry_value(height_cm_entry, index=player.index))
        height_cm = as_float(stat_row.get("height_cm"))
        stat_row["height_inches"] = "" if height_cm is None else round(height_cm / 2.54, 4)
        stat_row["weight_pounds"] = "" if weight_entry is None else _display(model.read_entry_value(weight_entry, index=player.index))
        stat_row["weight_kg"] = "" if weight_kg_entry is None else _display(model.read_entry_value(weight_kg_entry, index=player.index))
        for entry in stat_detail_entries:
            stat_row[entry.display_name] = _display(model.read_entry_value(entry, index=player.index, stat_selector=selector))
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
    total_steps = 7

    def emit_progress(step: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0, min(total_steps, step)), total_steps, message)

    emit_progress(0, "Checking player pool sources...")
    normalized = (request or PlayerGenerationPoolRequest()).normalized()
    root = normalized.root
    season = normalized.season
    force = normalized.force
    runs = pool_source_ids(root)
    if not runs:
        raise FileNotFoundError("no player pool sources found; use Add Current Roster to Pool SQL from the editor")
    if not force and _pool_is_current(root, season, runs):
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
    emit_progress(1, f"Loading NBA Master for season {season}...")
    master_players, key_index = load_master(root, season)
    emit_progress(2, f"Loading {len(runs)} player pool source(s)...")
    candidates, match_rows, fieldnames = load_candidates(root, key_index, runs)
    emit_progress(3, f"Scaling {len(candidates)} candidate position rows...")
    scales = scale_by_position(candidates)
    emit_progress(4, "Building same-position neighbor suggestions...")
    neighbor_rows, suggestion_rows = build_irl_neighbors(master_players, candidates, scales)

    emit_progress(5, "Preparing candidate model rows...")
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
        "season": season,
        "source_master_sqlite": str(MASTER_SQLITE.resolve()),
        "source_runs": [str((root / RUNS_DIR / run).resolve()) for run in runs],
        "rule": "same-position stat-profile neighbors only; no position weights; no cross-position blending",
        "features": list(FEATURES),
        "vital_columns": list(VITAL_COLUMNS),
        "target_players": len(master_players),
        "live_rows": len(match_rows),
        "matched_live_rows": sum(1 for r in match_rows if r["matched"]),
        "candidate_rows": len({(c["run_id"], c["player_index"]) for c in candidates}),
        "candidate_position_rows": len(candidates),
        "candidate_rows_by_position": {pos: sum(1 for c in candidates if c["position"] == pos) for pos in POSITIONS},
        "neighbor_rows": len(neighbor_rows),
        "suggested_field_rows": len(suggestion_rows),
        "created_files": [model_path.name],
        "status": f"Rebuilt player generation pool from {len(runs)} runs.",
    }
    emit_progress(6, "Writing player pool neighbor SQLite...")
    write_model_database(
        model_path,
        manifest=manifest,
        candidate_rows=candidate_rows,
        match_rows=match_rows,
        neighbor_rows=neighbor_rows,
        suggestion_rows=suggestion_rows,
    )
    pool_manifest = write_pool_database(
        root,
        season=season,
        runs=runs,
        candidates=candidates,
        match_rows=match_rows,
        fieldnames=fieldnames,
        model_path=model_path,
    )
    manifest["pool_summary"] = pool_manifest
    emit_progress(total_steps, "Player pool SQL sync complete.")
    return manifest


def ensure_player_generation_pool_current(*, root: Path | None = None, season: int = 2026, force: bool = False, progress_callback: Any | None = None) -> dict[str, Any]:
    return sync_player_generation_pool(PlayerGenerationPoolRequest(season=season, root=_REPO_ROOT if root is None else Path(root), force=force), progress_callback=progress_callback)


def build_position_stat_neighbor_model(root: Path, *, season: int = 2026, force: bool = False) -> dict[str, Any]:
    """Backward-compatible API for old callers; program workflow uses sync_player_generation_pool."""
    return ensure_player_generation_pool_current(root=root, season=season, force=force)


def next_output_dir(root: Path) -> Path:
    base = root / OUTPUT_DIR
    nums = []
    for p in base.iterdir() if base.exists() else []:
        if p.is_dir() and p.name.startswith(OUT_PREFIX):
            suffix = p.name[len(OUT_PREFIX):]
            if suffix.isdigit():
                nums.append(int(suffix))
    return base / f"{OUT_PREFIX}{max(nums, default=0) + 1:03d}"


def write_readme(out_dir: Path, manifest: Dict[str, Any]) -> None:
    text = f"""# Position stat-neighbor 2K model

This artifact implements the current modeling rule:

```text
If a 2K player's in-game sim stats align with an IRL player's stats, then that 2K player's attributes/tendencies are evidence for the IRL player's values.
```

Position buckets are strict: PG compares only to PG, SG only to SG, SF only to SF, PF only to PF, C only to C. No position weights or cross-position blending are used.

## Files

- `candidate_pool.csv` — 2K run players expanded into exact position buckets.
- `player_name_matches.csv` — live labels matched to NBA Master names.
- `irl_to_2k_neighbors.csv` — nearest 2K stat-profile matches for every NBA Master target player/position.
- `suggested_field_values.csv` — suggested 2K field values from nearest same-position stat-profile matches.
- `manifest.json` — source and summary.

## Summary

- Target season: {manifest['season']}.
- NBA Master target players: {manifest['target_players']}.
- Candidate rows: {manifest['candidate_rows']}.
- Candidate position-expanded rows: {manifest['candidate_position_rows']}.
- Matched live rows: {manifest['matched_live_rows']} / {manifest['live_rows']}.
- Neighbor rows: {manifest['neighbor_rows']}.
- Suggested field rows: {manifest['suggested_field_rows']}.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")



__all__ = [
    "PlayerGenerationPoolRequest",
    "build_position_stat_neighbor_model",
    "complete_run_ids",
    "ensure_player_generation_pool_current",
    "add_current_roster_to_player_generation_pool",
    "capture_active_roster_pool_rows",
    "player_pool_dir",
    "pool_database_path",
    "pool_source_ids",
    "position_stat_neighbor_model_path",
    "sync_player_generation_pool",
]
