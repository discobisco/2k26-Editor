from __future__ import annotations

import bisect
import re
import sqlite3
from functools import lru_cache
from math import isfinite, sqrt
from pathlib import Path
from statistics import NormalDist
from typing import Any

from player_era_context import player_era_context
from player_special_rules import researched_defense_quality_rule_for


_MASTER_DATABASE = Path(__file__).resolve().parent / "NBA Player Data" / "NBA_DATA_Master.sqlite"
_POOL_CALIBRATION_PROVENANCE = (
    "pool_packages=765_gp_valid_same_package_records;"
    "identity=(run_id,player_index);"
    "runs=editor_capture_001:415,editor_capture_002:350;"
    "pool_sha256=0acfd7ab0560e563737f743c9c1a6b1ccbd59c5e4415d2f32d9360aaea7dfac9;"
    "fit=field_specific_ols_on_perimeter_role_height_weight_with_same_package_residual_scale"
)

# Each target was fitted independently from complete GP-valid Pool packages.  The
# tuple is (intercept, perimeter-role coefficient, height coefficient, weight
# coefficient, residual standard deviation).  Height and weight are centered at
# the exact Pool means below.  Lateral, P&R IQ, and Contest are same-package
# semantic composites because those exact Attribute labels were not captured.
# These are continuous calibrations, not position bands or output gates.
_POOL_HEIGHT_CENTER = 76.04575163398692
_POOL_WEIGHT_CENTER = 198.03248209150323
_CALIBRATION: dict[str, tuple[float, float, float, float, float]] = {
    "block": (47.68951017, -2.29562254, 3.59626670, 0.03566835, 11.43932622),
    "defense_consistency": (41.16191571, 19.76683879, 2.43524234, 0.08418385, 11.88273199),
    "help_defense": (45.76107867, 19.93090055, 3.43569807, 0.09721121, 12.67381189),
    "interior_defense": (45.79868317, -2.76647874, 2.44150743, 0.11382704, 9.84815556),
    "pass_perception": (38.06904112, 40.89132879, 4.29566679, 0.02255723, 13.91619499),
    "perimeter_defense": (33.71088330, 45.86338649, 2.88853735, 0.07088420, 12.26868584),
    "steal": (34.87841283, 35.81475681, 2.48364059, 0.02255980, 11.00726531),
    "lateral_quickness": (31.89939328, 45.33874148, 3.25832799, 0.07509925, 12.12455866),
    "pick_and_roll_iq": (43.46149719, 19.84886967, 2.93547020, 0.09069753, 11.50524791),
    "contest_shot_attribute": (50.44894563, 3.52469525, 2.45040692, 0.09768933, 7.98725768),
    "t_foul": (63.32078326, -16.64156651, -0.33218055, -0.01287985, 14.83),  # ATD Foul 45-65, cap 95
    # Deliberately NOT on ATD numbers. derive_tendency_hardfoul pins this field to
    # 100 pre-1960 and for all but the bottom-quintile contact score in 1970-1989,
    # because 2K does not otherwise represent the physicality of those eras. The ATD
    # band (5-20, cap 45) describes a literal hard-contact rate; this field is used
    # as an engine propensity. Only the 1970s/80s low-contact exception reads it.
    "t_hard_foul": (62.64078510, -22.26446853, -2.67721871, -0.04814260, 15.95836388),
    "t_take_charge": (6.05666361, 7.88667278, 1.48002538, 0.05358680, 7.41),  # ATD Take Charge 5-15, cap 35
}

_POSITION_ROLE = {"PG": 1.0, "SG": 0.8, "SF": 0.5, "PF": 0.2, "C": 0.0}
_MISSING_STAT_POSITION_MULTIPLIERS = {
    "steal": {"PG": 1.30, "SG": 1.30, "SF": 0.90, "PF": 0.90, "C": 0.70},
    "block": {"PG": 0.70, "SG": 0.70, "SF": 0.90, "PF": 0.90, "C": 1.10},
}
_ROW_POPULATION_CACHE: dict[
    tuple[int, str],
    tuple[tuple[dict[str, Any], ...], tuple[float, ...]],
] = {}
_ELIGIBLE_ROWS_CACHE: dict[
    tuple[int, int],
    tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]],
] = {}
_DEFENSE_QUALITY_WEIGHTS = {
    "dws": 0.80,
    "team_win_pct": 0.10,
    "team_opp_ppg": 0.10,
}
_NBL_BAA_DEFENSE_REFERENCE_KEYS = {
    "perimeter_defense": "nbl_baa_perimeter_defense_reference_values",
    "defense_consistency": "nbl_baa_defense_consistency_reference_values",
}
_NBL_DISTRIBUTION_POPULATION_CACHE: dict[
    tuple[int, str],
    tuple[tuple[dict[str, Any], ...], tuple[tuple[float, float], ...]],
] = {}
# Direct-source weights are field-specific.  Blocks never supply more than ten
# percent of a broad-defense score, and steals do not author broad defense.
_DIRECT_SOURCES: dict[str, tuple[tuple[str, float], ...]] = {
    "block": (
        ("per_100.blk_per_100_poss", 0.36),
        ("advanced.blk_percent", 0.28),
        ("per_game.blk_per_game", 0.16),
        ("advanced.dws", 0.20),
    ),
    "defense_consistency": (("advanced.dws", 1.0),),
    "help_defense": (
        ("advanced.dbpm", 0.47),
        ("advanced.dws", 0.45),
        ("advanced.blk_percent", 0.08),
    ),
    "interior_defense": (("advanced.dws", 1.0),),
    "pass_perception": (
        ("crafted.disruption_per_100", 0.35),
        ("advanced.stl_percent", 0.30),
        ("per_100.stl_per_100_poss", 0.20),
        ("crafted.stock_percent", 0.15),
    ),
    "perimeter_defense": (("advanced.dws", 1.0),),
    "steal": (
        ("advanced.stl_percent", 0.36),
        ("per_100.stl_per_100_poss", 0.28),
        ("per_game.stl_per_game", 0.16),
        ("advanced.dws", 0.20),
    ),
    "lateral_quickness": (),
    "pick_and_roll_iq": (),
    "contest_shot_attribute": (
        ("advanced.dbpm", 0.45),
        ("advanced.dws", 0.45),
        ("advanced.blk_percent", 0.10),
    ),
    "t_foul": (
        ("per_36.pf_per_36_min", 0.55),
        ("per_game.pf_per_game", 0.25),
        ("derived.shooting_foul_committed_per_game", 0.20),
    ),
    "t_hard_foul": (
        ("derived.shooting_foul_committed_per_game", 0.55),
        ("per_36.pf_per_36_min", 0.30),
        ("per_game.pf_per_game", 0.15),
    ),
    "t_take_charge": (("derived.offensive_foul_drawn_per_game", 1.0),),
}

_SUBSTITUTES: dict[str, tuple[str, str, str]] = {
    "block": (
        "BLK, BLK%, and BLK per 100",
        "DWS plus continuous listed defensive role, exact height, and weight",
        "DWS supplies sustained defensive value while the field-specific context remains a role prior, not a fabricated block count",
    ),
    "defense_consistency": (
        "game-level defensive consistency measurement",
        "season-long DWS plus continuous role/size context calibrated to the captured Defensive Consistency field",
        "DWS is the primary sustained defensive-value signal while role and size retain field-specific context",
    ),
    "help_defense": (
        "DWS, DBPM, and BLK%",
        "continuous role/size help responsibility under the season's defensive rules",
        "frontcourt basket protection and backcourt safety duties support help responsibility without inventing rotations",
    ),
    "interior_defense": (
        "DWS and DBPM",
        "continuous primary/secondary matchup role and size",
        "historical centers defended the largest interior opponent while hybrid labels preserve a continuum",
    ),
    "pass_perception": (
        "STL, disruption, and stock evidence",
        "continuous backcourt-pressure/transition-safety role and size",
        "the substitute is a passing-lane responsibility prior and does not manufacture steals or deflections",
    ),
    "perimeter_defense": (
        "DWS and DBPM",
        "continuous primary/secondary matchup role and size",
        "historical guards picked up opposing backcourts while hybrid labels preserve a continuum",
    ),
    "steal": (
        "STL, STL%, and STL per 100",
        "DWS plus continuous ball-pressure role and size",
        "DWS supplies sustained defensive value while the substitute calibrates Steal without inventing an unavailable historical steal total",
    ),
    "lateral_quickness": (
        "defensive lateral-movement tracking; DWS and DBPM do not measure movement",
        "continuous perimeter-matchup role and size calibrated to same-package Perimeter Defense plus Agility",
        "lateral movement is kept separate from steals, blocks, and generic athletic constants",
    ),
    "pick_and_roll_iq": (
        "pick-and-roll coverage events; DWS and DBPM do not identify screen-action decisions",
        "continuous team-defense role and size calibrated to same-package Help IQ plus Defensive Consistency",
        "no modern tracking is projected into seasons where it was not recorded",
    ),
    "contest_shot_attribute": (
        "DWS, DBPM, and at most ten-percent BLK evidence",
        "continuous matchup/basket-protection role and size",
        "contest execution remains distinct from contest frequency and raw block production",
    ),
    "t_foul": (
        "PF rate and shooting fouls committed",
        "continuous contact-role context calibrated to the exact Foul tendency",
        "personal fouls are used only for foul behavior, never as generic defense",
    ),
    "t_hard_foul": (
        "shooting-foul and PF frequency; hard-foul classification is unavailable",
        "continuous contact-role and size context calibrated to the exact Hard Foul tendency",
        "contact opportunity is not asserted to be observed hard-foul severity",
    ),
    "t_take_charge": (
        "offensive fouls drawn",
        "continuous help-position role and size calibrated to the exact Take Charge tendency",
        "PF, DWS, STL, and BLK are not relabeled as charges when charge evidence is absent",
    ),
}


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if not text or text.upper() in {"NA", "N/A", "NONE", "NULL"}:
            return None
        number = float(text)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _source(evidence: Any, namespace: str) -> dict[str, Any]:
    source = getattr(evidence, namespace, {})
    return source if isinstance(source, dict) else {}


def _read(evidence: Any, path: str) -> float | None:
    namespace, _, key = path.partition(".")
    return _optional_number(_source(evidence, namespace).get(key))


def _row_value(row: dict[str, Any], path: str) -> float | None:
    namespace, _, key = path.partition(".")
    prefixes = {
        "season_info": "player_season_info",
        "per_game": "player_per_game",
        "totals": "player_totals",
        "per_36": "player_per_36_min",
        "per_100": "player_per_100_poss",
        "advanced": "advanced",
        "play_by_play": "player_play_by_play",
        "identity": "player_info",
        "team_summary": "team_summaries",
        "team_stats_per_game": "team_stats_per_game",
        "opponent_stats_per_game": "opponent_stats_per_game",
    }
    for candidate in (path, key, f"{prefixes.get(namespace, namespace)}.{key}", f"player_{namespace}.{key}"):
        if candidate in row:
            return _optional_number(row.get(candidate))
    return None


def _season(evidence: Any) -> int:
    value = _optional_number(getattr(evidence, "season", None))
    if value is None:
        value = _read(evidence, "season_info.season")
    return int(value or 0)


def _league(evidence: Any) -> str:
    return str(_source(evidence, "season_info").get("lg") or _source(evidence, "source_context").get("lg") or "").strip().upper()


def _games_played(evidence: Any) -> tuple[float, str] | None:
    for path in ("per_game.g", "season_info.g", "totals.g"):
        value = _read(evidence, path)
        if value is not None and value > 0.0:
            return value, path
    return None


def _row_games(row: dict[str, Any]) -> float | None:
    for path in ("per_game.g", "season_info.g", "totals.g"):
        value = _row_value(row, path)
        if value is not None:
            return value
    return None


def _row_season(row: dict[str, Any]) -> int | None:
    for key in ("season", "player_season_info.season", "season_info.season"):
        value = _optional_number(row.get(key))
        if value is not None:
            return int(value)
    return None


def _row_league(row: dict[str, Any]) -> str:
    for key in ("player_season_info.lg", "season_info.lg", "lg"):
        if key in row:
            return str(row.get(key) or "").strip().upper()
    return ""


def _eligible_rows(evidence: Any, rows: Any) -> tuple[dict[str, Any], ...]:
    season = _season(evidence)
    row_tuple = tuple(rows or ())
    cache_key = (id(row_tuple), season)
    cached = _ELIGIBLE_ROWS_CACHE.get(cache_key)
    if cached is not None and cached[0] is row_tuple:
        return cached[1]
    eligible: list[dict[str, Any]] = []
    for row in row_tuple:
        if not isinstance(row, dict):
            continue
        row_season = _row_season(row)
        if season and row_season != season:
            continue
        games = _row_games(row)
        if games is None or games <= 0.0:
            continue
        eligible.append(row)
    result = tuple(eligible)
    _ELIGIBLE_ROWS_CACHE[cache_key] = (row_tuple, result)
    return result


def _position_mix_from_text(text: object) -> tuple[tuple[str, float], ...] | None:
    text = str(text or "").upper().strip()
    compact = re.sub(r"[^A-Z]+", "", text)
    historical = {
        "G": ("PG", "SG"),
        "GF": ("SG", "SF"),
        "FG": ("SF", "SG"),
        "F": ("SF", "PF"),
        "FC": ("PF", "C"),
        "CF": ("C", "PF"),
        "C": ("C",),
    }.get(compact)
    positions = historical or tuple(dict.fromkeys(re.findall(r"(?:PG|SG|SF|PF|C)", text)))
    if not positions:
        return None
    weight = 1.0 / len(positions)
    return tuple((position, weight) for position in positions)


def _listed_position_mix(evidence: Any) -> tuple[tuple[tuple[str, float], ...], str] | None:
    season_position = _source(evidence, "season_info").get("pos")
    identity_position = _source(evidence, "identity").get("pos")
    mix = _position_mix_from_text(season_position or identity_position)
    if mix is None:
        return None
    source = "season_info.pos" if season_position else "identity.pos"
    return mix, source


def _offensive_position_mix(evidence: Any) -> tuple[tuple[str, float], ...]:
    values: list[tuple[str, float]] = []
    play_by_play = _source(evidence, "play_by_play")
    for position, key in (("PG", "pg_percent"), ("SG", "sg_percent"), ("SF", "sf_percent"), ("PF", "pf_percent"), ("C", "c_percent")):
        value = _optional_number(play_by_play.get(key))
        if value is not None and value > 0.0:
            values.append((position, value))
    total = sum(value for _, value in values)
    return tuple((position, value / total) for position, value in values) if total > 0.0 else ()


def _player_key(evidence: Any) -> tuple[int, str, str]:
    player_id = str(getattr(evidence, "player_id", "") or _source(evidence, "identity").get("player_id") or "").strip().upper()
    team = str(getattr(evidence, "team", "") or _source(evidence, "season_info").get("team") or "").strip().upper()
    return _season(evidence), player_id, team


@lru_cache(maxsize=None)
def _crafted_rows(season: int, league: str) -> dict[tuple[str, str], dict[str, Any]]:
    if season <= 0 or not league or not _MASTER_DATABASE.is_file():
        return {}
    uri = f"file:{_MASTER_DATABASE.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """
            SELECT c.*
            FROM crafted_player_metrics AS c
            JOIN player_per_game AS p
              ON p.season = c.season
             AND p.player_id = c.player_id
             AND p.team = c.team
            WHERE c.season = ? AND upper(p.lg) = ? AND p.g > 0
              AND upper(c.team) NOT IN ('TOT','2TM','3TM','4TM','5TM')
            """,
            (season, league),
        )
        return {
            (str(row["player_id"]).strip().upper(), str(row["team"]).strip().upper()): dict(row)
            for row in rows
        }


@lru_cache(maxsize=1)
def _defensive_matchup_rows_2018() -> dict[tuple[str, str], dict[str, Any]]:
    if not _MASTER_DATABASE.is_file():
        return {}
    uri = f"file:{_MASTER_DATABASE.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return {
            (str(row["player_id"]).strip().upper(), str(row["team"]).strip().upper()): dict(row)
            for row in connection.execute("SELECT * FROM crafted_defensive_versatility_2018 WHERE season = 2018")
        }


def _interpolate_role(position_number: float) -> float:
    points = ((1.0, 1.0), (2.0, 0.8), (3.0, 0.5), (4.0, 0.2), (5.0, 0.0))
    if position_number <= 1.0:
        return 1.0
    if position_number >= 5.0:
        return 0.0
    lower = int(position_number)
    fraction = position_number - lower
    return points[lower - 1][1] + fraction * (points[lower][1] - points[lower - 1][1])


def _perimeter_role(evidence: Any) -> tuple[float, tuple[str, ...]] | None:
    season, player_id, team = _player_key(evidence)
    if season == 2018 and player_id and team:
        matchup = _defensive_matchup_rows_2018().get((player_id, team))
        defended_position = _optional_number((matchup or {}).get("avg_defended_pos_est"))
        if defended_position is not None:
            return _interpolate_role(defended_position), (
                "crafted_defensive_versatility_2018.avg_defended_pos_est",
                "tracking_scope=2018_exact_player_team_only",
                "tracking_semantics=defensive_role_breadth_not_effectiveness",
            )
    offensive_mix = _offensive_position_mix(evidence)
    listed_mix = _listed_position_mix(evidence)
    mix = offensive_mix or (() if listed_mix is None else listed_mix[0])
    if not mix:
        return None
    role = sum(weight * _POSITION_ROLE[position] for position, weight in mix)
    if offensive_mix:
        source = "play_by_play.position_percentages"
    else:
        if listed_mix is None:
            return None
        source = listed_mix[1]
    return role, (
        source,
        "position_mix=" + ",".join(f"{position}:{weight:.6f}" for position, weight in mix),
    )


def _crafted_value(evidence: Any, key: str) -> float | None:
    season, player_id, team = _player_key(evidence)
    if not player_id or not team:
        return None
    return _optional_number(_crafted_rows(season, _league(evidence)).get((player_id, team), {}).get(key))


def _feature_value(evidence: Any, feature: str) -> float | None:
    if feature.startswith("crafted."):
        return _crafted_value(evidence, feature.split(".", 1)[1])
    if feature == "derived.shooting_foul_committed_per_game":
        count = _read(evidence, "play_by_play.shooting_foul_committed")
        if count is None:
            count = _crafted_value(evidence, "shooting_foul_committed")
        games = _games_played(evidence)
        return count / games[0] if count is not None and games is not None else None
    if feature == "derived.offensive_foul_drawn_per_game":
        count = _read(evidence, "play_by_play.offensive_foul_drawn")
        if count is None:
            count = _crafted_value(evidence, "offensive_foul_drawn")
        games = _games_played(evidence)
        return count / games[0] if count is not None and games is not None else None
    return _read(evidence, feature)


def _row_feature(row: dict[str, Any], feature: str) -> float | None:
    if feature.startswith("crafted."):
        return None
    if feature == "derived.shooting_foul_committed_per_game":
        count = _row_value(row, "play_by_play.shooting_foul_committed")
        games = _row_games(row)
        return count / games if count is not None and games is not None and games > 0.0 else None
    if feature == "derived.offensive_foul_drawn_per_game":
        count = _row_value(row, "play_by_play.offensive_foul_drawn")
        games = _row_games(row)
        return count / games if count is not None and games is not None and games > 0.0 else None
    return _row_value(row, feature)


def _feature_population(evidence: Any, rows: tuple[dict[str, Any], ...], feature: str) -> tuple[float, ...]:
    if feature.startswith("crafted."):
        metric = feature.split(".", 1)[1]
        leagues = tuple(sorted({_row_league(row) for row in rows if _row_league(row)}))
        return _crafted_population(_season(evidence), leagues, metric)
    cache_key = (id(rows), feature)
    cached = _ROW_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    population = tuple(sorted(value for row in rows if (value := _row_feature(row, feature)) is not None))
    _ROW_POPULATION_CACHE[cache_key] = (rows, population)
    return population


@lru_cache(maxsize=None)
def _crafted_population(season: int, leagues: tuple[str, ...], metric: str) -> tuple[float, ...]:
    values = (
        _optional_number(row.get(metric))
        for league in leagues
        for row in _crafted_rows(season, league).values()
    )
    return tuple(sorted(value for value in values if value is not None))


def _population_rank(value: float, population: tuple[float, ...]) -> float | None:
    if not population:
        return None
    left = bisect.bisect_left(population, value)
    right = bisect.bisect_right(population, value)
    return (left + right + 1.0) / (2.0 * (len(population) + 1.0))


def _smoothstep01(value: float) -> float:
    bounded = max(0.0, min(1.0, value))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def _direct_score(
    evidence: Any,
    rows: tuple[dict[str, Any], ...],
    field: str,
) -> tuple[float, tuple[str, ...], float, float] | None:
    total = 0.0
    weight_total = 0.0
    used: list[str] = []
    for feature, weight in _DIRECT_SOURCES[field]:
        value = _feature_value(evidence, feature)
        if value is None:
            continue
        rank = _population_rank(value, _feature_population(evidence, rows, feature))
        if rank is None:
            continue
        total += rank * weight
        weight_total += weight
        used.append(feature)
    if not used or weight_total <= 0.0:
        return None
    raw_score = total / weight_total
    games = _games_played(evidence)
    if games is None:
        return None
    maximum_games = max(games[0], max((_row_games(row) or 0.0 for row in rows), default=0.0))
    exposure_reliability = sqrt(games[0] / maximum_games)
    adjusted_score = 0.5 + (raw_score - 0.5) * exposure_reliability
    return adjusted_score, tuple(used), raw_score, exposure_reliability


def _context_value(field: str, evidence: Any) -> tuple[float, tuple[str, ...]] | None:
    role_result = _perimeter_role(evidence)
    if role_result is None:
        return None
    role, role_keys = role_result
    intercept, role_coefficient, height_coefficient, weight_coefficient, _ = _CALIBRATION[field]
    height = _read(evidence, "identity.ht_in_in")
    weight = _read(evidence, "identity.wt")
    value = intercept + role * role_coefficient
    keys = list(role_keys)
    if height is not None:
        value += (height - _POOL_HEIGHT_CENTER) * height_coefficient
        keys.append("identity.ht_in_in")
    if weight is not None:
        value += (weight - _POOL_WEIGHT_CENTER) * weight_coefficient
        keys.append("identity.wt")
    keys.extend((
        f"perimeter_role={role:.8f}",
        f"context_prediction={value:.8f}",
        f"calibration={_POOL_CALIBRATION_PROVENANCE}",
    ))
    return value, tuple(keys)


def _row_text(row: dict[str, Any], path: str) -> str:
    namespace, _, key = path.partition(".")
    prefixes = {"season_info": "player_season_info", "identity": "player_info"}
    for candidate in (path, key, f"{prefixes.get(namespace, namespace)}.{key}", f"player_{namespace}.{key}"):
        text = str(row.get(candidate) or "").strip()
        if text:
            return text
    return ""


def _row_perimeter_role(row: dict[str, Any]) -> float | None:
    weighted: list[tuple[str, float]] = []
    for position, key in (("PG", "pg_percent"), ("SG", "sg_percent"), ("SF", "sf_percent"), ("PF", "pf_percent"), ("C", "c_percent")):
        value = _row_value(row, f"play_by_play.{key}")
        if value is not None and value > 0.0:
            weighted.append((position, value))
    total = sum(value for _position, value in weighted)
    if total > 0.0:
        return sum(_POSITION_ROLE[position] * value for position, value in weighted) / total

    text = _row_text(row, "season_info.pos") or _row_text(row, "identity.pos")
    compact = re.sub(r"[^A-Z]+", "", text.upper())
    historical = {
        "G": ("PG", "SG"),
        "GF": ("SG", "SF"),
        "FG": ("SF", "SG"),
        "F": ("SF", "PF"),
        "FC": ("PF", "C"),
        "CF": ("C", "PF"),
        "C": ("C",),
    }.get(compact)
    positions = historical or tuple(dict.fromkeys(re.findall(r"(?:PG|SG|SF|PF|C)", text.upper())))
    if not positions:
        return None
    return sum(_POSITION_ROLE[position] for position in positions) / len(positions)


def _row_context_value(field: str, row: dict[str, Any]) -> float | None:
    role = _row_perimeter_role(row)
    if role is None:
        return None
    intercept, role_coefficient, height_coefficient, weight_coefficient, _ = _CALIBRATION[field]
    value = intercept + role * role_coefficient
    height = _row_value(row, "identity.ht_in_in")
    weight = _row_value(row, "identity.wt")
    if height is not None:
        value += (height - _POOL_HEIGHT_CENTER) * height_coefficient
    if weight is not None:
        value += (weight - _POOL_WEIGHT_CENTER) * weight_coefficient
    return value


def _direct_effect_responsibility(field: str, evidence: Any) -> float:
    role_result = _perimeter_role(evidence)
    if role_result is None:
        return 1.0
    perimeter_role = role_result[0]
    if field == "interior_defense":
        return 1.0 - perimeter_role
    if field == "perimeter_defense":
        return perimeter_role
    return 1.0


def _missing_stat_position_multiplier(field: str, evidence: Any) -> tuple[float, str] | None:
    multipliers = _MISSING_STAT_POSITION_MULTIPLIERS.get(field)
    listed = _listed_position_mix(evidence)
    if multipliers is None or listed is None:
        return None
    mix, source = listed
    return sum(weight * multipliers[position] for position, weight in mix), source


def _legal_value(field: str, value: float) -> int:
    if field.startswith("t_"):
        return max(0, min(100, round(value)))
    return max(25, min(99, round(value)))


def _derive(rule_name: str, field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    games = _games_played(evidence)
    if games is None:
        return None
    rows = _eligible_rows(evidence, league_player_rows)
    if field == "defense_consistency":
        if _league(evidence) == "NBL":
            quality = _defense_quality_score(evidence, rows)
            if quality is None:
                return None
            score, quality_keys = quality
            mapped = _nbl_baa_distribution_value(
                field,
                evidence,
                rows,
                quality_score=score,
            )
            if mapped is None:
                return None
            value, mapping_keys = mapped
            return {
                "value": value,
                "score": score,
                "source_rule": f"{rule_name}_nbl_baa_distribution_match",
                "evidence_keys": (games[1],) + quality_keys + mapping_keys + (
                    "rank_source=NBL_team_defense_quality;games_share_tiebreak_only",
                    "target_distribution=same_season_BAA_DWS_only_defense_consistency",
                ),
            }
        dws = _read(evidence, "advanced.dws")
        dws_population = tuple(
            sorted(
                value
                for row in rows
                if (value := _row_value(row, "advanced.dws")) is not None
            )
        )
        if dws is None or not dws_population:
            return None
        score = bisect.bisect_right(dws_population, dws) / len(dws_population)
        return {
            "value": max(25, min(99, round(25.0 + 74.0 * score))),
            "score": score,
            "source_rule": rule_name,
            "evidence_keys": (games[1], "advanced.dws", f"dws={dws:.8f}") + (
                f"same_season_same_league_rank_score={score:.8f}",
                "rank_source=dws_only",
                "mapping=round(25+74*same_season_same_league_rank_score)",
                "population=exact_same_season_same_league_gp_positive_unflattened_rows",
            ),
        }
    context = _context_value(field, evidence)
    if context is None:
        return None
    context_value, context_keys = context
    era = player_era_context(evidence)
    scored = _direct_score(evidence, rows, field)
    unavailable, substitute, validity = _SUBSTITUTES[field]
    common_keys = (games[1],) + context_keys + (
        f"era_context={era.era_key}",
        f"league={era.league}",
        "population=exact_same_season_same_league_gp_positive_unflattened_rows",
        "pool_identity=(run_id,player_index)",
        f"field_validity={validity}",
    )
    if scored is None:
        substitute_value = context_value
        position_skew_keys: tuple[str, ...] = ()
        position_skew = _missing_stat_position_multiplier(field, evidence)
        if position_skew is not None:
            multiplier, position_source = position_skew
            substitute_value *= multiplier
            position_skew_keys = (
                position_source,
                f"missing_stat_position_multiplier={multiplier:.8f}",
                "missing_stat_position_multiplier_contract="
                + (
                    "steal[G:1.30,F:0.90,C:0.70]"
                    if field == "steal"
                    else "block[G:0.70,F:0.90,C:1.10]"
                ),
            )
        return {
            "value": _legal_value(field, substitute_value),
            "source_rule": f"{rule_name}_field_specific_context_substitute",
            "evidence_keys": common_keys + position_skew_keys + (
                f"unavailable_direct_source={unavailable}",
                f"substitute_evidence={substitute}",
                "missing_source_policy=missing_is_not_zero",
            ),
        }
    score, source_keys, raw_score, exposure_reliability = scored
    residual_scale = _CALIBRATION[field][4]
    responsibility = _direct_effect_responsibility(field, evidence)
    value = context_value + NormalDist().inv_cdf(score) * residual_scale * responsibility
    return {
        "value": _legal_value(field, value),
        "score": score,
        "source_rule": rule_name,
        "evidence_keys": (games[1],) + source_keys + context_keys + (
            "direct_source=" + ",".join(source_keys),
            f"raw_same_season_population_score={raw_score:.8f}",
            f"same_season_population_score={score:.8f}",
            f"gp_exposure_reliability={exposure_reliability:.8f}",
            f"direct_effect_responsibility={responsibility:.8f}",
            f"era_context={era.era_key}",
            f"league={era.league}",
            "population=exact_same_season_same_league_gp_positive_unflattened_rows",
            "pool_identity=(run_id,player_index)",
            f"field_validity={validity}",
        ),
    }


def _team_win_pct(source: Any) -> float | None:
    wins = _row_value(source, "team_summary.w") if isinstance(source, dict) else _read(source, "team_summary.w")
    losses = _row_value(source, "team_summary.l") if isinstance(source, dict) else _read(source, "team_summary.l")
    if wins is None or losses is None or wins < 0.0 or losses < 0.0 or wins + losses <= 0.0:
        return None
    return wins / (wins + losses)


def _team_opponent_points_per_game(source: Any) -> float | None:
    opponent_points = _row_value(source, "opponent_stats_per_game.opp_pts_per_game") if isinstance(source, dict) else _read(source, "opponent_stats_per_game.opp_pts_per_game")
    if opponent_points is None or opponent_points < 0.0:
        return None
    return opponent_points


def _defense_quality_component_values(evidence: Any) -> dict[str, float | None]:
    return {
        "dws": _read(evidence, "advanced.dws"),
        "team_win_pct": _team_win_pct(evidence),
        "team_opp_ppg": _team_opponent_points_per_game(evidence),
    }


def _row_team_key(row: dict[str, Any], ordinal: int) -> str:
    for key in ("team", "player_season_info.team", "season_info.team"):
        text = str(row.get(key) or "").strip().upper()
        if text:
            return text
    return f"__ROW_{ordinal}"


def _defense_quality_component_populations(rows: tuple[dict[str, Any], ...]) -> dict[str, tuple[float, ...]]:
    dws = sorted(
        value
        for row in rows
        if (value := _row_value(row, "advanced.dws")) is not None
    )
    team_values: dict[str, dict[str, float]] = {
        "team_win_pct": {},
        "team_opp_ppg": {},
    }
    for ordinal, row in enumerate(rows):
        team_key = _row_team_key(row, ordinal)
        win_pct = _team_win_pct(row)
        opponent_points = _team_opponent_points_per_game(row)
        if win_pct is not None:
            team_values["team_win_pct"].setdefault(team_key, win_pct)
        if opponent_points is not None:
            team_values["team_opp_ppg"].setdefault(team_key, opponent_points)
    return {
        "dws": tuple(dws),
        "team_win_pct": tuple(sorted(team_values["team_win_pct"].values())),
        "team_opp_ppg": tuple(sorted(team_values["team_opp_ppg"].values())),
    }


def _defense_quality_component_provenance(name: str, value: float, score: float) -> tuple[str, ...]:
    if name == "dws":
        paths = ("advanced.dws",)
    elif name == "team_win_pct":
        paths = ("team_summary.w", "team_summary.l")
    else:
        paths = ("opponent_stats_per_game.opp_pts_per_game",)
    return (*paths, f"{name}={value:.8f}", f"{name}_same_league_percentile={score:.8f}")


def _defense_quality_score(
    evidence: Any,
    eligible_rows: tuple[dict[str, Any], ...],
) -> tuple[float, tuple[str, ...]] | None:
    component_values = _defense_quality_component_values(evidence)
    component_populations = _defense_quality_component_populations(eligible_rows)
    components: list[tuple[str, float, float]] = []
    quality_keys: list[str] = []
    for name, weight in _DEFENSE_QUALITY_WEIGHTS.items():
        value = component_values.get(name)
        population = component_populations.get(name, ())
        if value is None or not population:
            continue
        if name == "team_opp_ppg":
            component_score = (len(population) - bisect.bisect_left(population, value)) / len(population)
        else:
            component_score = bisect.bisect_right(population, value) / len(population)
        components.append((name, weight, component_score))
        quality_keys.extend(_defense_quality_component_provenance(name, value, component_score))
    total_weight = sum(weight for _name, weight, _component_score in components)
    if total_weight <= 0.0:
        return None
    score = sum(weight * component_score for _name, weight, component_score in components) / total_weight
    return score, (
        *quality_keys,
        "defense_quality_weights=dws:0.80,team_win_pct:0.10,team_opp_ppg:0.10",
        "team_opp_ppg_direction=lower_is_better",
        f"available_weight={total_weight:.8f}",
        "missing_components=omitted_and_available_weights_renormalized",
        "team_population=unique_exact_team_within_same_season_same_league",
    )


def _row_defense_quality_score(
    row: dict[str, Any],
    component_populations: dict[str, tuple[float, ...]],
) -> float | None:
    values = {
        "dws": _row_value(row, "advanced.dws"),
        "team_win_pct": _team_win_pct(row),
        "team_opp_ppg": _team_opponent_points_per_game(row),
    }
    components: list[tuple[float, float]] = []
    for name, weight in _DEFENSE_QUALITY_WEIGHTS.items():
        value = values.get(name)
        population = component_populations.get(name, ())
        if value is None or not population:
            continue
        if name == "team_opp_ppg":
            component_score = (len(population) - bisect.bisect_left(population, value)) / len(population)
        else:
            component_score = bisect.bisect_right(population, value) / len(population)
        components.append((weight, component_score))
    total_weight = sum(weight for weight, _score in components)
    if total_weight <= 0.0:
        return None
    return sum(weight * component_score for weight, component_score in components) / total_weight


def _position_side_multiplier(mix: tuple[tuple[str, float], ...], field: str) -> float:
    perimeter_role = sum(weight * _POSITION_ROLE[name] for name, weight in mix)
    if perimeter_role < 0.5:
        interior_multiplier = 1.0
        perimeter_multiplier = 0.15 + 0.5 * perimeter_role
    elif perimeter_role > 0.5:
        interior_multiplier = 0.15 + 0.5 * (1.0 - perimeter_role)
        perimeter_multiplier = 1.0
    else:
        interior_multiplier = perimeter_multiplier = 0.5
    return interior_multiplier if field == "interior_defense" else perimeter_multiplier


def _row_position_mix(row: dict[str, Any]) -> tuple[tuple[str, float], ...] | None:
    for key in ("player_season_info.pos", "season_info.pos", "pos", "player_info.pos", "identity.pos"):
        if key in row and row.get(key):
            return _position_mix_from_text(row.get(key))
    return None


def _games_share(source: Any) -> float | None:
    if isinstance(source, dict):
        games = _row_value(source, "per_game.g")
        team_games = _row_value(source, "team_stats_per_game.g")
    else:
        games = _read(source, "per_game.g")
        team_games = _read(source, "team_stats_per_game.g")
    if games is None or team_games is None or games < 0.0 or team_games <= 0.0:
        return None
    return games / team_games


def _row_has_researched_defense_override(row: dict[str, Any]) -> bool:
    player_id = str(row.get("player_id") or row.get("player_season_info.player_id") or "").strip().upper()
    team = str(row.get("team") or row.get("player_season_info.team") or "").strip().upper()
    season = _row_season(row) or 0
    return researched_defense_quality_rule_for(
        season=season,
        league=_row_league(row),
        player_id=player_id,
        team=team,
    ) is not None


def _nbl_distribution_population(
    field: str,
    eligible_rows: tuple[dict[str, Any], ...],
) -> tuple[tuple[float, float], ...]:
    cache_key = (id(eligible_rows), field)
    cached = _NBL_DISTRIBUTION_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is eligible_rows:
        return cached[1]
    component_populations = _defense_quality_component_populations(eligible_rows)
    signals: list[tuple[float, float]] = []
    for row in eligible_rows:
        if field == "perimeter_defense" and _row_has_researched_defense_override(row):
            continue
        quality_score = _row_defense_quality_score(row, component_populations)
        games_share = _games_share(row)
        if quality_score is None or games_share is None:
            continue
        if field == "perimeter_defense":
            mix = _row_position_mix(row)
            if mix is None:
                continue
            quality_score *= _position_side_multiplier(mix, field)
        signals.append((quality_score, games_share))
    population = tuple(sorted(signals))
    _NBL_DISTRIBUTION_POPULATION_CACHE[cache_key] = (eligible_rows, population)
    return population


def _midrank_signal_percentile(
    signal: tuple[float, float],
    population: tuple[tuple[float, float], ...],
) -> float | None:
    if len(population) < 2:
        return None
    left = bisect.bisect_left(population, signal)
    right = bisect.bisect_right(population, signal)
    midrank = (left + right - 1) / 2.0
    return max(0.0, min(1.0, midrank / (len(population) - 1)))


def _linear_percentile(values: tuple[float, ...], percentile: float) -> float:
    position = max(0.0, min(1.0, percentile)) * (len(values) - 1)
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _nbl_baa_distribution_value(
    field: str,
    evidence: Any,
    eligible_rows: tuple[dict[str, Any], ...],
    *,
    quality_score: float,
    position_multiplier: float = 1.0,
) -> tuple[int, tuple[str, ...]] | None:
    reference_key = _NBL_BAA_DEFENSE_REFERENCE_KEYS[field]
    raw_reference = _source(evidence, "source_context").get(reference_key)
    if not isinstance(raw_reference, (list, tuple)):
        return None
    reference_values = tuple(sorted(
        number
        for value in raw_reference
        if (number := _optional_number(value)) is not None
    ))
    games_share = _games_share(evidence)
    population = _nbl_distribution_population(field, eligible_rows)
    if len(reference_values) < 2 or games_share is None or len(population) < 2:
        return None
    routed_score = quality_score * position_multiplier if field == "perimeter_defense" else quality_score
    signal = (routed_score, games_share)
    percentile = _midrank_signal_percentile(signal, population)
    if percentile is None:
        return None
    value = max(25, min(99, int(round(_linear_percentile(reference_values, percentile)))))
    return value, (
        "season_info.lg",
        "league_rule=NBL",
        f"nbl_distribution_primary_score={routed_score:.8f}",
        "per_game.g",
        "team_stats_per_game.g",
        f"nbl_distribution_games_share_tiebreak={games_share:.8f}",
        f"same_season_nbl_distribution_percentile={percentile:.8f}",
        f"reference={reference_key};same-season BAA generated output distribution",
        f"reference_count={len(reference_values)}",
        f"nbl_population_count={len(population)}",
        "mapping=round(linear_percentile(same-season_BAA_generated_values,NBL_rank));clamp=25..99",
        "rank_order=defense_quality_then_games_share_tiebreak",
    )


def _derive_dws_defense(rule_name: str, field: str, evidence: Any, rows: Any) -> dict[str, Any] | None:
    """Author defensive quality, then route it by listed position.

    Player DWS remains the primary component. Exact-team win percentage and
    lower-is-better opponent points per game supply team context and become the complete quality
    signal when player DWS is unavailable. Missing components are omitted and
    the authored weights are renormalized; missing values are never zero-filled.
    """
    eligible_rows = _eligible_rows(evidence, rows)
    player_id = str(getattr(evidence, "player_id", "") or _source(evidence, "identity").get("player_id") or "").strip().upper()
    team = str(getattr(evidence, "team", "") or _source(evidence, "season_info").get("team") or "").strip().upper()
    special_rule = researched_defense_quality_rule_for(
        season=_season(evidence),
        league=_league(evidence),
        player_id=player_id,
        team=team,
    )
    if special_rule is not None:
        score = special_rule.quality_score
        quality_rule = f"{rule_name}_researched_exact_player_override"
        quality_keys = (
            "identity.player_id",
            "season_info.lg",
            *special_rule.provenance_evidence_keys,
        )
    else:
        quality = _defense_quality_score(evidence, eligible_rows)
        if quality is None:
            return None
        score, quality_keys = quality
        quality_rule = rule_name
    position = _listed_position_mix(evidence)
    multiplier = 1.0
    position_keys: tuple[str, ...] = ()
    if position is not None:
        mix, source = position
        perimeter_role = sum(weight * _POSITION_ROLE[name] for name, weight in mix)
        multiplier = _position_side_multiplier(mix, field)
        position_keys = (
            source,
            "position_mix=" + ",".join(f"{name}:{weight:.6f}" for name, weight in mix),
            f"perimeter_role={perimeter_role:.8f}",
            f"position_side_multiplier={multiplier:.8f}",
        )
    if special_rule is None and field == "perimeter_defense" and _league(evidence) == "NBL":
        mapped = _nbl_baa_distribution_value(
            field,
            evidence,
            eligible_rows,
            quality_score=score,
            position_multiplier=multiplier,
        )
        if mapped is not None:
            value, mapping_keys = mapped
            return {
                "value": value,
                "score": score * multiplier,
                "source_rule": f"{rule_name}_nbl_baa_distribution_match",
                "evidence_keys": quality_keys + position_keys + mapping_keys,
            }
    if special_rule is None and field == "interior_defense" and _league(evidence) == "NBL":
        height = _read(evidence, "identity.ht_in_in")
        height_population = tuple(sorted(
            value
            for row in eligible_rows
            if _row_league(row) == "NBL"
            and (value := _row_value(row, "identity.ht_in_in")) is not None
            and value > 0.0
        ))
        raw_height_rank = _population_rank(height, height_population) if height is not None and height > 0.0 else None
        if raw_height_rank is None:
            return None
        height_score = _smoothstep01(raw_height_rank)
        routed_score = score * multiplier
        adjusted_score = 0.80 * routed_score + 0.20 * height_score
        return {
            "value": round(25 + adjusted_score * 74),
            "score": adjusted_score,
            "source_rule": f"{rule_name}_nbl_height_blend",
            "evidence_keys": quality_keys + position_keys + (
                "identity.ht_in_in",
                f"height_same_season_nbl_percentile={raw_height_rank:.8f}",
                f"height_same_season_nbl_s_curve_score={height_score:.8f}",
                "height_curve=smoothstep(x)=x^2*(3-2x)",
                "nbl_interior_defense_weights=current_routed_defense:0.80,height:0.20",
                "height_population=same_season_NBL_GP_positive",
            ),
        }
    return {
        "value": round(25 + score * 74 * multiplier),
        "score": score,
        "source_rule": quality_rule,
        "evidence_keys": quality_keys + position_keys,
    }


def derive_attribute_block(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_block", "block", evidence, league_player_rows)


def derive_attribute_defenseconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_defenseconsistency", "defense_consistency", evidence, league_player_rows)


def derive_attribute_helpdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_helpdefense", "help_defense", evidence, league_player_rows)


def derive_attribute_interiordefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_dws_defense("derive_attribute_interiordefense", "interior_defense", evidence, league_player_rows)


def derive_attribute_passperception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_passperception", "pass_perception", evidence, league_player_rows)


def derive_attribute_perimeterdefense(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_dws_defense("derive_attribute_perimeterdefense", "perimeter_defense", evidence, league_player_rows)


def derive_attribute_steal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_steal", "steal", evidence, league_player_rows)


def derive_attribute_lateralquickness(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_lateralquickness", "lateral_quickness", evidence, league_player_rows)


def derive_attribute_pickandrolldefenseiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_pickandrolldefenseiq", "pick_and_roll_iq", evidence, league_player_rows)


def derive_attribute_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_attribute_contestshot", "contest_shot_attribute", evidence, league_player_rows)


def derive_tendency_blockshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    """Remain unresolved without Data Master block-attempt appetite evidence."""

    return None


def derive_tendency_contestshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    games = _games_played(evidence)
    dcontest = _read(evidence, "shotquality_contest.dcontest")
    if games is None or dcontest is None:
        return None
    population = tuple(
        sorted(
            value
            for row in _eligible_rows(evidence, league_player_rows)
            if (value := _row_value(row, "crafted_source_shotquality.dcontest")) is not None
        )
    )
    score = _population_rank(dcontest, population)
    if score is None:
        return None
    return {
        "value": max(0, min(100, round(100.0 * score))),
        "score": score,
        "source_rule": "derive_tendency_contestshot_data_master_dcontest_rank",
        "evidence_keys": (
            games[1],
            "shotquality_contest.dcontest",
            f"dcontest={dcontest:.8f}",
            f"same_season_same_league_dcontest_rank={score:.8f}",
            "source_database=NBA_DATA_Master.sqlite",
            "source_table=crafted_source_shotquality",
            "source_column=dcontest",
            "identity=crafted_player_id_map.status=mapped;nba_id_only;no_name_fallback",
            "source_grain=exact_nba_id_season",
            "source_team_abbreviation=provenance_only_not_identity",
            "metric_semantics=ShotQuality_defensive_contest_component_not_raw_attempt_count",
            "mapping=round(100*same_season_same_league_dcontest_rank)",
            "population=exact_same_season_same_league_gp_positive_mapped_Data_Master_rows",
            "independent_tendency=no_cross_field_normalization",
        ),
    }


def derive_tendency_foul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_tendency_foul", "t_foul", evidence, league_player_rows)


_HARD_FOUL_LOW_CONTACT_EXCEPTION_MAX_SCORE = 0.20


def derive_tendency_hardfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    games = _games_played(evidence)
    if games is None:
        return None
    era = player_era_context(evidence)
    if era.season < 1960:
        return {
            "value": 100,
            "source_rule": "derive_tendency_hardfoul_universal_pre_1960_maximum",
            "evidence_keys": (
                games[1],
                *era.evidence_keys,
                "season_boundary=season_ending_year<1960",
                "HARDFOUL=100",
                "scale_meaning=maximum_2K_propensity_not_literal_event_probability",
            ),
        }

    if not 1970 <= era.season < 1990:
        return None

    result = _derive("derive_tendency_hardfoul", "t_hard_foul", evidence, league_player_rows)
    if result is None:
        return None

    score = result.get("score")
    if score is not None and float(score) <= _HARD_FOUL_LOW_CONTACT_EXCEPTION_MAX_SCORE:
        return {
            **result,
            "source_rule": f"{result['source_rule']}_1970s_1980s_low_contact_exception",
            "evidence_keys": tuple(result["evidence_keys"]) + (
                *era.evidence_keys,
                f"hard_foul_contact_score={float(score):.8f}",
                "exception_policy=bottom_20_percent_same_season_contact_score_retains_player_evidence_value",
            ),
        }

    base_value = int(result["value"])
    return {
        **result,
        "value": 100,
        "source_rule": "derive_tendency_hardfoul_1970s_1980s_most_players_maximum",
        "evidence_keys": tuple(result["evidence_keys"]) + (
            *era.evidence_keys,
            f"player_evidence_hard_foul_value={base_value}",
            "exception_policy=bottom_20_percent_same_season_contact_score_retains_player_evidence_value",
            "exception_not_established=true" if score is None else f"hard_foul_contact_score={float(score):.8f}",
            "HARDFOUL=100",
            "scale_meaning=maximum_2K_propensity_not_literal_event_probability",
        ),
    }


def derive_tendency_onballsteal(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    """Remain unresolved without Data Master on-ball steal-attempt evidence."""

    return None


def derive_tendency_passinterception(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    """Remain unresolved without Data Master interception-attempt evidence."""

    return None


def derive_tendency_takecharge(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("derive_tendency_takecharge", "t_take_charge", evidence, league_player_rows)


__all__ = [
    "derive_attribute_block",
    "derive_attribute_defenseconsistency",
    "derive_attribute_helpdefense",
    "derive_attribute_interiordefense",
    "derive_attribute_passperception",
    "derive_attribute_perimeterdefense",
    "derive_attribute_steal",
    "derive_attribute_lateralquickness",
    "derive_attribute_pickandrolldefenseiq",
    "derive_attribute_contestshot",
    "derive_tendency_blockshot",
    "derive_tendency_contestshot",
    "derive_tendency_foul",
    "derive_tendency_hardfoul",
    "derive_tendency_onballsteal",
    "derive_tendency_passinterception",
    "derive_tendency_takecharge",
]