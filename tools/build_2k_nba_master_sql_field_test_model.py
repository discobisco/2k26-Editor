#!/usr/bin/env python3
"""Build a testable NBA Master SQL driven 2K field model.

This is the richer successor to the four-run-only bucket model. It uses:
- NBA_DATA_Master.sqlite for BRef/player/team/stat evidence.
- nba.sqlite draft_combine_stats for athleticism evidence.
- four current-active 2K exports only as target labels for testing.

It does not wire Player Generator runtime code. It writes a run-scoped artifact for
model testing/calibration.
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

RUNS = ("run_001", "run_002", "run_003", "run_004")
RUNS_DIR = Path("outputs/current_active_stat_extractor_runs")
MASTER_SQLITE = Path("nba2k_editor/Player Generator/NBA Player Data/NBA_DATA_Master.sqlite")
NBA_SQLITE = Path("nba2k_editor/Player Generator/NBA Player Data/nba.sqlite")
OUT_PREFIX = "NBA_MASTER_SQL_FIELD_TEST_MODEL_"
BASE_COLS = {"team_slot", "team_index", "team_label", "roster_slot", "player_index", "player_label"}
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

_NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}


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
    """Project matcher logic copied from game_port._person_name_keys."""
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
    return tuple(dict.fromkeys(key for key in keys if key))


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
    if not s or s.upper() in {"NA", "NAN", "NONE", "NULL"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def median_float(vals: Sequence[float]) -> float:
    return float(median(vals))


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def rmse(errors: Sequence[float]) -> Optional[float]:
    if not errors:
        return None
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def next_output_dir(root: Path) -> Path:
    base = root / RUNS_DIR
    existing = []
    if base.exists():
        for p in base.iterdir():
            if p.is_dir() and p.name.startswith(OUT_PREFIX):
                suffix = p.name[len(OUT_PREFIX) :]
                if suffix.isdigit():
                    existing.append(int(suffix))
    n = max(existing, default=0) + 1
    return base / f"{OUT_PREFIX}{n:03d}"


def is_aggregate_team(team: object) -> bool:
    value = str(team or "").upper()
    return value == "TOT" or bool(re.fullmatch(r"\dTM", value))


def row_get(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def select_player_rows(rows: List[sqlite3.Row]) -> Dict[str, sqlite3.Row]:
    by_player: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_player[str(row["player_id"])].append(row)
    selected = {}
    for player_id, group in by_player.items():
        aggregate = [r for r in group if is_aggregate_team(row_get(r, "team"))]
        candidates = aggregate or group
        selected[player_id] = max(candidates, key=lambda r: (as_float(row_get(r, "g")) or 0, as_float(row_get(r, "mp")) or as_float(row_get(r, "mp_per_game")) or 0))
    return selected


def load_table_by_player(con: sqlite3.Connection, table: str, season: int) -> Dict[str, Dict[str, Any]]:
    con.row_factory = sqlite3.Row
    rows = con.execute(f"select * from {table} where season = ?", (season,)).fetchall()
    selected = select_player_rows(rows)
    return {pid: dict(row) for pid, row in selected.items()}


def add_numeric_features(prefix: str, row: Optional[Dict[str, Any]], out: Dict[str, float]) -> None:
    if not row:
        return
    skip = {"season", "lg", "player", "player_id", "age", "team", "pos"}
    for key, value in row.items():
        if key in skip:
            continue
        v = as_float(value)
        if v is not None:
            out[f"{prefix}.{key}"] = v


def per36(row: Optional[Dict[str, Any]], col: str) -> Optional[float]:
    if not row:
        return None
    ratio = safe_div(as_float(row.get(col)), as_float(row.get("mp")))
    return None if ratio is None else ratio * 36.0


def neg(v: Optional[float]) -> Optional[float]:
    return None if v is None else -v


def load_combine_by_name(nba_con: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    nba_con.row_factory = sqlite3.Row
    rows = nba_con.execute("select * from draft_combine_stats").fetchall()
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        d = dict(row)
        # Keep first by key; combine rows are player-career measurements, not season rows.
        for key in person_name_keys(d.get("player_name"), f"{d.get('first_name','')} {d.get('last_name','')}"):
            by_key.setdefault(key, d)
    return by_key


def load_draft_by_name(nba_con: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    nba_con.row_factory = sqlite3.Row
    rows = nba_con.execute("select * from draft_history").fetchall()
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        d = dict(row)
        for key in person_name_keys(d.get("player_name")):
            by_key.setdefault(key, d)
    return by_key


def load_master_features(root: Path, season: int) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    master = sqlite3.connect(root / MASTER_SQLITE)
    nba = sqlite3.connect(root / NBA_SQLITE)
    tables = {
        "info": load_table_by_player(master, "player_season_info", season),
        "per_game": load_table_by_player(master, "player_per_game", season),
        "per36": load_table_by_player(master, "player_per_36_min", season),
        "per100": load_table_by_player(master, "player_per_100_poss", season),
        "advanced": load_table_by_player(master, "advanced", season),
        "shooting": load_table_by_player(master, "player_shooting", season),
        "pbp": load_table_by_player(master, "player_play_by_play", season),
    }
    player_info_rows = master.execute("select * from player_info").fetchall()
    player_info = {str(row["player_id"]): dict(row) for row in player_info_rows}
    combine_by_name = load_combine_by_name(nba)
    draft_by_name = load_draft_by_name(nba)

    player_ids = set().union(*(set(t.keys()) for t in tables.values()))
    players: Dict[str, Dict[str, Any]] = {}
    key_index: Dict[str, Dict[str, Any]] = {}
    combine_matched = 0
    draft_matched = 0

    for pid in sorted(player_ids):
        info = tables["info"].get(pid) or tables["per_game"].get(pid) or {}
        name = info.get("player") or pid
        features: Dict[str, float] = {}
        for prefix, table_rows in tables.items():
            add_numeric_features(prefix, table_rows.get(pid), features)
        add_numeric_features("bio", player_info.get(pid), features)

        pbp = tables["pbp"].get(pid)
        for col in [
            "bad_pass_turnover",
            "lost_ball_turnover",
            "shooting_foul_committed",
            "offensive_foul_committed",
            "shooting_foul_drawn",
            "offensive_foul_drawn",
            "points_generated_by_assists",
            "and1",
            "fga_blocked",
        ]:
            v = per36(pbp, col)
            if v is not None:
                features[f"pbp.{col}_per36"] = v
                if "turnover" in col or "fga_blocked" in col:
                    features[f"pbp.inverse_{col}_per36"] = -v

        adv = tables["advanced"].get(pid)
        if adv:
            tov = as_float(adv.get("tov_percent"))
            if tov is not None:
                features["advanced.inverse_tov_percent"] = -tov
            age = as_float(adv.get("age"))
            if age is not None:
                features["advanced.inverse_age"] = -age

        # Name-based combine/draft bridge from NBA API archive.
        combine = None
        draft = None
        for key in person_name_keys(name):
            combine = combine or combine_by_name.get(key)
            draft = draft or draft_by_name.get(key)
        if combine:
            combine_matched += 1
            for col, val in combine.items():
                v = as_float(val)
                if v is not None:
                    features[f"combine.{col}"] = v
            sprint = as_float(combine.get("three_quarter_sprint"))
            lane = as_float(combine.get("lane_agility_time"))
            mod_lane = as_float(combine.get("modified_lane_agility_time"))
            if sprint is not None:
                features["combine.inverse_three_quarter_sprint"] = -sprint
            if lane is not None:
                features["combine.inverse_lane_agility_time"] = -lane
            if mod_lane is not None:
                features["combine.inverse_modified_lane_agility_time"] = -mod_lane
        if draft:
            draft_matched += 1
            for col, val in draft.items():
                v = as_float(val)
                if v is not None:
                    features[f"draft.{col}"] = v
            pick = as_float(draft.get("overall_pick"))
            if pick is not None:
                features["draft.inverse_overall_pick"] = -pick

        row = {
            "player_id": pid,
            "player": name,
            "team": info.get("team", ""),
            "features": features,
            "has_combine": combine is not None,
            "has_draft": draft is not None,
        }
        players[pid] = row
        for key in person_name_keys(name):
            key_index.setdefault(key, row)

    master.close()
    nba.close()
    summary = {
        "season": season,
        "master_players": len(players),
        "combine_matched_players": combine_matched,
        "draft_matched_players": draft_matched,
    }
    return players, key_index, summary


def feature_spec_for_field(field: str, field_type: str) -> Tuple[List[Dict[str, str]], str]:
    f = field.lower()
    specs: List[Tuple[str, str, str]] = []
    status = "modeled"

    def add(name: str, grade: str = "direct", reason: str = "") -> None:
        specs.append((name, grade, reason))

    if field_type == "Attribute":
        if "3pt shot" in f:
            add("shooting.fg_percent_from_x3p_range", "direct", "3PT accuracy")
            add("per100.x3pa_per_100_poss", "support", "3PT sample/role")
            add("advanced.x3p_ar", "support", "3PT attempt share")
        elif "ball control" in f:
            add("advanced.inverse_tov_percent", "direct", "ball security")
            add("pbp.inverse_lost_ball_turnover_per36", "direct", "lost-ball control")
            add("advanced.ast_percent", "support", "on-ball creation")
        elif "close shot" in f:
            add("shooting.fg_percent_from_x0_3_range", "direct", "rim/close make rate")
            add("shooting.fg_percent_from_x3_10_range", "direct", "short close make rate")
        elif "draw foul" in f:
            add("advanced.f_tr", "direct", "free throw rate")
            add("pbp.shooting_foul_drawn_per36", "direct", "drawn shooting fouls")
        elif "driving dunk" in f:
            add("shooting.percent_dunks_of_fga", "direct", "dunk share")
            add("shooting.num_of_dunks", "direct", "dunk volume")
            add("combine.max_vertical_leap", "combine", "explosion")
        elif "driving layup" in f:
            add("shooting.fg_percent_from_x0_3_range", "direct", "rim finishing")
            add("shooting.percent_fga_from_x0_3_range", "support", "rim attempts")
            add("pbp.and1_per36", "support", "finishing through contact")
        elif "free throws" in f:
            add("per_game.ft_percent", "direct", "free throw percentage")
        elif "midrange shot" in f:
            add("shooting.fg_percent_from_x16_3p_range", "direct", "long midrange accuracy")
            add("shooting.percent_fga_from_x16_3p_range", "support", "midrange sample")
        elif "offensive consistency" in f:
            add("advanced.ows", "direct", "offensive win shares")
            add("advanced.obpm", "direct", "offensive impact")
            add("advanced.ts_percent", "support", "scoring efficiency")
        elif "pass accuracy" in f:
            add("advanced.ast_percent", "direct", "assist creation")
            add("per100.ast_per_100_poss", "direct", "assist rate")
            add("advanced.inverse_tov_percent", "support", "mistake avoidance")
        elif "passing iq" in f:
            add("advanced.ast_percent", "direct", "assist creation")
            add("advanced.inverse_tov_percent", "direct", "decision security")
        elif "passing vision" in f:
            add("advanced.ast_percent", "direct", "creation share")
            add("pbp.points_generated_by_assists_per36", "direct", "points generated by assists")
        elif any(x in f for x in ["post fade", "post hook", "post moves"]):
            status = "not_modeled"
        elif "shot iq" in f:
            add("advanced.ts_percent", "direct", "true shooting")
            add("advanced.e_fg_percent", "direct", "effective FG")
            add("advanced.inverse_tov_percent", "support", "low-error offense")
        elif "standing dunk" in f:
            add("shooting.percent_dunks_of_fga", "direct", "dunk share")
            add("shooting.num_of_dunks", "direct", "dunk volume")
            add("bio.ht_in_in", "support", "height/reach context")
            add("combine.standing_reach", "combine", "standing reach")
        elif "block" in f:
            add("advanced.blk_percent", "direct", "block percentage")
            add("per100.blk_per_100_poss", "direct", "block rate")
        elif "defensive consistency" in f:
            add("advanced.dws", "direct", "defensive win shares")
            add("advanced.dbpm", "direct", "defensive box impact")
        elif "help defense" in f:
            add("advanced.dbpm", "direct", "defensive impact")
            add("advanced.dws", "support", "defensive value")
        elif "interior defense" in f:
            add("advanced.blk_percent", "direct", "rim protection")
            add("advanced.drb_percent", "support", "interior board control")
            add("bio.ht_in_in", "support", "size")
            add("bio.wt", "support", "strength mass")
        elif "pass perception" in f:
            add("advanced.stl_percent", "support", "available disruption proxy")
            add("advanced.dbpm", "support", "defensive read impact")
        elif "perimeter defense" in f:
            add("advanced.stl_percent", "direct", "perimeter disruption")
            add("advanced.dbpm", "direct", "defensive impact")
            add("pbp.pg_percent", "support", "guard matchup context")
            add("pbp.sg_percent", "support", "wing matchup context")
        elif "steal" in f:
            add("advanced.stl_percent", "direct", "steal percentage")
            add("per100.stl_per_100_poss", "direct", "steal rate")
        elif "agility" in f:
            add("combine.inverse_lane_agility_time", "combine", "draft combine lane agility")
            add("combine.inverse_modified_lane_agility_time", "combine", "modified lane agility")
        elif f.endswith("speed") or " / speed" in f and "with ball" not in f:
            add("combine.inverse_three_quarter_sprint", "combine", "draft combine sprint")
            add("combine.inverse_lane_agility_time", "combine", "agility support")
        elif "speed with ball" in f:
            add("combine.inverse_three_quarter_sprint", "combine", "sprint with ball athletic base")
            add("combine.inverse_lane_agility_time", "combine", "change of direction")
            add("advanced.inverse_tov_percent", "support", "ball security support")
        elif "stamina" in f:
            add("per_game.mp_per_game", "direct", "minutes workload")
            add("per_game.g", "support", "availability")
            add("per_game.gs", "support", "starter workload")
        elif "strength" in f:
            add("combine.bench_press", "combine", "draft combine strength")
            add("combine.weight", "combine", "combine weight")
            add("bio.wt", "support", "listed playing weight")
        elif "vertical" in f:
            add("combine.max_vertical_leap", "combine", "draft combine max vertical")
            add("combine.standing_vertical_leap", "combine", "draft combine standing vertical")
            add("shooting.percent_dunks_of_fga", "support", "functional vertical/dunk signal")
        elif "durability" in f:
            add("per_game.g", "direct", "games played availability")
        elif "hands" in f:
            add("advanced.inverse_tov_percent", "direct", "ball-security proxy")
            add("pbp.inverse_bad_pass_turnover_per36", "support", "bad-pass avoidance")
            add("pbp.inverse_lost_ball_turnover_per36", "support", "lost-ball avoidance")
        elif "hustle" in f:
            add("advanced.orb_percent", "support", "effort boards")
            add("advanced.drb_percent", "support", "board activity")
            add("advanced.stl_percent", "support", "activity")
            add("advanced.blk_percent", "support", "activity")
        elif "intangibles" in f:
            add("advanced.ws", "support", "overall contribution")
            add("advanced.bpm", "support", "impact")
        elif "potential" in f:
            add("advanced.inverse_age", "support", "younger-player upside context")
            add("draft.inverse_overall_pick", "support", "draft capital")
        elif "defensive rebound" in f:
            add("advanced.drb_percent", "direct", "defensive rebound percentage")
            add("per100.drb_per_100_poss", "direct", "defensive rebound rate")
        elif "offensive rebound" in f:
            add("advanced.orb_percent", "direct", "offensive rebound percentage")
            add("per100.orb_per_100_poss", "direct", "offensive rebound rate")
        else:
            status = "not_modeled"
    else:
        exact_3pt = {
            "Jump Shooting / Shot 3pt",
            "Tendencies / Shoot",
        }
        exact_mid = {
            "Jump Shooting / Shot Mid",
        }
        exact_close = {
            "Jump Shooting / Shot Close",
            "Jump Shooting / Shot Under Basket",
            "Layups And Dunks / Driving Layup Tendency",
        }
        exact_dunk = {
            "Layups And Dunks / Driving Dunk Tendency",
            "Layups And Dunks / Standing Dunk Tendency",
        }
        exact_orb = {
            "Layups And Dunks / Putback",
            "Layups And Dunks / Putback Dunk",
            "Layups And Dunks / Crash",
        }
        exact_drive = {
            "Driving / Drive",
            "Driving / Attack Strong On Drive",
        }
        exact_pass = {
            "Passing / Dish To Open Man",
        }
        exact_foul = {
            "Defense / Foul",
        }
        exact_steal = {
            "Defense / On Ball Steal",
            "Defense / Pass Interception",
        }
        exact_block = {
            "Defense / Block Shot",
        }
        if field.startswith("Hot Zones /"):
            status = "not_modeled"
        elif field in exact_steal:
            add("advanced.stl_percent", "direct", "steal/pass-interception frequency proxy from steal percentage")
            add("per100.stl_per_100_poss", "direct", "steal rate")
        elif field in exact_block:
            add("advanced.blk_percent", "direct", "block frequency")
            add("per100.blk_per_100_poss", "direct", "block rate")
        elif field in exact_foul:
            add("pbp.shooting_foul_committed_per36", "direct", "shooting foul frequency")
            add("pbp.offensive_foul_committed_per36", "direct", "offensive foul frequency")
            add("per100.pf_per_100_poss", "support", "personal foul rate")
        elif field in exact_3pt:
            add("shooting.percent_fga_from_x3p_range", "direct", "3PT shot share")
            add("per100.x3pa_per_100_poss", "direct", "3PT attempt rate")
            add("advanced.x3p_ar", "direct", "3PT attempt ratio")
            if field == "Tendencies / Shoot":
                add("advanced.usg_percent", "direct", "overall usage")
                add("per100.fga_per_100_poss", "direct", "overall shot attempt rate")
        elif field in exact_mid:
            add("shooting.percent_fga_from_x16_3p_range", "direct", "midrange shot share")
            add("shooting.percent_fga_from_x10_16_range", "support", "short-mid share")
        elif field in exact_close:
            add("shooting.percent_fga_from_x0_3_range", "direct", "rim/close attempt share")
            add("shooting.percent_fga_from_x3_10_range", "support", "short attempt share")
            add("advanced.f_tr", "support", "drive/contact rate")
        elif field in exact_dunk:
            add("shooting.percent_dunks_of_fga", "direct", "dunk share")
            add("shooting.num_of_dunks", "direct", "dunk volume")
            add("combine.max_vertical_leap", "combine", "explosion support")
        elif field in exact_orb:
            add("advanced.orb_percent", "direct", "offensive rebound activity")
            add("per100.orb_per_100_poss", "direct", "offensive rebound rate")
        elif field in exact_drive:
            add("advanced.f_tr", "direct", "drive/contact proxy")
            add("shooting.percent_fga_from_x0_3_range", "direct", "rim pressure")
            add("pbp.and1_per36", "support", "drive finish contact")
        elif field == "Freelance / Touches":
            add("advanced.usg_percent", "direct", "usage")
            add("per100.fga_per_100_poss", "direct", "shot attempt rate")
            add("advanced.ast_percent", "support", "touch creation")
        elif field in exact_pass:
            add("advanced.ast_percent", "direct", "assist creation")
            add("per100.ast_per_100_poss", "direct", "assist rate")
            add("pbp.points_generated_by_assists_per36", "support", "assist value")
        else:
            status = "not_modeled"

    return [{"feature": n, "grade": g, "reason": r} for n, g, r in specs], status


def target_fields_from_runs(root: Path) -> Dict[Tuple[str, str], str]:
    run_dir = root / RUNS_DIR / RUNS[0]
    out: Dict[Tuple[str, str], str] = {}
    for file_name, typ in [("current_active_player_attributes.csv", "Attribute"), ("current_active_player_tendencies.csv", "Tendency")]:
        rows = read_csv(run_dir / file_name)
        if not rows:
            continue
        for col in rows[0].keys():
            if col not in BASE_COLS:
                out[(col, typ)] = col
    return out


def load_live_run_rows(root: Path, run_id: str) -> List[Dict[str, Any]]:
    run_dir = root / RUNS_DIR / run_id
    attrs = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_attributes.csv")}
    tends = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_tendencies.csv")}
    stats = {int(r["player_index"]): r for r in read_csv(run_dir / "current_active_player_stats.csv")}
    rows = []
    for idx, s in stats.items():
        rows.append(
            {
                "run_id": run_id,
                "player_index": idx,
                "player_label": s.get("player_label", ""),
                "team_label": s.get("team_label", ""),
                "attributes": attrs.get(idx, {}),
                "tendencies": tends.get(idx, {}),
            }
        )
    return rows


def actual_value(row: Dict[str, Any], field: str, typ: str) -> Optional[float]:
    source = row["attributes"] if typ == "Attribute" else row["tendencies"]
    return as_float(source.get(field))


def match_live_player(label: str, key_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for key in person_name_keys(label):
        if key in key_index:
            return key_index[key]
    tokens = tuple(token for token in name_tokens(label) if token not in _NAME_SUFFIXES)
    if len(tokens) == 2:
        reversed_label = f"{tokens[1]} {tokens[0]}"
        for key in person_name_keys(reversed_label):
            if key in key_index:
                return key_index[key]
    return None


def build_model_scope(root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    fields = target_fields_from_runs(root)
    rows = []
    for (field, typ) in sorted(fields):
        specs, status = feature_spec_for_field(field, typ)
        rows.append(
            {
                "Input Field": field,
                "Type": typ,
                "Model Status": status if specs else "not_modeled",
                "Feature Count": len(specs),
                "Features": "; ".join(s["feature"] for s in specs),
                "Feature Grades": "; ".join(f"{s['feature']}={s['grade']}" for s in specs),
                "Reason": "; ".join(f"{s['feature']}: {s['reason']}" for s in specs),
            }
        )
    summary = {
        "reviewed_fields": len(rows),
        "modeled_fields": sum(r["Model Status"] == "modeled" for r in rows),
        "not_modeled_fields": sum(r["Model Status"] != "modeled" for r in rows),
    }
    return rows, summary


def build_samples(root: Path, key_index: Dict[str, Dict[str, Any]], scope_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    modeled = {(r["Input Field"], r["Type"]): [f.strip() for f in str(r["Features"]).split(";") if f.strip()] for r in scope_rows if r["Model Status"] == "modeled"}
    samples = []
    match_rows = []
    seen_matches = set()
    for run_id in RUNS:
        for live in load_live_run_rows(root, run_id):
            player = match_live_player(live["player_label"], key_index)
            key = (run_id, live["player_index"])
            if key not in seen_matches:
                seen_matches.add(key)
                match_rows.append(
                    {
                        "run_id": run_id,
                        "player_index": live["player_index"],
                        "live_player_label": live["player_label"],
                        "matched": player is not None,
                        "master_player": "" if player is None else player["player"],
                        "master_player_id": "" if player is None else player["player_id"],
                        "master_team": "" if player is None else player["team"],
                        "has_combine": "" if player is None else player["has_combine"],
                    }
                )
            if not player:
                continue
            features = player["features"]
            for (field, typ), feature_names in modeled.items():
                y = actual_value(live, field, typ)
                if y is None:
                    continue
                present = [{"feature": name, "value": features.get(name)} for name in feature_names if features.get(name) is not None]
                if not present:
                    continue
                samples.append(
                    {
                        "run_id": run_id,
                        "player_index": live["player_index"],
                        "player_label": live["player_label"],
                        "master_player": player["player"],
                        "master_player_id": player["player_id"],
                        "field": field,
                        "type": typ,
                        "actual": y,
                        "features": present,
                    }
                )
    return samples, match_rows


def fit_knots(points: Sequence[Tuple[float, float]], max_knots: int = 9) -> List[Dict[str, Any]]:
    clean = sorted((float(x), float(y)) for x, y in points if math.isfinite(float(x)) and math.isfinite(float(y)))
    if not clean:
        return []
    by_x: Dict[float, List[float]] = defaultdict(list)
    for x, y in clean:
        by_x[x].append(y)
    collapsed = [(x, median_float(ys), len(ys)) for x, ys in sorted(by_x.items())]
    if len(collapsed) <= max_knots:
        return [{"x": x, "y": y, "rows": n} for x, y, n in collapsed]
    bin_size = max(1, math.ceil(len(collapsed) / max_knots))
    knots = []
    for i in range(0, len(collapsed), bin_size):
        chunk = collapsed[i : i + bin_size]
        xs, ys, n = [], [], 0
        for x, y, rows in chunk:
            xs.extend([x] * rows)
            ys.extend([y] * rows)
            n += rows
        knots.append({"x": median_float(xs), "y": median_float(ys), "rows": n})
    return knots


def predict_from_knots(x: float, knots: Sequence[Dict[str, Any]]) -> Optional[float]:
    if not knots:
        return None
    if len(knots) == 1 or x <= knots[0]["x"]:
        return float(knots[0]["y"])
    if x >= knots[-1]["x"]:
        return float(knots[-1]["y"])
    for left, right in zip(knots, knots[1:]):
        lx, rx = float(left["x"]), float(right["x"])
        if lx <= x <= rx:
            if rx == lx:
                return float(right["y"])
            return float(left["y"]) + ((x - lx) / (rx - lx)) * (float(right["y"]) - float(left["y"]))
    return float(knots[-1]["y"])


def train_calibrators(samples: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    points: Dict[Tuple[str, str], List[Tuple[float, float]]] = defaultdict(list)
    for sample in samples:
        for f in sample["features"]:
            points[(sample["field"], f["feature"])].append((float(f["value"]), float(sample["actual"])))
    return {key: fit_knots(vals) for key, vals in points.items()}


def predict_sample(sample: Dict[str, Any], calibrators: Dict[Tuple[str, str], List[Dict[str, Any]]]) -> Tuple[Optional[float], str]:
    preds = []
    vals = []
    for f in sample["features"]:
        name = f["feature"]
        value = float(f["value"])
        vals.append(f"{name}={round(value, 6)}")
        p = predict_from_knots(value, calibrators.get((sample["field"], name), []))
        if p is not None:
            preds.append(p)
    if not preds:
        return None, "; ".join(vals)
    return median_float(preds), "; ".join(vals)


def build_holdout(samples: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for holdout_run in RUNS:
        train = [s for s in samples if s["run_id"] != holdout_run]
        test = [s for s in samples if s["run_id"] == holdout_run]
        calibrators = train_calibrators(train)
        for sample in test:
            pred, feature_values = predict_sample(sample, calibrators)
            if pred is None:
                continue
            actual = float(sample["actual"])
            pred_round = int(round(pred))
            rows.append(
                {
                    "holdout_run": holdout_run,
                    "player_index": sample["player_index"],
                    "player_label": sample["player_label"],
                    "master_player": sample["master_player"],
                    "master_player_id": sample["master_player_id"],
                    "Input Field": sample["field"],
                    "Type": sample["type"],
                    "actual_value": int(round(actual)),
                    "predicted_value": pred_round,
                    "raw_predicted_value": round(pred, 4),
                    "abs_error": abs(pred_round - actual),
                    "signed_error": pred_round - actual,
                    "feature_values": feature_values,
                }
            )
    return rows


def build_metrics(preds: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    by_field: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in preds:
        by_field[(row["Input Field"], row["Type"])].append(row)
    rows = []
    for (field, typ), vals in sorted(by_field.items()):
        actuals = [float(v["actual_value"]) for v in vals]
        predicted = [float(v["predicted_value"]) for v in vals]
        errors = [float(v["abs_error"]) for v in vals]
        signed = [float(v["signed_error"]) for v in vals]
        corr = pearson(actuals, predicted)
        rows.append(
            {
                "Input Field": field,
                "Type": typ,
                "tested_rows": len(vals),
                "mae": round(sum(errors) / len(errors), 4),
                "rmse": round(rmse(errors) or 0.0, 4),
                "median_abs_error": round(median_float(errors), 4),
                "bias_signed_error": round(sum(signed) / len(signed), 4),
                "within_5_pct": round(100.0 * sum(e <= 5 for e in errors) / len(errors), 2),
                "within_10_pct": round(100.0 * sum(e <= 10 for e in errors) / len(errors), 2),
                "actual_min": min(actuals),
                "actual_max": max(actuals),
                "predicted_min": min(predicted),
                "predicted_max": max(predicted),
                "pearson_actual_predicted": "" if corr is None else round(corr, 4),
            }
        )
    all_errors = [float(v["abs_error"]) for v in preds]
    all_signed = [float(v["signed_error"]) for v in preds]
    summary = {
        "tested_prediction_rows": len(preds),
        "tested_fields": len(by_field),
        "overall_mae": round(sum(all_errors) / len(all_errors), 4) if all_errors else None,
        "overall_rmse": round(rmse(all_errors) or 0.0, 4) if all_errors else None,
        "overall_median_abs_error": round(median_float(all_errors), 4) if all_errors else None,
        "overall_bias_signed_error": round(sum(all_signed) / len(all_signed), 4) if all_signed else None,
        "overall_within_5_pct": round(100.0 * sum(e <= 5 for e in all_errors) / len(all_errors), 2) if all_errors else None,
        "overall_within_10_pct": round(100.0 * sum(e <= 10 for e in all_errors) / len(all_errors), 2) if all_errors else None,
    }
    return rows, summary


def write_model_knots(out_dir: Path, samples: Sequence[Dict[str, Any]]) -> int:
    calibrators = train_calibrators(samples)
    rows = []
    for (field, feature), knots in sorted(calibrators.items()):
        for i, knot in enumerate(knots, 1):
            rows.append(
                {
                    "Input Field": field,
                    "Feature": feature,
                    "knot_index": i,
                    "feature_value": round(float(knot["x"]), 8),
                    "field_value_median": round(float(knot["y"]), 4),
                    "training_rows": int(knot["rows"]),
                }
            )
    write_csv(out_dir / "model_knots.csv", rows, ["Input Field", "Feature", "knot_index", "feature_value", "field_value_median", "training_rows"])
    return len(rows)


def write_readme(out_dir: Path, manifest: Dict[str, Any]) -> None:
    text = f"""# NBA Master SQL field test model

Standalone test model using NBA Master SQLite stats plus NBA API draft-combine measurements.

## Files

- `model_scope.csv` — every active export field with modeled/not-modeled status and SQL features.
- `player_name_matches.csv` — live 2K player labels matched to NBA Master rows using the project name-key logic.
- `model_knots.csv` — fitted SQL feature -> 2K field calibration knots.
- `holdout_predictions.csv` — leave-one-run-out player/field predictions.
- `field_metrics.csv` — field-level MAE/RMSE/correlation/within-5/within-10.
- `manifest.json` — source lineage and summary.

## Summary

- Season: {manifest['season']}.
- Master players: {manifest['master_summary']['master_players']}.
- Live player match rate: {manifest['match_summary']['matched_players']} / {manifest['match_summary']['live_player_rows']} rows.
- Combine matched master players: {manifest['master_summary']['combine_matched_players']}.
- Reviewed fields: {manifest['scope_summary']['reviewed_fields']}.
- Modeled fields: {manifest['scope_summary']['modeled_fields']}.
- Holdout tested fields: {manifest['holdout_summary']['tested_fields']}.
- Holdout prediction rows: {manifest['holdout_summary']['tested_prediction_rows']}.
- Overall MAE: {manifest['holdout_summary']['overall_mae']}.
- Overall within 10: {manifest['holdout_summary']['overall_within_10_pct']}%.

## Contract

This is not production Player Generator wiring. It is the richer SQL-backed model artifact for testing. Athleticism fields use `nba.sqlite.draft_combine_stats` where available.

2K exported sim stats are not discarded as noise: they are the empirical link between 2K attributes/tendencies and IRL stat targets. Incomplete injuries/trades/availability make season-context interpretation imperfect, but the stat relationships remain calibration evidence.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else next_output_dir(root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _, key_index, master_summary = load_master_features(root, args.season)
    scope_rows, scope_summary = build_model_scope(root)
    samples, match_rows = build_samples(root, key_index, scope_rows)
    holdout = build_holdout(samples)
    metrics_rows, holdout_summary = build_metrics(holdout)
    knot_count = write_model_knots(out_dir, samples)

    write_csv(out_dir / "model_scope.csv", scope_rows, ["Input Field", "Type", "Model Status", "Feature Count", "Features", "Feature Grades", "Reason"])
    write_csv(out_dir / "player_name_matches.csv", match_rows, ["run_id", "player_index", "live_player_label", "matched", "master_player", "master_player_id", "master_team", "has_combine"])
    write_csv(out_dir / "holdout_predictions.csv", holdout, ["holdout_run", "player_index", "player_label", "master_player", "master_player_id", "Input Field", "Type", "actual_value", "predicted_value", "raw_predicted_value", "abs_error", "signed_error", "feature_values"])
    write_csv(out_dir / "field_metrics.csv", metrics_rows, ["Input Field", "Type", "tested_rows", "mae", "rmse", "median_abs_error", "bias_signed_error", "within_5_pct", "within_10_pct", "actual_min", "actual_max", "predicted_min", "predicted_max", "pearson_actual_predicted"])

    match_summary = {
        "live_player_rows": len(match_rows),
        "matched_players": sum(str(r["matched"]) == "True" for r in match_rows),
        "unmatched_players": sum(str(r["matched"]) != "True" for r in match_rows),
        "matched_with_combine": sum(str(r["has_combine"]) == "True" for r in match_rows),
    }
    manifest = {
        "output_dir": str(out_dir),
        "season": args.season,
        "source_master_sqlite": str((root / MASTER_SQLITE).resolve()),
        "source_nba_sqlite": str((root / NBA_SQLITE).resolve()),
        "source_runs": [str((root / RUNS_DIR / r).resolve()) for r in RUNS],
        "name_key_logic": "copied from nba2k_editor/Player Generator/game_port.py::_person_name_keys",
        "master_summary": master_summary,
        "scope_summary": scope_summary,
        "match_summary": match_summary,
        "training_sample_rows": len(samples),
        "model_knot_rows": knot_count,
        "holdout_summary": holdout_summary,
        "algorithm": "SQL feature semantic map -> per-field/per-feature piecewise median calibration -> median-combine features -> leave-one-run-out testing",
        "no_runtime_wiring": True,
        "created_files": ["README.md", "model_scope.csv", "player_name_matches.csv", "model_knots.csv", "holdout_predictions.csv", "field_metrics.csv", "manifest.json"],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    write_readme(out_dir, manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
