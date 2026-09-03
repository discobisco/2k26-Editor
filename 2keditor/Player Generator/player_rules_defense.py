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
# tuple is (intercept, height coefficient, weight coefficient, residual standard
# deviation).  There is no role column: the role axis was a hand-picked split -- PG 1.0,
# SG 0.8, SF 0.5, PF 0.2, C 0.0 -- and on perimeter and interior defence it *was* the
# rating, 45.9 points of swing decided by a position label.  Each role contribution is
# folded into its intercept at the neutral role of 0.5, so every field keeps its level
# while win shares, height and weight decide who is above whom.  The column is deleted
# rather than zeroed: while it existed, so did the machinery computing it, and that
# machinery refused to rate a player with no listed position at all.  Height and weight are centered at
# the exact Pool means below.  Lateral, P&R IQ, and Contest are same-package
# semantic composites because those exact Attribute labels were not captured.
# These are continuous calibrations, not position bands or output gates.
_POOL_HEIGHT_CENTER = 76.04575163398692
_POOL_WEIGHT_CENTER = 198.03248209150323
_CALIBRATION: dict[str, tuple[float, float, float, float]] = {
    "block": (46.54169890, 3.59626670, 0.03566835, 11.43932622),
    "defense_consistency": (51.04533511, 2.43524234, 0.08418385, 11.88273199),
    "help_defense": (55.72652895, 3.43569807, 0.09721121, 12.67381189),
    "interior_defense": (44.41544380, 2.44150743, 0.11382704, 9.84815556),
    "pass_perception": (58.51470552, 4.29566679, 0.02255723, 13.91619499),
    "perimeter_defense": (56.64257654, -2.00000000, -0.04500000, 12.26868584),
    "steal": (52.78579124, -1.20000000, -0.02000000, 11.00726531),
    "lateral_quickness": (54.56876402, 3.25832799, 0.07509925, 12.12455866),
    "pick_and_roll_iq": (53.38593203, 2.93547020, 0.09069753, 11.50524791),
    "contest_shot_attribute": (52.21129325, 2.45040692, 0.09768933, 7.98725768),
    "t_foul": (55.00000000, -0.33218055, -0.01287985, 14.83000000),  # ATD Foul 45-65, cap 95
    # Deliberately NOT on ATD numbers. derive_tendency_hardfoul pins this field to
    # 100 pre-1960 and for all but the bottom-quintile contact score in 1970-1989,
    # because 2K does not otherwise represent the physicality of those eras. The ATD
    # band (5-20, cap 45) describes a literal hard-contact rate; this field is used
    # as an engine propensity. Only the 1970s/80s low-contact exception reads it.
    "t_hard_foul": (51.50855084, -2.67721871, -0.04814260, 15.95836388),
    "t_take_charge": (10.00000000, 1.48002538, 0.05358680, 7.41000000),  # ATD Take Charge 5-15, cap 35
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
_BAA_DEFENSE_QUALITY_WEIGHTS = {
    "dws": 0.65,
    "team_win_pct": 0.175,
    "team_opp_ppg": 0.175,
}
_BAA_ROUTED_DEFENSE_POPULATION_CACHE: dict[
    tuple[int, str],
    tuple[tuple[dict[str, Any], ...], tuple[float, ...]],
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
    # Defensive win shares lead. Reading a passing lane is a defensive skill, and every
    # other term here -- disruption, steal rate, stocks -- is a tracking-era measurement:
    # steal percentage and per-100 possessions do not exist before 1973-74. Without DWS
    # the whole recipe went unavailable in the early seasons and the field fell through
    # to a size-and-role prior, so the one recorded defensive measurement of the era
    # reached it not at all.
    "pass_perception": (
        ("advanced.dws", 0.40),
        ("crafted.disruption_per_100", 0.22),
        ("advanced.stl_percent", 0.18),
        ("per_100.stl_per_100_poss", 0.12),
        ("crafted.stock_percent", 0.08),
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
        "DWS with STL, disruption, and stock evidence",
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
    intercept, height_coefficient, weight_coefficient, _ = _CALIBRATION[field]
    height = _read(evidence, "identity.ht_in_in")
    weight = _read(evidence, "identity.wt")
    value = intercept
    keys: list[str] = []
    if height is not None:
        value += (height - _POOL_HEIGHT_CENTER) * height_coefficient
        keys.append("identity.ht_in_in")
    if weight is not None:
        value += (weight - _POOL_WEIGHT_CENTER) * weight_coefficient
        keys.append("identity.wt")
    keys.extend((
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


def _row_context_value(field: str, row: dict[str, Any]) -> float | None:
    intercept, height_coefficient, weight_coefficient, _ = _CALIBRATION[field]
    value = intercept
    height = _row_value(row, "identity.ht_in_in")
    weight = _row_value(row, "identity.wt")
    if height is not None:
        value += (height - _POOL_HEIGHT_CENTER) * height_coefficient
    if weight is not None:
        value += (weight - _POOL_WEIGHT_CENTER) * weight_coefficient
    return value


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
        dws = _read(evidence, "advanced.dws")
        dws_population = tuple(
            sorted(
                value
                for row in rows
                if (value := _row_value(row, "advanced.dws")) is not None
            )
        )
        if dws is None or len(dws_population) < 2:
            return None
        # Min-max across the league's real DWS range, not a rank. Going 1, 2, 3 down the
        # order throws away the size of the gaps -- the distance between the best
        # defender in the league and the second best is evidence, and a rank reports it
        # as one step, the same step as between the 40th and the 41st. The league's
        # highest defensive win share is the only 99 and its lowest is the only 25.
        low, high = dws_population[0], dws_population[-1]
        span = high - low
        if span <= 0.0:
            return None
        score = (dws - low) / span
        return {
            "value": max(25, min(99, round(25.0 + 74.0 * score))),
            "score": score,
            "source_rule": rule_name,
            "evidence_keys": (games[1], "advanced.dws", f"dws={dws:.8f}") + (
                f"same_league_min_dws={low:.8f}",
                f"same_league_max_dws={high:.8f}",
                f"dws_magnitude_score={score:.8f}",
                "rank_source=dws_minmax_not_rank",
                "mapping=round(25+74*(dws-min)/(max-min))",
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
        substitute_value, position_skew_keys = _defensive_substitute_adjustment(
            field, evidence, rows, context_value
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
    residual_scale = _CALIBRATION[field][3]
    value = context_value + NormalDist().inv_cdf(score) * residual_scale
    return {
        "value": _legal_value(field, value),
        "score": score,
        "source_rule": rule_name,
        "evidence_keys": (games[1],) + source_keys + context_keys + (
            "direct_source=" + ",".join(source_keys),
            f"raw_same_season_population_score={raw_score:.8f}",
            f"same_season_population_score={score:.8f}",
            f"gp_exposure_reliability={exposure_reliability:.8f}",
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


def _defense_quality_weights(source: Any) -> dict[str, float]:
    league = _row_league(source) if isinstance(source, dict) else _league(source)
    if league == "NBL":
        # NBL has no individual DWS. Wins are an overall team outcome, not an
        # individual defensive measurement, so use the defensive team signal.
        return {"team_opp_ppg": 1.0}
    if league == "BAA":
        return _BAA_DEFENSE_QUALITY_WEIGHTS
    return _DEFENSE_QUALITY_WEIGHTS


def _defense_quality_component_score(
    name: str,
    value: float,
    population: tuple[float, ...],
    *,
    league: str,
) -> float:
    if name == "dws" and league == "BAA":
        minimum = population[0]
        maximum = population[-1]
        if maximum <= minimum:
            return 0.5
        return max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
    if name == "team_opp_ppg":
        return (len(population) - bisect.bisect_left(population, value)) / len(population)
    return bisect.bisect_right(population, value) / len(population)


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
    population_rows = eligible_rows
    if _league(evidence) == "NBL":
        population_rows = tuple(row for row in eligible_rows if _row_league(row) == "NBL")
    component_populations = _defense_quality_component_populations(population_rows)
    components: list[tuple[str, float, float]] = []
    quality_keys: list[str] = []
    weights = _defense_quality_weights(evidence)
    league = _league(evidence)
    for name, weight in weights.items():
        value = component_values.get(name)
        population = component_populations.get(name, ())
        if value is None or not population:
            continue
        component_score = _defense_quality_component_score(
            name,
            value,
            population,
            league=league,
        )
        if name == "dws" and league == "BAA":
            quality_keys.extend((
                "advanced.dws",
                f"dws={value:.8f}",
                f"dws_same_league_min={population[0]:.8f}",
                f"dws_same_league_max={population[-1]:.8f}",
                f"dws_minmax_score={component_score:.8f}",
                f"dws_minmax_rating_25_99={round(25.0 + 74.0 * component_score)}",
                "dws_mapping=minimum_DWS:25,maximum_DWS:99",
            ))
        else:
            quality_keys.extend(_defense_quality_component_provenance(name, value, component_score))
        components.append((name, weight, component_score))
    total_weight = sum(weight for _name, weight, _component_score in components)
    if total_weight <= 0.0:
        return None
    score = sum(weight * component_score for _name, weight, component_score in components) / total_weight
    return score, (
        *quality_keys,
        "defense_quality_weights=" + ",".join(
            f"{name}:{weight:.2f}" if weight == round(weight, 2) else f"{name}:{weight:.3f}"
            for name, weight in weights.items()
        ),
        "team_opp_ppg_direction=lower_is_better",
        f"available_weight={total_weight:.8f}",
        "missing_components=omitted_and_available_weights_renormalized",
        "team_population=unique_exact_team_within_same_season_same_league",
    )


#: Field name to the attribute key a researched rule authors it under.
_FIELD_ATTRIBUTE_NAMES = {
    "interior_defense": "INTERIORDEFENSE",
    "perimeter_defense": "PERIMETERDEFENSE",
    "steal": "STEAL",
    "block": "BLOCK",
}


#: Interior defence: rating points at the edge of the weight-for-height band. An
#: underweight big gets moved off the block; a heavy one holds it.
_INTERIOR_WEIGHT_DEVIATION_RANGE = 9.0

#: Block: rating points across the season's height percentile range.
_BLOCK_HEIGHT_PERCENTILE_RANGE = 14.0

#: Help defence is learned -- it accrues with seasons on the floor rather than peaking.
_HELP_DEFENSE_AGE_ONSET = 22.0
_HELP_DEFENSE_AGE_SPAN = 8.0
_HELP_DEFENSE_AGE_RANGE = 7.0

#: Pass perception needs both the read and the legs to act on it, so it peaks at 29.
_PASS_PERCEPTION_PEAK_AGE = 29.0
_PASS_PERCEPTION_AGE_SPAN = 8.0
_PASS_PERCEPTION_AGE_RANGE = 6.0


def _height_weight_slope(rows: tuple[dict[str, Any], ...]) -> tuple[float, float, float] | None:
    """Least-squares weight-on-height over the season, for the expected build."""

    pairs = [
        (h, w)
        for row in rows
        if (h := _row_value(row, "identity.ht_in_in")) is not None
        and (w := _row_value(row, "identity.wt")) is not None
    ]
    if len(pairs) < 3:
        return None
    mean_h = sum(h for h, _ in pairs) / len(pairs)
    mean_w = sum(w for _, w in pairs) / len(pairs)
    denominator = sum((h - mean_h) ** 2 for h, _ in pairs)
    if denominator <= 0.0:
        return None
    slope = sum((h - mean_h) * (w - mean_w) for h, w in pairs) / denominator
    return slope, mean_h, mean_w


def _defensive_substitute_adjustment(
    field: str,
    evidence: Any,
    rows: tuple[dict[str, Any], ...],
    context_value: float,
) -> tuple[float, tuple[str, ...]]:
    """The substitute value for a field whose own evidence the era never recorded.

    The body prediction is the starting point and each field then takes the one body or
    age term that is specifically about it. Defensive win shares are deliberately not
    blended in here: every one of these fields already carries DWS in its own recipe, so
    a second helping at the substitute stage counted the same evidence twice. Everything
    here is continuous; nothing switches on a threshold.
    """

    value = context_value
    keys: list[str] = []

    height = _read(evidence, "identity.ht_in_in")
    player_weight = _read(evidence, "identity.wt")
    age = _read(evidence, "season_info.age")

    if field == "interior_defense" and height is not None and player_weight is not None:
        fit = _height_weight_slope(rows)
        if fit is not None:
            slope, mean_h, mean_w = fit
            expected = mean_w + (height - mean_h) * slope
            spread = [
                abs(w - (mean_w + (h - mean_h) * slope))
                for row in rows
                if (h := _row_value(row, "identity.ht_in_in")) is not None
                and (w := _row_value(row, "identity.wt")) is not None
            ]
            typical = sorted(spread)[len(spread) // 2] if spread else 0.0
            if typical > 0.0:
                deviation = max(-1.0, min(1.0, (player_weight - expected) / (2.0 * typical)))
                value += deviation * _INTERIOR_WEIGHT_DEVIATION_RANGE
                keys.extend((
                    "identity.ht_in_in",
                    "identity.wt",
                    f"expected_weight_for_height={expected:.8f}",
                    f"weight_for_height_deviation={deviation:.8f}",
                    "interior_rationale=an_underweight_big_gets_moved_off_the_block",
                ))

    if field == "block" and height is not None:
        heights = sorted(
            h for row in rows if (h := _row_value(row, "identity.ht_in_in")) is not None
        )
        if len(heights) >= 2:
            below = sum(1 for h in heights if h < height)
            equal = sum(1 for h in heights if h == height)
            percentile = (below + equal / 2.0) / len(heights)
            value += (percentile - 0.5) * 2.0 * _BLOCK_HEIGHT_PERCENTILE_RANGE
            keys.extend((
                "identity.ht_in_in",
                f"same_season_height_percentile={percentile:.8f}",
                "block_rationale=a_block_is_reach_before_it_is_anything_else",
            ))

    if field == "help_defense" and age is not None:
        accrual = max(0.0, min(1.0, (age - _HELP_DEFENSE_AGE_ONSET) / _HELP_DEFENSE_AGE_SPAN))
        value += (accrual - 0.5) * 2.0 * _HELP_DEFENSE_AGE_RANGE
        keys.extend((
            "season_info.age",
            f"help_defense_age_accrual={accrual:.8f}",
            "help_rationale=rotations_are_learned_so_this_accrues_rather_than_peaking",
        ))

    if field == "pass_perception" and age is not None:
        distance = abs(age - _PASS_PERCEPTION_PEAK_AGE) / _PASS_PERCEPTION_AGE_SPAN
        curve = max(0.0, 1.0 - distance ** 2)
        value += (curve - 0.5) * 2.0 * _PASS_PERCEPTION_AGE_RANGE
        keys.extend((
            "season_info.age",
            f"pass_perception_age_curve={curve:.8f}",
            f"pass_perception_peak_age={_PASS_PERCEPTION_PEAK_AGE:g}",
            "pass_rationale=the_read_needs_the_legs_to_act_on_it",
        ))

    return value, tuple(keys)


#: The interior/perimeter split runs on reach: none at 6'0", full at 6'10".
_SIDE_SPLIT_FLOOR_HEIGHT = 72.0
_SIDE_SPLIT_SPAN = 10.0
_SIDE_SPLIT_DEPTH = 0.45


def _side_multiplier_from_height(height: float | None, field: str) -> float:
    """How much of a player's defensive quality lands on each side of the floor.

    This used to be read off the position label: a listed guard had his interior defence
    multiplied by 0.15 and a listed centre his perimeter defence, so a 6'7" "G-F" and a
    6'7" "F-C" split the same body two different ways. It runs on reach instead, with no
    threshold anywhere -- at 6'0" the split is 1.00 perimeter / 0.55 interior, and at
    6'10" it is the reverse.
    """

    if height is None:
        return 1.0 - _SIDE_SPLIT_DEPTH / 2.0
    reach = max(0.0, min(1.0, (height - _SIDE_SPLIT_FLOOR_HEIGHT) / _SIDE_SPLIT_SPAN))
    if field == "interior_defense":
        return 1.0 - _SIDE_SPLIT_DEPTH * (1.0 - reach)
    if field == "perimeter_defense":
        return 1.0 - _SIDE_SPLIT_DEPTH * reach
    return 1.0


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
    league = _row_league(row)
    for name, weight in _defense_quality_weights(row).items():
        value = values.get(name)
        population = component_populations.get(name, ())
        if value is None or not population:
            continue
        component_score = _defense_quality_component_score(
            name,
            value,
            population,
            league=league,
        )
        components.append((weight, component_score))
    total_weight = sum(weight for weight, _score in components)
    if total_weight <= 0.0:
        return None
    return sum(weight * component_score for weight, component_score in components) / total_weight


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


def _baa_routed_defense_population(
    field: str,
    eligible_rows: tuple[dict[str, Any], ...],
) -> tuple[float, ...]:
    cache_key = (id(eligible_rows), field)
    cached = _BAA_ROUTED_DEFENSE_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is eligible_rows:
        return cached[1]
    baa_rows = tuple(row for row in eligible_rows if _row_league(row) == "BAA")
    component_populations = _defense_quality_component_populations(baa_rows)
    signals: list[float] = []
    for row in baa_rows:
        if _row_has_researched_defense_override(row):
            continue
        quality_score = _row_defense_quality_score(row, component_populations)
        if quality_score is None:
            continue
        signals.append(quality_score * _side_multiplier_from_height(_row_value(row, "identity.ht_in_in"), field))
    population = tuple(sorted(signals))
    _BAA_ROUTED_DEFENSE_POPULATION_CACHE[cache_key] = (eligible_rows, population)
    return population


def _derive_dws_defense(rule_name: str, field: str, evidence: Any, rows: Any) -> dict[str, Any] | None:
    """Author defensive quality, then route it across the floor by reach.

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
        # The rule authors each side of the floor separately -- Mikan is 99 inside and 36
        # on the perimeter -- so read the researched value for this field rather than
        # rebuilding it from a single quality score.
        authored = special_rule.expected_values_by_field.get(
            f"Attributes/{_FIELD_ATTRIBUTE_NAMES.get(field, '')}"
        )
        score = (authored - 25.0) / 74.0 if authored is not None else special_rule.quality_score
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
    # A researched exact override is the finding itself, not a quality score to be
    # routed, so reach does not scale it.
    side_height = _read(evidence, "identity.ht_in_in")
    multiplier = 1.0 if special_rule is not None else _side_multiplier_from_height(side_height, field)
    position_keys: tuple[str, ...] = (
        "identity.ht_in_in",
        f"reach_side_multiplier={multiplier:.8f}",
        "side_split=interior_rises_with_reach;perimeter_falls_with_reach;no_position_label",
    )
    if special_rule is None and _league(evidence) == "BAA":
        population = _baa_routed_defense_population(field, eligible_rows)
        routed_score = score * multiplier
        if len(population) >= 2 and population[-1] > population[0]:
            minimum = population[0]
            maximum = population[-1]
            final_score = max(0.0, min(1.0, (routed_score - minimum) / (maximum - minimum)))
            return {
                "value": _legal_value(field, 25 + 74 * final_score),
                "score": score,
                "source_rule": quality_rule,
                "evidence_keys": quality_keys + position_keys + (
                    f"baa_routed_defense_score={routed_score:.8f}",
                    f"baa_routed_defense_min={minimum:.8f}",
                    f"baa_routed_defense_max={maximum:.8f}",
                    f"baa_routed_defense_minmax_score={final_score:.8f}",
                    "baa_final_mapping=minimum_routed_BAA_value:25,maximum_routed_BAA_value:99",
                    "final_mapping=round(25+74*BAA_routed_minmax_score);clamp=25..99",
                ),
            }
    return {
        "value": _legal_value(field, 25 + score * 74 * multiplier),
        "score": score,
        "source_rule": quality_rule,
        "evidence_keys": quality_keys + position_keys + (
            "final_mapping=round(25+74*defense_quality_score*reach_side_multiplier);clamp=25..99",
        ),
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
    pre_1960 = era.season < 1960
    if not pre_1960 and not 1970 <= era.season < 1990:
        return None

    result = _derive("derive_tendency_hardfoul", "t_hard_foul", evidence, league_player_rows)
    if result is None:
        return None

    # Pre-1960 takes the same treatment as the 1970s and 80s: the era's physicality
    # pins most players to the maximum, but the league's gentlest fifth keeps its own
    # evidence. A flat 100 for every player alive gave 333 of 333 the same number and
    # said nothing about any of them.
    score = result.get("score")
    if score is not None and float(score) <= _HARD_FOUL_LOW_CONTACT_EXCEPTION_MAX_SCORE:
        return {
            **result,
            "source_rule": (
                "derive_tendency_hardfoul_pre_1960_low_contact_exception"
                if pre_1960
                else f"{result['source_rule']}_1970s_1980s_low_contact_exception"
            ),
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
        "source_rule": (
            "derive_tendency_hardfoul_pre_1960_maximum"
            if pre_1960
            else "derive_tendency_hardfoul_1970s_1980s_most_players_maximum"
        ),
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