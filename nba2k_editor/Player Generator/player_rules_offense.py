from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

from player_era_context import filter_same_league_rows, player_era_context
from player_rules_athleticism import derive_attribute_vertical


_POPULATION_CACHE: dict[
    tuple[int, int, str],
    tuple[object, tuple[dict[str, Any], ...]],
] = {}
_POPULATION_VALUE_CACHE: dict[
    tuple[int, str],
    tuple[object, tuple[float, ...]],
] = {}
_POPULATION_POSITION_CACHE: dict[
    int,
    tuple[object, tuple[dict[str, float], ...]],
] = {}
_ROBUST_SUMMARY_CACHE: dict[
    tuple[int, str],
    tuple[object, tuple[float, float] | None],
] = {}


@dataclass(frozen=True)
class _Recipe:
    name: str
    signals: tuple[tuple[str, float], ...]
    unavailable: str = ""
    substitute: str = ""
    why_valid: str = ""


# Field-exact target centers and one-standard-deviation scales are frozen from
# the 765 GP-valid complete Pool packages. Historical shooting execution uses
# the immutable SQL Pool packages directly through the range lookup below.
_ATTRIBUTE_CALIBRATION: dict[str, tuple[float, float]] = {
    "BALLCONTROL": (52.0, 28.2),
    "DRAWFOUL": (56.0, 25.9),
    "OFFENSIVECONSISTENCY": (57.0, 25.9),
    "PASSACCURACY": (53.0, 25.9),
    "PASSIQ": (54.0, 27.4),
    "PASSVISION": (47.0, 25.9),
    "IQSHOT": (57.0, 25.9),
    "3POINT": (30.0, 20.8),
    "CLOSESHOT": (62.0, 23.7),
    "DRIVINGDUNK": (45.0, 18.5),
    "DRIVINGLAYUP": (58.0, 23.0),
    "MIDRANGE": (52.0, 16.3),
    "POSTCONTROL": (49.0, 27.4),
    "POSTFADE": (45.0, 11.9),
    "POSTHOOK": (48.0, 22.2),
    "STANDINGDUNK": (37.0, 19.3),
}

_TENDENCY_CALIBRATION: dict[str, tuple[float, float]] = {
    "SHOT": (46.0, 17.8),
    "3POINTSHOT": (45.0, 22.0),
    "CLOSESHOT": (37.0, 20.0),
    "MIDRANGESHOT": (37.0, 19.3),
    "TRIPLETHREATIDLE": (30.0, 14.1),
    "TRIPLETHREATJAB": (23.0, 19.3),
    "TRIPLETHREATPUMPFake": (27.0, 15.6),
    "TRIPLETHREATSHOT": (24.0, 17.0),
    "SETUPDRIBBLE": (43.0, 21.5),
    "SETUPWITHHESITATION": (22.0, 14.8),
    "SETUPWITHSIZEUP": (15.0, 13.3),
    "DRIVE": (48.0, 20.0),
    "DRIVERIGHT": (45.0, 18.5),
    "DRIVINGCROSSOVER": (16.0, 21.5),
    "DRIVINGDOUBLECROSSOVER": (18.0, 23.0),
    "DRIVINGSPIN": (15.0, 17.8),
    "DRIVINGHALFSPIN": (18.0, 23.0),
    "DRIVINGSTEPBACK": (20.0, 24.5),
    "DRIVINGBEHINDTHEBACK": (18.0, 22.2),
    "DRIVINGDRIBBLEHESITATION": (25.0, 20.0),
    "DRIVINGINANDOUT": (22.0, 23.7),
    "NODRIVINGDRIBBLEMOVE": (70.0, 18.5),
    "ATTACKSTRONGONDRIVE": (46.0, 20.0),
    "OFFSCREENDRIVE": (40.0, 21.5),
    "SPOTUPDRIVE": (42.0, 18.5),
    "ALLEYOOOPASS": (20.0, 17.8),
    "DISHTOOPENMAN": (37.0, 14.1),
    "FLASHYPASS": (20.0, 17.0),
    "POSTUP": (29.0, 23.7),
    "POSTBACKDOWN": (16.0, 14.1),
    "POSTAGGRESSIVEBACKDOWN": (13.0, 11.9),
    "POSTFACEUP": (9.0, 7.4),
    "POSTSPIN": (3.0, 3.7),
    "POSTDRIVE": (11.0, 8.2),
    "POSTHOPSHOT": (1.0, 4.4),
}

# User-observed NBA 2K mid-range response anchors. Each context is the expected
# make probability at the same MIDRANGE Attribute. Runtime historical inversion
# is explicitly the wide-open stationary spot-up/set-shot context; contexts are
# never averaged or normalized into attempt shares.
_MIDRANGE_RESPONSE_ANCHORS: dict[str, tuple[tuple[int, float], ...]] = {
    "spot_up": ((25, 0.0015), (80, 0.45), (99, 0.55)),
    "off_screen": ((25, 0.0015), (80, 0.40), (99, 0.50)),
    "pull_up": ((25, 0.0015), (80, 0.40), (99, 0.50)),
    "contested": ((25, 0.0015), (80, 0.35), (99, 0.45)),
}

def _piecewise_linear_response(
    x: float,
    anchors: tuple[tuple[int, float], ...],
) -> float:
    for anchor_x, anchor_y in anchors:
        if x == anchor_x:
            return anchor_y
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x < x1:
            return y0 + (x - x0) * (y1 - y0) / (x1 - x0)
    return anchors[-1][1]


def midrange_make_probability_for_rating(rating: int, *, context: str) -> float:
    anchors = _MIDRANGE_RESPONSE_ANCHORS[context]
    return _piecewise_linear_response(float(max(25, min(99, rating))), anchors)


def midrange_rating_for_make_probability(make_probability: float, *, context: str) -> int:
    target = max(0.0, min(1.0, float(make_probability)))
    anchors = _MIDRANGE_RESPONSE_ANCHORS[context]
    if target <= anchors[0][1]:
        return anchors[0][0]
    for (rating0, probability0), (rating1, probability1) in zip(anchors, anchors[1:]):
        if target <= probability1:
            rating = rating0 + (target - probability0) * (rating1 - rating0) / (probability1 - probability0)
            return max(25, min(99, int(round(rating))))
    return anchors[-1][0]

_ROW_PREFIX = {
    "per_game": "player_per_game",
    "totals": "player_totals",
    "per_36": "player_per_36_min",
    "per_100": "player_per_100_poss",
    "advanced": "advanced",
    "shooting": "player_shooting",
    "play_by_play": "player_play_by_play",
    "identity": "player_info",
    "season_info": "player_season_info",
    "team_stats_per_game": "team_stats_per_game",
    "team_stats_per_100": "team_stats_per_100_poss",
    "team_summary": "team_summaries",
    "team_totals": "team_totals",
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _league(source: Any) -> str:
    if isinstance(source, dict):
        value = source.get("player_season_info.lg") or source.get("player_per_game.lg") or source.get("lg")
    else:
        season_info = getattr(source, "season_info", {})
        per_game = getattr(source, "per_game", {})
        value = season_info.get("lg") or per_game.get("lg")
    return str(value or "").strip().upper()


def _season(source: Any) -> int:
    if isinstance(source, dict):
        value = source.get("season") or source.get("player_season_info.season")
    else:
        value = getattr(source, "season", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _basic_value(source: Any, path: str) -> float | None:
    section, _, field = path.partition(".")
    if not field:
        return None
    if isinstance(source, dict):
        prefix = _ROW_PREFIX.get(section, section)
        value = source.get(f"{prefix}.{field}")
        if value is None and section == "per_game":
            value = source.get(field)
        return _number(value)
    mapping = getattr(source, section, None)
    if isinstance(mapping, dict):
        value = mapping.get(field)
        if value is not None:
            return _number(value)
    context = getattr(source, "source_context", {})
    if isinstance(context, dict):
        prefix = _ROW_PREFIX.get(section, section)
        return _number(context.get(f"{prefix}.{field}"))
    return None


def _gp(source: Any) -> float | None:
    for path in ("per_game.g", "totals.g", "advanced.g"):
        value = _basic_value(source, path)
        if value is not None:
            return value if value > 0.0 else None
    return None


def _recorded_assists_available(source: Any) -> bool:
    # The pre-PER NBL source has no recorded assists. Zeroes through the final
    # NBL season are absence markers, not zero passing production.
    return not (_league(source) == "NBL" and _season(source) < 1952)


def _position_vector(source: Any) -> dict[str, float]:
    result = {position: 0.0 for position in ("PG", "SG", "SF", "PF", "C")}
    play_values = {
        position: _basic_value(source, f"play_by_play.{position.lower()}_percent")
        for position in result
    }
    play_total = sum(value or 0.0 for value in play_values.values())
    if play_total > 0.0:
        for position, value in play_values.items():
            result[position] = (value or 0.0) / play_total
        return result

    if isinstance(source, dict):
        primary = source.get("player_season_info.pos")
        secondary = source.get("player_info.pos")
    else:
        primary = getattr(source, "season_info", {}).get("pos")
        secondary = getattr(source, "identity", {}).get("pos")
    primary_vector = _parse_positions(primary)
    secondary_vector = _parse_positions(secondary)
    if any(primary_vector.values()) and any(secondary_vector.values()):
        for position in result:
            result[position] = 0.7 * primary_vector[position] + 0.3 * secondary_vector[position]
    elif any(primary_vector.values()):
        result = primary_vector
    else:
        result = secondary_vector
    total = sum(result.values())
    return {position: value / total for position, value in result.items()} if total > 0.0 else result


def _parse_positions(value: Any) -> dict[str, float]:
    result = {position: 0.0 for position in ("PG", "SG", "SF", "PF", "C")}
    text = str(value or "").strip().upper().replace("/", "-")
    if not text:
        return result
    tokens = [token for token in text.split("-") if token]
    token_weights = (0.65, 0.35) if len(tokens) > 1 else (1.0,)
    for token, token_weight in zip(tokens, token_weights):
        if token == "G":
            result["PG"] += token_weight * 0.5
            result["SG"] += token_weight * 0.5
        elif token == "F":
            result["SF"] += token_weight * 0.5
            result["PF"] += token_weight * 0.5
        elif token in result:
            result[token] += token_weight
    return result


def _role_value(source: Any, role: str) -> float | None:
    return _role_value_from_positions(_position_vector(source), role)


def _role_value_from_positions(positions: dict[str, float], role: str) -> float | None:
    if not any(positions.values()):
        return None
    guard = positions["PG"] + 0.7 * positions["SG"] + 0.2 * positions["SF"]
    wing = 0.3 * positions["SG"] + positions["SF"] + 0.45 * positions["PF"]
    big = 0.55 * positions["PF"] + positions["C"]
    values = {
        "guard": guard,
        "wing": wing,
        "big": big,
        "creator": guard + 0.35 * wing,
        "post": big + 0.25 * wing,
        "interior": big + 0.2 * wing,
    }
    return values.get(role)


def _team_total(source: Any, field: str) -> float | None:
    direct = _basic_value(source, f"team_totals.{field}")
    if direct is not None and direct > 0.0:
        return direct
    per_game = _basic_value(source, f"team_stats_per_game.{field}_per_game")
    games = _basic_value(source, "team_stats_per_game.g")
    if per_game is None or games is None or games <= 0.0:
        return None
    return per_game * games


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _derived_value(source: Any, name: str) -> float | None:
    if name == "attempt_share":
        return _ratio(_basic_value(source, "totals.fga"), _team_total(source, "fga"))
    if name == "scoring_share":
        return _ratio(_basic_value(source, "totals.pts"), _team_total(source, "pts"))
    if name == "assist_share":
        if not _recorded_assists_available(source):
            return None
        return _ratio(_basic_value(source, "totals.ast"), _team_total(source, "ast"))
    if name == "assist_decision_efficiency":
        if not _recorded_assists_available(source):
            return None
        assists = _basic_value(source, "per_game.ast_per_game")
        turnovers = _basic_value(source, "per_game.tov_per_game")
        if assists is None or turnovers is None or assists + turnovers <= 0.0:
            return None
        return assists / (assists + turnovers)
    if name == "foul_pressure":
        value = _basic_value(source, "advanced.f_tr")
        if value is not None:
            return value
        value = _ratio(_basic_value(source, "totals.fta"), _basic_value(source, "totals.fga"))
        if value is not None:
            return value
        return _basic_value(source, "per_game.fta_per_game")
    if name == "three_attempt_rate":
        value = _basic_value(source, "advanced.x3p_ar")
        if value is not None:
            return value
        return _ratio(_basic_value(source, "totals.x3pa"), _basic_value(source, "totals.fga"))
    if name == "rim_attempt_rate":
        return _basic_value(source, "shooting.percent_fga_from_x0_3_range")
    if name == "short_attempt_rate":
        rim = _basic_value(source, "shooting.percent_fga_from_x0_3_range")
        short = _basic_value(source, "shooting.percent_fga_from_x3_10_range")
        return rim + short if rim is not None and short is not None else rim or short
    if name == "three_to_ten_attempt_rate":
        return _basic_value(source, "shooting.percent_fga_from_x3_10_range")
    if name == "mid_attempt_rate":
        parts = [
            _basic_value(source, "shooting.percent_fga_from_x10_16_range"),
            _basic_value(source, "shooting.percent_fga_from_x16_3p_range"),
        ]
        live = [value for value in parts if value is not None]
        return sum(live) if live else None
    if name == "dunk_rate":
        return _ratio(_basic_value(source, "shooting.num_of_dunks"), _basic_value(source, "totals.fga"))
    if name == "bad_pass_per_game":
        return _ratio(_basic_value(source, "play_by_play.bad_pass_turnover"), _gp(source))
    if name == "lost_ball_per_game":
        return _ratio(_basic_value(source, "play_by_play.lost_ball_turnover"), _gp(source))
    if name == "shooting_foul_drawn_per_game":
        return _ratio(_basic_value(source, "play_by_play.shooting_foul_drawn"), _gp(source))
    if name == "assist_points_per_game":
        return _ratio(_basic_value(source, "play_by_play.points_generated_by_assists"), _gp(source))
    if name == "and1_per_game":
        return _ratio(_basic_value(source, "play_by_play.and1"), _gp(source))
    if name == "blocked_attempt_rate":
        return _ratio(_basic_value(source, "play_by_play.fga_blocked"), _basic_value(source, "totals.fga"))
    if name == "unassisted_two_rate":
        assisted = _basic_value(source, "shooting.percent_assisted_x2p_fg")
        return 1.0 - assisted if assisted is not None else None
    return None


def _value(source: Any, key: str) -> float | None:
    if key.startswith("role."):
        return _role_value(source, key.split(".", 1)[1])
    if key.startswith("derived."):
        return _derived_value(source, key.split(".", 1)[1])
    if key.startswith("!"):
        value = _value(source, key[1:])
        return -value if value is not None else None
    if key.startswith("per_game.ast") or key.startswith("totals.ast") or key.startswith("advanced.ast"):
        if not _recorded_assists_available(source):
            return None
    return _basic_value(source, key)


def _population(evidence: Any, rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    season = _season(evidence)
    league = _league(evidence)
    cache_key = (id(rows), season, league)
    cached = _POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    population = tuple(
        row
        for row in filter_same_league_rows(evidence, rows)
        if _gp(row) is not None and (not season or _season(row) == season)
    )
    _POPULATION_CACHE[cache_key] = (rows, population)
    return population


def _population_position_vectors(population: tuple[dict[str, Any], ...]) -> tuple[dict[str, float], ...]:
    cache_key = id(population)
    cached = _POPULATION_POSITION_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        return cached[1]
    vectors = tuple(_position_vector(row) for row in population)
    _POPULATION_POSITION_CACHE[cache_key] = (population, vectors)
    return vectors


def _population_values(population: tuple[dict[str, Any], ...], key: str) -> tuple[float, ...]:
    cache_key = (id(population), key)
    cached = _POPULATION_VALUE_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        return cached[1]
    collected: list[float] = []
    if key.startswith("role."):
        role = key.split(".", 1)[1]
        for positions in _population_position_vectors(population):
            value = _role_value_from_positions(positions, role)
            if value is not None:
                collected.append(value)
    else:
        for row in population:
            value = _value(row, key)
            if value is not None:
                collected.append(value)
    values = tuple(collected)
    _POPULATION_VALUE_CACHE[cache_key] = (population, values)
    return values


def _robust_summary(population: Iterable[float]) -> tuple[float, float] | None:
    ordered = sorted(population)
    if len(ordered) < 5:
        return None
    median = statistics.median(ordered)
    deviations = [abs(item - median) for item in ordered]
    scale = statistics.median(deviations) * 1.4826
    if scale <= 1e-12:
        q1 = ordered[(len(ordered) - 1) // 4]
        q3 = ordered[(3 * (len(ordered) - 1)) // 4]
        scale = (q3 - q1) / 1.349
    return (median, scale) if scale > 1e-12 else None


def _robust_z(value: float, population: list[float]) -> float | None:
    summary = _robust_summary(population)
    if summary is None:
        return None
    median, scale = summary
    return (value - median) / scale


def _robust_z_for_population(
    value: float,
    population: tuple[dict[str, Any], ...],
    key: str,
) -> float | None:
    cache_key = (id(population), key)
    cached = _ROBUST_SUMMARY_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        summary = cached[1]
    else:
        summary = _robust_summary(_population_values(population, key))
        _ROBUST_SUMMARY_CACHE[cache_key] = (population, summary)
    if summary is None:
        return None
    median, scale = summary
    return (value - median) / scale


_RECIPE_REQUIRED_DIRECT_EVIDENCE: dict[str, tuple[str, ...]] = {
    # Attribute recipes: a tracked/location recipe is applicable only when at
    # least one field-defining source survives.  Role, body, touch, foul/load,
    # and efficiency context may support that source; they may not select the
    # modern recipe by themselves.
    "tracked_handle_security": ("derived.lost_ball_per_game", "advanced.tov_percent", "derived.unassisted_two_rate"),
    "tracked_foul_creation": ("derived.shooting_foul_drawn_per_game", "derived.and1_per_game"),
    "repeatable_scoring_load": ("per_36.pts_per_36_min",),
    "tracked_pass_completion_proxy": ("derived.assist_points_per_game", "derived.bad_pass_per_game", "derived.assist_decision_efficiency"),
    "tracked_pass_decisions": ("advanced.ast_percent", "derived.assist_decision_efficiency", "derived.bad_pass_per_game"),
    "tracked_creation_vision": ("derived.assist_points_per_game", "advanced.ast_percent", "derived.bad_pass_per_game"),
    "tracked_shot_selection": ("per_game.e_fg_percent", "derived.blocked_attempt_rate", "advanced.tov_percent"),
    "location_close_execution": ("shooting.fg_percent_from_x0_3_range", "shooting.fg_percent_from_x3_10_range"),
    "tracked_driving_finish": ("shooting.fg_percent_from_x0_3_range", "derived.and1_per_game", "derived.blocked_attempt_rate", "derived.dunk_rate"),
    "tracked_driving_layup_finish": ("shooting.fg_percent_from_x0_3_range", "derived.blocked_attempt_rate", "derived.and1_per_game"),
    "location_midrange_execution": ("shooting.fg_percent_from_x10_16_range", "shooting.fg_percent_from_x16_3p_range"),
    "tracked_post_security": ("derived.lost_ball_per_game", "advanced.tov_percent", "derived.unassisted_two_rate"),
    "location_post_fade_execution": ("shooting.fg_percent_from_x10_16_range", "shooting.fg_percent_from_x3_10_range"),
    "location_post_hook_execution": ("shooting.fg_percent_from_x3_10_range", "shooting.fg_percent_from_x0_3_range"),
    "tracked_standing_finish": ("derived.dunk_rate", "shooting.fg_percent_from_x0_3_range"),
    # Tendency recipes with a historical recipe behind them.  The modern
    # recipe needs location/event/self-creation evidence, not merely position,
    # height, foul pressure, or generic offensive responsibility.
    "triple_threat_jab": ("derived.mid_attempt_rate",),
    "triple_threat_pump": ("derived.short_attempt_rate",),
    "triple_threat_shoot": ("derived.mid_attempt_rate", "derived.three_attempt_rate"),
    "no_setup_dribble": ("derived.unassisted_two_rate",),
    "setup_hesitation": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "setup_sizeup": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "drive_frequency": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "drive_right_without_laterality": ("derived.rim_attempt_rate",),
    "driving_crossover": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "driving_double_crossover": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "driving_spin": ("derived.short_attempt_rate", "derived.unassisted_two_rate"),
    "driving_half_spin": ("derived.short_attempt_rate", "derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "driving_stepback": ("derived.mid_attempt_rate", "derived.three_attempt_rate", "derived.unassisted_two_rate"),
    "driving_behind_back": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "driving_hesitation": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "driving_in_out": ("derived.unassisted_two_rate", "derived.lost_ball_per_game"),
    "no_driving_move": ("derived.unassisted_two_rate",),
    "attack_strong_drive": ("derived.rim_attempt_rate",),
    "off_screen_drive": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "spot_up_drive": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "alley_oop_pass_behavior": ("derived.bad_pass_per_game",),
    "dish_open_man_behavior": ("derived.bad_pass_per_game", "advanced.tov_percent"),
    "flashy_pass_behavior": ("derived.bad_pass_per_game", "derived.lost_ball_per_game"),
    "post_up_frequency": ("derived.short_attempt_rate",),
    "post_backdown": ("derived.short_attempt_rate",),
    "post_aggressive_backdown": ("derived.short_attempt_rate",),
    "post_face_up": ("derived.mid_attempt_rate",),
    "post_spin": ("derived.short_attempt_rate", "derived.unassisted_two_rate"),
    "post_drive": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "post_hop_shot": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "alley_oop_finish": ("derived.dunk_rate", "derived.rim_attempt_rate"),
    "under_basket_attempt": ("derived.rim_attempt_rate",),
    "driving_dunk_frequency": ("derived.dunk_rate", "derived.rim_attempt_rate"),
    "driving_layup_frequency": ("derived.rim_attempt_rate", "derived.dunk_rate"),
    "euro_step_frequency": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "flashy_dunk_frequency": ("derived.dunk_rate",),
    "floater_frequency": ("derived.three_to_ten_attempt_rate", "derived.unassisted_two_rate"),
    "shoot_from_post": ("derived.short_attempt_rate", "derived.mid_attempt_rate"),
    "hop_post_shot": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "hop_step_layup": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "off_screen_mid": ("derived.mid_attempt_rate", "shooting.percent_assisted_x2p_fg"),
    "spot_up_mid": ("derived.mid_attempt_rate", "shooting.percent_assisted_x2p_fg"),
    "post_drop_step": ("derived.short_attempt_rate",),
    "post_fade_left": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "post_fade_right": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "post_hook_left": ("derived.three_to_ten_attempt_rate", "derived.unassisted_two_rate"),
    "post_hook_right": ("derived.three_to_ten_attempt_rate", "derived.unassisted_two_rate"),
    "post_shimmy": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "post_stepback": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "post_up_and_under": ("derived.short_attempt_rate", "derived.unassisted_two_rate"),
    "spin_jumper": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "spin_layup": ("derived.rim_attempt_rate", "derived.unassisted_two_rate"),
    "standing_dunk_frequency": ("derived.dunk_rate", "derived.rim_attempt_rate"),
    "use_glass": ("derived.three_to_ten_attempt_rate", "derived.rim_attempt_rate"),
}


def _estimated_total(source: Any, field: str) -> float | None:
    total = _basic_value(source, f"totals.{field}")
    if total is not None and total >= 0.0:
        return total
    per_game = _basic_value(source, f"per_game.{field}_per_game")
    games = _gp(source)
    if per_game is None or games is None or per_game < 0.0:
        return None
    return per_game * games


def _exposure_reliability(source: Any, key: str) -> tuple[float, str] | None:
    """Return continuous evidence reliability for noisy rates/percentages."""
    clean = key.lstrip("!")
    games = _gp(source)
    fga = _estimated_total(source, "fga")
    fta = _estimated_total(source, "fta")
    x3pa = _estimated_total(source, "x3pa")

    exposure: float | None = None
    prior = 0.0
    basis = ""
    if clean == "per_game.ft_percent":
        exposure, prior, basis = fta, 40.0, "recorded_fta"
    elif clean in {"per_game.fg_percent", "per_game.e_fg_percent", "advanced.ts_percent"}:
        exposure, prior, basis = fga, 100.0, "recorded_fga"
    elif clean == "per_game.x3p_percent":
        exposure, prior, basis = x3pa, 40.0, "recorded_3pa"
    elif clean in {"advanced.f_tr", "derived.foul_pressure"}:
        exposure, prior, basis = fga, 100.0, "foul_pressure_fga_denominator"
    elif clean in {"advanced.tov_percent", "derived.assist_decision_efficiency"}:
        exposure, prior, basis = games, 20.0, "games_with_possession_decisions"
    elif clean.startswith("shooting.fg_percent_from_"):
        exposure, prior, basis = fga, 80.0, "recorded_fga_location_opportunities"
    elif clean in {
        "derived.three_attempt_rate",
        "derived.rim_attempt_rate",
        "derived.short_attempt_rate",
        "derived.three_to_ten_attempt_rate",
        "derived.mid_attempt_rate",
        "derived.dunk_rate",
        "derived.blocked_attempt_rate",
        "derived.unassisted_two_rate",
        "shooting.percent_corner_3s_of_3pa",
        "shooting.percent_assisted_x2p_fg",
        "shooting.percent_assisted_x3p_fg",
    }:
        exposure, prior, basis = fga, 80.0, "recorded_fga_behavior_opportunities"
    elif clean in {
        "derived.bad_pass_per_game",
        "derived.lost_ball_per_game",
        "derived.shooting_foul_drawn_per_game",
        "derived.assist_points_per_game",
        "derived.and1_per_game",
    } or (clean.startswith("per_game.") and clean.endswith("_per_game")) or clean.startswith("per_36."):
        exposure, prior, basis = games, 20.0, "games_played_rate_exposure"

    if exposure is None or exposure < 0.0:
        return None
    reliability = exposure / (exposure + prior) if prior > 0.0 else 1.0
    return reliability, f"exposure_reliability[{clean}]={reliability:.8f};basis={basis};exposure={exposure:.6f};prior={prior:.6f}"


def _recipe_score(
    evidence: Any,
    population: tuple[dict[str, Any], ...],
    recipe: _Recipe,
) -> tuple[float, tuple[str, ...]] | None:
    required = _RECIPE_REQUIRED_DIRECT_EVIDENCE.get(recipe.name, ())
    if required and not any(_value(evidence, key) is not None for key in required):
        return None
    components: list[tuple[float, float, str]] = []
    reliability_evidence: list[str] = []
    for key, weight in recipe.signals:
        current = _value(evidence, key)
        if current is None:
            continue
        z_value = _robust_z_for_population(current, population, key)
        if z_value is None:
            continue
        reliability = _exposure_reliability(evidence, key)
        if reliability is not None:
            factor, reliability_key = reliability
            z_value *= factor
            reliability_evidence.append(reliability_key)
        components.append((z_value, weight, key))
    total_weight = sum(abs(weight) for _value_z, weight, _key in components)
    if total_weight <= 0.0:
        return None
    score = sum(value_z * weight for value_z, weight, _key in components) / total_weight
    evidence_keys = (*tuple(
        dict.fromkeys(
            source_path
            for _value_z, _weight, key in components
            for source_path in _provenance_sources(key.lstrip("!"))
        )
    ), *tuple(dict.fromkeys(reliability_evidence)))
    return score, evidence_keys


def _recipe_rank_score(
    evidence: Any,
    population: tuple[dict[str, Any], ...],
    recipe: _Recipe,
) -> tuple[float, tuple[str, ...]] | None:
    required = _RECIPE_REQUIRED_DIRECT_EVIDENCE.get(recipe.name, ())
    if required and not any(_value(evidence, key) is not None for key in required):
        return None
    components: list[tuple[float, float, str]] = []
    rank_evidence: list[str] = []
    for key, signed_weight in recipe.signals:
        current = _value(evidence, key)
        population_values = sorted(_population_values(population, key))
        if current is None or not population_values:
            continue
        percentile = bisect.bisect_right(population_values, current) / len(population_values)
        weight = abs(signed_weight)
        directed_percentile = percentile if signed_weight >= 0.0 else 1.0 - percentile
        components.append((directed_percentile, weight, key))
        direction = "positive" if signed_weight >= 0.0 else "inverse"
        rank_evidence.append(
            f"same_season_same_league_rank[{key}]={directed_percentile:.8f};"
            f"raw_percentile={percentile:.8f};direction={direction}"
        )
    total_weight = sum(weight for _percentile, weight, _key in components)
    if total_weight <= 0.0:
        return None
    score = sum(percentile * weight for percentile, weight, _key in components) / total_weight
    evidence_keys = tuple(
        dict.fromkeys(
            source_path
            for _percentile, _weight, key in components
            for source_path in _provenance_sources(key.lstrip("!"))
        )
    )
    return score, (*evidence_keys, *rank_evidence)


def _provenance_sources(key: str) -> tuple[str, ...]:
    if key.startswith("role."):
        return (
            key,
            "play_by_play.pg_percent",
            "play_by_play.sg_percent",
            "play_by_play.sf_percent",
            "play_by_play.pf_percent",
            "play_by_play.c_percent",
            "season_info.pos",
            "identity.pos",
        )
    derived_sources = {
        "derived.attempt_share": ("totals.fga", "team_stats_per_game.fga_per_game", "team_stats_per_game.g"),
        "derived.scoring_share": ("totals.pts", "team_stats_per_game.pts_per_game", "team_stats_per_game.g"),
        "derived.assist_share": ("totals.ast", "team_stats_per_game.ast_per_game", "team_stats_per_game.g"),
        "derived.assist_decision_efficiency": ("per_game.ast_per_game", "per_game.tov_per_game"),
        "derived.foul_pressure": ("advanced.f_tr", "totals.fta", "totals.fga", "per_game.fta_per_game"),
        "derived.three_attempt_rate": ("advanced.x3p_ar", "totals.x3pa", "totals.fga"),
        "derived.rim_attempt_rate": ("shooting.percent_fga_from_x0_3_range",),
        "derived.short_attempt_rate": ("shooting.percent_fga_from_x0_3_range", "shooting.percent_fga_from_x3_10_range"),
        "derived.three_to_ten_attempt_rate": ("shooting.percent_fga_from_x3_10_range",),
        "derived.mid_attempt_rate": ("shooting.percent_fga_from_x10_16_range", "shooting.percent_fga_from_x16_3p_range"),
        "derived.dunk_rate": ("shooting.num_of_dunks", "totals.fga"),
        "derived.bad_pass_per_game": ("play_by_play.bad_pass_turnover", "per_game.g"),
        "derived.lost_ball_per_game": ("play_by_play.lost_ball_turnover", "per_game.g"),
        "derived.shooting_foul_drawn_per_game": ("play_by_play.shooting_foul_drawn", "per_game.g"),
        "derived.assist_points_per_game": ("play_by_play.points_generated_by_assists", "per_game.g"),
        "derived.and1_per_game": ("play_by_play.and1", "per_game.g"),
        "derived.blocked_attempt_rate": ("play_by_play.fga_blocked", "totals.fga"),
        "derived.unassisted_two_rate": ("shooting.percent_assisted_x2p_fg",),
    }
    return derived_sources.get(key, (key,))


def _resolved(
    source_rule: str,
    value: float,
    evidence_keys: tuple[str, ...],
    recipe: _Recipe,
    *,
    tendency: bool,
) -> dict[str, Any]:
    low, high = (0, 100) if tendency else (25, 99)
    rounded = max(low, min(high, int(round(value))))
    provenance = (
        *evidence_keys,
        "population=same-season,same-league,GP>0",
        "pool_calibration=field-exact target distribution;765 GP-valid packages;identity=(run_id,player_index)",
        f"recipe={recipe.name}",
    )
    if recipe.unavailable:
        provenance += (
            f"unavailable_direct_source={recipe.unavailable}",
            f"substitute_source={recipe.substitute}",
            f"validity={recipe.why_valid}",
        )
    return {"value": rounded, "source_rule": source_rule, "evidence_keys": provenance}


def _derive(
    source_rule: str,
    field: str,
    evidence: Any,
    league_player_rows: Any,
    recipes: tuple[_Recipe, ...],
    *,
    tendency: bool = False,
) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    population = _population(evidence, league_player_rows)
    calibration = _TENDENCY_CALIBRATION[field] if tendency else _ATTRIBUTE_CALIBRATION[field]
    for recipe in recipes:
        if field == "OFFENSIVECONSISTENCY" and not tendency:
            ranked = _recipe_rank_score(evidence, population, recipe)
            if ranked is None:
                continue
            score, evidence_keys = ranked
            resolved_source_rule = (
                f"{source_rule}_field_specific_context_substitute"
                if recipe.unavailable
                else source_rule
            )
            provenance = (
                *evidence_keys,
                "population=same-season,same-league,GP>0",
                f"recipe={recipe.name}",
                f"rank_score={score:.8f}",
                "mapping=round(25+74*same_season_same_league_rank_score)",
            )
            if recipe.unavailable:
                provenance += (
                    f"unavailable_direct_source={recipe.unavailable}",
                    f"substitute_source={recipe.substitute}",
                    f"validity={recipe.why_valid}",
                )
            return {
                "value": max(25, min(99, int(round(25.0 + 74.0 * score)))),
                "source_rule": resolved_source_rule,
                "evidence_keys": provenance,
            }
        scored = _recipe_score(evidence, population, recipe)
        if scored is None:
            continue
        score, evidence_keys = scored
        center, scale = calibration
        value = center + score * scale
        value, absolute_evidence = _absolute_attribute_adjustment(field, evidence, value)
        resolved_source_rule = (
            f"{source_rule}_field_specific_context_substitute"
            if recipe.unavailable
            else source_rule
        )
        return _resolved(resolved_source_rule, value, (*evidence_keys, *absolute_evidence), recipe, tendency=tendency)
    return None


def _absolute_attribute_adjustment(field: str, evidence: Any, relative_value: float) -> tuple[float, tuple[str, ...]]:
    """Keep same-league rank extremes tied to an absolute basketball scale."""
    if field in {"BALLCONTROL", "PASSACCURACY", "PASSIQ", "PASSVISION"}:
        if not _recorded_assists_available(evidence):
            return relative_value, ()
        assists = _basic_value(evidence, "per_game.ast_per_game")
        if assists is None:
            return relative_value, ()
        decision = _derived_value(evidence, "assist_decision_efficiency")
        if field == "BALLCONTROL":
            touch = _basic_value(evidence, "per_game.ft_percent")
            absolute_value = 32.0 + 7.0 * assists
            if touch is not None:
                absolute_value += 25.0 * touch
        elif field == "PASSACCURACY":
            absolute_value = 34.0 + 8.5 * assists
            if decision is not None:
                absolute_value += 12.0 * (decision - 0.5)
        elif field == "PASSIQ":
            absolute_value = 34.0 + 8.0 * assists
            if decision is not None:
                absolute_value += 18.0 * (decision - 0.5)
        else:
            absolute_value = 30.0 + 9.0 * assists
        value = 0.35 * relative_value + 0.65 * absolute_value
        return value, (
            f"absolute_ast_per_game_anchor={assists:.6f}",
            "absolute_anchor_reason=low early AST/G cannot become modern-elite handling or passing from same-league rank/position alone",
        )

    center = _ATTRIBUTE_CALIBRATION.get(field, (relative_value, 0.0))[0]
    games = _gp(evidence)
    fga = _estimated_total(evidence, "fga")
    fta = _estimated_total(evidence, "fta")
    fg_percent = _basic_value(evidence, "per_game.fg_percent")
    ft_percent = _basic_value(evidence, "per_game.ft_percent")
    ts_percent = _basic_value(evidence, "advanced.ts_percent")
    fta_per_game = _basic_value(evidence, "per_game.fta_per_game")

    absolute_value: float | None = None
    reliability = 1.0
    anchor = ""
    if field == "DRAWFOUL" and fta_per_game is not None:
        reliability = games / (games + 20.0) if games is not None else 0.0
        absolute_value = 30.0 + 7.0 * fta_per_game
        anchor = f"30+7*FTA/G({fta_per_game:.6f})"
    elif field == "IQSHOT" and (ts_percent is not None or fg_percent is not None):
        execution = ts_percent if ts_percent is not None else fg_percent
        assert execution is not None
        reliability = fga / (fga + 100.0) if fga is not None else 0.0
        absolute_value = 25.0 + 100.0 * execution
        anchor = f"25+100*{'TS%' if ts_percent is not None else 'FG%'}({execution:.6f})"
    elif field in {"CLOSESHOT", "DRIVINGDUNK", "DRIVINGLAYUP", "POSTCONTROL", "POSTHOOK", "STANDINGDUNK"} and fg_percent is not None:
        slope = {
            "CLOSESHOT": 150.0,
            "DRIVINGDUNK": 110.0,
            "DRIVINGLAYUP": 140.0,
            "POSTCONTROL": 120.0,
            "POSTHOOK": 130.0,
            "STANDINGDUNK": 100.0,
        }[field]
        reliability = fga / (fga + 100.0) if fga is not None else 0.0
        absolute_value = 25.0 + slope * fg_percent
        anchor = f"25+{slope:.0f}*FG%({fg_percent:.6f})"
    elif field == "POSTFADE" and (ft_percent is not None or fg_percent is not None):
        touch = ft_percent if ft_percent is not None else fg_percent
        assert touch is not None
        exposure = fta if ft_percent is not None else fga
        reliability = exposure / (exposure + 40.0) if exposure is not None else 0.0
        absolute_value = 25.0 + 55.0 * touch
        anchor = f"25+55*{'FT%' if ft_percent is not None else 'FG%'}({touch:.6f})"

    if absolute_value is None:
        return relative_value, ()
    reliable_absolute = center + reliability * (absolute_value - center)
    value = 0.45 * relative_value + 0.55 * reliable_absolute
    return value, (
        f"absolute_field_anchor={anchor}",
        f"absolute_field_anchor_reliability={reliability:.8f}",
        "absolute_anchor_reason=era-relative rank is blended with continuous field-specific execution/load so low exposure cannot become modern elite",
    )


_ATTR_RECIPES: dict[str, tuple[_Recipe, ...]] = {
    "BALLCONTROL": (
        _Recipe("tracked_handle_security", (("!derived.lost_ball_per_game", 0.40), ("!advanced.tov_percent", 0.30), ("derived.unassisted_two_rate", 0.20), ("role.creator", 0.10))),
        _Recipe("recorded_handle_security", (("!advanced.tov_percent", 0.40), ("role.creator", 0.35), ("per_game.ft_percent", 0.25)), "lost-ball tracking and self-created-shot splits", "turnover restraint, continuous guard/wing participation, and weak free-throw touch", "AST is excluded; the remaining sources describe handle security and applicable on-ball responsibility"),
        _Recipe("unrecorded_assist_era_handle", (("role.creator", 0.55), ("derived.attempt_share", 0.25), ("per_game.ft_percent", 0.20)), "assists, lost-ball events, and player turnovers", "continuous primary/secondary creator-position participation plus observed shooting responsibility and touch", "the 1946-47 NBL research identifies guards as ball advancers; scoring responsibility distinguishes handling load without inventing AST zeroes"),
    ),
    "DRAWFOUL": (
        _Recipe("tracked_foul_creation", (("derived.shooting_foul_drawn_per_game", 0.50), ("derived.and1_per_game", 0.20), ("derived.foul_pressure", 0.30))),
        _Recipe("recorded_free_throw_pressure", (("derived.foul_pressure", 0.55), ("per_game.fta_per_game", 0.45)), "shooting-foul-drawn and and-one events", "recorded FTA/FGA pressure and FTA volume", "both are direct outcomes of forcing shooting fouls rather than shooting efficiency"),
    ),
    "OFFENSIVECONSISTENCY": (
        _Recipe("repeatable_scoring_load", (("per_36.pts_per_36_min", 0.35), ("derived.scoring_share", 0.30), ("advanced.ts_percent", 0.20), ("advanced.tov_percent", -0.15))),
        _Recipe("all_era_repeatable_scoring", (("per_game.pts_per_game", 0.35), ("derived.scoring_share", 0.35), ("advanced.ts_percent", 0.20), ("per_game.fg_percent", 0.10)), "game-log scoring variance and complete possession outcomes", "same-season scoring responsibility with bounded efficiency support", "load supplies most of the signal, so broad efficiency alone cannot create elite consistency"),
    ),
    "PASSACCURACY": (
        _Recipe("tracked_pass_completion_proxy", (("derived.assist_points_per_game", 0.35), ("!derived.bad_pass_per_game", 0.35), ("derived.assist_decision_efficiency", 0.30))),
        _Recipe("recorded_assist_accuracy", (("per_game.ast_per_game", 0.45), ("derived.assist_share", 0.30), ("advanced.tov_percent", -0.25)), "pass completion, placement, and bad-pass event tracking", "recorded assist outcomes and turnover restraint", "AST is used only for passing execution; low AST/G and low team-assist responsibility remain low"),
        _Recipe("unrecorded_assist_era_accuracy", (("role.creator", 0.55), ("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.15)), "assists and passing-error outcomes", "continuous ball-advancer position, shooting touch, and observed offensive responsibility", "research supports guard ball advancement; the weak touch/load terms avoid assigning modern-elite passing from position alone"),
    ),
    "PASSIQ": (
        _Recipe("tracked_pass_decisions", (("advanced.ast_percent", 0.35), ("derived.assist_decision_efficiency", 0.35), ("!derived.bad_pass_per_game", 0.30))),
        _Recipe("recorded_assist_decisions", (("derived.assist_share", 0.40), ("per_game.ast_per_game", 0.35), ("advanced.tov_percent", -0.25)), "potential assists, passing decisions, and bad-pass events", "recorded team-assist responsibility, AST/G, and turnover restraint", "the output remains passing-specific and cannot be raised by generic win shares or efficiency"),
        _Recipe("unrecorded_assist_era_pass_iq", (("role.creator", 0.60), ("derived.attempt_share", 0.20), ("per_game.ft_percent", 0.20)), "assists, player turnovers, and pass-decision events", "continuous researched ball-advancer role with weak responsibility/touch support", "no unrecorded zero is used and the target calibration keeps ordinary early guards below modern elite levels"),
    ),
    "PASSVISION": (
        _Recipe("tracked_creation_vision", (("derived.assist_points_per_game", 0.45), ("advanced.ast_percent", 0.35), ("!derived.bad_pass_per_game", 0.20))),
        _Recipe("recorded_creation_vision", (("derived.assist_share", 0.50), ("per_game.ast_per_game", 0.35), ("role.creator", 0.15)), "potential assists, pass targets, and points generated by assists", "observed assist responsibility and continuous creator-position participation", "the substitute measures seeing and completing scoring passes, not speed or athleticism"),
        _Recipe("unrecorded_assist_era_vision", (("role.creator", 0.65), ("derived.attempt_share", 0.20), ("per_game.ft_percent", 0.15)), "assists and chance-creation tracking", "continuous researched ball-advancer role with weak offensive responsibility/touch support", "position is not a hard archetype gate and cannot by itself reach elite output"),
    ),
    "IQSHOT": (
        _Recipe("tracked_shot_selection", (("advanced.ts_percent", 0.40), ("per_game.e_fg_percent", 0.25), ("!derived.blocked_attempt_rate", 0.20), ("!advanced.tov_percent", 0.15))),
        _Recipe("all_era_shot_selection", (("advanced.ts_percent", 0.50), ("per_game.fg_percent", 0.30), ("per_game.ft_percent", 0.20)), "shot-quality, blocked-attempt, and possession decision tracking", "recorded shooting efficiency with free-throw touch", "the narrower Shot-IQ calibration prevents broad efficiency from indiscriminately producing 97-99"),
    ),
    "CLOSESHOT": (
        _Recipe("location_close_execution", (("shooting.fg_percent_from_x0_3_range", 0.65), ("shooting.fg_percent_from_x3_10_range", 0.35))),
        _Recipe("historical_close_execution", (("per_game.fg_percent", 0.55), ("advanced.ts_percent", 0.25), ("role.interior", 0.20)), "0-3 and 3-10 foot make results", "overall make efficiency with continuous interior-position context", "field-goal execution is observed; position only allocates the otherwise unrecorded historical result toward close play"),
    ),
    "DRIVINGDUNK": (
        _Recipe("tracked_driving_finish", (("shooting.fg_percent_from_x0_3_range", 0.45), ("derived.and1_per_game", 0.20), ("!derived.blocked_attempt_rate", 0.20), ("derived.dunk_rate", 0.15))),
        _Recipe("historical_driving_finish", (("per_game.fg_percent", 0.40), ("advanced.f_tr", 0.25), ("role.interior", 0.20), ("identity.ht_in_in", 0.15)), "driving-dunk make, block, and and-one events", "recorded finishing efficiency, foul pressure, and continuous body/position context", "dunk execution requires finishing outcomes plus reach; body context never replaces observed efficiency"),
    ),
    "DRIVINGLAYUP": (
        _Recipe("tracked_driving_layup_finish", (("shooting.fg_percent_from_x0_3_range", 0.55), ("!derived.blocked_attempt_rate", 0.20), ("derived.and1_per_game", 0.15), ("derived.foul_pressure", 0.10))),
        _Recipe("historical_driving_layup_finish", (("per_game.fg_percent", 0.45), ("per_game.ft_percent", 0.20), ("derived.foul_pressure", 0.20), ("role.guard", 0.15)), "driving-layup make, block, and and-one events", "recorded finishing efficiency, touch, foul pressure, and continuous perimeter participation", "the substitute remains finishing-oriented and does not use attempt share as execution"),
    ),
    "MIDRANGE": (
        _Recipe("location_midrange_execution", (("shooting.fg_percent_from_x10_16_range", 0.55 / 0.90), ("shooting.fg_percent_from_x16_3p_range", 0.35 / 0.90))),
        _Recipe("historical_midrange_touch", (("per_game.ft_percent", 0.45), ("per_game.fg_percent", 0.35), ("role.wing", 0.20)), "10-16 and 16-foot-to-line make results", "free-throw touch, observed field-goal execution, and continuous perimeter/wing context", "free-throw accuracy is a stationary touch substitute, not an attempt-frequency or scoring-share signal"),
    ),
    "POSTCONTROL": (
        _Recipe("tracked_post_security", (("!derived.lost_ball_per_game", 0.35), ("!advanced.tov_percent", 0.30), ("derived.unassisted_two_rate", 0.15), ("role.post", 0.20))),
        _Recipe("historical_post_security", (("role.post", 0.45), ("per_game.fg_percent", 0.30), ("per_game.ft_percent", 0.15), ("identity.wt", 0.10)), "post touches, post turnovers, and move-success events", "continuous post-position/body participation with recorded scoring control and touch", "AST is excluded; size supplies context while scoring execution prevents a fixed big-man override"),
        _Recipe("unrecorded_assist_era_post_security", (("role.post", 0.55), ("per_game.fg_percent", 0.30), ("identity.wt", 0.15)), "post events, assists, and player turnovers", "continuous researched frontcourt role, body leverage, and observed scoring execution", "no missing assist value is converted to zero"),
    ),
    "POSTFADE": (
        _Recipe("location_post_fade_execution", (("shooting.fg_percent_from_x10_16_range", 0.45), ("shooting.fg_percent_from_x3_10_range", 0.30), ("per_game.ft_percent", 0.15), ("role.post", 0.10))),
        _Recipe("historical_post_fade_touch", (("per_game.ft_percent", 0.40), ("per_game.fg_percent", 0.30), ("role.post", 0.20), ("identity.ht_in_in", 0.10)), "post-fade make results", "shooting touch and continuous post/body context", "fade execution needs touch; post context only distinguishes the missing historical shot type"),
    ),
    "POSTHOOK": (
        _Recipe("location_post_hook_execution", (("shooting.fg_percent_from_x3_10_range", 0.45), ("shooting.fg_percent_from_x0_3_range", 0.30), ("role.post", 0.15), ("identity.ht_in_in", 0.10))),
        _Recipe("historical_post_hook_finish", (("per_game.fg_percent", 0.45), ("role.post", 0.30), ("identity.ht_in_in", 0.15), ("per_game.ft_percent", 0.10)), "post-hook make results", "observed finishing with continuous post/reach context", "hook range and reach differ from fade touch, keeping the two post skills semantically separate"),
    ),
}


_TENDENCY_RECIPES: dict[str, tuple[_Recipe, ...]] = {
    "TRIPLETHREATIDLE": (_Recipe("triple_threat_hold", (("derived.attempt_share", 0.45), ("role.wing", 0.30), ("role.post", 0.25)), "triple-threat state events", "observed shooting responsibility and continuous wing/post participation", "triple-threat states occur before perimeter or post scoring decisions"),),
    "TRIPLETHREATJAB": (_Recipe("triple_threat_jab", (("derived.mid_attempt_rate", 0.40), ("derived.attempt_share", 0.35), ("role.wing", 0.25)), "jab-step events", "midrange attempt location, shooting responsibility, and wing participation", "jab steps are shot-creation behavior, not make efficiency"), _Recipe("historical_triple_threat_jab", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "jab-step and location events", "shooting responsibility and continuous wing participation", "the substitute varies with observed role and never becomes an execution rating")),
    "TRIPLETHREATPUMPFake": (_Recipe("triple_threat_pump", (("derived.short_attempt_rate", 0.35), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10)), "pump-fake events", "short-shot frequency, foul pressure, and shooting responsibility", "pump fakes are attempt/behavior signals"), _Recipe("historical_triple_threat_pump", (("derived.foul_pressure", 0.45), ("derived.attempt_share", 0.35), ("role.post", 0.20)), "pump-fake and location events", "recorded foul pressure and offensive responsibility", "the substitute is behavior-oriented rather than efficiency-oriented")),
    "TRIPLETHREATSHOT": (_Recipe("triple_threat_shoot", (("derived.mid_attempt_rate", 0.35), ("derived.three_attempt_rate", 0.30), ("derived.attempt_share", 0.35)), "triple-threat shot events", "recorded jump-shot location and shooting responsibility", "all inputs describe attempt selection"), _Recipe("historical_triple_threat_shoot", (("derived.attempt_share", 0.70), ("role.wing", 0.30)), "triple-threat and shot-location events", "shooting responsibility and continuous perimeter participation", "the substitute does not use make efficiency")),
    "SETUPDRIBBLE": (_Recipe("no_setup_dribble", (("!role.creator", 0.55), ("role.post", 0.25), ("!derived.unassisted_two_rate", 0.20)), "setup-dribble events", "inverse creation responsibility and assisted/post role", "players who do not self-create are more likely to attack without extended setup"), _Recipe("historical_no_setup_dribble", (("!role.creator", 0.65), ("role.post", 0.35)), "setup-dribble and assisted-shot events", "continuous position responsibility", "this is a role tendency, not a hard archetype gate")),
    "SETUPWITHHESITATION": (_Recipe("setup_hesitation", (("role.creator", 0.35), ("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.15)), "hesitation events", "self-creation, live-dribble exposure, and drive pressure", "AST is excluded and all inputs identify on-ball setup behavior"), _Recipe("historical_setup_hesitation", (("role.creator", 0.55), ("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20)), "hesitation and self-created-shot events", "continuous creator role, drive pressure, and observed shooting responsibility", "no AST signal authors this move tendency")),
    "SETUPWITHSIZEUP": (_Recipe("setup_sizeup", (("role.creator", 0.40), ("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.10)), "size-up events", "on-ball creation, self-created attempts, and live-dribble exposure", "AST is excluded; turnover exposure is behavior rather than execution"), _Recipe("historical_setup_sizeup", (("role.creator", 0.60), ("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20)), "size-up and self-created-shot events", "continuous creator role, drive pressure, and observed responsibility", "no AST signal or fixed guard template is used")),
    "DRIVE": (_Recipe("drive_frequency", (("derived.rim_attempt_rate", 0.35), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.20), ("derived.attempt_share", 0.20)), "drive events", "rim attempts, foul pressure, self-creation, and attempt responsibility", "each input measures drive selection or opportunity, never finishing efficiency"), _Recipe("historical_drive_frequency", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.35), ("role.creator", 0.30)), "drive, rim-location, and assisted-shot events", "foul pressure, attempt responsibility, and continuous creator role", "the all-era substitute remains frequency/behavior evidence")),
    "DRIVERIGHT": (_Recipe("drive_right_without_laterality", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.25), ("role.creator", 0.25)), "left/right drive direction", "overall recorded drive participation", "public season data has no handed drive split; package-calibrated drive participation is the narrowest non-identity substitute and laterality remains uncertain"), _Recipe("historical_drive_right_without_laterality", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.35), ("role.creator", 0.30)), "drive direction and drive events", "observed drive pressure and continuous creator responsibility", "this resolves activity but cannot claim observed handedness")),
    "DRIVINGCROSSOVER": (_Recipe("driving_crossover", (("role.creator", 0.30), ("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.20)), "crossover events", "self-creation, live-dribble exposure, and drive pressure", "AST is excluded and the sources describe applicable on-ball behavior"), _Recipe("historical_driving_crossover", (("role.creator", 0.55), ("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20)), "crossover and self-created-shot events", "continuous creator role, drive pressure, and offensive responsibility", "the substitute avoids AST and fixed move ratings")),
    "DRIVINGDOUBLECROSSOVER": (_Recipe("driving_double_crossover", (("role.creator", 0.35), ("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.15)), "double-crossover events", "extended live-dribble creation and drive pressure", "lost-ball exposure differentiates a longer move from a basic crossover"), _Recipe("historical_driving_double_crossover", (("role.creator", 0.60), ("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20)), "double-crossover and live-dribble events", "continuous creator role, drive pressure, and observed responsibility", "AST is excluded and the lower field-exact calibration keeps this rarer move distinct")),
    "DRIVINGSPIN": (_Recipe("driving_spin", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.20)), "spin-move events", "short-area self-creation and drive pressure", "spin usage is a behavior signal"), _Recipe("historical_driving_spin", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.30), ("role.creator", 0.20), ("role.post", 0.15)), "spin-move and location events", "drive pressure and continuous perimeter/post creation", "both perimeter and post players can spin without a hard position gate")),
    "DRIVINGHALFSPIN": (_Recipe("driving_half_spin", (("role.creator", 0.30), ("derived.short_attempt_rate", 0.25), ("derived.unassisted_two_rate", 0.25), ("derived.lost_ball_per_game", 0.20)), "half-spin events", "live-dribble self-creation and short-area activity", "the field-exact calibration separates it from full-spin frequency"), _Recipe("historical_driving_half_spin", (("role.creator", 0.45), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25)), "half-spin and live-dribble events", "creator responsibility and drive pressure", "no generic constant is used")),
    "DRIVINGSTEPBACK": (_Recipe("driving_stepback", (("derived.mid_attempt_rate", 0.30), ("derived.three_attempt_rate", 0.20), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.25)), "driving-stepback events", "pull-up location and self-creation", "stepbacks are attempt behavior, not shot efficiency"), _Recipe("historical_driving_stepback", (("derived.attempt_share", 0.35), ("role.creator", 0.35), ("per_game.ft_percent", 0.30)), "stepback and pull-up events", "creator responsibility, shooting load, and weak touch context", "touch only distinguishes plausible pull-up behavior when locations are absent")),
    "DRIVINGBEHINDTHEBACK": (_Recipe("driving_behind_back", (("role.creator", 0.35), ("derived.unassisted_two_rate", 0.25), ("derived.foul_pressure", 0.20), ("derived.lost_ball_per_game", 0.20)), "behind-the-back events", "extended creator possession, drive pressure, and self-created attempts", "AST is excluded; live-dribble exposure is field-specific behavior evidence"), _Recipe("historical_driving_behind_back", (("role.creator", 0.60), ("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20)), "behind-the-back and live-dribble events", "continuous creator role, drive pressure, and offensive responsibility", "the substitute excludes AST and named-player templates")),
    "DRIVINGDRIBBLEHESITATION": (_Recipe("driving_hesitation", (("role.creator", 0.30), ("derived.unassisted_two_rate", 0.25), ("derived.foul_pressure", 0.25), ("derived.lost_ball_per_game", 0.20)), "driving-hesitation events", "self-created drive pressure and live-dribble exposure", "AST is excluded and all inputs describe on-ball behavior"), _Recipe("historical_driving_hesitation", (("role.creator", 0.50), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.20)), "driving-hesitation and self-created-shot events", "continuous creator responsibility and foul pressure", "no AST signal authors the tendency")),
    "DRIVINGINANDOUT": (_Recipe("driving_in_out", (("role.creator", 0.30), ("derived.unassisted_two_rate", 0.30), ("derived.foul_pressure", 0.20), ("derived.lost_ball_per_game", 0.20)), "in-and-out events", "live-dribble self-creation and drive pressure", "the input family is behavior-specific"), _Recipe("historical_driving_in_out", (("role.creator", 0.55), ("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20)), "in-and-out and self-created-shot events", "continuous creator role, drive pressure, and offensive responsibility", "AST is excluded and no move constant is inserted")),
    "NODRIVINGDRIBBLEMOVE": (_Recipe("no_driving_move", (("!role.creator", 0.35), ("!derived.unassisted_two_rate", 0.30), ("!derived.foul_pressure", 0.20), ("role.post", 0.15)), "no-move drive events", "inverse self-creation and drive pressure with post role", "this is the semantic inverse of move-based creation"), _Recipe("historical_no_driving_move", (("!role.creator", 0.55), ("!derived.attempt_share", 0.25), ("role.post", 0.20)), "drive-move and assisted-shot events", "inverse creator responsibility and continuous post role", "the field remains coupled coherently to the other driving tendencies")),
    "ATTACKSTRONGONDRIVE": (_Recipe("attack_strong_drive", (("derived.foul_pressure", 0.35), ("derived.rim_attempt_rate", 0.30), ("derived.attempt_share", 0.20), ("identity.wt", 0.15)), "strong-drive events", "rim pressure, foul creation, responsibility, and body leverage", "inputs measure physical drive behavior, not finishing skill"), _Recipe("historical_attack_strong_drive", (("derived.foul_pressure", 0.45), ("derived.attempt_share", 0.30), ("identity.wt", 0.25)), "strong-drive and rim events", "foul pressure, responsibility, and body leverage", "the substitute is continuous across positions")),
    "OFFSCREENDRIVE": (_Recipe("off_screen_drive", (("derived.rim_attempt_rate", 0.30), ("derived.attempt_share", 0.25), ("derived.unassisted_two_rate", -0.20), ("role.wing", 0.25)), "off-screen drive events", "rim frequency, scoring responsibility, assisted context, and wing participation", "off-screen actions differ from primary isolation creation"), _Recipe("historical_off_screen_drive", (("derived.attempt_share", 0.45), ("role.wing", 0.35), ("role.creator", -0.20)), "off-screen and assisted-shot events", "wing scoring responsibility with reduced primary-creator weight", "the substitute remains role/behavior evidence")),
    "SPOTUPDRIVE": (_Recipe("spot_up_drive", (("derived.rim_attempt_rate", 0.30), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", -0.20), ("role.wing", 0.25)), "spot-up drive events", "rim/foul pressure from a non-primary-creation wing context", "spot-up drives are behavior frequency"), _Recipe("historical_spot_up_drive", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.35), ("role.wing", 0.30)), "spot-up and assisted-shot events", "drive pressure and wing scoring responsibility", "no execution percentage is mapped directly")),
    "ALLEYOOOPASS": (_Recipe("alley_oop_pass_behavior", (("role.creator", 0.40), ("!derived.bad_pass_per_game", 0.25), ("derived.foul_pressure", 0.20), ("role.big", -0.15)), "alley-oop pass events", "continuous passer role, pass security, and rim-pressure context", "AST is excluded; the low-frequency field calibration prevents role alone from creating elite output"), _Recipe("historical_alley_oop_pass", (("role.creator", 0.70), ("derived.foul_pressure", 0.30)), "alley-oop and pass-target events", "continuous researched ball-advancer role and rim pressure", "AST is excluded and the output remains uncertain where pass events are absent")),
    "DISHTOOPENMAN": (_Recipe("dish_open_man_behavior", (("role.creator", 0.45), ("!derived.bad_pass_per_game", 0.35), ("!advanced.tov_percent", 0.20)), "pass-target openness events", "continuous passer role and pass/possession security", "AST is excluded; the sources concern willingness and decision behavior"), _Recipe("historical_dish_open_man", (("role.creator", 0.70), ("per_game.ft_percent", 0.20), ("derived.foul_pressure", 0.10)), "open-target pass events", "continuous ball-advancer role with weak touch/pressure context", "no missing or low AST value is transformed into elite output")),
    "FLASHYPASS": (_Recipe("flashy_pass_behavior", (("role.creator", 0.45), ("derived.bad_pass_per_game", 0.30), ("derived.lost_ball_per_game", 0.15), ("derived.foul_pressure", 0.10)), "flashy-pass events", "continuous creator role and higher-risk live-ball exposure", "AST is excluded; bad-pass exposure differentiates flair frequency from accuracy"), _Recipe("historical_flashy_pass", (("role.creator", 0.75), ("derived.foul_pressure", 0.25)), "flashy-pass and pass-event tracking", "continuous researched ball-advancer role and live-ball pressure", "the low calibration and no named-player template keep ordinary passers low")),
    "POSTUP": (_Recipe("post_up_frequency", (("role.post", 0.40), ("derived.short_attempt_rate", 0.30), ("derived.attempt_share", 0.20), ("identity.wt", 0.10)), "post-up events", "continuous post position/body context and short-shot responsibility", "all terms describe post opportunity and frequency"), _Recipe("historical_post_up_frequency", (("role.post", 0.50), ("derived.attempt_share", 0.30), ("identity.wt", 0.20)), "post-up and shot-location events", "continuous post role, responsibility, and body leverage", "the substitute is not a fixed big-man band")),
    "POSTBACKDOWN": (_Recipe("post_backdown", (("role.post", 0.35), ("identity.wt", 0.25), ("derived.short_attempt_rate", 0.20), ("derived.attempt_share", 0.20)), "backdown events", "post role, leverage, short attempts, and responsibility", "the tendency is behavior/frequency"), _Recipe("historical_post_backdown", (("role.post", 0.50), ("identity.wt", 0.30), ("derived.attempt_share", 0.20)), "backdown and post-touch events", "continuous post role and leverage", "no hard size threshold is used")),
    "POSTAGGRESSIVEBACKDOWN": (_Recipe("post_aggressive_backdown", (("identity.wt", 0.30), ("derived.foul_pressure", 0.25), ("role.post", 0.25), ("derived.short_attempt_rate", 0.20)), "aggressive-backdown events", "leverage, foul pressure, and post frequency", "the terms distinguish forceful behavior from ordinary backdowns"), _Recipe("historical_post_aggressive_backdown", (("identity.wt", 0.35), ("derived.foul_pressure", 0.30), ("role.post", 0.35)), "aggressive-backdown and post-touch events", "continuous leverage, foul pressure, and post role", "no arbitrary weight gate is used")),
    "POSTFACEUP": (_Recipe("post_face_up", (("role.wing", 0.25), ("role.post", 0.25), ("derived.mid_attempt_rate", 0.30), ("per_game.ft_percent", 0.20)), "post-face-up events", "hybrid wing/post role and midrange attempt behavior", "face-up play differs from backdown play through perimeter touch/location"), _Recipe("historical_post_face_up", (("role.wing", 0.30), ("role.post", 0.30), ("per_game.ft_percent", 0.25), ("derived.attempt_share", 0.15)), "face-up and midrange events", "hybrid role, touch, and responsibility", "the substitute remains continuous across secondary positions")),
    "POSTSPIN": (_Recipe("post_spin", (("role.post", 0.30), ("derived.short_attempt_rate", 0.25), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.20)), "post-spin events", "post self-creation and short-area pressure", "all terms identify move frequency"), _Recipe("historical_post_spin", (("role.post", 0.45), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25)), "post-spin and post-touch events", "post role, foul pressure, and responsibility", "the low target calibration preserves move rarity")),
    "POSTDRIVE": (_Recipe("post_drive", (("role.post", 0.25), ("derived.foul_pressure", 0.30), ("derived.rim_attempt_rate", 0.25), ("derived.unassisted_two_rate", 0.20)), "post-drive events", "post role with rim/foul self-creation", "the tendency is separated from post-spin and face-up execution"), _Recipe("historical_post_drive", (("role.post", 0.35), ("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.30)), "post-drive and rim events", "post role, drive pressure, and responsibility", "no finishing percentage is used as frequency")),
    "POSTHOPSHOT": (_Recipe("post_hop_shot", (("role.post", 0.25), ("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15)), "post-hop-shot events", "post self-created midrange attempt behavior", "field-exact low-frequency calibration keeps the move rare"), _Recipe("historical_post_hop_shot", (("role.post", 0.40), ("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.30)), "post-hop and midrange events", "post role, touch, and offensive responsibility", "the substitute does not infer make execution")),
}

_TENDENCY_CALIBRATION.update(
    {
        "POSTHOPSTEP": (9.0, 11.9),
        "3POINTCENTERLEFTSHOT": (0.0, 11.6),
        "3POINTCENTERRIGHTSHOT": (0.0, 15.6),
        "3POINTCENTERSHOT": (0.0, 18.5),
        "3POINTLEFTSHOT": (0.0, 8.9),
        "3POINTOFFSCREENSHOT": (0.0, 15.0),
        "3POINTRIGHTSHOT": (0.0, 14.8),
        "3POINTSPOTUPSHOT": (0.0, 23.0),
        "ALLEYOOP": (14.0, 17.0),
        "BASKETUNDERSHOT": (89.0, 35.6),
        "CENTERLEFTMIDSHOT": (17.0, 7.4),
        "CENTERMIDRIGHTSHOT": (18.0, 6.7),
        "CENTERMIDSHOT": (18.0, 8.2),
        "CLOSELEFTSHOT": (23.0, 14.1),
        "CLOSEMIDDLESHOT": (28.0, 17.8),
        "CLOSERIGHTSHOT": (24.0, 14.1),
        "CONTESTEDJUMPER3POINT": (0.0, 8.0),
        "CONTESTEDJUMPERMID": (15.0, 12.6),
        "CONTESTEDJUMPERMIDRANGE": (15.0, 12.6),
        "DRIVEPULLUP3POINT": (0.0, 7.0),
        "DRIVEPULLUPMID": (11.0, 7.4),
        "DRIVEPULLUPMIDRANGE": (11.0, 7.4),
        "DRIVINGDUNK": (20.0, 22.2),
        "DRIVINGLAYUP": (49.0, 20.0),
        "EUROSTEPLAYUP": (19.0, 11.9),
        "FLASHYDUNK": (8.0, 17.0),
        "FLOATER": (35.0, 17.8),
        "FROMPOSTSHOT": (32.0, 18.5),
        "HOPPOSTSHOT": (1.0, 4.4),
        "HOPSTEPLAYUP": (25.0, 16.3),
        "LEFTMIDSHOT": (19.0, 6.7),
        "MIDOFFSCREENSHOT": (32.0, 17.8),
        "MIDRIGHTSHOT": (18.0, 6.7),
        "MIDSPOTUPSHOT": (45.0, 16.3),
        "POSTDROPSTEP": (9.0, 11.9),
        "POSTFADELEFT": (12.0, 11.9),
        "POSTFADERIGHT": (11.0, 11.9),
        "POSTHOOKLEFT": (9.0, 12.6),
        "POSTHOOKRIGHT": (14.0, 13.3),
        "POSTSHIMMYSHOT": (9.0, 8.2),
        "POSTSTEPBACKSHOT": (1.0, 6.7),
        "POSTUPANDUNDER": (20.0, 12.6),
        "SPINJUMPER": (16.0, 10.4),
        "SPINLAYUP": (30.0, 17.8),
        "STANDINGDUNK": (22.0, 21.5),
        "STEPBACKJUMPER3POINT": (0.0, 6.0),
        "STEPBACKJUMPERMID": (13.0, 8.2),
        "STEPBACKJUMPERMIDRANGE": (13.0, 8.2),
        "STEPTHROUGH": (15.0, 12.6),
        "TRANSITIONPULLUP3POINT": (0.0, 5.0),
        "USEGLASS": (14.0, 14.8),
    }
)

_TENDENCY_RECIPES.update(
    {
        "POSTHOPSTEP": (_Recipe("post_hop_step_alias", (("role.post", 0.35), ("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.20), ("identity.wt", 0.15)), "post-hop-step events and a captured field-exact target", "post/drop-step context plus the captured Post Drop Step output distribution", "this live alias has no separate Pool label; source behavior is kept distinct from the hop-shot tendency"),),
        "3POINTCENTERLEFTSHOT": (_Recipe("center_left_three_location", (("derived.three_attempt_rate", 0.65), ("shooting.percent_corner_3s_of_3pa", -0.35)), "left-center three location events", "non-corner three-attempt share", "the source separates center from corner mass but not left from right; laterality remains uncertain"),),
        "3POINTCENTERRIGHTSHOT": (_Recipe("center_right_three_location", (("derived.three_attempt_rate", 0.65), ("shooting.percent_corner_3s_of_3pa", -0.35)), "right-center three location events", "non-corner three-attempt share", "the source separates center from corner mass but not left from right; laterality remains uncertain"),),
        "3POINTCENTERSHOT": (_Recipe("center_three_location", (("derived.three_attempt_rate", 0.60), ("shooting.percent_corner_3s_of_3pa", -0.40)), "center three location events", "recorded non-corner three-attempt share", "center mass is the complement of recorded corner share"),),
        "3POINTLEFTSHOT": (_Recipe("left_corner_three_location", (("derived.three_attempt_rate", 0.55), ("shooting.percent_corner_3s_of_3pa", 0.45)), "left-corner three events", "recorded corner share and total three-attempt rate", "public data has no left/right split; corner frequency is direct and laterality remains uncertain"),),
        "3POINTRIGHTSHOT": (_Recipe("right_corner_three_location", (("derived.three_attempt_rate", 0.55), ("shooting.percent_corner_3s_of_3pa", 0.45)), "right-corner three events", "recorded corner share and total three-attempt rate", "public data has no left/right split; corner frequency is direct and laterality remains uncertain"),),
        "3POINTOFFSCREENSHOT": (_Recipe("off_screen_three", (("derived.three_attempt_rate", 0.35), ("shooting.percent_assisted_x3p_fg", 0.35), ("role.wing", 0.20), ("role.creator", -0.10)), "off-screen three events", "three frequency, assisted-three context, and off-ball wing role", "the substitute distinguishes off-ball shooting from pull-up creation"),),
        "3POINTSPOTUPSHOT": (_Recipe("spot_up_three", (("derived.three_attempt_rate", 0.40), ("shooting.percent_assisted_x3p_fg", 0.40), ("role.creator", -0.20)), "spot-up three events", "three frequency and assisted-three context with reduced primary creation", "the inputs describe catch-and-shoot opportunity rather than execution"),),
        "ALLEYOOP": (_Recipe("alley_oop_finish", (("derived.dunk_rate", 0.45), ("role.interior", 0.30), ("derived.rim_attempt_rate", 0.25)), "alley-oop finish events", "dunk frequency, rim location, and interior role", "the target is finish selection, not dunk execution"), _Recipe("historical_alley_oop_finish", (("role.interior", 0.55), ("derived.attempt_share", 0.25), ("identity.ht_in_in", 0.20)), "alley-oop, dunk, and rim events", "continuous interior/reach context and offensive responsibility", "the low field calibration prevents a fixed big-man tendency")),
        "BASKETUNDERSHOT": (_Recipe("under_basket_attempt", (("derived.rim_attempt_rate", 0.55), ("role.interior", 0.35), ("derived.attempt_share", 0.10)), "under-basket events", "recorded rim frequency and continuous interior participation", "the source is location/frequency evidence"), _Recipe("historical_under_basket_attempt", (("role.interior", 0.55), ("derived.attempt_share", 0.30), ("identity.ht_in_in", 0.15)), "under-basket and rim-location events", "continuous interior/reach context and attempt responsibility", "no hard height or position gate is used")),
        "CENTERLEFTMIDSHOT": (_Recipe("center_left_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.25)), "left-center midrange events", "recorded midrange share and wing participation", "public data has no left/right split; lateral uncertainty is explicit"), _Recipe("historical_center_left_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "midrange and directional events", "shooting responsibility and continuous wing role", "the output remains a tendency")),
        "CENTERMIDRIGHTSHOT": (_Recipe("center_right_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.25)), "right-center midrange events", "recorded midrange share and wing participation", "public data has no left/right split; lateral uncertainty is explicit"), _Recipe("historical_center_right_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "midrange and directional events", "shooting responsibility and continuous wing role", "the output remains a tendency")),
        "CENTERMIDSHOT": (_Recipe("center_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.25)), "center-mid events", "recorded midrange share and wing participation", "the source captures range though not exact court coordinates"), _Recipe("historical_center_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "midrange location events", "shooting responsibility and continuous wing role", "no make percentage authors frequency")),
        "LEFTMIDSHOT": (_Recipe("left_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.25)), "left-mid events", "recorded midrange share and wing participation", "public data has no laterality split"), _Recipe("historical_left_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "midrange and directional events", "shooting responsibility and continuous wing role", "laterality remains uncertain")),
        "MIDRIGHTSHOT": (_Recipe("right_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.25)), "right-mid events", "recorded midrange share and wing participation", "public data has no laterality split"), _Recipe("historical_right_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.45)), "midrange and directional events", "shooting responsibility and continuous wing role", "laterality remains uncertain")),
        "CLOSELEFTSHOT": (_Recipe("left_close_location", (("derived.short_attempt_rate", 0.75), ("role.interior", 0.25)), "left-close events", "recorded short-shot share and interior participation", "public data has no left/right split"), _Recipe("historical_left_close", (("derived.attempt_share", 0.50), ("role.interior", 0.50)), "close-location events", "shooting responsibility and continuous interior role", "laterality remains uncertain")),
        "CLOSEMIDDLESHOT": (_Recipe("middle_close_location", (("derived.rim_attempt_rate", 0.65), ("role.interior", 0.35)), "middle-close events", "recorded rim share and interior participation", "central rim opportunity is the closest available location evidence"), _Recipe("historical_middle_close", (("role.interior", 0.55), ("derived.attempt_share", 0.45)), "close-location events", "continuous interior role and shooting responsibility", "no efficiency value authors frequency")),
        "CLOSERIGHTSHOT": (_Recipe("right_close_location", (("derived.short_attempt_rate", 0.75), ("role.interior", 0.25)), "right-close events", "recorded short-shot share and interior participation", "public data has no left/right split"), _Recipe("historical_right_close", (("derived.attempt_share", 0.50), ("role.interior", 0.50)), "close-location events", "shooting responsibility and continuous interior role", "laterality remains uncertain")),
        "CONTESTEDJUMPER3POINT": (_Recipe("contested_three", (("derived.three_attempt_rate", 0.35), ("shooting.percent_assisted_x3p_fg", -0.25), ("role.creator", 0.25), ("derived.attempt_share", 0.15)), "contested-three events", "three volume, self-created context, and shooting responsibility", "self-created high-volume threes are the narrowest season-level contested-shot substitute"),),
        "DRIVEPULLUP3POINT": (_Recipe("drive_pullup_three", (("derived.three_attempt_rate", 0.30), ("shooting.percent_assisted_x3p_fg", -0.30), ("role.creator", 0.25), ("derived.foul_pressure", 0.15)), "pull-up-three events", "unassisted three context and live-dribble creator pressure", "the substitute separates pull-ups from spot-ups"),),
        "DRIVINGDUNK": (_Recipe("driving_dunk_frequency", (("derived.dunk_rate", 0.50), ("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.15), ("role.creator", 0.10)), "driving-dunk attempt events", "dunk/rim frequency and drive pressure", "makes count as observed action frequency here, never execution"), _Recipe("historical_driving_dunk_frequency", (("derived.foul_pressure", 0.35), ("role.interior", 0.30), ("derived.attempt_share", 0.20), ("identity.ht_in_in", 0.15)), "driving-dunk and rim events", "drive pressure, continuous role/reach, and attempt responsibility", "no fixed athlete template is used")),
        "DRIVINGLAYUP": (_Recipe("driving_layup_frequency", (("derived.rim_attempt_rate", 0.45), ("derived.foul_pressure", 0.25), ("derived.dunk_rate", -0.15), ("role.creator", 0.15)), "driving-layup events", "rim pressure excluding dunk share plus creator role", "the sources describe action selection"), _Recipe("historical_driving_layup_frequency", (("derived.foul_pressure", 0.40), ("role.creator", 0.30), ("derived.attempt_share", 0.30)), "driving-layup and rim events", "drive pressure and offensive responsibility", "no make efficiency authors frequency")),
        "EUROSTEPLAYUP": (_Recipe("euro_step_frequency", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.20)), "Euro-step events", "self-created rim/foul pressure", "the field-exact low-frequency calibration distinguishes the move"), _Recipe("historical_euro_step", (("derived.foul_pressure", 0.40), ("role.creator", 0.35), ("derived.attempt_share", 0.25)), "Euro-step and drive events", "drive pressure and creator responsibility", "no constant move package is inserted")),
        "FLASHYDUNK": (_Recipe("flashy_dunk_frequency", (("derived.dunk_rate", 0.45), ("role.creator", 0.20), ("identity.ht_in_in", 0.20), ("derived.foul_pressure", 0.15)), "flashy-dunk events", "dunk frequency with live-drive/reach context", "the target is behavior frequency"), _Recipe("historical_flashy_dunk", (("role.interior", 0.35), ("role.creator", 0.25), ("identity.ht_in_in", 0.20), ("derived.attempt_share", 0.20)), "flashy-dunk and dunk events", "continuous reach/role and responsibility", "the low calibration prevents body context from creating a fixed high value")),
        "FLOATER": (_Recipe("floater_frequency", (("derived.three_to_ten_attempt_rate", 0.55), ("role.guard", 0.25), ("derived.unassisted_two_rate", 0.20)), "floater events", "3-10 foot attempt share and self-created guard context", "3-10 feet is valid for floaters, not layup moves"), _Recipe("historical_floater", (("role.guard", 0.40), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.30)), "floater and 3-10 foot events", "continuous guard drive pressure and responsibility", "the substitute stays distinct from layup execution")),
        "FROMPOSTSHOT": (_Recipe("shoot_from_post", (("role.post", 0.35), ("derived.short_attempt_rate", 0.25), ("derived.mid_attempt_rate", 0.25), ("derived.attempt_share", 0.15)), "post-shot events", "post role and recorded short/mid attempt mass", "the target is post shot selection"), _Recipe("historical_shoot_from_post", (("role.post", 0.50), ("derived.attempt_share", 0.30), ("identity.wt", 0.20)), "post-shot and location events", "continuous post role, responsibility, and leverage", "no efficiency score authors the tendency")),
        "HOPPOSTSHOT": (_Recipe("hop_post_shot", (("role.post", 0.30), ("derived.mid_attempt_rate", 0.30), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15)), "post-hop-shot events", "self-created post/midrange behavior", "the exact low-frequency target keeps the move rare"), _Recipe("historical_hop_post_shot", (("role.post", 0.45), ("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.25)), "post-hop and location events", "post role, touch, and responsibility", "no generic constant is used")),
        "HOPSTEPLAYUP": (_Recipe("hop_step_layup", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.20)), "hop-step layup events", "self-created rim/foul pressure", "3-10 foot attempts are deliberately excluded"), _Recipe("historical_hop_step_layup", (("derived.foul_pressure", 0.40), ("role.creator", 0.35), ("derived.attempt_share", 0.25)), "hop-step and drive events", "drive pressure and creator responsibility", "the field remains a behavior tendency")),
        "POSTDROPSTEP": (_Recipe("post_drop_step", (("role.post", 0.35), ("derived.short_attempt_rate", 0.30), ("identity.wt", 0.20), ("derived.foul_pressure", 0.15)), "drop-step events", "post role, short frequency, leverage, and foul pressure", "all inputs describe move opportunity"), _Recipe("historical_post_drop_step", (("role.post", 0.45), ("identity.wt", 0.30), ("derived.attempt_share", 0.25)), "drop-step and post-touch events", "continuous post role, leverage, and responsibility", "no hard big-man gate is used")),
        "POSTFADELEFT": (_Recipe("post_fade_left", (("role.post", 0.30), ("derived.mid_attempt_rate", 0.35), ("per_game.ft_percent", 0.20), ("derived.unassisted_two_rate", 0.15)), "left post-fade events", "post self-created midrange touch", "public data has no left/right split; laterality remains uncertain"), _Recipe("historical_post_fade_left", (("role.post", 0.40), ("per_game.ft_percent", 0.35), ("derived.attempt_share", 0.25)), "post-fade and directional events", "post role, touch, and responsibility", "laterality is not fabricated")),
        "POSTFADERIGHT": (_Recipe("post_fade_right", (("role.post", 0.30), ("derived.mid_attempt_rate", 0.35), ("per_game.ft_percent", 0.20), ("derived.unassisted_two_rate", 0.15)), "right post-fade events", "post self-created midrange touch", "public data has no left/right split; laterality remains uncertain"), _Recipe("historical_post_fade_right", (("role.post", 0.40), ("per_game.ft_percent", 0.35), ("derived.attempt_share", 0.25)), "post-fade and directional events", "post role, touch, and responsibility", "laterality is not fabricated")),
        "POSTHOOKLEFT": (_Recipe("post_hook_left", (("role.post", 0.35), ("derived.three_to_ten_attempt_rate", 0.35), ("identity.ht_in_in", 0.15), ("derived.unassisted_two_rate", 0.15)), "left post-hook events", "post short-area self-creation and reach", "public data has no left/right split"), _Recipe("historical_post_hook_left", (("role.post", 0.45), ("identity.ht_in_in", 0.25), ("derived.attempt_share", 0.30)), "post-hook and directional events", "post role, reach, and responsibility", "laterality remains uncertain")),
        "POSTHOOKRIGHT": (_Recipe("post_hook_right", (("role.post", 0.35), ("derived.three_to_ten_attempt_rate", 0.35), ("identity.ht_in_in", 0.15), ("derived.unassisted_two_rate", 0.15)), "right post-hook events", "post short-area self-creation and reach", "public data has no left/right split"), _Recipe("historical_post_hook_right", (("role.post", 0.45), ("identity.ht_in_in", 0.25), ("derived.attempt_share", 0.30)), "post-hook and directional events", "post role, reach, and responsibility", "laterality remains uncertain")),
        "POSTSHIMMYSHOT": (_Recipe("post_shimmy", (("role.post", 0.30), ("derived.mid_attempt_rate", 0.30), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15)), "post-shimmy events", "post self-created midrange touch", "the low target calibration distinguishes this rare move"), _Recipe("historical_post_shimmy", (("role.post", 0.45), ("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.25)), "post-shimmy and location events", "post role, touch, and responsibility", "no fixed post package is used")),
        "POSTSTEPBACKSHOT": (_Recipe("post_stepback", (("role.post", 0.25), ("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.25), ("role.wing", 0.15)), "post-stepback events", "hybrid post/wing self-created midrange behavior", "the field-exact low target keeps the move rare"), _Recipe("historical_post_stepback", (("role.post", 0.35), ("role.wing", 0.25), ("per_game.ft_percent", 0.20), ("derived.attempt_share", 0.20)), "post-stepback and location events", "hybrid role, touch, and responsibility", "no generic move constant is used")),
        "POSTUPANDUNDER": (_Recipe("post_up_and_under", (("role.post", 0.30), ("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.20), ("derived.unassisted_two_rate", 0.20)), "up-and-under events", "post short-area self-creation and foul pressure", "the inputs identify move frequency"), _Recipe("historical_post_up_and_under", (("role.post", 0.45), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25)), "up-and-under and post-touch events", "post role, foul pressure, and responsibility", "no execution output is reused")),
        "SPINJUMPER": (_Recipe("spin_jumper", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.30), ("role.creator", 0.20), ("derived.foul_pressure", 0.15)), "spin-jumper events", "self-created midrange and live-drive pressure", "the tendency remains distinct from driving spin"), _Recipe("historical_spin_jumper", (("role.creator", 0.35), ("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.35)), "spin-jumper and pull-up events", "creator role, touch, and responsibility", "no fixed move package is inserted")),
        "SPINLAYUP": (_Recipe("spin_layup", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.20)), "spin-layup events", "self-created rim/foul pressure", "3-10 foot location is deliberately excluded"), _Recipe("historical_spin_layup", (("derived.foul_pressure", 0.40), ("role.creator", 0.35), ("derived.attempt_share", 0.25)), "spin-layup and drive events", "drive pressure and creator responsibility", "no make efficiency authors frequency")),
        "STEPBACKJUMPER3POINT": (_Recipe("stepback_three", (("derived.three_attempt_rate", 0.30), ("shooting.percent_assisted_x3p_fg", -0.30), ("role.creator", 0.25), ("derived.attempt_share", 0.15)), "stepback-three events", "self-created three frequency and creator responsibility", "the field-exact low target keeps the move rare"),),
        "STEPBACKJUMPERMID": (_Recipe("stepback_mid_alias", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("role.creator", 0.20), ("derived.attempt_share", 0.10)), "stepback-mid events and a captured field-exact alias", "self-created midrange behavior and the captured Stepback Jumper Mid-Range distribution", "the active alias has no separate Pool label"),),
        "STEPBACKJUMPERMIDRANGE": (_Recipe("stepback_midrange", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("role.creator", 0.20), ("derived.attempt_share", 0.10)), "stepback-midrange events", "self-created midrange and creator responsibility", "the target is attempt behavior"),),
        "STEPTHROUGH": (_Recipe("step_through", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.20), ("role.post", 0.20)), "step-through events", "short-area self-creation, foul pressure, and post participation", "the field is authored once from its exact action context"), _Recipe("historical_step_through", (("derived.foul_pressure", 0.35), ("role.post", 0.30), ("role.creator", 0.20), ("derived.attempt_share", 0.15)), "step-through and short-location events", "drive/post pressure and responsibility", "no shared shot-family output is redistributed")),
        "TRANSITIONPULLUP3POINT": (_Recipe("transition_pullup_three", (("derived.three_attempt_rate", 0.35), ("shooting.percent_assisted_x3p_fg", -0.20), ("role.creator", 0.25), ("derived.scoring_share", 0.20)), "transition-pull-up-three events", "self-created three volume and transition-capable creator load", "the low field-exact target preserves rarity"),),
        "USEGLASS": (_Recipe("use_glass", (("derived.three_to_ten_attempt_rate", 0.50), ("derived.rim_attempt_rate", 0.25), ("role.interior", 0.15), ("role.guard", 0.10)), "bank-shot events", "3-10 foot and rim attempt context", "3-10 feet is permitted for glass use and is not reused for layup moves"), _Recipe("historical_use_glass", (("role.interior", 0.40), ("role.guard", 0.25), ("derived.attempt_share", 0.20), ("per_game.ft_percent", 0.15)), "bank-shot and 3-10 foot events", "continuous close-shot role and weak touch/responsibility context", "the target remains a behavior tendency")),
    }
)


_SHOT_EXECUTION_FIELDS = {
    "IQSHOT",
    "CLOSESHOT",
    "DRIVINGDUNK",
    "DRIVINGLAYUP",
    "MIDRANGE",
    "POSTFADE",
    "POSTHOOK",
    "STANDINGDUNK",
}

def _attribute(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    attempts = _estimated_total(evidence, "fga")
    if field in _SHOT_EXECUTION_FIELDS and attempts is not None and attempts <= 0.0:
        return {
            "value": 25,
            "source_rule": f"derive_attribute_{field.lower()}_zero_recorded_execution",
            "evidence_keys": (
                "totals.fga",
                "recorded_FGA=0",
                "unavailable_direct_source=field-specific made/attempt execution",
                "substitute_source=zero recorded field-goal attempts",
                "validity=attribute is demonstrated execution; no attempts resolve to the legal attribute floor rather than role or body context",
            ),
        }
    return _derive(f"derive_attribute_{field.lower()}", field, evidence, league_player_rows, _ATTR_RECIPES[field])


_DUNK_ATTEMPT_TENDENCY_FIELDS = {"DRIVINGDUNK", "STANDINGDUNK"}


def _tendency(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    result = _derive(f"derive_tendency_{field.lower()}", field, evidence, league_player_rows, _TENDENCY_RECIPES[field], tendency=True)
    if result is None or field not in _DUNK_ATTEMPT_TENDENCY_FIELDS:
        return result
    era = player_era_context(evidence)
    if era.dunk_attempt_multiplier >= 1.0:
        return result
    unsuppressed = int(result["value"])
    adjusted = max(0, min(100, round(unsuppressed * era.dunk_attempt_multiplier)))
    return {
        **result,
        "value": adjusted,
        "source_rule": f"{result['source_rule']}_historical_dunk_attempt_suppression",
        "evidence_keys": tuple(result["evidence_keys"]) + (
            *era.evidence_keys,
            f"unsuppressed_dunk_attempt_tendency={unsuppressed}",
            f"historically_suppressed_dunk_attempt_tendency={adjusted}",
            "attribute_unchanged=true",
            "hard_foul_model_is_separate=true",
        ),
    }


def derive_attribute_ballcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("BALLCONTROL", evidence, league_player_rows)


def derive_attribute_drawfoul(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("DRAWFOUL", evidence, league_player_rows)


def derive_attribute_offensiveconsistency(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("OFFENSIVECONSISTENCY", evidence, league_player_rows)


def derive_attribute_passaccuracy(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("PASSACCURACY", evidence, league_player_rows)


def derive_attribute_passiq(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("PASSIQ", evidence, league_player_rows)


def derive_attribute_passvision(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("PASSVISION", evidence, league_player_rows)


def derive_attribute_iqshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("IQSHOT", evidence, league_player_rows)


def derive_attribute_3point(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    era = player_era_context(evidence)
    if not era.has_three_point_line:
        return {
            "value": 25,
            "source_rule": "derive_attribute_3point_pre_line",
            "evidence_keys": (*era.evidence_keys, "pre_line_3POINT=25"),
        }
    attempts = _basic_value(evidence, "totals.x3pa")
    percentage = _basic_value(evidence, "per_game.x3p_percent")
    if attempts is None or attempts <= 0.0 or percentage is None:
        return {
            "value": 25,
            "source_rule": "derive_attribute_3point_no_made_attempt_evidence",
            "evidence_keys": (*era.evidence_keys, "totals.x3pa<=0_or_unavailable", "no demonstrated 3PT execution=legal_attribute_floor"),
        }
    population = _population(evidence, league_player_rows)
    peer_percentages = [value for row in population if (value := _value(row, "per_game.x3p_percent")) is not None and (_basic_value(row, "totals.x3pa") or 0.0) > 0.0]
    z_value = _robust_z(percentage, peer_percentages)
    if z_value is None:
        return None
    reliability = attempts / (attempts + 40.0)
    center, scale = _ATTRIBUTE_CALIBRATION["3POINT"]
    recipe = _Recipe("attempt_confidence_shrunk_3PT_execution", (("per_game.x3p_percent", 1.0),))
    return _resolved(
        "derive_attribute_3point",
        center + z_value * math.sqrt(reliability) * scale,
        ("per_game.x3p_percent", "totals.x3pa", f"attempt_confidence={reliability:.8f}"),
        recipe,
        tendency=False,
    )


def derive_attribute_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("CLOSESHOT", evidence, league_player_rows)


def derive_attribute_drivingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("DRIVINGDUNK", evidence, league_player_rows)


def derive_attribute_drivinglayup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("DRIVINGLAYUP", evidence, league_player_rows)


def derive_attribute_midrange(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    attempts = _estimated_total(evidence, "fga")
    if attempts is not None and attempts <= 0.0:
        return {
            "value": 25,
            "source_rule": "derive_attribute_midrange_zero_recorded_execution",
            "evidence_keys": (
                "totals.fga",
                "recorded_FGA=0",
                "MIDRANGE=25",
            ),
        }

    location_inputs = (
        ("shooting.fg_percent_from_x10_16_range", 0.55),
        ("shooting.fg_percent_from_x16_3p_range", 0.35),
    )
    observed = [
        (key, value, weight)
        for key, weight in location_inputs
        if (value := _basic_value(evidence, key)) is not None
    ]
    if observed:
        return _attribute("MIDRANGE", evidence, league_player_rows)

    ft_percent = _basic_value(evidence, "per_game.ft_percent")
    if ft_percent is not None:
        target = max(0.0, min(1.0, ft_percent)) * 0.5
        rating = midrange_rating_for_make_probability(target, context="spot_up")
        return {
            "value": rating,
            "source_rule": "derive_attribute_midrange_historical_ft_half_open_spot_up_response_map",
            "evidence_keys": (
                "per_game.ft_percent",
                f"historical_ft_percent={ft_percent:.8f}",
                f"target_open_spot_up_make_probability=0.5*FT%={target:.8f}",
                "response_anchor_25=spot_up_0.0015",
                "response_anchor_80=spot_up_0.45",
                "response_anchor_99=spot_up_0.55",
                "mapping=inverse_piecewise_linear_open_spot_up_response",
                "context_weighting=none",
                "ft_percent_does_not_author_action_tendencies=true",
            ),
        }

    return _attribute("MIDRANGE", evidence, league_player_rows)


def derive_attribute_postcontrol(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("POSTCONTROL", evidence, league_player_rows)


def derive_attribute_postfade(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("POSTFADE", evidence, league_player_rows)


def derive_attribute_posthook(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _attribute("POSTHOOK", evidence, league_player_rows)


def _standing_dunk_frame_score(source: Any) -> float | None:
    height_in = _basic_value(source, "identity.ht_in_in")
    weight_lb = _basic_value(source, "identity.wt")
    if height_in is None or weight_lb is None:
        return None
    return 5.0 * (height_in - 76.0) + 0.12 * (weight_lb - 180.0)


def derive_attribute_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    height_in = _basic_value(evidence, "identity.ht_in_in")
    weight_lb = _basic_value(evidence, "identity.wt")
    if height_in is None or weight_lb is None:
        return None
    if height_in < 76.0:
        return {
            "value": 25,
            "source_rule": "derive_attribute_standingdunk_under_6_4_height_gate",
            "evidence_keys": (
                "identity.ht_in_in",
                f"height_in={height_in:.6f}",
                "standing_dunk_height_threshold_in=76",
                "standing_dunk_height_gate=height_below_6_4_resolves_to_25",
            ),
        }

    vertical_result = derive_attribute_vertical(evidence, league_player_rows=league_player_rows)
    if vertical_result is None:
        return None
    vertical = int(vertical_result["value"])
    if height_in <= 79.0 and vertical <= 40:
        return {
            "value": 25,
            "source_rule": "derive_attribute_standingdunk_lower_height_vertical_gate",
            "evidence_keys": (
                "identity.ht_in_in",
                "identity.wt",
                *tuple(vertical_result["evidence_keys"]),
                f"height_in={height_in:.6f}",
                f"generated_VERTICAL={vertical}",
                "lower_height_boundary=through_6_7",
                "generated_VERTICAL<=40_resolves_to_25",
            ),
        }

    population = _population(evidence, league_player_rows)
    population_scores = sorted(
        score
        for row in population
        if (score := _standing_dunk_frame_score(row)) is not None
    )
    frame_score = _standing_dunk_frame_score(evidence)
    if frame_score is None or not population_scores:
        return None
    left = bisect.bisect_left(population_scores, frame_score)
    right = bisect.bisect_right(population_scores, frame_score)
    frame_percentile = (left + right) / (2.0 * len(population_scores))
    value = 25.0 + 74.0 * frame_percentile**0.55 + 0.25 * (vertical - 65.0)

    lower_height_cap: float | None = None
    if height_in <= 77.0:
        lower_height_cap = 40.0 + 0.80 * max(0.0, vertical - 40.0)
    elif height_in <= 79.0:
        lower_height_cap = 25.0 + 1.20 * max(0.0, vertical - 40.0)
    if lower_height_cap is not None:
        value = min(value, lower_height_cap)

    stored = max(25, min(99, round(value)))
    return {
        "value": stored,
        "source_rule": "derive_attribute_standingdunk_frame_vertical_field_specific_context_substitute",
        "evidence_keys": (
            "identity.ht_in_in",
            "identity.wt",
            *tuple(vertical_result["evidence_keys"]),
            f"height_in={height_in:.6f}",
            f"weight_lb={weight_lb:.6f}",
            f"generated_VERTICAL={vertical}",
            f"frame_score={frame_score:.8f}",
            f"same_season_same_league_frame_percentile={frame_percentile:.8f}",
            "frame_score=5*(height_in-76)+0.12*(weight_lb-180)",
            "mapping=25+74*frame_percentile^0.55+0.25*(generated_VERTICAL-65)",
            "lower_height_vertical_cap=active" if lower_height_cap is not None else "lower_height_vertical_cap=not_applicable",
            "unavailable_direct_source=literal_stationary_dunk_execution_measurement",
            "substitute_source=height_weight_leverage_plus_generated_VERTICAL_and_same_season_same_league_frame_rank",
            "validity=standing_dunk_physical_execution_potential_only; no FG%, foul pressure, broad dunk total, or moving action evidence",
            "DRIVINGDUNK_attribute_unchanged=true",
        ),
    }


def derive_tendency_shot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    population = _population(evidence, league_player_rows)
    share = _derived_value(evidence, "attempt_share")
    if share is None:
        scoring_share = _derived_value(evidence, "scoring_share")
        if scoring_share is None:
            return None
        peer_scoring_shares = [
            value
            for row in population
            if (value := _derived_value(row, "scoring_share")) is not None
        ]
        scoring_z = _robust_z(scoring_share, peer_scoring_shares)
        if scoring_z is None:
            return None
        center, scale = _TENDENCY_CALIBRATION["SHOT"]
        recipe = _Recipe(
            "team_scoring_share_historical_shot_load",
            (("derived.scoring_share", 1.0),),
            "player/team field-goal attempts",
            "player share of recorded team points",
            "SHOT is a role/frequency tendency; scoring share is the exact all-era team-load substitute when attempts were not recorded",
        )
        return _resolved(
            "derive_tendency_shot_team_scoring_share_field_specific_context_substitute",
            center + scoring_z * scale,
            (
                "totals.pts",
                "team_stats_per_game.pts_per_game",
                "team_stats_per_game.g",
                f"scoring_share={scoring_share:.8f}",
                "unavailable_direct_source=player/team field-goal attempts",
                "substitute_source=player share of recorded team points",
                "validity=SHOT is role/frequency; team scoring share measures historical offensive load",
            ),
            recipe,
            tendency=True,
        )
    peer_shares = [value for row in population if (value := _derived_value(row, "attempt_share")) is not None]
    z_value = _robust_z(share, peer_shares)
    if z_value is None:
        return None
    center, scale = _TENDENCY_CALIBRATION["SHOT"]
    recipe = _Recipe("team_attempt_share", (("derived.attempt_share", 1.0),))
    result = _resolved(
        "derive_tendency_shot_team_attempt_share",
        center + z_value * scale,
        ("totals.fga", "team_totals.fga", f"shot_attempt_share={share:.8f}"),
        recipe,
        tendency=True,
    )
    return result


def derive_tendency_3pointshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    era = player_era_context(evidence)
    if not era.has_three_point_line:
        return {
            "value": 0,
            "source_rule": "derive_tendency_3pointshot_pre_line",
            "evidence_keys": (*era.evidence_keys, "pre_line_3POINTSHOT=0"),
        }
    attempts = _basic_value(evidence, "totals.x3pa")
    if attempts is not None and attempts <= 0.0:
        return {
            "value": 0,
            "source_rule": "derive_tendency_3pointshot_zero_attempts",
            "evidence_keys": (*era.evidence_keys, "totals.x3pa=0", "zero recorded attempts=zero attempt tendency"),
        }
    return _derive(
        "derive_tendency_3pointshot",
        "3POINTSHOT",
        evidence,
        league_player_rows,
        (_Recipe("recorded_three_attempt_rate", (("derived.three_attempt_rate", 1.0),)),),
        tendency=True,
    )


def derive_tendency_closeshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive(
        "derive_tendency_closeshot",
        "CLOSESHOT",
        evidence,
        league_player_rows,
        (
            _Recipe("recorded_short_attempt_location", (("derived.short_attempt_rate", 0.80), ("role.interior", 0.20))),
            _Recipe("historical_close_attempt_role", (("derived.attempt_share", 0.45), ("role.interior", 0.40), ("derived.foul_pressure", 0.15)), "0-10 foot attempt location", "shooting responsibility, continuous interior participation, and foul pressure", "the sources describe close-shot opportunity/frequency rather than execution"),
        ),
        tendency=True,
    )


def derive_tendency_midshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive(
        "derive_tendency_midshot",
        "MIDRANGESHOT",
        evidence,
        league_player_rows,
        (
            _Recipe("recorded_midrange_attempt_location", (("derived.mid_attempt_rate", 0.80), ("role.wing", 0.20))),
            _Recipe("historical_midrange_attempt_role", (("derived.attempt_share", 0.45), ("role.wing", 0.40), ("per_game.ft_percent", 0.15)), "10-foot-to-line attempt location", "shooting responsibility, continuous perimeter/wing participation, and weak touch context", "attempt share authors frequency; touch only distinguishes plausible historical jump-shooting behavior"),
        ),
        tendency=True,
    )


def derive_tendency_triplethreatidle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("TRIPLETHREATIDLE", evidence, league_player_rows)


def derive_tendency_triplethreatjab(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("TRIPLETHREATJAB", evidence, league_player_rows)


def derive_tendency_triplethreatpumpfake(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("TRIPLETHREATPUMPFake", evidence, league_player_rows)


def derive_tendency_triplethreatshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("TRIPLETHREATSHOT", evidence, league_player_rows)


def derive_tendency_setupdribble(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("SETUPDRIBBLE", evidence, league_player_rows)


def derive_tendency_setupwithhesitation(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("SETUPWITHHESITATION", evidence, league_player_rows)


def derive_tendency_setupwithsizeup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("SETUPWITHSIZEUP", evidence, league_player_rows)


def derive_tendency_drive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVE", evidence, league_player_rows)


def derive_tendency_driveright(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVERIGHT", evidence, league_player_rows)


def derive_tendency_drivingcrossover(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGCROSSOVER", evidence, league_player_rows)


def derive_tendency_drivingdoublecrossover(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGDOUBLECROSSOVER", evidence, league_player_rows)


def derive_tendency_drivingspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGSPIN", evidence, league_player_rows)


def derive_tendency_drivinghalfspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGHALFSPIN", evidence, league_player_rows)


def derive_tendency_drivingstepback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGSTEPBACK", evidence, league_player_rows)


def derive_tendency_drivingbehindtheback(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGBEHINDTHEBACK", evidence, league_player_rows)


def derive_tendency_drivingdribblehesitation(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGDRIBBLEHESITATION", evidence, league_player_rows)


def derive_tendency_drivinginandout(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DRIVINGINANDOUT", evidence, league_player_rows)


def derive_tendency_nodrivingdribblemove(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("NODRIVINGDRIBBLEMOVE", evidence, league_player_rows)


def derive_tendency_attackstrongondrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("ATTACKSTRONGONDRIVE", evidence, league_player_rows)


def derive_tendency_offscreendrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("OFFSCREENDRIVE", evidence, league_player_rows)


def derive_tendency_spotupdrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("SPOTUPDRIVE", evidence, league_player_rows)


def derive_tendency_alleyoopass(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("ALLEYOOOPASS", evidence, league_player_rows)


def derive_tendency_dishtoopenman(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("DISHTOOPENMAN", evidence, league_player_rows)


def derive_tendency_flashypass(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("FLASHYPASS", evidence, league_player_rows)


def derive_tendency_postup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTUP", evidence, league_player_rows)


def derive_tendency_postbackdown(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTBACKDOWN", evidence, league_player_rows)


def derive_tendency_postaggressivebackdown(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTAGGRESSIVEBACKDOWN", evidence, league_player_rows)


def derive_tendency_postfaceup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTFACEUP", evidence, league_player_rows)


def derive_tendency_postspin(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTSPIN", evidence, league_player_rows)


def derive_tendency_postdrive(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTDRIVE", evidence, league_player_rows)


def derive_tendency_posthopshot(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _tendency("POSTHOPSHOT", evidence, league_player_rows)


def _three_point_tendency(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    era = player_era_context(evidence)
    if not era.has_three_point_line:
        return {
            "value": 0,
            "source_rule": f"derive_tendency_{field.lower()}_pre_line",
            "evidence_keys": (*era.evidence_keys, f"pre_line_{field}=0"),
        }
    attempts = _basic_value(evidence, "totals.x3pa")
    if attempts is not None and attempts <= 0.0:
        return {
            "value": 0,
            "source_rule": f"derive_tendency_{field.lower()}_zero_attempts",
            "evidence_keys": (*era.evidence_keys, "totals.x3pa=0", "zero recorded attempts=zero three-point action tendency"),
        }
    return _tendency(field, evidence, league_player_rows)


_EXTRA_TENDENCY_FUNCTIONS: dict[str, str] = {
    "derive_tendency_posthopstep": "POSTHOPSTEP",
    "derive_tendency_3pointcenterleftshot": "3POINTCENTERLEFTSHOT",
    "derive_tendency_3pointcenterrightshot": "3POINTCENTERRIGHTSHOT",
    "derive_tendency_3pointcentershot": "3POINTCENTERSHOT",
    "derive_tendency_3pointleftshot": "3POINTLEFTSHOT",
    "derive_tendency_3pointoffscreenshot": "3POINTOFFSCREENSHOT",
    "derive_tendency_3pointrightshot": "3POINTRIGHTSHOT",
    "derive_tendency_3pointspotupshot": "3POINTSPOTUPSHOT",
    "derive_tendency_alleyoop": "ALLEYOOP",
    "derive_tendency_basketundershot": "BASKETUNDERSHOT",
    "derive_tendency_centerleftmidshot": "CENTERLEFTMIDSHOT",
    "derive_tendency_centermidrightshot": "CENTERMIDRIGHTSHOT",
    "derive_tendency_centermidshot": "CENTERMIDSHOT",
    "derive_tendency_closeleftshot": "CLOSELEFTSHOT",
    "derive_tendency_closemiddleshot": "CLOSEMIDDLESHOT",
    "derive_tendency_closerightshot": "CLOSERIGHTSHOT",
    "derive_tendency_contestedjumper3point": "CONTESTEDJUMPER3POINT",
    "derive_tendency_contestedjumpermid": "CONTESTEDJUMPERMID",
    "derive_tendency_contestedjumpermidrange": "CONTESTEDJUMPERMIDRANGE",
    "derive_tendency_drivepullup3point": "DRIVEPULLUP3POINT",
    "derive_tendency_drivepullupmid": "DRIVEPULLUPMID",
    "derive_tendency_drivepullupmidrange": "DRIVEPULLUPMIDRANGE",
    "derive_tendency_drivingdunk": "DRIVINGDUNK",
    "derive_tendency_drivinglayup": "DRIVINGLAYUP",
    "derive_tendency_eurosteplayup": "EUROSTEPLAYUP",
    "derive_tendency_flashydunk": "FLASHYDUNK",
    "derive_tendency_floater": "FLOATER",
    "derive_tendency_frompostshot": "FROMPOSTSHOT",
    "derive_tendency_hoppostshot": "HOPPOSTSHOT",
    "derive_tendency_hopsteplayup": "HOPSTEPLAYUP",
    "derive_tendency_leftmidshot": "LEFTMIDSHOT",
    "derive_tendency_midoffscreenshot": "MIDOFFSCREENSHOT",
    "derive_tendency_midrightshot": "MIDRIGHTSHOT",
    "derive_tendency_midspotupshot": "MIDSPOTUPSHOT",
    "derive_tendency_postdropstep": "POSTDROPSTEP",
    "derive_tendency_postfadeleft": "POSTFADELEFT",
    "derive_tendency_postfaderight": "POSTFADERIGHT",
    "derive_tendency_posthookleft": "POSTHOOKLEFT",
    "derive_tendency_posthookright": "POSTHOOKRIGHT",
    "derive_tendency_postshimmyshot": "POSTSHIMMYSHOT",
    "derive_tendency_poststepbackshot": "POSTSTEPBACKSHOT",
    "derive_tendency_postupandunder": "POSTUPANDUNDER",
    "derive_tendency_spinjumper": "SPINJUMPER",
    "derive_tendency_spinlayup": "SPINLAYUP",
    "derive_tendency_standingdunk": "STANDINGDUNK",
    "derive_tendency_stepbackjumper3point": "STEPBACKJUMPER3POINT",
    "derive_tendency_stepbackjumpermid": "STEPBACKJUMPERMID",
    "derive_tendency_stepbackjumpermidrange": "STEPBACKJUMPERMIDRANGE",
    "derive_tendency_stepthrough": "STEPTHROUGH",
    "derive_tendency_transitionpullup3point": "TRANSITIONPULLUP3POINT",
    "derive_tendency_useglass": "USEGLASS",
}
_EXTRA_THREE_POINT_FIELDS = {
    "3POINTCENTERLEFTSHOT",
    "3POINTCENTERRIGHTSHOT",
    "3POINTCENTERSHOT",
    "3POINTLEFTSHOT",
    "3POINTOFFSCREENSHOT",
    "3POINTRIGHTSHOT",
    "3POINTSPOTUPSHOT",
    "CONTESTEDJUMPER3POINT",
    "DRIVEPULLUP3POINT",
    "STEPBACKJUMPER3POINT",
    "TRANSITIONPULLUP3POINT",
}

# The available season source contract has broad range, assisted-shot, dunk,
# body, and creator-role signals, but no exact event source for these action
# contexts. Those generic signals cannot manufacture an action Tendency.
# Returning unresolved lets the active-field completion owner write 0 until an
# exact event source or explicitly approved researched action rule is wired.
_EXACT_ACTION_EVIDENCE_ONLY_FIELDS = {
    "CONTESTEDJUMPERMID",
    "CONTESTEDJUMPERMIDRANGE",
    "DRIVEPULLUPMID",
    "DRIVEPULLUPMIDRANGE",
    "MIDOFFSCREENSHOT",
    "MIDSPOTUPSHOT",
    "STANDINGDUNK",
}


def _install_tendency_rule(function_name: str, field: str) -> None:
    def rule(evidence: Any, *, league_player_rows: Any = (), _field: str = field) -> dict[str, Any] | None:
        if _field in _EXACT_ACTION_EVIDENCE_ONLY_FIELDS:
            return None
        if _field in _EXTRA_THREE_POINT_FIELDS:
            return _three_point_tendency(_field, evidence, league_player_rows)
        return _tendency(_field, evidence, league_player_rows)
    rule.__name__ = function_name
    rule.__qualname__ = function_name
    globals()[function_name] = rule


for _function_name, _field_name in _EXTRA_TENDENCY_FUNCTIONS.items():
    _install_tendency_rule(_function_name, _field_name)


__all__ = [name for name in globals() if name.startswith("derive_attribute_") or name.startswith("derive_tendency_")]