from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


#: Above 1.0 the curve pushes the ends of the league apart instead of crowding the
#: middle. Intangibles is a separation field: the gap between the best player in a
#: league and a replacement one should read as a gap.
_INTANGIBLES_DISPARITY_EXPONENT = 1.6

_INTANGIBLES_VORP_MAX = 12.47
_INTANGIBLES_LINEAR_WEIGHT = 0.1318558994
_INTANGIBLES_TAIL_WEIGHT = 0.8681331006
_INTANGIBLES_TAIL_EXPONENT = 22.89826001


_ROW_PREFIXES: dict[str, tuple[str, ...]] = {
    "identity": ("player_info", "identity"),
    "season_info": ("player_season_info", "season_info"),
    "per_game": ("player_per_game", "per_game"),
    "totals": ("player_totals", "totals"),
    "per_36": ("player_per_36", "per_36"),
    "advanced": ("advanced", "player_advanced"),
    "shooting": ("shooting", "player_shooting"),
    "play_by_play": ("play_by_play", "player_play_by_play"),
    "team_totals": ("team_totals",),
    "team_stats_per_game": ("team_stats_per_game",),
    "opponent_stats_per_game": ("opponent_stats_per_game",),
    "team_summary": ("team_summaries", "team_summary"),
}

_NBL_HUSTLE_WEIGHTS = (("games_share", 0.50), ("fta_per_game", 0.30), ("team_win_pct", 0.20))
_NBL_INTANGIBLES_WEIGHTS = (("team_point_differential", 0.60), ("nbl_scoring_share", 0.40))
NBL_BAA_OVERLAP_INTANGIBLES_REFERENCE_KEY = "nbl_baa_overlap_intangibles_reference_values"
_NBL_BAA_REFERENCE_KEYS = {
    "HUSTLE": "nbl_baa_hustle_reference_values",
    "INTANGIBLES": NBL_BAA_OVERLAP_INTANGIBLES_REFERENCE_KEY,
}
_NBL_WEIGHTS_BY_FIELD = {
    "HUSTLE": _NBL_HUSTLE_WEIGHTS,
    "INTANGIBLES": _NBL_INTANGIBLES_WEIGHTS,
}


@dataclass(frozen=True)
class _NblCalculationTable:
    population: tuple[Any, ...]
    signal_populations: dict[str, tuple[float, ...]]
    composite_populations: dict[str, tuple[float, ...]]
    composite_moments: dict[str, tuple[float, float]]
    composite_winners: dict[str, tuple[str, str]]


_NBL_CALCULATION_TABLE_CACHE: dict[
    tuple[int, int],
    tuple[object, _NblCalculationTable],
] = {}
_MENTAL_POPULATION_CACHE: dict[
    tuple[int, int],
    tuple[object, tuple[Any, ...]],
] = {}
_MENTAL_SIGNAL_SUMMARY_CACHE: dict[
    tuple[int, str],
    tuple[object, tuple[float, float] | None],
] = {}


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _source_map(source: Any, namespace: str) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        nested = source.get(namespace)
        return nested if isinstance(nested, Mapping) else source
    value = getattr(source, namespace, {})
    return value if isinstance(value, Mapping) else {}


def _source_value(source: Any, namespace: str, key: str) -> float | None:
    if isinstance(source, Mapping):
        for prefix in _ROW_PREFIXES.get(namespace, (namespace,)):
            if (value := _optional_number(source.get(f"{prefix}.{key}"))) is not None:
                return value
        nested_map = source.get(namespace)
        if isinstance(nested_map, Mapping) and (value := _optional_number(nested_map.get(key))) is not None:
            return value
        return _optional_number(source.get(key))
    values = _source_map(source, namespace)
    nested = values.get(key)
    if nested is not None:
        return _optional_number(nested)
    for prefix in _ROW_PREFIXES.get(namespace, (namespace,)):
        if (value := _optional_number(values.get(f"{prefix}.{key}"))) is not None:
            return value
    return None


def _text_value(source: Any, namespace: str, key: str) -> str:
    values = _source_map(source, namespace)
    value = values.get(key)
    if value is None:
        for prefix in _ROW_PREFIXES.get(namespace, (namespace,)):
            value = values.get(f"{prefix}.{key}")
            if value is not None:
                break
    return str(value or "").strip()


def _gp(source: Any) -> float | None:
    for namespace, key in (("per_game", "g"), ("totals", "g")):
        value = _source_value(source, namespace, key)
        if value is not None and value > 0.0:
            return value
    if isinstance(source, Mapping):
        value = _optional_number(source.get("games"))
        if value is not None and value > 0.0:
            return value
    return None


def _season(source: Any) -> int:
    raw = getattr(source, "season", None)
    if raw is None and isinstance(source, Mapping):
        raw = source.get("season") or source.get("year")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _league(source: Any) -> str:
    return _text_value(source, "season_info", "lg").upper()


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _estimated_total(source: Any, field: str) -> float | None:
    total = _source_value(source, "totals", field)
    if total is not None and total >= 0.0:
        return total
    per_game = _source_value(source, "per_game", f"{field}_per_game")
    games = _gp(source)
    if per_game is None or games is None or per_game < 0.0:
        return None
    return per_game * games


def _team_total(source: Any, field: str) -> float | None:
    direct = _source_value(source, "team_totals", field)
    if direct is not None and direct > 0.0:
        return direct
    per_game = _source_value(source, "team_stats_per_game", f"{field}_per_game")
    games = _source_value(source, "team_stats_per_game", "g")
    if per_game is None or games is None or games <= 0.0:
        return None
    return per_game * games


def _rate(source: Any, field: str) -> float | None:
    direct = _source_value(source, "per_36", f"{field}_per_36_min")
    if direct is not None:
        return direct
    per_game = _source_value(source, "per_game", f"{field}_per_game")
    minutes = _source_value(source, "per_game", "mp_per_game")
    if per_game is not None and minutes is not None and minutes > 0.0:
        return per_game * 36.0 / minutes
    return per_game


def _position_vector(source: Any) -> dict[str, float]:
    result = {position: 0.0 for position in ("PG", "SG", "SF", "PF", "C")}
    found = False
    for position, key in (("PG", "pg_percent"), ("SG", "sg_percent"), ("SF", "sf_percent"), ("PF", "pf_percent"), ("C", "c_percent")):
        value = _source_value(source, "play_by_play", key)
        if value is not None:
            result[position] = max(0.0, value)
            found = found or value > 0.0
    if found:
        total = sum(result.values())
        if total > 1.5:
            result = {key: value / 100.0 for key, value in result.items()}
        return result
    text = _text_value(source, "season_info", "pos") or _text_value(source, "identity", "pos")
    text = text.upper().replace(" ", "")
    tokens = [token for token in text.split("-") if token]
    weights = (0.65, 0.35) if len(tokens) > 1 else (1.0,)
    for token, weight in zip(tokens, weights):
        if token == "G":
            result["PG"] += weight * 0.5
            result["SG"] += weight * 0.5
        elif token == "F":
            result["SF"] += weight * 0.5
            result["PF"] += weight * 0.5
        elif token in result:
            result[token] += weight
    return result


def _role(source: Any, name: str) -> float | None:
    positions = _position_vector(source)
    if not any(positions.values()):
        return None
    guard = positions["PG"] + 0.7 * positions["SG"] + 0.2 * positions["SF"]
    wing = 0.3 * positions["SG"] + positions["SF"] + 0.45 * positions["PF"]
    interior = 0.55 * positions["PF"] + positions["C"] + 0.2 * positions["SF"]
    return {
        "creator": guard + 0.35 * wing,
        "wing": wing,
        "interior": interior,
    }.get(name)


def _signal(source: Any, name: str) -> float | None:
    if name.startswith("role."):
        return _role(source, name.split(".", 1)[1])
    if name == "attempt_share":
        return _ratio(_estimated_total(source, "fga"), _team_total(source, "fga"))
    if name == "scoring_share":
        return _ratio(_estimated_total(source, "pts"), _team_total(source, "pts"))
    if name == "hand_frame_fit":
        height = _source_value(source, "identity", "ht_in_in")
        if height is None:
            return None
        low, high = _HANDS_FRAME_BAND
        distance = 0.0 if low <= height <= high else (low - height if height < low else height - high)
        return max(0.0, 1.0 - distance / _HANDS_FRAME_FALLOFF)
    if name == "catch_security":
        # How reliably the ball stuck when it arrived. Nothing measures hand size, so
        # the signifiers are finishing what was caught and holding onto it.
        parts = [
            value
            for value in (
                _source_value(source, "per_game", "fg_percent"),
                _source_value(source, "per_game", "ft_percent"),
            )
            if value is not None
        ]
        return sum(parts) / len(parts) if parts else None
    if name == "fg_stability":
        return _source_value(source, "per_game", "fg_percent")
    if name == "ft_stability":
        return _source_value(source, "per_game", "ft_percent")
    if name == "team_win_pct":
        wins = _source_value(source, "team_summary", "w")
        losses = _source_value(source, "team_summary", "l")
        return _ratio(wins, (wins or 0.0) + (losses or 0.0))
    if name == "assist_share":
        return _ratio(_estimated_total(source, "ast"), _team_total(source, "ast"))
    if name == "foul_pressure":
        value = _source_value(source, "advanced", "f_tr")
        return value if value is not None else _ratio(_estimated_total(source, "fta"), _estimated_total(source, "fga"))
    if name == "turnover_rate":
        value = _source_value(source, "advanced", "tov_percent")
        return value if value is not None else _rate(source, "tov")
    if name == "lost_ball_security":
        lost = _source_value(source, "play_by_play", "lost_ball_turnover")
        opportunities = sum(value or 0.0 for value in (_estimated_total(source, "fga"), _estimated_total(source, "ast"), _estimated_total(source, "tov")))
        if lost is None or opportunities <= 0.0:
            return None
        return 1.0 - min(1.0, lost / opportunities)
    if name == "secure_possession_rate":
        values = [_rate(source, "trb"), _rate(source, "stl")]
        live = [value for value in values if value is not None]
        return sum(live) if live else None
    if name == "orb_rate":
        value = _source_value(source, "advanced", "orb_percent")
        return value if value is not None else _rate(source, "orb")
    if name == "stl_rate":
        return _rate(source, "stl")
    if name == "blk_rate":
        return _rate(source, "blk")
    if name == "charge_rate":
        return _ratio(_source_value(source, "play_by_play", "offensive_foul_drawn"), _gp(source))
    if name == "foul_rate":
        return _rate(source, "pf")
    if name == "trb_rate":
        return _rate(source, "trb")
    if name == "dws":
        return _source_value(source, "advanced", "dws")
    if name == "games_share":
        return _ratio(_gp(source), _source_value(source, "team_stats_per_game", "g"))
    if name == "ft_percent":
        return _source_value(source, "per_game", "ft_percent")
    if name == "mid_attempt_rate":
        parts = [
            _source_value(source, "shooting", "percent_fga_from_x10_16_range"),
            _source_value(source, "shooting", "percent_fga_from_x16_3p_range"),
        ]
        live = [value for value in parts if value is not None]
        return sum(live) if live else None
    if name == "three_attempt_rate":
        value = _source_value(source, "advanced", "x3p_ar")
        return value if value is not None else _ratio(_estimated_total(source, "x3pa"), _estimated_total(source, "fga"))
    if name == "rim_attempt_rate":
        return _source_value(source, "shooting", "percent_fga_from_x0_3_range")
    if name == "assisted_two_rate":
        return _source_value(source, "shooting", "percent_assisted_x2p_fg")
    return None


_SIGNAL_PROVENANCE: dict[str, tuple[str, ...]] = {
    "attempt_share": ("totals.fga", "team_stats_per_game.fga_per_game", "team_stats_per_game.g"),
    "scoring_share": ("totals.pts", "team_stats_per_game.pts_per_game", "team_stats_per_game.g"),
    "hand_frame_fit": ("identity.ht_in_in",),
    "catch_security": ("per_game.fg_percent", "per_game.ft_percent"),
    "fg_stability": ("per_game.fg_percent",),
    "ft_stability": ("per_game.ft_percent",),
    "team_win_pct": ("team_summary.w", "team_summary.l"),
    "assist_share": ("totals.ast", "team_stats_per_game.ast_per_game", "team_stats_per_game.g"),
    "foul_pressure": ("advanced.f_tr", "totals.fta", "totals.fga"),
    "turnover_rate": ("advanced.tov_percent", "per_36.tov_per_36_min", "per_game.tov_per_game"),
    "lost_ball_security": ("play_by_play.lost_ball_turnover", "totals.fga", "totals.ast", "totals.tov"),
    "secure_possession_rate": ("per_36.trb_per_36_min", "per_36.stl_per_36_min"),
    "orb_rate": ("advanced.orb_percent", "per_36.orb_per_36_min"),
    "stl_rate": ("per_36.stl_per_36_min",),
    "blk_rate": ("per_36.blk_per_36_min",),
    "charge_rate": ("play_by_play.offensive_foul_drawn", "per_game.g"),
    "foul_rate": ("per_36.pf_per_36_min", "per_game.pf_per_game", "per_game.mp_per_game"),
    "trb_rate": ("per_36.trb_per_36_min",),
    "dws": ("advanced.dws",),
    "games_share": ("per_game.g", "team_stats_per_game.g"),
    "fta_per_game": ("per_game.fta_per_game",),
    "team_point_differential": ("team_stats_per_game.pts_per_game", "opponent_stats_per_game.opp_pts_per_game"),
    "nbl_scoring_share": ("per_game.pts_per_game", "team_stats_per_game.pts_per_game"),
    "ft_percent": ("per_game.ft_percent",),
    "mid_attempt_rate": ("shooting.percent_fga_from_x10_16_range", "shooting.percent_fga_from_x16_3p_range"),
    "three_attempt_rate": ("advanced.x3p_ar", "totals.x3pa", "totals.fga"),
    "rim_attempt_rate": ("shooting.percent_fga_from_x0_3_range",),
    "assisted_two_rate": ("shooting.percent_assisted_x2p_fg",),
    "role.creator": ("play_by_play.pg_percent", "play_by_play.sg_percent", "play_by_play.sf_percent", "season_info.pos"),
    "role.wing": ("play_by_play.sg_percent", "play_by_play.sf_percent", "play_by_play.pf_percent", "season_info.pos"),
    "role.interior": ("play_by_play.sf_percent", "play_by_play.pf_percent", "play_by_play.c_percent", "season_info.pos"),
}


@dataclass(frozen=True)
class _Recipe:
    name: str
    signals: tuple[tuple[str, float], ...]
    required: tuple[str, ...] = ()
    unavailable: str = ""
    substitute: str = ""
    validity: str = ""


_CALIBRATION: dict[str, tuple[float, float]] = {
    "HANDS": (68.0, 23.722),
    # Narrowed from 20.756 once HUSTLE became DWS-led. At the pool scale the top of
    # the defensive-win-share distribution was wide enough to put twelve players on
    # 99 at once; at 13.0 the ceiling goes to the outright leader.
    "HUSTLE": (65.0, 13.0),
    "ISOVSPOOR": (15.0, 14.83),  # ATD ISO vs Poor 5-25, cap 75
    "ISOVSAVERAGE": (10.0, 14.83),  # ATD ISO vs Average 0-20, cap 70
    "ISOVSGOOD": (7.5, 11.12),  # ATD ISO vs Good 0-15, cap 60
    "ISOVSELITE": (5.0, 7.41),  # ATD ISO vs Elite 0-10, cap 50
    "PLAYDISCIPLINE": (55.0, 22.24),  # ATD Play Discipline 40-70, cap 90
    "ROLLVSPOP": (50.0, 14.83),  # ATD Roll vs Pop 40-60, cap 85
    "TOUCHES": (40.0, 7.41),  # ATD Touch 35-45, cap 75
    "TRANSITIONSPOTUP": (50.0, 14.83),  # ATD Spot vs Cut 40-60, cap 85
}

#: Hands belong to the 6'6"-7'2" frame: big enough to palm and swallow a pass, not so
#: big that everything is reach. Hand size is unmeasurable, so the frame sets the band
#: and catching signifiers place a player inside it.
_HANDS_FRAME_BAND = (78.0, 86.0)
_HANDS_FRAME_FALLOFF = 10.0

_HANDS_RECIPES = (
    _Recipe("tracked_catch_and_ball_security", (("lost_ball_security", 0.55), ("turnover_rate", -0.30), ("secure_possession_rate", 0.15)), ("lost_ball_security", "turnover_rate")),
    _Recipe("historical_hand_eye_and_secure_possession", (("hand_frame_fit", 0.40), ("catch_security", 0.35), ("secure_possession_rate", 0.15), ("ft_percent", 0.10)), ("ft_percent", "catch_security", "secure_possession_rate"), "tracked lost-ball and catch outcomes", "the frame that catches and holds a pass, plus recorded catching signifiers", "guards topped this field on free-throw touch alone; hands belong to the 6ft6-7ft2 frame and are placed inside that band by how reliably the ball stuck"),
    # A player who never attempted a free throw, in a league that recorded no
    # assists, rebounds or turnovers, has no possession evidence at all. Eighteen
    # 1946-47 players are in that position -- every one of them a one-to-seven game
    # appearance. Leaving the field unresolved dropped it off their card entirely and
    # silently shifted every total-attribute comparison against them, so schedule
    # exposure carries the field and states that it is doing so.
    _Recipe("no_recorded_possession_evidence_exposure", (("games_share", 1.0),), ("games_share",), "lost-ball, catch, free-throw, assist, rebound and turnover outcomes", "schedule availability alone", "no possession evidence of any kind was recorded for this player; exposure is the only observed signal and it places brief appearances near the attribute floor rather than at the population centre"),
)
_HUSTLE_RECIPES = (
    _Recipe("recorded_effort_event_activity", (("orb_rate", 0.28), ("stl_rate", 0.20), ("blk_rate", 0.12), ("charge_rate", 0.12), ("foul_rate", 0.08), ("dws", 0.20)), ("orb_rate", "stl_rate", "blk_rate", "charge_rate")),
    _Recipe("historical_rebound_foul_availability_activity", (("dws", 0.50), ("trb_rate", 0.25), ("foul_rate", 0.17), ("games_share", 0.08)), ("trb_rate", "foul_rate", "dws"), "offensive boards, steals, blocks, charges, and loose-ball recoveries", "sustained defensive value, recorded total-rebound activity, foul activity, and schedule availability", "defence is where hustle shows up, so defensive win shares lead; the rebound and foul terms keep the physical-activity evidence in the mix and no body or name template authors HUSTLE"),
)
_ISO_RECIPES = (
    _Recipe("self_created_isolation_load", (("assisted_two_rate", -0.35), ("attempt_share", 0.25), ("foul_pressure", 0.25), ("role.creator", 0.10),), ("assisted_two_rate",)),
    _Recipe("historical_creator_isolation_load", (("attempt_share", 0.40), ("foul_pressure", 0.30), ("role.creator", 0.10),), ("attempt_share", "scoring_share"), "isolation play-type and unassisted-shot event counts", "offensive responsibility, live-contact pressure, and continuous creator role", "the substitute estimates self-created possession load and the four defender classes share one base score"),
)
# Foul rate is a negative discipline signal in both recipes: a player who repeatedly
# fouls is the player who leaves his assignment, gambles, and plays outside the call.
# It is the one discipline signal every era records, so it also carries the historical
# recipe when team totals are thin.
_PLAY_DISCIPLINE_RECIPES = (
    _Recipe("assisted_structure_and_decision_security", (("assisted_two_rate", 0.30), ("turnover_rate", -0.22), ("foul_rate", -0.18), ("attempt_share", -0.15), ("role.creator", 0.10),), ("assisted_two_rate", "turnover_rate")),
    _Recipe("historical_team_role_discipline", (("attempt_share", -0.38), ("assist_share", 0.25), ("foul_rate", -0.22), ("role.creator", 0.10),), ("attempt_share", "assist_share", "foul_rate"), "play-call adherence and freelance possession events", "lower self-directed shot load, team assist responsibility, recorded foul activity, and reduced primary-creator role", "the substitute describes structured team-role behavior rather than shooting execution; fouling is the all-era record of playing outside the call"),
    # The 1946-47 NBL recorded neither assists nor personal fouls, so both recipes
    # above resolve to nothing and the tendency dropped off all 172 NBL cards. Scoring
    # share is the load measure that league did record -- the research supplement is
    # explicit that NBL FGM share is observed make production rather than attempt
    # share -- and free-throw pressure stands in for the unrecorded foul activity.
    _Recipe("nbl_recorded_stability_discipline", (("scoring_share", -0.25), ("fg_stability", 0.25), ("ft_stability", 0.25), ("team_win_pct", 0.25)), ("scoring_share", "fg_stability", "team_win_pct"), "assists, personal fouls, and freelance possession events", "recorded scoring share, reliability-weighted FG/FT stability, and exact team record", "all available NBL evidence contributes continuously; missing FT% is omitted rather than converted to zero"),
)
_ROLL_POP_RECIPES = (
    _Recipe("screen_roll_rim_preference", (("mid_attempt_rate", -0.30), ("three_attempt_rate", -0.30), ("rim_attempt_rate", 0.20), ("role.wing", 0.10), ("role.interior", 0.10),), ("mid_attempt_rate", "three_attempt_rate", "rim_attempt_rate")),
    _Recipe("historical_screen_roll_touch_role", (("ft_percent", -0.40), ("foul_pressure", 0.15), ("role.wing", 0.10), ("role.interior", 0.10),), ("ft_percent", "foul_pressure", "role.wing", "role.interior"), "screen roll/pop event destinations and shot locations", "recorded shooting touch plus continuous spacing-versus-interior role", "higher output means roll preference; the all-era substitute separates rim pressure from spacing"),
)
_TRANSITION_SPOTUP_RECIPES = (
    _Recipe("transition_perimeter_receiver_context", (("three_attempt_rate", 0.30), ("mid_attempt_rate", 0.25), ("assisted_two_rate", 0.25), ("role.creator", 0.10),), ("three_attempt_rate", "mid_attempt_rate", "assisted_two_rate")),
    _Recipe("historical_transition_receiver_role", (("attempt_share", 0.20), ("ft_percent", 0.20), ("role.wing", 0.10), ("role.creator", 0.10),), ("role.wing", "role.creator"), "transition spot-up event and assisted-location counts", "off-ball wing role, reduced primary creation, shooting responsibility, and recorded touch", "the substitute estimates running to a receiving spot rather than transition pull-up creation"),
)


def _population(evidence: Any, rows: Any) -> tuple[Any, ...]:
    season = _season(evidence)
    cache_key = (id(rows), season)
    cached = _MENTAL_POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    population = tuple(
        row
        for row in rows
        if _gp(row) is not None
        and (not season or not _season(row) or _season(row) == season)
    )
    _MENTAL_POPULATION_CACHE[cache_key] = (rows, population)
    return population


def _robust_summary(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 5:
        return None
    median = statistics.median(values)
    scale = statistics.median(abs(value - median) for value in values) * 1.4826
    if scale <= 1e-12:
        ordered = sorted(values)
        q1 = ordered[(len(ordered) - 1) // 4]
        q3 = ordered[(3 * (len(ordered) - 1)) // 4]
        scale = (q3 - q1) / 1.349
    return (median, scale) if scale > 1e-12 else None


def _signal_summary(population: tuple[Any, ...], signal: str) -> tuple[float, float] | None:
    cache_key = (id(population), signal)
    cached = _MENTAL_SIGNAL_SUMMARY_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        return cached[1]
    summary = _robust_summary([
        value
        for row in population
        if (value := _signal(row, signal)) is not None
    ])
    _MENTAL_SIGNAL_SUMMARY_CACHE[cache_key] = (population, summary)
    return summary


# Every signal in these recipes is a rate over the same denominator -- the playing
# time the player actually got -- so they are all noise together at low exposure.
# One game of four minutes yields 18 PF/36 and a 0.0 turnover rate, and shrinking
# only one of them just hands authorship to the other. Shrink the finished score
# instead, so a player with no meaningful sample lands on the calibration center
# rather than on whichever signal has the smallest denominator. Same
# exposure/(exposure+prior) form used in player_rules_offense; minutes are the real
# denominator and are used when the era recorded them, games otherwise.
_MINUTES_EXPOSURE_PRIOR = 300.0
_GAMES_EXPOSURE_PRIOR = 20.0


def _exposure_total_minutes(source: Any) -> float | None:
    total = _source_value(source, "totals", "mp")
    if total is not None:
        return total
    per_game = _source_value(source, "per_game", "mp_per_game")
    games = _gp(source)
    return per_game * games if per_game is not None and games is not None else None


def _exposure_reliability(evidence: Any) -> tuple[float, str] | None:
    minutes = _exposure_total_minutes(evidence)
    if minutes is not None and minutes >= 0.0:
        exposure, prior, basis = minutes, _MINUTES_EXPOSURE_PRIOR, "total_minutes_rate_exposure"
    else:
        games = _gp(evidence)
        if games is None or games < 0.0:
            return None
        exposure, prior, basis = games, _GAMES_EXPOSURE_PRIOR, "games_played_rate_exposure"
    reliability = exposure / (exposure + prior)
    return reliability, (
        f"exposure_reliability[recipe_score]={reliability:.8f};"
        f"basis={basis};exposure={exposure:.6f};prior={prior:.6f};"
        "shrinks_toward=calibration_center"
    )


def _recipe_score(evidence: Any, population: tuple[Any, ...], recipe: _Recipe) -> tuple[float, tuple[str, ...]] | None:
    if recipe.required and not any(_signal(evidence, name) is not None for name in recipe.required):
        return None
    components: list[tuple[float, float, str]] = []
    provenance: list[str] = []
    for name, weight in recipe.signals:
        current = _signal(evidence, name)
        if current is None:
            continue
        summary = _signal_summary(population, name)
        if summary is None:
            continue
        median, scale = summary
        z_value = (current - median) / scale
        if name == "fg_stability" and bool(_source_map(evidence, "per_game").get("fg_percent_imputed")):
            imputed_reliability = _source_value(evidence, "per_game", "fg_percent_imputation_reliability")
            if imputed_reliability is not None:
                z_value *= max(0.0, min(1.0, imputed_reliability))
                provenance.append(f"imputed_fg_reliability={imputed_reliability:.8f}")
        components.append((z_value, weight, name))
        provenance.extend(_SIGNAL_PROVENANCE.get(name, (name,)))
        provenance.append(f"same_season_same_league_z[{name}]={z_value:.8f}")
    total_weight = sum(abs(weight) for _z, weight, _name in components)
    if total_weight <= 0.0:
        return None
    score = sum(z_value * weight for z_value, weight, _name in components) / total_weight
    reliability = _exposure_reliability(evidence)
    if reliability is not None:
        factor, reliability_key = reliability
        score *= factor
        provenance.append(reliability_key)
    return score, tuple(dict.fromkeys(provenance))


def _derive(field: str, evidence: Any, rows: Any, recipes: tuple[_Recipe, ...], *, tendency: bool) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    population = _population(evidence, rows)
    for recipe in recipes:
        if recipe.name.startswith("nbl_") and _league(evidence) != "NBL":
            continue
        scored = _recipe_score(evidence, population, recipe)
        if scored is None:
            continue
        score, evidence_keys = scored
        center, scale = _CALIBRATION[field]
        low, high = (0, 100) if tendency else (25, 99)
        value = max(low, min(high, int(round(center + score * scale))))
        source_rule = f"derive_{'tendency' if tendency else 'attribute'}_{field.lower()}"
        if recipe.name == "nbl_recorded_stability_discipline":
            source_rule += "_nbl_recorded_stability"
        if recipe.unavailable:
            source_rule += "_field_specific_context_substitute"
        provenance = (
            *evidence_keys,
            "population=same-season,same-league,GP>0",
            "pool_calibration=editor_capture_001+002;765 GP-valid packages;identity=(run_id,player_index);output-scale-only",
            f"recipe={recipe.name}",
            f"formula=center({center:.3f})+robust_weighted_z({score:.8f})*scale({scale:.3f})",
        )
        if field == "ROLLVSPOP":
            provenance += ("scale_direction=higher_roll;lower_pop",)
        if field == "TRANSITIONSPOTUP":
            provenance += ("scale_direction=higher_spot_up;lower_cut",)
        if recipe.unavailable:
            provenance += (
                f"unavailable_direct_source={recipe.unavailable}",
                f"substitute_source={recipe.substitute}",
                f"validity={recipe.validity}",
            )
        return {"value": value, "source_rule": source_rule, "evidence_keys": provenance}
    return None


def _intangibles_forward_value(rating: int) -> float:
    t = (rating - 25) / 74
    return _INTANGIBLES_VORP_MAX * (
        _INTANGIBLES_LINEAR_WEIGHT * t
        + _INTANGIBLES_TAIL_WEIGHT * (t**_INTANGIBLES_TAIL_EXPONENT)
    )


def _intangibles_rating_from_vorp(vorp: float | None) -> int:
    if vorp is None or vorp <= 0.0:
        return 25
    return min(range(25, 100), key=lambda rating: abs(_intangibles_forward_value(rating) - vorp))


def _nbl_population(evidence: Any, rows: Any) -> tuple[Any, ...]:
    season = _season(evidence)
    return tuple(
        row
        for row in rows
        if _gp(row) is not None
        and _league(row) == "NBL"
        and (not season or not _season(row) or _season(row) == season)
    )


def _nbl_team_key(row: Any, ordinal: int) -> str:
    team = _text_value(row, "season_info", "team").upper()
    return team or f"__ROW_{ordinal}"


def _identity_key(source: Any) -> tuple[str, str]:
    player_id = str(
        getattr(source, "player_id", "")
        or _text_value(source, "identity", "player_id")
        or _text_value(source, "season_info", "player_id")
    ).strip().upper()
    team = str(
        getattr(source, "team", "")
        or _text_value(source, "season_info", "team")
    ).strip().upper()
    return player_id, team


def _nbl_source_value(source: Any, namespace: str, key: str) -> float | None:
    if not isinstance(source, Mapping):
        return _source_value(source, namespace, key)
    nested = source.get(namespace)
    if isinstance(nested, Mapping) and (value := _optional_number(nested.get(key))) is not None:
        return value
    for prefix in _ROW_PREFIXES.get(namespace, (namespace,)):
        if (value := _optional_number(source.get(f"{prefix}.{key}"))) is not None:
            return value
    return _optional_number(source.get(key))


def _nbl_signal(source: Any, name: str) -> float | None:
    if name == "games_share":
        return _ratio(
            _nbl_source_value(source, "per_game", "g"),
            _nbl_source_value(source, "team_stats_per_game", "g"),
        )
    if name == "fta_per_game":
        return _nbl_source_value(source, "per_game", "fta_per_game")
    if name == "team_win_pct":
        wins = _nbl_source_value(source, "team_summary", "w")
        losses = _nbl_source_value(source, "team_summary", "l")
        if wins is None or losses is None or wins < 0.0 or losses < 0.0 or wins + losses <= 0.0:
            return None
        return wins / (wins + losses)
    if name == "team_point_differential":
        points = _nbl_source_value(source, "team_stats_per_game", "pts_per_game")
        opponent_points = _nbl_source_value(source, "opponent_stats_per_game", "opp_pts_per_game")
        return points - opponent_points if points is not None and opponent_points is not None else None
    if name == "nbl_scoring_share":
        return _ratio(
            _nbl_source_value(source, "per_game", "pts_per_game"),
            _nbl_source_value(source, "team_stats_per_game", "pts_per_game"),
        )
    return None


def _nbl_signal_population(rows: tuple[Any, ...], signal: str) -> tuple[float, ...]:
    if signal in {"team_win_pct", "team_point_differential"}:
        team_values: dict[str, float] = {}
        for ordinal, row in enumerate(rows):
            value = _nbl_signal(row, signal)
            if value is not None:
                team_values.setdefault(_nbl_team_key(row, ordinal), value)
        return tuple(sorted(team_values.values()))
    return tuple(sorted(value for row in rows if (value := _nbl_signal(row, signal)) is not None))


def _midrank_percentile(value: float, population: tuple[float, ...]) -> float | None:
    if len(population) < 2:
        return None
    left = bisect.bisect_left(population, value)
    right = bisect.bisect_right(population, value)
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


def _nbl_composite_score(
    source: Any,
    population: tuple[Any, ...],
    weights: tuple[tuple[str, float], ...],
    *,
    signal_populations: Mapping[str, tuple[float, ...]] | None = None,
    include_evidence: bool = True,
) -> tuple[float, tuple[str, ...]] | None:
    components: list[tuple[str, float, float]] = []
    evidence_keys: list[str] = []
    for signal, weight in weights:
        current = _nbl_signal(source, signal)
        ranked_population = (
            signal_populations.get(signal, ())
            if signal_populations is not None
            else _nbl_signal_population(population, signal)
        )
        if current is None or not ranked_population:
            return None
        percentile = _midrank_percentile(current, ranked_population)
        if percentile is None:
            return None
        components.append((signal, weight, percentile))
        if include_evidence:
            evidence_keys.extend(_SIGNAL_PROVENANCE[signal])
            evidence_keys.append(f"raw_{signal}={current:.8f}")
            evidence_keys.append(f"same_season_nbl_percentile[{signal}]={percentile:.8f}")
    return sum(weight * percentile for _signal_name, weight, percentile in components), tuple(evidence_keys)


def _nbl_calculation_table(evidence: Any, rows: Any) -> _NblCalculationTable:
    season = _season(evidence)
    cache_key = (id(rows), season)
    cached = _NBL_CALCULATION_TABLE_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]

    population = _nbl_population(evidence, rows)
    signals = tuple(dict.fromkeys(
        signal
        for weights in _NBL_WEIGHTS_BY_FIELD.values()
        for signal, _weight in weights
    ))
    signal_populations = {
        signal: _nbl_signal_population(population, signal)
        for signal in signals
    }
    composite_populations: dict[str, tuple[float, ...]] = {}
    composite_moments: dict[str, tuple[float, float]] = {}
    composite_winners: dict[str, tuple[str, str]] = {}
    for field, weights in _NBL_WEIGHTS_BY_FIELD.items():
        ranked = tuple(
            (result[0], _identity_key(row))
            for row in population
            if (
                result := _nbl_composite_score(
                    row,
                    population,
                    weights,
                    signal_populations=signal_populations,
                    include_evidence=False,
                )
            ) is not None
        )
        composites = tuple(sorted(score for score, _identity in ranked))
        composite_populations[field] = composites
        composite_moments[field] = (
            statistics.mean(composites) if composites else 0.0,
            statistics.pstdev(composites) if len(composites) >= 2 else 0.0,
        )
        if ranked:
            top_score = max(score for score, _identity in ranked)
            composite_winners[field] = min(identity for score, identity in ranked if score == top_score)
    table = _NblCalculationTable(
        population=population,
        signal_populations=signal_populations,
        composite_populations=composite_populations,
        composite_moments=composite_moments,
        composite_winners=composite_winners,
    )
    _NBL_CALCULATION_TABLE_CACHE[cache_key] = (rows, table)
    return table


@lru_cache(maxsize=None)
def _reference_moments(values: tuple[float, ...]) -> tuple[float, float]:
    return statistics.mean(values), statistics.pstdev(values)


def _derive_nbl_adjusted_attribute(
    field: str,
    evidence: Any,
    rows: Any,
    *,
    weights: tuple[tuple[str, float], ...],
) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    table = _nbl_calculation_table(evidence, rows)
    scored = _nbl_composite_score(
        evidence,
        table.population,
        weights,
        signal_populations=table.signal_populations,
    )
    if scored is None:
        return None
    composite, evidence_keys = scored
    composite_population = table.composite_populations.get(field, ())
    context = _source_map(evidence, "source_context")
    reference_key = _NBL_BAA_REFERENCE_KEYS[field]
    raw_reference = context.get(reference_key)
    if not isinstance(raw_reference, (list, tuple)):
        return None
    reference_values = tuple(sorted(
        number
        for value in raw_reference
        if (number := _optional_number(value)) is not None
    ))
    if len(reference_values) < 2 or len(composite_population) < 2:
        return None
    if field == "INTANGIBLES":
        percentile = _midrank_percentile(composite, composite_population)
        winner = table.composite_winners.get(field)
        if percentile is None or winner is None:
            return None
        mapped_value = max(25, min(99, int(round(_linear_percentile(reference_values, percentile)))))
        unique_league_maximum = composite == composite_population[-1] and _identity_key(evidence) == winner
        value = mapped_value
        mapping_keys = (
            f"same_season_nbl_composite_percentile={percentile:.8f}",
            f"unique_99_winner={winner[0]}:{winner[1]}",
            f"unique_99_applied={str(unique_league_maximum).lower()}",
            f"overlap_reference_count={len(reference_values)}",
            "mapping=round(linear_percentile(1947-1950_BAA_WS_path_values_for_exact_NBL_BAA_overlap_IDs,NBL_composite_rank));only_unique_league_winner_may_equal_99",
        )
    else:
        nbl_mean, nbl_sd = table.composite_moments[field]
        reference_mean, reference_sd = _reference_moments(reference_values)
        if nbl_sd <= 0.0 or reference_sd <= 0.0:
            return None
        standardized = (composite - nbl_mean) / nbl_sd
        value = max(25, min(99, int(round(reference_mean + standardized * reference_sd))))
        mapping_keys = (
            f"nbl_composite_mean={nbl_mean:.8f}",
            f"nbl_composite_population_sd={nbl_sd:.8f}",
            f"reference_mean={reference_mean:.8f}",
            f"reference_population_sd={reference_sd:.8f}",
            f"standardized_nbl_composite={standardized:.8f}",
            "mapping=round(BAA_mean+standardized_NBL_composite*BAA_population_sd);clamp=25..99",
        )
    weight_text = ",".join(f"{signal}:{weight:.2f}" for signal, weight in weights)
    return {
        "value": value,
        "score": composite,
        "source_rule": (
            "derive_attribute_intangibles_nbl_cross_league_overlap_calibrated"
            if field == "INTANGIBLES"
            else f"derive_attribute_{field.lower()}_nbl_team_record_counting_stats"
        ),
        "evidence_keys": tuple(dict.fromkeys((
            "season_info.lg",
            "league_rule=NBL",
            *evidence_keys,
            "population=same-season,NBL,GP>0",
            "team_context_population=unique_exact_team",
            f"weights={weight_text}",
            (
                f"reference={reference_key};1947-1950 exact-ID NBL/BAA overlap calibrated to BAA win-share path"
                if field == "INTANGIBLES"
                else f"reference={reference_key};same-season BAA generated output distribution"
            ),
            f"reference_count={len(reference_values)}",
            *mapping_keys,
        ))),
    }


def derive_attribute_hands(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("HANDS", evidence, league_player_rows, _HANDS_RECIPES, tendency=False)


def derive_attribute_hustle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _league(evidence) == "NBL":
        return _derive_nbl_adjusted_attribute(
            "HUSTLE",
            evidence,
            league_player_rows,
            weights=_NBL_HUSTLE_WEIGHTS,
        )
    return _derive("HUSTLE", evidence, league_player_rows, _HUSTLE_RECIPES, tendency=False)


def derive_attribute_intangibles(
    evidence: Any,
    *,
    league_player_rows: Any = (),
) -> dict[str, Any] | None:
    if _league(evidence) == "NBL":
        return _derive_nbl_adjusted_attribute(
            "INTANGIBLES",
            evidence,
            league_player_rows,
            weights=_NBL_INTANGIBLES_WEIGHTS,
        )
    if _gp(evidence) is None:
        return None
    raw_vorp = _source_value(evidence, "advanced", "vorp")
    if raw_vorp is not None:
        rating = _intangibles_rating_from_vorp(raw_vorp)
        state = "nonpositive" if raw_vorp <= 0.0 else "observed"
        return {
            "value": rating,
            "source_rule": "derive_attribute_intangibles",
            "evidence_keys": (
                "per_game.g",
                "advanced.vorp",
                f"raw_vorp_state={state}",
                f"raw_vorp={raw_vorp}",
                "mapping=integer_inverse_of_approved_0_12.47_vorp_curve",
            ),
        }

    # VORP is not computed before 1974. Same-season, same-league Win Shares preserve
    # the magnitude gap between early stars: a rank would put 18.6, 16.3, and 11.8
    # next to one another even though their contributed-win totals are far apart.
    # Dividing positive WS by the exact league maximum keeps the comparison inside
    # one schedule and league while retaining that spacing. Missing WS is unresolved.
    win_shares = _source_value(evidence, "advanced", "ws")
    if win_shares is None:
        return None
    population_rows = tuple(
        row
        for row in _population(evidence, league_player_rows)
        if _league(row) == _league(evidence)
        if _source_value(row, "advanced", "ws") is not None
    )
    population = sorted(
        value
        for row in population_rows
        if (value := _source_value(row, "advanced", "ws")) is not None
    )
    if not population:
        return None
    top_win_shares = population[-1]
    floor_win_shares = population[0]
    # Normalise across the league's real range rather than clamping at zero. Clamping
    # put every player at or below nothing on the same number -- 121 of 333 landed on
    # the attribute floor together, and a -0.1 season read identically to a -2.4 one.
    # Feerick's 18.6 down to Becker's -2.4 is 21 points of genuine separation.
    span = top_win_shares - floor_win_shares
    linear_score = (win_shares - floor_win_shares) / span if span > 0.0 else 0.0
    # And widen it. A league where the best player contributed eighteen wins and the
    # worst cost his team three is not a league of near-equals; a linear share still
    # crowds the middle, so the curve pushes the ends apart.
    magnitude_score = max(0.0, min(1.0, linear_score)) ** _INTANGIBLES_DISPARITY_EXPONENT
    mapped_value = max(25, min(99, int(round(25.0 + 74.0 * magnitude_score))))
    winner = (
        min(
            _identity_key(row)
            for row in population_rows
            if _source_value(row, "advanced", "ws") == top_win_shares
        )
        if top_win_shares > 0.0
        else ("", "")
    )
    unique_league_maximum = top_win_shares > 0.0 and win_shares == top_win_shares and _identity_key(evidence) == winner
    value = mapped_value
    return {
        "value": value,
        "score": magnitude_score,
        "source_rule": "derive_attribute_intangibles_historical_win_share_magnitude",
        "evidence_keys": (
            "per_game.g",
            "advanced.ws",
            "unavailable_direct_source=advanced.vorp (first computed for season 1974)",
            "substitute_evidence=same-season same-league win share magnitude",
            "validity=WS is recorded from 1947 and measures contributed wins; same-league "
            "maximum normalization preserves the spacing between early-season stars",
            f"raw_win_shares={win_shares}",
            f"same_league_max_win_shares={top_win_shares}",
            f"win_share_magnitude_score={magnitude_score:.8f}",
            f"unique_99_winner={winner[0]}:{winner[1]}",
            f"unique_99_applied={str(unique_league_maximum).lower()}",
            "population=exact_same-season,same-league,GP>0,win-share-recorded",
            f"same_league_min_win_shares={floor_win_shares}",
            f"win_share_linear_share={linear_score:.8f}",
            f"disparity_exponent={_INTANGIBLES_DISPARITY_EXPONENT:g}",
            "mapping=round(25+74*((WS-same_league_min_WS)/(same_league_max_WS-same_league_min_WS))^disparity_exponent);only_unique_league_winner_may_equal_99",
        ),
    }


def derive_attribute_potential(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def _derive_iso(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    return _derive(field, evidence, league_player_rows, _ISO_RECIPES, tendency=True)


def derive_tendency_isovsaveragedefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_iso("ISOVSAVERAGE", evidence, league_player_rows)


def derive_tendency_isovselitedefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_iso("ISOVSELITE", evidence, league_player_rows)


def derive_tendency_isovsgooddefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_iso("ISOVSGOOD", evidence, league_player_rows)


def derive_tendency_isovspoordefender(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive_iso("ISOVSPOOR", evidence, league_player_rows)


def derive_tendency_playdiscipline(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("PLAYDISCIPLINE", evidence, league_player_rows, _PLAY_DISCIPLINE_RECIPES, tendency=True)


def derive_tendency_rollvspop(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("ROLLVSPOP", evidence, league_player_rows, _ROLL_POP_RECIPES, tendency=True)


def derive_tendency_transitionspotup(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("TRANSITIONSPOTUP", evidence, league_player_rows, _TRANSITION_SPOTUP_RECIPES, tendency=True)


def _touch_source_value(source: Any, namespace: str, key: str) -> float | None:
    if isinstance(source, dict):
        prefixes = {
            "totals": "player_totals",
            "advanced": "player_advanced",
            "team_stats_per_game": "team_stats_per_game",
        }
        for candidate in (f"{namespace}.{key}", f"{prefixes[namespace]}.{key}"):
            if candidate in source:
                return _optional_number(source.get(candidate))
        return None
    values = getattr(source, namespace, {})
    return _optional_number(values.get(key)) if isinstance(values, dict) else None


def _touch_team_total(source: Any, field: str) -> float | None:
    per_game = _touch_source_value(source, "team_stats_per_game", f"{field}_per_game")
    games = _touch_source_value(source, "team_stats_per_game", "g")
    if per_game is None or games is None or games <= 0.0:
        return None
    return per_game * games


def _touch_team_share(source: Any, field: str) -> float | None:
    player_total = _touch_source_value(source, "totals", field)
    team_total = _touch_team_total(source, field)
    if player_total is None or team_total is None or team_total <= 0.0:
        return None
    return player_total / team_total


def _touch_component(source: Any, name: str) -> float | None:
    if name == "fga_share":
        return _touch_team_share(source, "fga")
    if name == "ast_share":
        return _touch_team_share(source, "ast")
    if name == "usg_percent":
        return _touch_source_value(source, "advanced", "usg_percent")
    if name == "fgm_share":
        return _touch_team_share(source, "fg")
    if name == "fta_share":
        return _touch_team_share(source, "fta")
    raise KeyError(name)


def _touch_component_population(rows: Any, name: str) -> tuple[float, ...]:
    return tuple(
        sorted(
            value
            for row in tuple(rows or ())
            if isinstance(row, dict) and (value := _touch_component(row, name)) is not None
        )
    )


def _touch_component_provenance(name: str, value: float, percentile: float) -> tuple[str, ...]:
    if name == "fga_share":
        paths = ("totals.fga", "team_stats_per_game.fga_per_game", "team_stats_per_game.g")
    elif name == "ast_share":
        paths = ("totals.ast", "team_stats_per_game.ast_per_game", "team_stats_per_game.g")
    elif name == "usg_percent":
        paths = ("advanced.usg_percent",)
    elif name == "fgm_share":
        paths = ("totals.fg", "team_stats_per_game.fg_per_game", "team_stats_per_game.g")
    else:
        paths = ("totals.fta", "team_stats_per_game.fta_per_game", "team_stats_per_game.g")
    return (*paths, f"{name}={value:.8f}", f"{name}_same_league_percentile={percentile:.8f}")


_NORMAL_DISTRIBUTION = statistics.NormalDist()
# Keeps the probit finite when a rank lands on exactly 0.0 or 1.0.
_RANK_PROBIT_LIMIT = 0.9995


def _value_from_rank(field: str, rank: float) -> int:
    """Score a 0-1 population rank through the same center/scale every rule uses.

    A rank is not a rating: multiplying it by 100 put the median player at 50
    whatever the tendency was. TOUCHES is centered at 40, so the rank has to become
    a z-score and go through the field's own scale.
    """
    center, scale = _CALIBRATION[field]
    bounded = min(max(float(rank), 1.0 - _RANK_PROBIT_LIMIT), _RANK_PROBIT_LIMIT)
    return max(0, min(100, int(round(center + _NORMAL_DISTRIBUTION.inv_cdf(bounded) * scale))))


def derive_tendency_touches(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    """Rank the player's share of team offensive involvement.

    FGA and AST use exact player-total / team-total shares. USG% remains direct
    because it is already a team-possession share while the player is on court.
    Missing components are omitted and the available authored weights are
    renormalized; missing values are never converted to zero.
    """
    weighted_components = (
        ("fga_share", 0.45),
        ("ast_share", 0.30),
        ("usg_percent", 0.25),
    )
    available: list[tuple[str, float, float]] = []
    provenance: list[str] = []
    for name, weight in weighted_components:
        value = _touch_component(evidence, name)
        population = _touch_component_population(league_player_rows, name)
        if value is None or not population:
            continue
        percentile = bisect.bisect_right(population, value) / len(population)
        available.append((name, weight, percentile))
        provenance.extend(_touch_component_provenance(name, value, percentile))
    source_rule = "derive_tendency_touches_team_offensive_share"
    weight_provenance = "touches_weights=fga_team_share:0.45,ast_team_share:0.30,usg_percent:0.25"
    if not available:
        # Historical NBL rows do not contain FGA, AST, or USG%. Use the closest
        # surviving team-relative scoring-opportunity evidence: made-field-goal
        # share plus free-throw-attempt share. FGM is imperfect because misses are
        # unavailable, so this substitute is isolated and explicitly provenanced.
        fallback_components = (("fgm_share", 0.65), ("fta_share", 0.35))
        for name, weight in fallback_components:
            value = _touch_component(evidence, name)
            population = _touch_component_population(league_player_rows, name)
            if value is None or not population:
                continue
            percentile = bisect.bisect_right(population, value) / len(population)
            available.append((name, weight, percentile))
            provenance.extend(_touch_component_provenance(name, value, percentile))
        source_rule = "derive_tendency_touches_historical_team_scoring_opportunity_share"
        weight_provenance = "touches_historical_weights=fgm_team_share:0.65,fta_team_share:0.35"
        provenance.extend(
            (
                "unavailable_exact_touch_inputs=totals.fga,totals.ast,advanced.usg_percent",
                "historical_substitute=player_fgm_share_and_fta_share_of_exact_team_totals",
                "historical_substitute_reason=FGA_AST_USG_unrecorded;FGM_and_FTA_preserve_team_relative_scoring_opportunity",
            )
        )
    available_weight = sum(weight for _name, weight, _percentile in available)
    if available_weight <= 0.0:
        return None
    score = sum(weight * percentile for _name, weight, percentile in available) / available_weight
    return {
        "value": _value_from_rank("TOUCHES", score),
        "source_rule": source_rule,
        "evidence_keys": (
            *provenance,
            weight_provenance,
            *(("usg_percent_semantics=already_team_possession_share_while_on_court",) if source_rule == "derive_tendency_touches_team_offensive_share" else ()),
            f"available_weight={available_weight:.8f}",
            "missing_components=omitted_and_available_weights_renormalized",
            "comparison_population=exact_same_season_same_league",
        ),
    }


__all__ = [
    "derive_attribute_hands",
    "derive_attribute_hustle",
    "derive_attribute_intangibles",
    "derive_attribute_potential",
    "derive_tendency_isovsaveragedefender",
    "derive_tendency_isovselitedefender",
    "derive_tendency_isovsgooddefender",
    "derive_tendency_isovspoordefender",
    "derive_tendency_playdiscipline",
    "derive_tendency_rollvspop",
    "derive_tendency_touches",
    "derive_tendency_transitionspotup",
]
