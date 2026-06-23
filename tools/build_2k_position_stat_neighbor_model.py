#!/usr/bin/env python3
"""Build a position-bucket 2K sim-stat nearest-neighbor model.

Core contract:
- 2K exported sim stats are the link between 2K field packages and IRL stats.
- Compare PG only to PG, SG only to SG, SF only to SF, PF only to PF, C only to C.
- No position weights and no cross-position blending.
- NBA Master SQL provides IRL target stats/positions.
- 2K run exports provide sim-output stats plus actual 2K attributes/tendencies to transfer.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RUNS = ("run_001", "run_002", "run_003", "run_004", "run_005", "run_006", "run_007")
POSITIONS = ("PG", "SG", "SF", "PF", "C")
RUNS_DIR = Path("outputs/current_active_stat_extractor_runs/Pull from DATA runs")
OUTPUT_DIR = Path("outputs/current_active_stat_extractor_runs")
MASTER_SQLITE = Path("nba2k_editor/Player Generator/NBA Player Data/NBA_DATA_Master.sqlite")
OUT_PREFIX = "POSITION_STAT_NEIGHBOR_MODEL_"
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
_NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
_FIRST_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "ALEX": ("ALEXANDER", "ALEXANDRE"),
    "ALEXANDER": ("ALEX", "ALEXANDRE"),
    "ALEXANDRE": ("ALEX", "ALEXANDER"),
    "BUB": ("CARLTON",),
    "CARLTON": ("BUB",),
    "BONES": ("NAH", "NAHSHON"),
    "CAM": ("CAMERON",),
    "CAMERON": ("CAM",),
    "MO": ("MOHAMED", "MOUHAMED"),
    "MOHAMED": ("MO", "MOUHAMED"),
    "MOUHAMED": ("MO", "MOHAMED"),
    "NIC": ("NICK", "NICOLAS", "NICHOLAS"),
    "NICK": ("NIC", "NICOLAS", "NICHOLAS"),
    "NICOLAS": ("NIC", "NICK", "NICHOLAS"),
    "NICHOLAS": ("NIC", "NICK", "NICOLAS"),
    "ROB": ("ROBERT",),
    "ROBERT": ("ROB",),
    "SVI": ("SVIATOSLAV",),
    "SVIATOSLAV": ("SVI",),
}
_EXACT_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "DAMIANLILLARD": ("DAME", "DAMEDOLLA"),
    "DAME": ("DAMIANLILLARD",),
    "DAMEDOLLA": ("DAMIANLILLARD",),
    "FREDVANVLEET": ("FVV",),
    "FVV": ("FREDVANVLEET",),
    "KYRIEIRVING": ("UNCLEDREW",),
    "UNCLEDREW": ("KYRIEIRVING",),
    "TYRESEHALIBURTON": ("HALI",),
    "HALI": ("TYRESEHALIBURTON",),
    "TERRYROZIER": ("SCARYTERRY",),
    "TERRYROZIERIII": ("TERRYROZIER", "SCARYTERRY"),
    "SCARYTERRY": ("TERRYROZIER", "TERRYROZIERIII"),
    "MAXWELLLEWIS": ("MAXLEWIS",),
    "MAXLEWIS": ("MAXWELLLEWIS",),
}


def ascii_name_text(value: object) -> str:
    text = str(value or "")
    for bad, good in (
        ("\u00c4\u008d", "č"),
        ("\u00c4\u008c", "Č"),
        ("\u00c4i\u00c5\u00ab", "čiū"),
        ("\u00c5\u00ab", "ū"),
        ("\u00c4\u2021", "ć"),
        ("\u00c4\u2020", "Ć"),
        ("\u00c3\u00a9", "é"),
    ):
        text = text.replace(bad, good)
    text = text.replace("ё", "e").replace("Ё", "E")
    try:
        text = text.encode("cp1252").decode("utf-8")
    except Exception:
        pass
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", ascii_name_text(value).upper())


def name_tokens(value: object) -> tuple[str, ...]:
    text = ascii_name_text(value).upper()
    return tuple(token for token in re.split(r"[^A-Z0-9]+", text) if token)


def person_name_keys(*values: object) -> tuple[str, ...]:
    keys: list[str] = []
    for value in values:
        exact = identity(value)
        if exact:
            keys.append(exact)
            keys.extend(_EXACT_NAME_ALIASES.get(exact, ()))
        tokens = name_tokens(value)
        if not tokens:
            continue
        without_suffix = tuple(token for token in tokens if token not in _NAME_SUFFIXES)
        if without_suffix and without_suffix != tokens:
            keys.append("".join(without_suffix))
        if len(without_suffix) >= 2:
            first = without_suffix[0]
            last = without_suffix[-1]
            keys.append(first + last)
            for alias in _FIRST_NAME_ALIASES.get(first, ()):
                keys.append(alias + last)
    return tuple(dict.fromkeys(k for k in keys if k))


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
    found = []
    for pos in POSITIONS:
        if re.search(rf"\b{pos}\b", text):
            found.append(pos)
    if not found:
        if text == "G":
            found = ["PG", "SG"]
        elif text == "F":
            found = ["SF", "PF"]
        elif text == "F-C":
            found = ["SF", "PF", "C"]
        elif text == "G-F":
            found = ["PG", "SG", "SF"]
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


def load_master(root: Path, season: int) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    con = sqlite3.connect(root / MASTER_SQLITE)
    con.row_factory = sqlite3.Row
    tables = {}
    for table in ["player_season_info", "player_per_game", "player_per_36_min", "advanced", "player_play_by_play"]:
        rows = con.execute(f"select * from {table} where season = ?", (season,)).fetchall()
        tables[table] = {pid: dict(row) for pid, row in select_player_rows(rows).items()}
    players: Dict[str, Dict[str, Any]] = {}
    key_index: Dict[str, Dict[str, Any]] = {}
    player_ids = set().union(*(set(t.keys()) for t in tables.values()))
    for pid in sorted(player_ids):
        pg = tables["player_per_game"].get(pid, {})
        p36 = tables["player_per_36_min"].get(pid, {})
        info = tables["player_season_info"].get(pid, {})
        adv = tables["advanced"].get(pid, {})
        pbp = tables["player_play_by_play"].get(pid, {})
        name = pg.get("player") or info.get("player") or pid
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
        }
        players[pid] = row
        for key in person_name_keys(name):
            key_index.setdefault(key, row)
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


def match_live_player(label: str, key_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for key in person_name_keys(label):
        if key in key_index:
            return key_index[key]
    tokens = tuple(token for token in name_tokens(label) if token not in _NAME_SUFFIXES)
    if len(tokens) == 2:
        for key in person_name_keys(f"{tokens[1]} {tokens[0]}"):
            if key in key_index:
                return key_index[key]
    return None


def load_candidates(root: Path, key_index: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    candidates: List[Dict[str, Any]] = []
    match_rows: List[Dict[str, Any]] = []
    fieldnames: list[str] = []
    for run_id in RUNS:
        run_dir = root / RUNS_DIR / run_id
        stats_rows = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_stats.csv")}
        attrs_rows = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_attributes.csv")}
        tends_rows = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_tendencies.csv")}
        if not fieldnames and attrs_rows and tends_rows:
            attr_fields = [c for c in next(iter(attrs_rows.values())).keys() if c not in BASE_COLS]
            tend_fields = [c for c in next(iter(tends_rows.values())).keys() if c not in BASE_COLS]
            fieldnames = [f"Attribute::{c}" for c in attr_fields] + [f"Tendency::{c}" for c in tend_fields]
        for idx, stats in stats_rows.items():
            label = stats.get("player_label", "")
            master = match_live_player(label, key_index)
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
            for pos in master["positions"]:
                candidates.append({
                    "run_id": run_id,
                    "player_index": idx,
                    "player_label": label,
                    "master_player": master["player"],
                    "master_player_id": master["player_id"],
                    "position": pos,
                    "features": feats,
                    "fields": fields,
                })
    return candidates, match_rows, fieldnames


def scale_by_position(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Tuple[float, float]]]:
    out: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for pos in POSITIONS:
        rows = [c for c in candidates if c["position"] == pos]
        pos_scales = {}
        for feat in FEATURES:
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


def distance(a: Dict[str, Optional[float]], b: Dict[str, Optional[float]], scales: Dict[str, Tuple[float, float]]) -> Tuple[Optional[float], int]:
    parts = []
    for feat in FEATURES:
        av = a.get(feat)
        bv = b.get(feat)
        if av is None or bv is None:
            continue
        scale = scales.get(feat, (0.0, 1.0))[1] or 1.0
        parts.append(((float(av) - float(bv)) / scale) ** 2)
    if len(parts) < 6:
        return None, len(parts)
    return math.sqrt(sum(parts) / len(parts)), len(parts)


def nearest_neighbors(target_features: Dict[str, Optional[float]], pos: str, candidates_by_pos: Dict[str, List[Dict[str, Any]]], scales: Dict[str, Dict[str, Tuple[float, float]]], *, exclude_player_id: str = "", exclude_run: str = "", k: int = 10) -> List[Dict[str, Any]]:
    rows = []
    for c in candidates_by_pos.get(pos, []):
        if exclude_player_id and c["master_player_id"] == exclude_player_id:
            continue
        if exclude_run and c["run_id"] == exclude_run:
            continue
        dist, common = distance(target_features, c["features"], scales[pos])
        if dist is None:
            continue
        rows.append({"candidate": c, "distance": dist, "common_features": common})
    rows.sort(key=lambda r: r["distance"])
    return rows[:k]


def build_irl_neighbors(master_players: Dict[str, Dict[str, Any]], candidates: List[Dict[str, Any]], scales: Dict[str, Dict[str, Tuple[float, float]]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_pos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        by_pos[c["position"]].append(c)
    neighbor_rows: List[Dict[str, Any]] = []
    suggestion_rows: List[Dict[str, Any]] = []
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
            top5 = [n["candidate"] for n in neigh[:5]]
            if not top5:
                continue
            all_fields = sorted(set().union(*(set(c["fields"].keys()) for c in top5)))
            for field_key in all_fields:
                vals = [float(c["fields"][field_key]) for c in top5 if field_key in c["fields"]]
                if not vals:
                    continue
                kind, field = field_key.split("::", 1)
                suggestion_rows.append({
                    "target_player": player["player"],
                    "target_player_id": player["player_id"],
                    "target_team": player["team"],
                    "position": pos,
                    "Type": kind,
                    "Input Field": field,
                    "suggested_top1": int(round(top5[0]["fields"].get(field_key, median_float(vals)))),
                    "suggested_top5_median": round(median_float(vals), 4),
                    "neighbor_count": len(vals),
                    "top_neighbor": top5[0]["player_label"],
                })
    return neighbor_rows, suggestion_rows


def build_holdout(candidates: List[Dict[str, Any]], scales: Dict[str, Dict[str, Tuple[float, float]]], fieldnames: Sequence[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    by_pos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        by_pos[c["position"]].append(c)
    pred_rows: List[Dict[str, Any]] = []
    for c in candidates:
        neigh = nearest_neighbors(c["features"], c["position"], by_pos, scales, exclude_player_id=c["master_player_id"], exclude_run=c["run_id"], k=5)
        top = [n["candidate"] for n in neigh]
        if not top:
            continue
        for field_key in fieldnames:
            actual = c["fields"].get(field_key)
            vals = [n["fields"][field_key] for n in top if field_key in n["fields"]]
            if actual is None or not vals:
                continue
            pred = median_float([float(v) for v in vals])
            kind, field = field_key.split("::", 1)
            pred_rows.append({
                "holdout_run": c["run_id"],
                "player_index": c["player_index"],
                "player_label": c["player_label"],
                "master_player_id": c["master_player_id"],
                "position": c["position"],
                "Type": kind,
                "Input Field": field,
                "actual_value": int(round(float(actual))),
                "predicted_value": int(round(pred)),
                "raw_predicted_value": round(pred, 4),
                "abs_error": abs(int(round(pred)) - float(actual)),
                "top_neighbors": "; ".join(n["player_label"] for n in top[:5]),
            })
    by_field: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in pred_rows:
        by_field[(r["Type"], r["Input Field"])].append(r)
    metric_rows = []
    for (kind, field), rows in sorted(by_field.items()):
        errors = [float(r["abs_error"]) for r in rows]
        metric_rows.append({
            "Type": kind,
            "Input Field": field,
            "tested_rows": len(rows),
            "mae": round(sum(errors) / len(errors), 4),
            "median_abs_error": round(median_float(errors), 4),
            "within_5_pct": round(100.0 * sum(e <= 5 for e in errors) / len(errors), 2),
            "within_10_pct": round(100.0 * sum(e <= 10 for e in errors) / len(errors), 2),
        })
    all_errors = [float(r["abs_error"]) for r in pred_rows]
    summary = {
        "prediction_rows": len(pred_rows),
        "tested_fields": len(by_field),
        "overall_mae": round(sum(all_errors) / len(all_errors), 4) if all_errors else None,
        "overall_median_abs_error": round(median_float(all_errors), 4) if all_errors else None,
        "overall_within_5_pct": round(100.0 * sum(e <= 5 for e in all_errors) / len(all_errors), 2) if all_errors else None,
        "overall_within_10_pct": round(100.0 * sum(e <= 10 for e in all_errors) / len(all_errors), 2) if all_errors else None,
    }
    return pred_rows, metric_rows, summary


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
- `holdout_predictions.csv` — candidate-to-candidate leave-run/same-player-excluded validation predictions.
- `holdout_field_metrics.csv` — field-level validation errors.
- `manifest.json` — source and summary.

## Summary

- Target season: {manifest['season']}.
- NBA Master target players: {manifest['target_players']}.
- Candidate rows: {manifest['candidate_rows']}.
- Candidate position-expanded rows: {manifest['candidate_position_rows']}.
- Matched live rows: {manifest['matched_live_rows']} / {manifest['live_rows']}.
- Neighbor rows: {manifest['neighbor_rows']}.
- Suggested field rows: {manifest['suggested_field_rows']}.
- Holdout MAE: {manifest['holdout_summary']['overall_mae']}.
- Holdout within 10: {manifest['holdout_summary']['overall_within_10_pct']}%.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out_dir = next_output_dir(root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    master_players, key_index = load_master(root, args.season)
    candidates, match_rows, fieldnames = load_candidates(root, key_index)
    scales = scale_by_position(candidates)
    neighbor_rows, suggestion_rows = build_irl_neighbors(master_players, candidates, scales)
    holdout_rows, holdout_metric_rows, holdout_summary = build_holdout(candidates, scales, fieldnames)

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
        for feat in FEATURES:
            row[feat] = c["features"].get(feat)
        candidate_rows.append(row)

    write_csv(out_dir / "candidate_pool.csv", candidate_rows, ["run_id", "player_index", "player_label", "master_player", "master_player_id", "position", *FEATURES])
    write_csv(out_dir / "player_name_matches.csv", match_rows, ["run_id", "player_index", "live_player_label", "matched", "master_player", "master_player_id", "positions"])
    write_csv(out_dir / "irl_to_2k_neighbors.csv", neighbor_rows, ["target_player", "target_player_id", "target_team", "position", "neighbor_rank", "distance", "common_features", "neighbor_run_id", "neighbor_player_index", "neighbor_live_label", "neighbor_master_player", "neighbor_master_player_id"])
    write_csv(out_dir / "suggested_field_values.csv", suggestion_rows, ["target_player", "target_player_id", "target_team", "position", "Type", "Input Field", "suggested_top1", "suggested_top5_median", "neighbor_count", "top_neighbor"])
    write_csv(out_dir / "holdout_predictions.csv", holdout_rows, ["holdout_run", "player_index", "player_label", "master_player_id", "position", "Type", "Input Field", "actual_value", "predicted_value", "raw_predicted_value", "abs_error", "top_neighbors"])
    write_csv(out_dir / "holdout_field_metrics.csv", holdout_metric_rows, ["Type", "Input Field", "tested_rows", "mae", "median_abs_error", "within_5_pct", "within_10_pct"])

    manifest = {
        "output_dir": str(out_dir),
        "season": args.season,
        "source_master_sqlite": str((root / MASTER_SQLITE).resolve()),
        "source_runs": [str((root / RUNS_DIR / run).resolve()) for run in RUNS],
        "rule": "same-position stat-profile neighbors only; no position weights; no cross-position blending",
        "features": list(FEATURES),
        "target_players": len(master_players),
        "live_rows": len(match_rows),
        "matched_live_rows": sum(1 for r in match_rows if r["matched"]),
        "candidate_rows": len({(c["run_id"], c["player_index"]) for c in candidates}),
        "candidate_position_rows": len(candidates),
        "candidate_rows_by_position": {pos: sum(1 for c in candidates if c["position"] == pos) for pos in POSITIONS},
        "neighbor_rows": len(neighbor_rows),
        "suggested_field_rows": len(suggestion_rows),
        "holdout_summary": holdout_summary,
        "created_files": ["README.md", "candidate_pool.csv", "player_name_matches.csv", "irl_to_2k_neighbors.csv", "suggested_field_values.csv", "holdout_predictions.csv", "holdout_field_metrics.csv", "manifest.json"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(out_dir, manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
