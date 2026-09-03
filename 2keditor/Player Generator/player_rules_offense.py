from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Iterable

from nbl_baa_projection import REFERENCE_CONTEXT_KEY as NBL_BAA_REFERENCE_CONTEXT_KEY
from player_era_context import player_era_context
from player_era_role import era_role_playstyle_enabled as _era_role_playstyle_on
from player_rules_athleticism import derive_attribute_vertical, derive_attribute_vertical_unadjusted


_POPULATION_CACHE: dict[
    tuple[int, int],
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
_NBL_ASSIST_RAW_CACHE: dict[
    tuple[int, str, str],
    tuple[object, dict[tuple[str, str], float], tuple[float, ...]],
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
    # Stretched from the pool scale of 28.2 so the best handler in a season reaches
    # 99. At 28.2 the whole league sat inside 27-76: the field ranked players fine
    # but never used the top third of its own range, so the league's best ball
    # handler read as merely above average.
    "BALLCONTROL": (52.0, 70.0),
    "DRAWFOUL": (56.0, 25.9),
    "OFFENSIVECONSISTENCY": (57.0, 25.9),
    "PASSACCURACY": (53.0, 25.9),
    "PASSIQ": (54.0, 27.4),
    "PASSVISION": (47.0, 25.9),
    # Widened from 25.9 so the outright best shot selector in a season reaches 99.
    # Feerick shot .401 in a league averaging .279 and topped out at 90.
    "IQSHOT": (57.0, 34.0),
    "3POINT": (30.0, 20.8),
    "CLOSESHOT": (62.0, 23.7),
    "DRIVINGDUNK": (45.0, 18.5),
    "DRIVINGLAYUP": (58.0, 23.0),
    "MIDRANGE": (52.0, 16.3),
    # Raised from a centre of 49. Restoring the recipe chain fixed *who* rates highly
    # on post control but left the field sitting low across the board, in an era
    # where the post was where offence actually happened.
    "POSTCONTROL": (58.0, 27.4),
    "POSTFADE": (45.0, 11.9),
    "POSTHOOK": (48.0, 22.2),
    "STANDINGDUNK": (37.0, 19.3),
}

# Centers and scales come from Docs/ATD Committee Official Master Tendency (1).xlsx:
# each field's center is the middle of the sheet's baseline range and its scale that
# range's width. They replaced values frozen from a captured 2K roster, which the
# sheet explicitly rules out as a realism target ("Default 2K values are engine
# evidence only... they are not the ATD realism scale"). The five directional
# three-point zone slices are not named on the sheet and keep their old centers.
_TENDENCY_CALIBRATION: dict[str, tuple[float, float]] = {
    "SHOT": (37.5, 11.12),  # ATD Shot 30-45, cap 75
    "3POINTSHOT": (35.0, 14.83),  # ATD Shot Three 25-45, cap 75
    "CLOSESHOT": (27.5, 11.12),  # ATD Shot Close 20-35, cap 60
    "MIDRANGESHOT": (10.0, 7.41),  # ATD Shot Mid 5-15, cap 45
    "TRIPLETHREATIDLE": (22.5, 18.53),  # ATD Triple Threat Idle 10-35, cap 65
    "TRIPLETHREATJAB": (20.0, 14.83),  # ATD Triple Threat Jab Step 10-30, cap 55
    "TRIPLETHREATPUMPFake": (17.5, 11.12),  # ATD Triple Threat Pump Fake 10-25, cap 55
    "TRIPLETHREATSHOT": (27.5, 11.12),  # ATD Triple Threat Shoot 20-35, cap 55
    "SETUPDRIBBLE": (37.5, 11.12),  # ATD No Setup Dribble 30-45, cap 85
    "SETUPWITHHESITATION": (15.0, 14.83),  # ATD Setup with Hesitation 5-25, cap 55
    "SETUPWITHSIZEUP": (15.0, 14.83),  # ATD Setup with Size-Up 5-25, cap 55
    "DRIVE": (35.0, 14.83),  # ATD Drive 25-45, cap 75
    "DRIVINGCROSSOVER": (20.0, 14.83),  # ATD Driving Crossover 10-30, cap 60
    "DRIVINGDOUBLECROSSOVER": (5.0, 7.41),  # ATD Driving Double Crossover 0-10, cap 40
    "DRIVINGSPIN": (12.5, 11.12),  # ATD Driving Spin 5-20, cap 50
    "DRIVINGHALFSPIN": (7.5, 11.12),  # ATD Driving Half Spin 0-15, cap 45
    "DRIVINGSTEPBACK": (12.5, 11.12),  # ATD Driving Step Back 5-20, cap 55
    "DRIVINGBEHINDTHEBACK": (10.0, 7.41),  # ATD Driving Behind The Back 5-15, cap 50
    "DRIVINGDRIBBLEHESITATION": (20.0, 14.83),  # ATD Driving Dribble Hesitation 10-30, cap 65
    "DRIVINGINANDOUT": (15.0, 14.83),  # ATD Drive In & Out 5-25, cap 65
    "NODRIVINGDRIBBLEMOVE": (37.5, 11.12),  # ATD No Drive Dribble Move 30-45, cap 90
    "ATTACKSTRONGONDRIVE": (62.5, 18.53),  # ATD Attack Strong on Drive 50-75, cap 90
    "OFFSCREENDRIVE": (12.5, 11.12),  # ATD Off-Screen Drive 5-20, cap 60
    "SPOTUPDRIVE": (30.0, 14.83),  # ATD Spot-Up Drive 20-40, cap 70
    "ALLEYOOOPASS": (15.0, 14.83),  # ATD Alley-Oop Pass 5-25, cap 65
    "DISHTOOPENMAN": (35.0, 14.83),  # ATD Dish to Open Man 25-45, cap 65
    "FLASHYPASS": (15.0, 14.83),  # ATD Flashy Pass 5-25, cap 60
    "POSTUP": (27.5, 25.95),  # ATD Post Up 10-45, cap 85
    "POSTBACKDOWN": (27.5, 25.95),  # ATD Post Back Down 10-45, cap 80
    "POSTAGGRESSIVEBACKDOWN": (20.0, 14.83),  # ATD Post Aggressive Back Down 10-30, cap 70
    "POSTFACEUP": (22.5, 18.53),  # ATD Post Face Up 10-35, cap 60
    "POSTSPIN": (20.0, 14.83),  # ATD Post Spin 10-30, cap 55
    "POSTDRIVE": (20.0, 14.83),  # ATD Post Drive 10-30, cap 55
    "POSTHOPSHOT": (10.0, 14.83),  # ATD Post Hop Shot 0-20, cap 45
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


# User-observed NBA 2K close-range response: a close-shot Attribute of 99 finishes
# roughly 55%, 25 finishes roughly 1%, near-linear in between.
_CLOSE_RANGE_RESPONSE_ANCHORS: tuple[tuple[int, float], ...] = ((25, 0.01), (99, 0.55))

# User-observed NBA 2K standing-dunk response, given a competent playmaker feeding the
# roll: a modern big finishing anywhere from ~55% to ~70% at the rim reads as a 99
# STANDINGDUNK; it falls off below that.
_RIM_FINISH_RESPONSE_ANCHORS: tuple[tuple[int, float], ...] = ((25, 0.05), (65, 0.32), (99, 0.55))


def _rating_from_anchors(anchors: tuple[tuple[int, float], ...], make_probability: float) -> int:
    target = max(0.0, min(1.0, float(make_probability)))
    if target <= anchors[0][1]:
        return anchors[0][0]
    for (rating0, probability0), (rating1, probability1) in zip(anchors, anchors[1:]):
        if target <= probability1:
            rating = rating0 + (target - probability0) * (rating1 - rating0) / (probability1 - probability0)
            return max(25, min(99, int(round(rating))))
    return anchors[-1][0]


def close_range_rating_for_make_probability(make_probability: float) -> int:
    return _rating_from_anchors(_CLOSE_RANGE_RESPONSE_ANCHORS, make_probability)


def rim_finish_rating_for_make_probability(make_probability: float) -> int:
    return _rating_from_anchors(_RIM_FINISH_RESPONSE_ANCHORS, make_probability)

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


#: A shooting percentage is undefined at zero attempts, but "took no shots" is an
#: observation, not a gap. The repository's missing-is-not-zero rule protects leagues
#: that never recorded attempts -- the 1947 NBL has no FGA column at all -- and must
#: not be stretched to cover a player whose zero attempts are written in the box
#: score. Ken Corley played three games, took no shots and scored no points; dropping
#: his shooting terms as "unknown" left position alone to carry post control and put
#: a centre who never scored near the top of the field.
_ZERO_ATTEMPT_PERCENTAGES = {
    "per_game.fg_percent": ("per_game.fga_per_game", "totals.fga"),
    "per_game.ft_percent": ("per_game.fta_per_game", "totals.fta"),
    "per_game.e_fg_percent": ("per_game.fga_per_game", "totals.fga"),
    "advanced.ts_percent": ("per_game.fga_per_game", "totals.fga"),
}


def _recorded_zero_attempt_percentage(source: Any, path: str) -> bool:
    """True when the attempts behind this percentage are recorded and equal zero."""

    for attempts_path in _ZERO_ATTEMPT_PERCENTAGES.get(path, ()):
        attempts = _raw_basic_value(source, attempts_path)
        if attempts is not None:
            return attempts == 0.0
    return False


def _basic_value(source: Any, path: str) -> float | None:
    value = _raw_basic_value(source, path)
    if value is None and path in _ZERO_ATTEMPT_PERCENTAGES and _recorded_zero_attempt_percentage(source, path):
        return 0.0
    return value


def _raw_basic_value(source: Any, path: str) -> float | None:
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


def _baa_reference_values(evidence: Any, field_key: str) -> tuple[float, ...]:
    """Every BAA reference value for this field, league-wide.

    This used to take a position family and return only the BAA players carrying that
    label, so an NBL player's target distribution was chosen by the letter beside his
    name. There is no family argument any more.
    """

    context = getattr(evidence, "source_context", {})
    references = context.get(NBL_BAA_REFERENCE_CONTEXT_KEY) if isinstance(context, Mapping) else None
    if not isinstance(references, (tuple, list)):
        return ()
    values = []
    for reference in references:
        if not isinstance(reference, Mapping):
            continue
        targets = reference.get("targets")
        value = targets.get(field_key) if isinstance(targets, Mapping) else None
        if isinstance(value, (int, float)):
            values.append(float(value))
    return tuple(sorted(values))


def _midrank(value: float, values: tuple[float, ...]) -> float | None:
    if len(values) < 2:
        return None
    left = bisect.bisect_left(values, value)
    right = bisect.bisect_right(values, value)
    return ((left + right - 1) / 2.0) / (len(values) - 1)


def _linear_quantile(values: tuple[float, ...], percentile: float) -> float:
    position = max(0.0, min(1.0, percentile)) * (len(values) - 1)
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


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


#: Driving dunks belong to the 6'6"-6'8" build: tall enough to finish above the rim
#: off one foot, still quick and springy enough to get there off a live dribble. Both
#: smaller guards and true seven-foot pivots fall away from it, so height enters this
#: field as distance from a band rather than as "taller is better".
_DUNK_HEIGHT_BAND = (78.0, 80.0)
_DUNK_HEIGHT_FALLOFF_INCHES = 8.0
#: Where the low side of the dunk curve reaches zero: six foot.
_DUNK_ZERO_HEIGHT = 72.0
#: The tall side declines toward this rather than to zero.
_DUNK_TALL_FLOOR = 0.45
#: Where standing dunk reaches its full ceiling: 6'10".
_STANDING_DUNK_FULL_HEIGHT = 82.0


#: Dunking off a live dribble is a young, light-framed act. Height sets the band, and
#: mass carried above what the frame implies plus years past the athletic peak both
#: take a player out of it -- Ed Sadowski at 6'5", 240lb and 31 topped this field on
#: height alone.
_DUNK_EXPECTED_WEIGHT_INTERCEPT = 140.0
_DUNK_EXPECTED_WEIGHT_PER_INCH = 4.2
_DUNK_WEIGHT_TOLERANCE = 80.0
_DUNK_PEAK_AGE = 26.0
_DUNK_AGE_DECAY_PER_YEAR = 0.04
_DUNK_MIN_AGE_SHARE = 0.55


def _dunk_height_fit(height: float | None) -> float | None:
    if height is None:
        return None
    low, high = _DUNK_HEIGHT_BAND
    if low <= height <= high:
        return 1.0
    if height < low:
        # Reaches zero exactly at six foot, so a player that size carries no dunk
        # evidence at all rather than being cut off by a rule.
        return max(0.0, (height - _DUNK_ZERO_HEIGHT) / (low - _DUNK_ZERO_HEIGHT))
    # The tall side declines but never vanishes. A seven-footer dunks; he just does it
    # off two feet in traffic rather than off a live dribble, which is what this field
    # is asking about.
    return max(_DUNK_TALL_FLOOR, 1.0 - (height - high) / _DUNK_HEIGHT_FALLOFF_INCHES)


def _dunk_athletic_fit(source: Any) -> float | None:
    height = _basic_value(source, "identity.ht_in_in")
    fit = _dunk_height_fit(height)
    if fit is None:
        return None
    weight = _basic_value(source, "identity.wt")
    if weight is not None and height is not None:
        expected = _DUNK_EXPECTED_WEIGHT_INTERCEPT + _DUNK_EXPECTED_WEIGHT_PER_INCH * (height - 60.0)
        excess = max(0.0, weight - expected)
        fit *= max(0.4, 1.0 - excess / _DUNK_WEIGHT_TOLERANCE)
    age = _basic_value(source, "season_info.age")
    if age is not None:
        fit *= max(_DUNK_MIN_AGE_SHARE, 1.0 - _DUNK_AGE_DECAY_PER_YEAR * max(0.0, age - _DUNK_PEAK_AGE))
    return fit


#: Reading a defence is learned. Pass IQ carries an experience term that Pass Vision
#: does not, which is what lets the two fields cross: a veteran distributor can out-
#: think a quicker one who sees more.
_PASSING_EXPERIENCE_ONSET = 21.0
_PASSING_EXPERIENCE_SPAN = 12.0


def _derived_value(source: Any, name: str) -> float | None:
    if name == "passing_experience":
        age = _basic_value(source, "season_info.age")
        if age is None:
            return None
        return max(0.0, min(1.0, (age - _PASSING_EXPERIENCE_ONSET) / _PASSING_EXPERIENCE_SPAN))
    if name == "turnover_rate_per_36":
        per_36 = _basic_value(source, "per_36.tov_per_36_min")
        if per_36 is not None:
            return per_36
        per_game = _basic_value(source, "per_game.tov_per_game")
        minutes = _basic_value(source, "per_game.mp_per_game")
        if per_game is None or minutes is None or minutes <= 0.0:
            return None
        return per_game * 36.0 / minutes
    if name == "dunk_height_fit":
        return _dunk_athletic_fit(source)
    if name == "attempt_share":
        return _ratio(_basic_value(source, "totals.fga"), _team_total(source, "fga"))
    if name == "scoring_share":
        return _ratio(_basic_value(source, "totals.pts"), _team_total(source, "pts"))
    if name == "team_win_pct":
        wins = _basic_value(source, "team_summary.w")
        losses = _basic_value(source, "team_summary.l")
        return _ratio(wins, (wins or 0.0) + (losses or 0.0))
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
        return _ratio(
            _basic_value(source, "per_game.fta_per_game"),
            _basic_value(source, "per_game.fga_per_game"),
        )
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
    """Every same-season player in the selected scope.

    The scope is the comparison, deliberately. Selecting "All leagues" means ranking
    these players against each other, so an NBL player is compared to the full pull
    wherever the signal exists in both leagues; selecting one league compares him only
    to that league. A player's card therefore depends on the scope he was generated
    under, which is the intent -- comparing a 1947 NBL guard only to other NBL guards
    is what inflated them against their BAA counterparts in the first place.
    """

    season = _season(evidence)
    cache_key = (id(rows), season)
    cached = _POPULATION_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    population = tuple(
        row
        for row in rows
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
    "ows_only": ("advanced.ows",),
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
    "contested_midrange_frequency": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "drive_pullup_midrange_frequency": ("derived.mid_attempt_rate", "derived.unassisted_two_rate"),
    "off_screen_shot_action": ("shooting.percent_assisted_x2p_fg", "shooting.percent_assisted_x3p_fg"),
    "spot_up_shot_action": ("shooting.percent_assisted_x2p_fg", "shooting.percent_assisted_x3p_fg"),
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
    if clean in {"per_game.fg_percent", "per_game.e_fg_percent"} and bool(_basic_value(source, "per_game.fg_percent_imputed")):
        imputed = _basic_value(source, "per_game.fg_percent_imputation_reliability")
        if imputed is not None:
            reliability *= max(0.0, min(1.0, imputed))
            basis += f";imputed_fg_reliability={imputed:.8f}"
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
    # Renormalising onto whatever signals happened to resolve treats a partial recipe
    # as if it were complete. Ken Corley played three games, took no shots and had no
    # recorded position, so both shooting terms of the post-control recipe dropped out
    # and role.post carried 82% of a field it contributes 45% to -- a centre who never
    # scored came out at 97. Shrink the score toward the population mean in proportion
    # to how much of the recipe's declared weight actually resolved, so a rule running
    # on a fraction of its evidence produces a correspondingly unremarkable value.
    declared_weight = sum(abs(weight) for _key, weight in recipe.signals)
    completeness = total_weight / declared_weight if declared_weight > 0.0 else 1.0
    completeness_keys: tuple[str, ...] = ()
    if completeness < 1.0:
        score *= completeness
        completeness_keys = (
            f"recipe_evidence_completeness={completeness:.6f}",
            "partial_recipe_policy=shrink_toward_population_mean_by_resolved_weight_share",
        )
    evidence_keys = (*tuple(
        dict.fromkeys(
            source_path
            for _value_z, _weight, key in components
            for source_path in _provenance_sources(key.lstrip("!"))
        )
    ), *tuple(dict.fromkeys(reliability_evidence)), *completeness_keys)
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
        reliability = _exposure_reliability(evidence, key)
        if reliability is not None:
            factor, reliability_key = reliability
            directed_percentile = 0.5 + (directed_percentile - 0.5) * factor
            rank_evidence.append(reliability_key)
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


def _unrecorded_assist_raw_value(
    field: str,
    source: dict[str, Any],
    population: tuple[dict[str, Any], ...],
) -> float | None:
    # Scored once. This used to re-score the player under each of his listed position
    # families and keep the highest, so a "G-F" outscored a "G" on the strength of the
    # second letter. The recipe no longer reads position, so every branch returned the
    # same number and the maximum was over a list of identical values.
    recipe = next(recipe for recipe in _ATTR_RECIPES[field] if recipe.name.startswith("unrecorded_assist_era_"))
    center, scale = _ATTRIBUTE_CALIBRATION[field]
    scored = _recipe_score(source, population, recipe)
    if scored is None:
        return None
    return float(max(25, min(99, int(round(center + scored[0] * scale)))))


#: Matches nbl_baa_projection._TEAM_SUCCESS_BLEND_WEIGHT. The passing fields kept
#: this blend while the projection owned them; it moves with them.
_NBL_TEAM_SUCCESS_BLEND_WEIGHT = 0.40


def _nbl_team_win_pct(source: Any) -> float | None:
    wins = _value(source, "team_summary.w")
    losses = _value(source, "team_summary.l")
    if wins is None or losses is None or wins < 0.0 or losses < 0.0 or wins + losses <= 0.0:
        return None
    return wins / (wins + losses)


def _nbl_team_win_percentile(evidence: Any, population: tuple[dict[str, Any], ...]) -> float | None:
    """Where this player's team sits among same-season NBL teams, by record."""

    current = _nbl_team_win_pct(evidence)
    if current is None:
        return None
    by_team: dict[str, float] = {}
    for ordinal, row in enumerate(population):
        team = str(
            row.get("player_season_info.team") or row.get("team") or f"__ROW_{ordinal}"
        ).strip().upper()
        value = _nbl_team_win_pct(row)
        if value is not None:
            by_team.setdefault(team, value)
    ordered = tuple(sorted(by_team.values()))
    if len(ordered) < 2:
        return None
    return _midrank(current, ordered)


def nbl_baa_assist_calibrated_value(
    field: str,
    evidence: Any,
    league_player_rows: Any,
) -> tuple[float, tuple[str, ...]] | None:
    if _league(evidence) != "NBL" or _recorded_assists_available(evidence):
        return None
    # Same-season NBL only. _population filters by season but not league, so under
    # the "All leagues" scope it also carries the BAA rows and every z-score below
    # would shift with the selected league -- the same player generating different
    # ratings depending on a UI filter. project_nbl_fields already scopes its own
    # source rows this way; this keeps the direct NBL recipes scope-invariant too.
    population = tuple(
        row for row in _population(evidence, league_player_rows) if _league(row) == "NBL"
    )
    # League-wide on both sides. This mapped an NBL player's rank among his own listed
    # position onto the BAA distribution for that same position, so the label picked both
    # his peer group and his target -- a "G" and a "C" with identical box scores landed in
    # different places for no reason the evidence supports.
    reference_values = _baa_reference_values(evidence, f"Attributes/{field}")
    player_id = str(getattr(evidence, "player_id", "") or "").strip().upper()
    team = str(getattr(evidence, "team", "") or "").strip().upper()
    cache_key = (id(population), field)
    cached = _NBL_ASSIST_RAW_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        raw_by_key, ordered_raw = cached[1], cached[2]
    else:
        raw_by_key: dict[tuple[str, str], float] = {}
        for row in population:
            if _league(row) != "NBL":
                continue
            raw = _unrecorded_assist_raw_value(field, row, population)
            if raw is None:
                continue
            row_player_id = str(row.get("player_season_info.player_id") or row.get("player_id") or "").strip().upper()
            row_team = str(row.get("player_season_info.team") or row.get("team") or "").strip().upper()
            raw_by_key[(row_player_id, row_team)] = raw
        ordered_raw = tuple(sorted(raw_by_key.values()))
        _NBL_ASSIST_RAW_CACHE[cache_key] = (population, raw_by_key, ordered_raw)
    current_raw = raw_by_key.get((player_id, team))
    if current_raw is None or len(ordered_raw) < 2 or len(reference_values) < 2:
        return None
    percentile = _midrank(current_raw, ordered_raw)
    if percentile is None:
        return None
    individual = _linear_quantile(reference_values, percentile)

    # The projection blended these same passing fields 40% with team success, and
    # taking them out of the projection took the blend with them: NBL team attribute
    # means stopped tracking team record and Detroit, 4-40, was no longer the floor.
    # A season's worth of unrecorded assists is thin individual evidence, and how much
    # a team won is real evidence about the players on it, so the blend is restored
    # here against the same league-wide BAA reference distribution.
    team_percentile = _nbl_team_win_percentile(evidence, population)
    if team_percentile is None:
        return individual, (
            "nbl_unrecorded_assist_scope=league_wide;no_position_family",
            f"nbl_unrecorded_assist_raw_median={statistics.median(ordered_raw):.8f}",
            f"baa_recorded_assist_target_median={statistics.median(reference_values):.8f}",
            f"baa_recorded_assist_reference_count={len(reference_values)}",
            f"nbl_unrecorded_assist_raw_percentile={percentile:.8f}",
            "team_success_blend=unavailable_no_same_season_nbl_team_record",
            "mapping=BAA_recorded_assist_quantile(NBL_unrecorded_assist_raw_percentile)",
        )
    team_value = _linear_quantile(reference_values, team_percentile)
    value = (
        (1.0 - _NBL_TEAM_SUCCESS_BLEND_WEIGHT) * individual
        + _NBL_TEAM_SUCCESS_BLEND_WEIGHT * team_value
    )
    return value, (
        "nbl_unrecorded_assist_scope=league_wide;no_position_family",
        f"nbl_unrecorded_assist_raw_median={statistics.median(ordered_raw):.8f}",
        f"baa_recorded_assist_target_median={statistics.median(reference_values):.8f}",
        f"baa_recorded_assist_reference_count={len(reference_values)}",
        f"nbl_unrecorded_assist_raw_percentile={percentile:.8f}",
        "team_summary.w",
        "team_summary.l",
        f"individual_value={individual:.8f}",
        f"same_season_nbl_team_win_percentile={team_percentile:.8f}",
        f"team_success_reference_value={team_value:.8f}",
        "team_success_reference=league_wide_BAA_recorded_assist_distribution",
        f"team_success_blend_weight={_NBL_TEAM_SUCCESS_BLEND_WEIGHT:.2f}",
        "mapping=round("
        f"{1.0 - _NBL_TEAM_SUCCESS_BLEND_WEIGHT:.2f}*BAA_recorded_assist_quantile(NBL_raw_percentile)+"
        f"{_NBL_TEAM_SUCCESS_BLEND_WEIGHT:.2f}*BAA_recorded_assist_quantile(NBL_team_win_percentile))",
    )


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
        "derived.team_win_pct": ("team_summary.w", "team_summary.l"),
        "derived.assist_share": ("totals.ast", "team_stats_per_game.ast_per_game", "team_stats_per_game.g"),
        "derived.assist_decision_efficiency": ("per_game.ast_per_game", "per_game.tov_per_game"),
        "derived.foul_pressure": (
            "advanced.f_tr",
            "totals.fta",
            "totals.fga",
            "per_game.fta_per_game",
            "per_game.fga_per_game",
        ),
        "derived.three_attempt_rate": ("advanced.x3p_ar", "totals.x3pa", "totals.fga"),
        "derived.passing_experience": ("season_info.age",),
        "derived.turnover_rate_per_36": ("per_36.tov_per_36_min", "per_game.tov_per_game", "per_game.mp_per_game"),
        "derived.dunk_height_fit": ("identity.ht_in_in", "identity.wt", "season_info.age"),
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
        "population=same-season,selected-scope,GP>0",
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
        if recipe.name.startswith("nbl_") and _league(evidence) != "NBL":
            continue
        if (
            field in {"BALLCONTROL", "PASSACCURACY", "PASSIQ", "PASSVISION"}
            and not _recorded_assists_available(evidence)
            and not recipe.name.startswith("unrecorded_assist_era_")
        ):
            continue
        # OFFENSIVECONSISTENCY is offensive win shares min-maxed across the league's real
        # range, not a rank. Going 1, 2, 3 down the order throws away the size of the
        # gaps: the distance between the league's best offensive player and the second
        # best is evidence, and a rank reports it as one step -- the same step it reports
        # between the 40th and the 41st. The league's highest OWS is the only 99 and its
        # lowest is the only 25.
        if field == "OFFENSIVECONSISTENCY" and not tendency:
            own_league = _league(evidence)
            league_ows = sorted(
                value
                for row in population
                if _league(row) == own_league and (value := _value(row, "advanced.ows")) is not None
            )
            own_ows = _value(evidence, "advanced.ows")
            if own_ows is None or len(league_ows) < 2:
                continue
            low, high = league_ows[0], league_ows[-1]
            if high - low <= 0.0:
                continue
            score = (own_ows - low) / (high - low)
            evidence_keys = (
                "advanced.ows",
                f"ows={own_ows:.8f}",
                f"same_league_min_ows={low:.8f}",
                f"same_league_max_ows={high:.8f}",
                f"ows_magnitude_score={score:.8f}",
                "rank_source=ows_minmax_not_rank",
            )
            resolved_source_rule = (
                f"{source_rule}_field_specific_context_substitute"
                if recipe.unavailable
                else source_rule
            )
            provenance = (
                *evidence_keys,
                "population=same-season,selected-scope,GP>0",
                f"recipe={recipe.name}",
                f"ows_magnitude_mapping=round(25+74*(ows-min)/(max-min))",
            )
            value = 25.0 + 74.0 * score
            provenance += ("mapping=round(25+74*same_season_same_league_rank_score)",)
            if recipe.unavailable:
                provenance += (
                    f"unavailable_direct_source={recipe.unavailable}",
                    f"substitute_source={recipe.substitute}",
                    f"validity={recipe.why_valid}",
                )
            return {
                "value": max(25, min(99, int(round(value)))),
                "source_rule": resolved_source_rule,
                "evidence_keys": provenance,
            }
        scored = _recipe_score(evidence, population, recipe)
        if scored is None:
            continue
        score, evidence_keys = scored
        center, scale = calibration
        value = center + score * scale
        # Attributes only. These anchors convert execution (FG%, FT%, AST/G) into a
        # rating, and CLOSESHOT / DRIVINGDUNK / DRIVINGLAYUP / STANDINGDUNK name both
        # an attribute and a tendency. Applying an execution anchor to a tendency
        # asks how *well* a player finishes in order to decide how *often* he tries,
        # which the ATD sheet separates: attributes determine effectiveness,
        # tendencies create attempts. It also pushed those tendencies past their ATD
        # caps regardless of the calibration band.
        absolute_evidence: tuple[str, ...] = ()
        if not tendency:
            value, absolute_evidence = _absolute_attribute_adjustment(field, evidence, value, population)
        resolved_source_rule = (
            f"{source_rule}_field_specific_context_substitute"
            if recipe.unavailable
            else source_rule
        )

        return _resolved(resolved_source_rule, value, (*evidence_keys, *absolute_evidence), recipe, tendency=tendency)
    return None


#: A ceiling should only bind when there is evidence behind it. With little exposure
#: the ceiling relaxes upward toward the attribute maximum rather than collapsing to
#: the calibration centre, which is what a shrink-toward-centre does to a *cap* and
#: which flattened whole fields onto one value. A recorded zero is the exception: no
#: made shot is unambiguous however few the attempts, so it binds at full strength.
def _execution_reliability(percentage: float | None, exposure: float | None, prior: float) -> float:
    if percentage is not None and percentage <= 0.0:
        return 1.0
    if exposure is None or exposure <= 0.0:
        return 0.0
    return exposure / (exposure + prior)


def _relaxed_ceiling(ceiling: float, reliability: float) -> float:
    return ceiling + (1.0 - max(0.0, min(1.0, reliability))) * (99.0 - ceiling)


#: Fields where recorded shooting is an upper bound rather than one term in a blend.
#: DRAWFOUL and IQSHOT stay blended: drawing contact and choosing shots are not the
#: same claim as making them.
# DRIVINGLAYUP and POSTFADE are deliberately absent. A layup is the one shot every
# player can make, and a fade is a touch shot -- neither should fall off a cliff from
# 48 to 25 because a bench player's season shows no made field goal. They keep the
# blend, which moves them down smoothly instead.
_EXECUTION_CEILING_FIELDS = frozenset({
    "DRIVINGDUNK",
    "POSTHOOK",
    "STANDINGDUNK",
})


_POST_BODY_CACHE: dict[int, tuple[object, tuple[float, ...]]] = {}


def _standing_dunk_height_fit(source: Any) -> float | None:
    """Standing dunk rises with reach; it does not peak and fall away.

    The driving-dunk bell is about getting up off a live dribble, which is a 6'6"-6'8"
    act. Dunking from a standstill is pure reach, so the curve only shares the short
    end: zero at six foot, climbing to full by 6'10" and staying there. Using the
    driving bell here put a 7'1" player on 58.
    """

    height = _basic_value(source, "identity.ht_in_in")
    if height is None:
        return None
    return max(0.0, min(1.0, (height - _DUNK_ZERO_HEIGHT) / (_STANDING_DUNK_FULL_HEIGHT - _DUNK_ZERO_HEIGHT)))


def _attribute_bounds(value: float) -> int:
    return max(25, min(99, int(round(value))))


def _post_body_score(source: Any) -> float | None:
    height = _basic_value(source, "identity.ht_in_in")
    weight = _basic_value(source, "identity.wt")
    if height is None or weight is None:
        return None
    # Height leads: reach is what wins the position. Mass holds it once it is won.
    return 0.65 * height + 0.35 * (weight / 3.0)


def _post_body_percentile(evidence: Any, population: tuple[dict[str, Any], ...]) -> float | None:
    current = _post_body_score(evidence)
    if current is None:
        return None
    cache_key = id(population)
    cached = _POST_BODY_CACHE.get(cache_key)
    if cached is not None and cached[0] is population:
        ordered = cached[1]
    else:
        ordered = tuple(sorted(
            score for row in population if (score := _post_body_score(row)) is not None
        ))
        _POST_BODY_CACHE[cache_key] = (population, ordered)
    if len(ordered) < 2:
        return None
    left = bisect.bisect_left(ordered, current)
    right = bisect.bisect_right(ordered, current)
    return ((left + right - 1.0) / 2.0) / (len(ordered) - 1.0)


def _absolute_attribute_adjustment(field: str, evidence: Any, relative_value: float, population: tuple[dict[str, Any], ...] = ()) -> tuple[float, tuple[str, ...]]:
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
    if field in {"DRIVINGDUNK", "STANDINGDUNK"}:
        fit = _dunk_athletic_fit(evidence) if field == "DRIVINGDUNK" else _standing_dunk_height_fit(evidence)
        if fit is not None:
            ceiling = 25.0 + 74.0 * fit
            return min(relative_value, ceiling), (
                "identity.ht_in_in",
                "identity.wt",
                "season_info.age",
                f"dunk_athletic_fit={fit:.8f}",
                f"dunk_body_ceiling={ceiling:.4f}",
                "mapping=min(relative_value,25+74*dunk_athletic_fit)",
                "absolute_anchor_reason=dunking is reach and spring; the curve reaches zero at six foot so a player that size sits on the floor without a rule saying so",
            )
    if field == "POSTCONTROL":
        body = _post_body_percentile(evidence, population)
        if body is not None:
            # Working the block is a body skill before it is a scoring skill, so the
            # smallest, lightest frame in the league cannot rate above the floor no
            # matter what his role says.
            ceiling = 25.0 + 74.0 * body
            return min(relative_value, ceiling), (
                "identity.ht_in_in",
                "identity.wt",
                f"post_body_percentile={body:.8f}",
                f"post_body_ceiling={ceiling:.4f}",
                "mapping=min(relative_value,25+74*same_season_same_league_body_percentile)",
                "absolute_anchor_reason=post position is held with height and mass; the smallest frame in the league is the floor",
            )
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
    elif (
        field == "CLOSESHOT"
        and fg_percent is not None
        and _basic_value(evidence, "shooting.fg_percent_from_x0_3_range") is None
        and _basic_value(evidence, "shooting.fg_percent_from_x3_10_range") is None
    ):
        # Original shrink-toward-centre construction, unchanged. It reaches the floor
        # on its own now that a recorded zero counts as fully reliable evidence.
        reliability = _execution_reliability(fg_percent, fga, 100.0)
        response_cap = close_range_rating_for_make_probability(fg_percent)
        reliable_cap = center + reliability * (response_cap - center)
        return min(relative_value, reliable_cap), (
            f"historical_close_response_probability={fg_percent:.6f}",
            f"historical_close_response_rating={response_cap}",
            f"historical_close_response_reliability={reliability:.8f}",
            f"historical_close_reliable_cap={reliable_cap:.8f}",
            "historical_close_cap_reason=overall_FG_percent_is_only_an_upper_bound_for_untracked_close_only_execution",
            "mapping=min(relative_value,reliability_shrunk_close_range_response)",
        )
    elif field in {"CLOSESHOT", "DRIVINGDUNK", "DRIVINGLAYUP", "POSTCONTROL", "POSTHOOK", "STANDINGDUNK"} and fg_percent is not None:
        slope = {
            "CLOSESHOT": 150.0,
            "DRIVINGDUNK": 110.0,
            "DRIVINGLAYUP": 140.0,
            "POSTCONTROL": 120.0,
            "POSTHOOK": 130.0,
            "STANDINGDUNK": 100.0,
        }[field]
        reliability = _execution_reliability(fg_percent, fga, 100.0)
        absolute_value = 25.0 + slope * fg_percent
        anchor = f"25+{slope:.0f}*FG%({fg_percent:.6f})"
    elif field == "POSTFADE" and (ft_percent is not None or fg_percent is not None):
        # A turnaround fade needs both the touch to shoot it and the ability to make a
        # field goal. Anchoring on free-throw touch alone rescued players who never
        # made a field goal all season -- they shot well from the line and came out
        # near 50. The geometric mean requires both: zero on either side is zero.
        if ft_percent is not None and fg_percent is not None:
            touch = (max(0.0, ft_percent) * max(0.0, fg_percent)) ** 0.5
            anchor = f"25+55*sqrt(FT%({ft_percent:.6f})*FG%({fg_percent:.6f}))"
        else:
            touch = ft_percent if ft_percent is not None else fg_percent
            assert touch is not None
            anchor = f"25+55*{'FT%' if ft_percent is not None else 'FG%'}({touch:.6f})"
        exposure = fta if ft_percent is not None else fga
        reliability = _execution_reliability(touch, exposure, 40.0)
        absolute_value = 25.0 + 55.0 * touch

    if absolute_value is None:
        return relative_value, ()
    reliable_absolute = center + reliability * (absolute_value - center)
    if field in _EXECUTION_CEILING_FIELDS and reliability >= 1.0:
        # A fully reliable execution reading is an upper bound rather than one voice in
        # a blend. In practice that means a recorded zero: no made shot is unambiguous,
        # so a player who made none all season cannot rate above the floor on a field
        # that asks whether he could make it. Every other reading stays blended --
        # applying an absolute FG% ceiling to everyone compressed a league that shot
        # 28% into a narrow band and cost the win-share rankings a full three points.
        return min(relative_value, absolute_value), (
            f"absolute_field_anchor={anchor}",
            f"absolute_field_anchor_reliability={reliability:.8f}",
            "mapping=min(relative_value,field_specific_execution_ceiling)",
            "absolute_anchor_reason=shot execution cannot exceed what the player's recorded shooting demonstrates",
        )
    value = 0.45 * relative_value + 0.55 * reliable_absolute
    return value, (
        f"absolute_field_anchor={anchor}",
        f"absolute_field_anchor_reliability={reliability:.8f}",
        "absolute_anchor_reason=era-relative rank is blended with continuous field-specific execution/load so low exposure cannot become modern elite",
    )


_ATTR_RECIPES: dict[str, tuple[_Recipe, ...]] = {
    "BALLCONTROL": (
        _Recipe("tracked_handle_security", (("!derived.lost_ball_per_game", 0.40), ("!advanced.tov_percent", 0.30), ("derived.unassisted_two_rate", 0.20))),
        _Recipe("recorded_handle_security", (("!advanced.tov_percent", 0.40), ("per_game.ft_percent", 0.25)), "lost-ball tracking and self-created-shot splits", "turnover restraint, continuous guard/wing participation, and weak free-throw touch", "AST is excluded; the remaining sources describe handle security and applicable on-ball responsibility"),
        _Recipe("unrecorded_assist_era_handle", (("derived.attempt_share", 0.25), ("per_game.ft_percent", 0.20)), "assists, lost-ball events, and player turnovers", "continuous primary/secondary creator-position participation plus observed shooting responsibility and touch", "the 1946-47 NBL research identifies guards as ball advancers; scoring responsibility distinguishes handling load without inventing AST zeroes"),
    ),
    "DRAWFOUL": (
        _Recipe("tracked_foul_creation", (("derived.shooting_foul_drawn_per_game", 0.50), ("derived.and1_per_game", 0.20), ("derived.foul_pressure", 0.30))),
        _Recipe("recorded_free_throw_pressure", (("derived.foul_pressure", 0.55), ("per_game.fta_per_game", 0.45)), "shooting-foul-drawn and and-one events", "recorded FTA/FGA pressure and FTA volume", "both are direct outcomes of forcing shooting fouls rather than shooting efficiency"),
    ),
    # NBL players have no win shares, so this resolves to nothing for them and the
    # field is filled by the same-season BAA common-feature projection, which owns
    # every key in nbl_baa_projection.PROJECTED_FIELD_KEYS. A second NBL-only recipe
    # here produced a competing owner for the same field and, because it mapped a
    # within-NBL rank onto the BAA distribution, put ten NBL players at exactly 99
    # against the BAA's four. One field, one owner.
    "OFFENSIVECONSISTENCY": (
        _Recipe("ows_only", (("advanced.ows", 1.0),)),
    ),
    "PASSACCURACY": (
        _Recipe("tracked_pass_completion_proxy", (("derived.assist_points_per_game", 0.35), ("!derived.bad_pass_per_game", 0.35), ("derived.assist_decision_efficiency", 0.30))),
        _Recipe("recorded_pass_security", (("!derived.turnover_rate_per_36", 0.45), ("advanced.tov_percent", -0.20), ("per_game.ast_per_game", 0.20), ("derived.assist_share", 0.15)), "pass completion, placement, and bad-pass event tracking", "turnover restraint per 36 minutes with recorded assist outcomes in support", "accuracy is about passes that arrive, so it is led by how rarely the ball is given away rather than by how often an assist was credited"),
        _Recipe("unrecorded_assist_era_accuracy", (("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.15)), "assists and passing-error outcomes", "continuous ball-advancer position, shooting touch, and observed offensive responsibility", "research supports guard ball advancement; the weak touch/load terms avoid assigning modern-elite passing from position alone"),
    ),
    "PASSIQ": (
        _Recipe("tracked_pass_decisions", (("advanced.ast_percent", 0.35), ("derived.assist_decision_efficiency", 0.35), ("!derived.bad_pass_per_game", 0.30))),
        _Recipe("recorded_assist_decisions", (("derived.assist_share", 0.35), ("per_game.ast_per_game", 0.30), ("advanced.tov_percent", -0.20), ("derived.passing_experience", 0.15)), "potential assists, passing decisions, and bad-pass events", "recorded team-assist responsibility, AST/G, and turnover restraint", "the output remains passing-specific and cannot be raised by generic win shares or efficiency"),
        _Recipe("unrecorded_assist_era_pass_iq", (("derived.passing_experience", 0.30), ("derived.attempt_share", 0.15), ("per_game.ft_percent", 0.10)), "assists, player turnovers, and pass-decision events", "continuous researched ball-advancer role with weak responsibility/touch support", "no unrecorded zero is used and the target calibration keeps ordinary early guards below modern elite levels"),
    ),
    "PASSVISION": (
        _Recipe("tracked_creation_vision", (("derived.assist_points_per_game", 0.45), ("advanced.ast_percent", 0.35), ("!derived.bad_pass_per_game", 0.20))),
        _Recipe("recorded_creation_vision", (("derived.assist_share", 0.50), ("per_game.ast_per_game", 0.35)), "potential assists, pass targets, and points generated by assists", "observed assist responsibility and continuous creator-position participation", "the substitute measures seeing and completing scoring passes, not speed or athleticism"),
        _Recipe("unrecorded_assist_era_vision", (("derived.attempt_share", 0.20), ("per_game.ft_percent", 0.15)), "assists and chance-creation tracking", "continuous researched ball-advancer role with weak offensive responsibility/touch support", "position is not a hard archetype gate and cannot by itself reach elite output"),
    ),
    "IQSHOT": (
        _Recipe("tracked_shot_selection", (("advanced.ts_percent", 0.40), ("per_game.e_fg_percent", 0.25), ("!derived.blocked_attempt_rate", 0.20), ("!advanced.tov_percent", 0.15))),
        _Recipe("all_era_shot_selection", (("advanced.ts_percent", 0.50), ("per_game.fg_percent", 0.30), ("per_game.ft_percent", 0.20)), "shot-quality, blocked-attempt, and possession decision tracking", "recorded shooting efficiency with free-throw touch", "the narrower Shot-IQ calibration prevents broad efficiency from indiscriminately producing 97-99"),
    ),
    "CLOSESHOT": (
        _Recipe("location_close_execution", (("shooting.fg_percent_from_x0_3_range", 0.65), ("shooting.fg_percent_from_x3_10_range", 0.35))),
        _Recipe("historical_close_execution", (("per_game.fg_percent", 0.40), ("advanced.ts_percent", 0.15)), "0-3 and 3-10 foot make results", "overall make efficiency with continuous interior-position context", "field-goal execution is observed; interior position carries more of the unrecorded close result and the guard term keeps perimeter players off the top of a shot they rarely took"),
    ),
    "DRIVINGDUNK": (
        _Recipe("tracked_driving_finish", (("shooting.fg_percent_from_x0_3_range", 0.45), ("derived.and1_per_game", 0.20), ("!derived.blocked_attempt_rate", 0.20), ("derived.dunk_rate", 0.15))),
        _Recipe("historical_driving_finish", (("derived.dunk_height_fit", 0.50), ("per_game.fg_percent", 0.30), ("advanced.f_tr", 0.20)), "driving-dunk make, block, and and-one events", "recorded finishing efficiency, foul pressure, and continuous body/position context", "dunk execution requires finishing outcomes plus reach; body context never replaces observed efficiency"),
    ),
    "DRIVINGLAYUP": (
        _Recipe("tracked_driving_layup_finish", (("shooting.fg_percent_from_x0_3_range", 0.55), ("!derived.blocked_attempt_rate", 0.20), ("derived.and1_per_game", 0.15), ("derived.foul_pressure", 0.10))),
        _Recipe("historical_driving_layup_finish", (("per_game.fg_percent", 0.35), ("per_game.ft_percent", 0.15), ("derived.foul_pressure", 0.15)), "driving-layup make, block, and and-one events", "recorded finishing efficiency, touch, foul pressure, and continuous perimeter participation", "the substitute remains finishing-oriented and does not use attempt share as execution"),
    ),
    "MIDRANGE": (
        _Recipe("location_midrange_execution", (("shooting.fg_percent_from_x10_16_range", 0.55 / 0.90), ("shooting.fg_percent_from_x16_3p_range", 0.35 / 0.90))),
        _Recipe("historical_midrange_touch", (("per_game.ft_percent", 0.40), ("per_game.fg_percent", 0.25)), "10-16 and 16-foot-to-line make results", "free-throw touch, observed field-goal execution, and continuous perimeter/wing context", "free-throw accuracy is a stationary touch substitute; the negative big term keeps pivots off a shot the era did not ask them to take, and Joe Fulks holds his midrange through his documented calling card rather than through position"),
    ),
    # Scoring volume is deliberately absent. Ranking POSTCONTROL on points made the
    # league's leading perimeter scorer a post hub -- Joe Fulks, the era's signature
    # jump shooter, reached 88 on height plus PPG alone. Post control is measured by
    # where the shots came from and how they were finished, not by how many there were.
    "POSTCONTROL": (
        _Recipe("tracked_post_security", (("!derived.lost_ball_per_game", 0.35), ("!advanced.tov_percent", 0.30), ("derived.unassisted_two_rate", 0.15))),
        _Recipe("historical_post_security", (("per_game.fg_percent", 0.30), ("per_game.ft_percent", 0.15), ("identity.wt", 0.10)), "post touches, post turnovers, and move-success events", "continuous post-position/body participation with recorded scoring control and touch", "AST is excluded; size supplies context while scoring execution prevents a fixed big-man override"),
        _Recipe("unrecorded_assist_era_post_security", (("per_game.fg_percent", 0.30), ("identity.wt", 0.15)), "post events, assists, and player turnovers", "continuous researched frontcourt role, body leverage, and observed scoring execution", "no missing assist value is converted to zero"),
    ),
    "POSTFADE": (
        _Recipe("location_post_fade_execution", (("shooting.fg_percent_from_x10_16_range", 0.45), ("shooting.fg_percent_from_x3_10_range", 0.30), ("per_game.ft_percent", 0.15))),
        _Recipe("historical_post_fade_touch", (("per_game.ft_percent", 0.35), ("per_game.fg_percent", 0.20)), "post-fade make results", "shooting touch and continuous wing context", "the turnaround fade is a wing and swingman shot rather than a pivot shot, so wing role carries it and the negative big term moves centres down; Joe Fulks holds his through his documented calling card"),
    ),
    "POSTHOOK": (
        _Recipe("location_post_hook_execution", (("shooting.fg_percent_from_x3_10_range", 0.45), ("shooting.fg_percent_from_x0_3_range", 0.30), ("identity.ht_in_in", 0.10))),
        _Recipe("historical_post_hook_finish", (("per_game.fg_percent", 0.35), ("identity.ht_in_in", 0.15)), "post-hook make results", "observed finishing with continuous post/reach context", "hook range and reach differ from fade touch; post role carries more of the result and the guard term keeps backcourt players off a frontcourt shot"),
    ),
}


_TENDENCY_RECIPES: dict[str, tuple[_Recipe, ...]] = {
    "TRIPLETHREATIDLE": (_Recipe("triple_threat_hold", (("derived.attempt_share", 0.45), ("role.wing", 0.10), ("role.post", 0.10),), "triple-threat state events", "observed shooting responsibility and continuous wing/post participation", "triple-threat states occur before perimeter or post scoring decisions"),),
    "TRIPLETHREATJAB": (_Recipe("triple_threat_jab", (("derived.mid_attempt_rate", 0.40), ("derived.attempt_share", 0.35), ("role.wing", 0.10),), "jab-step events", "midrange attempt location, shooting responsibility, and wing participation", "jab steps are shot-creation behavior, not make efficiency"), _Recipe("historical_triple_threat_jab", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "jab-step and location events", "shooting responsibility and continuous wing participation", "the substitute varies with observed role and never becomes an execution rating")),
    "TRIPLETHREATPUMPFake": (_Recipe("triple_threat_pump", (("derived.short_attempt_rate", 0.35), ("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "pump-fake events", "short-shot frequency, foul pressure, and shooting responsibility", "pump fakes are attempt/behavior signals"), _Recipe("historical_triple_threat_pump", (("derived.foul_pressure", 0.45), ("derived.attempt_share", 0.35), ("role.post", 0.10),), "pump-fake and location events", "recorded foul pressure and offensive responsibility", "the substitute is behavior-oriented rather than efficiency-oriented")),
    "TRIPLETHREATSHOT": (_Recipe("triple_threat_shoot", (("derived.mid_attempt_rate", 0.35), ("derived.three_attempt_rate", 0.30), ("derived.attempt_share", 0.35)), "triple-threat shot events", "recorded jump-shot location and shooting responsibility", "all inputs describe attempt selection"), _Recipe("historical_triple_threat_shoot", (("derived.attempt_share", 0.70), ("role.wing", 0.10),), "triple-threat and shot-location events", "shooting responsibility and continuous perimeter participation", "the substitute does not use make efficiency")),
    "SETUPDRIBBLE": (_Recipe("no_setup_dribble", (("!derived.unassisted_two_rate", 0.20), ("!role.creator", 0.10), ("role.post", 0.10),), "setup-dribble events", "inverse creation responsibility and assisted/post role", "players who do not self-create are more likely to attack without extended setup"), _Recipe("historical_no_setup_dribble", (("!derived.attempt_share", 1.0), ("!role.creator", 0.10), ("role.post", 0.10),), "setup-dribble and assisted-shot events", "inverse shot responsibility", "a player with little of his team's shot load catches and goes rather than working for his own shot; position is not an input")),
    "SETUPWITHHESITATION": (_Recipe("setup_hesitation", (("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "hesitation events", "self-creation, live-dribble exposure, and drive pressure", "AST is excluded and all inputs identify on-ball setup behavior"), _Recipe("historical_setup_hesitation", (("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "hesitation and self-created-shot events", "continuous creator role, drive pressure, and observed shooting responsibility", "no AST signal authors this move tendency")),
    "SETUPWITHSIZEUP": (_Recipe("setup_sizeup", (("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.10), ("role.creator", 0.10),), "size-up events", "on-ball creation, self-created attempts, and live-dribble exposure", "AST is excluded; turnover exposure is behavior rather than execution"), _Recipe("historical_setup_sizeup", (("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "size-up and self-created-shot events", "continuous creator role, drive pressure, and observed responsibility", "no AST signal or fixed guard template is used")),
    "DRIVE": (_Recipe("drive_frequency", (("derived.rim_attempt_rate", 0.35), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.20), ("derived.attempt_share", 0.20)), "drive events", "rim attempts, foul pressure, self-creation, and attempt responsibility", "each input measures drive selection or opportunity, never finishing efficiency"), _Recipe("historical_drive_frequency", (("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20), ("role.creator", 0.10), ("role.post", 0.10),), "drive, rim-location, and assisted-shot events", "foul pressure and shooting responsibility allocated through continuous creator-versus-post role", "post scoring and post-drawn fouls cannot become perimeter Drive without on-ball creator participation")),
    "DRIVINGCROSSOVER": (_Recipe("driving_crossover", (("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.20), ("role.creator", 0.10),), "crossover events", "self-creation, live-dribble exposure, and drive pressure", "AST is excluded and the sources describe applicable on-ball behavior"), _Recipe("historical_driving_crossover", (("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "crossover and self-created-shot events", "continuous creator role, drive pressure, and offensive responsibility", "the substitute avoids AST and fixed move ratings")),
    "DRIVINGDOUBLECROSSOVER": (_Recipe("driving_double_crossover", (("derived.unassisted_two_rate", 0.30), ("derived.lost_ball_per_game", 0.20), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "double-crossover events", "extended live-dribble creation and drive pressure", "lost-ball exposure differentiates a longer move from a basic crossover"), _Recipe("historical_driving_double_crossover", (("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "double-crossover and live-dribble events", "continuous creator role, drive pressure, and observed responsibility", "AST is excluded and the lower field-exact calibration keeps this rarer move distinct")),
    "DRIVINGSPIN": (_Recipe("driving_spin", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.10),), "spin-move events", "short-area self-creation and drive pressure", "spin usage is a behavior signal"), _Recipe("historical_driving_spin", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.30), ("role.creator", 0.10), ("role.post", 0.10),), "spin-move and location events", "drive pressure and continuous perimeter/post creation", "both perimeter and post players can spin without a hard position gate")),
    "DRIVINGHALFSPIN": (_Recipe("driving_half_spin", (("derived.short_attempt_rate", 0.25), ("derived.unassisted_two_rate", 0.25), ("derived.lost_ball_per_game", 0.20), ("role.creator", 0.10),), "half-spin events", "live-dribble self-creation and short-area activity", "the field-exact calibration separates it from full-spin frequency"), _Recipe("historical_driving_half_spin", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "half-spin and live-dribble events", "creator responsibility and drive pressure", "no generic constant is used")),
    "DRIVINGSTEPBACK": (_Recipe("driving_stepback", (("derived.mid_attempt_rate", 0.30), ("derived.three_attempt_rate", 0.20), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.10),), "driving-stepback events", "pull-up location and self-creation", "stepbacks are attempt behavior, not shot efficiency"), _Recipe("historical_driving_stepback", (("derived.attempt_share", 0.35), ("per_game.ft_percent", 0.30), ("role.creator", 0.10),), "stepback and pull-up events", "creator responsibility, shooting load, and weak touch context", "touch only distinguishes plausible pull-up behavior when locations are absent")),
    "DRIVINGBEHINDTHEBACK": (_Recipe("driving_behind_back", (("derived.unassisted_two_rate", 0.25), ("derived.foul_pressure", 0.20), ("derived.lost_ball_per_game", 0.20), ("role.creator", 0.10),), "behind-the-back events", "extended creator possession, drive pressure, and self-created attempts", "AST is excluded; live-dribble exposure is field-specific behavior evidence"), _Recipe("historical_driving_behind_back", (("derived.foul_pressure", 0.20), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "behind-the-back and live-dribble events", "continuous creator role, drive pressure, and offensive responsibility", "the substitute excludes AST and named-player templates")),
    "DRIVINGDRIBBLEHESITATION": (_Recipe("driving_hesitation", (("derived.unassisted_two_rate", 0.25), ("derived.foul_pressure", 0.25), ("derived.lost_ball_per_game", 0.20), ("role.creator", 0.10),), "driving-hesitation events", "self-created drive pressure and live-dribble exposure", "AST is excluded and all inputs describe on-ball behavior"), _Recipe("historical_driving_hesitation", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "driving-hesitation and self-created-shot events", "continuous creator responsibility and foul pressure", "no AST signal authors the tendency")),
    "DRIVINGINANDOUT": (_Recipe("driving_in_out", (("derived.unassisted_two_rate", 0.30), ("derived.foul_pressure", 0.20), ("derived.lost_ball_per_game", 0.20), ("role.creator", 0.10),), "in-and-out events", "live-dribble self-creation and drive pressure", "the input family is behavior-specific"), _Recipe("historical_driving_in_out", (("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20), ("role.creator", 0.10),), "in-and-out and self-created-shot events", "continuous creator role, drive pressure, and offensive responsibility", "AST is excluded and no move constant is inserted")),
    "NODRIVINGDRIBBLEMOVE": (_Recipe("no_driving_move", (("!derived.unassisted_two_rate", 0.30), ("!derived.foul_pressure", 0.20), ("!role.creator", 0.10), ("role.post", 0.10),), "no-move drive events", "inverse self-creation and drive pressure with post role", "this is the semantic inverse of move-based creation"), _Recipe("historical_no_driving_move", (("!derived.attempt_share", 0.25), ("!role.creator", 0.10), ("role.post", 0.10),), "drive-move and assisted-shot events", "inverse creator responsibility and continuous post role", "the field remains coupled coherently to the other driving tendencies")),
    "ATTACKSTRONGONDRIVE": (_Recipe("attack_strong_drive", (("derived.foul_pressure", 0.35), ("derived.rim_attempt_rate", 0.30), ("derived.attempt_share", 0.20), ("identity.wt", 0.15)), "strong-drive events", "rim pressure, foul creation, responsibility, and body leverage", "inputs measure physical drive behavior, not finishing skill"), _Recipe("historical_attack_strong_drive", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.15), ("identity.wt", 0.15), ("role.creator", 0.10), ("role.post", 0.10),), "strong-drive and rim events", "foul pressure and leverage conditioned by continuous creator-versus-post role", "weight and post-drawn fouls cannot identify a strong drive without on-ball creator participation")),
    "OFFSCREENDRIVE": (_Recipe("off_screen_drive", (("derived.rim_attempt_rate", 0.30), ("derived.attempt_share", 0.25), ("derived.unassisted_two_rate", -0.20), ("role.wing", 0.10),), "off-screen drive events", "rim frequency, scoring responsibility, assisted context, and wing participation", "off-screen actions differ from primary isolation creation"), _Recipe("historical_off_screen_drive", (("derived.attempt_share", 0.45), ("role.wing", 0.10), ("role.creator", 0.10),), "off-screen and assisted-shot events", "wing scoring responsibility with reduced primary-creator weight", "the substitute remains role/behavior evidence")),
    "SPOTUPDRIVE": (_Recipe("spot_up_drive", (("derived.rim_attempt_rate", 0.30), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", -0.20), ("role.wing", 0.10),), "spot-up drive events", "rim/foul pressure from a non-primary-creation wing context", "spot-up drives are behavior frequency"), _Recipe("historical_spot_up_drive", (("derived.foul_pressure", 0.25), ("derived.attempt_share", 0.20), ("role.wing", 0.10), ("role.post", 0.10),), "spot-up and assisted-shot events", "drive pressure and scoring responsibility allocated through continuous wing-versus-post role", "post scoring cannot become a spot-up perimeter drive without wing participation")),
    "ALLEYOOOPASS": (_Recipe("alley_oop_pass_behavior", (("!derived.bad_pass_per_game", 0.25), ("derived.foul_pressure", 0.20), ("role.creator", 0.10), ("role.big", 0.10),), "alley-oop pass events", "continuous passer role, pass security, and rim-pressure context", "AST is excluded; the low-frequency field calibration prevents role alone from creating elite output"), _Recipe("historical_alley_oop_pass", (("derived.foul_pressure", 0.30), ("role.creator", 0.10),), "alley-oop and pass-target events", "continuous researched ball-advancer role and rim pressure", "AST is excluded and the output remains uncertain where pass events are absent")),
    "DISHTOOPENMAN": (_Recipe("dish_open_man_behavior", (("!derived.bad_pass_per_game", 0.35), ("!advanced.tov_percent", 0.20), ("role.creator", 0.10),), "pass-target openness events", "continuous passer role and pass/possession security", "AST is excluded; the sources concern willingness and decision behavior"), _Recipe("historical_dish_open_man", (("per_game.ft_percent", 0.20), ("derived.foul_pressure", 0.10), ("role.creator", 0.10),), "open-target pass events", "continuous ball-advancer role with weak touch/pressure context", "no missing or low AST value is transformed into elite output")),
    "FLASHYPASS": (_Recipe("flashy_pass_behavior", (("derived.bad_pass_per_game", 0.30), ("derived.lost_ball_per_game", 0.15), ("derived.foul_pressure", 0.10), ("role.creator", 0.10),), "flashy-pass events", "continuous creator role and higher-risk live-ball exposure", "AST is excluded; bad-pass exposure differentiates flair frequency from accuracy"), _Recipe("historical_flashy_pass", (("derived.foul_pressure", 0.25), ("role.creator", 0.10),), "flashy-pass and pass-event tracking", "continuous researched ball-advancer role and live-ball pressure", "the low calibration and no named-player template keep ordinary passers low")),
    "POSTUP": (_Recipe("post_up_frequency", (("derived.short_attempt_rate", 0.30), ("derived.attempt_share", 0.20), ("identity.wt", 0.10), ("role.post", 0.10),), "post-up events", "continuous post position/body context and short-shot responsibility", "all terms describe post opportunity and frequency"), _Recipe("historical_post_up_frequency", (("derived.attempt_share", 0.30), ("identity.wt", 0.20), ("role.post", 0.10),), "post-up and shot-location events", "continuous post role, responsibility, and body leverage", "the substitute is not a fixed big-man band")),
    "POSTBACKDOWN": (_Recipe("post_backdown", (("identity.wt", 0.25), ("derived.short_attempt_rate", 0.20), ("derived.attempt_share", 0.20), ("role.post", 0.10),), "backdown events", "post role, leverage, short attempts, and responsibility", "the tendency is behavior/frequency"), _Recipe("historical_post_backdown", (("identity.wt", 0.30), ("derived.attempt_share", 0.20), ("role.post", 0.10),), "backdown and post-touch events", "continuous post role and leverage", "no hard size threshold is used")),
    "POSTAGGRESSIVEBACKDOWN": (_Recipe("post_aggressive_backdown", (("identity.wt", 0.30), ("derived.foul_pressure", 0.25), ("derived.short_attempt_rate", 0.20), ("role.post", 0.10),), "aggressive-backdown events", "leverage, foul pressure, and post frequency", "the terms distinguish forceful behavior from ordinary backdowns"), _Recipe("historical_post_aggressive_backdown", (("identity.wt", 0.35), ("derived.foul_pressure", 0.30), ("role.post", 0.10),), "aggressive-backdown and post-touch events", "continuous leverage, foul pressure, and post role", "no arbitrary weight gate is used")),
    "POSTFACEUP": (_Recipe("post_face_up", (("derived.mid_attempt_rate", 0.30), ("per_game.ft_percent", 0.20), ("role.wing", 0.10), ("role.post", 0.10),), "post-face-up events", "hybrid wing/post role and midrange attempt behavior", "face-up play differs from backdown play through perimeter touch/location"), _Recipe("historical_post_face_up", (("per_game.ft_percent", 0.25), ("derived.attempt_share", 0.15), ("role.wing", 0.10), ("role.post", 0.10),), "face-up and midrange events", "hybrid role, touch, and responsibility", "the substitute remains continuous across secondary positions")),
    "POSTSPIN": (_Recipe("post_spin", (("derived.short_attempt_rate", 0.25), ("derived.foul_pressure", 0.25), ("derived.unassisted_two_rate", 0.20), ("role.post", 0.10),), "post-spin events", "post self-creation and short-area pressure", "all terms identify move frequency"), _Recipe("historical_post_spin", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "post-spin and post-touch events", "post role, foul pressure, and responsibility", "the low target calibration preserves move rarity")),
    "POSTDRIVE": (_Recipe("post_drive", (("derived.foul_pressure", 0.30), ("derived.rim_attempt_rate", 0.25), ("derived.unassisted_two_rate", 0.20), ("role.post", 0.10),), "post-drive events", "post role with rim/foul self-creation", "the tendency is separated from post-spin and face-up execution"), _Recipe("historical_post_drive", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.30), ("role.post", 0.10),), "post-drive and rim events", "post role, drive pressure, and responsibility", "no finishing percentage is used as frequency")),
    "POSTHOPSHOT": (_Recipe("post_hop_shot", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15), ("role.post", 0.10),), "post-hop-shot events", "post self-created midrange attempt behavior", "field-exact low-frequency calibration keeps the move rare"), _Recipe("historical_post_hop_shot", (("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.30), ("role.post", 0.10),), "post-hop and midrange events", "post role, touch, and offensive responsibility", "the substitute does not infer make execution")),
}

_TENDENCY_CALIBRATION.update(
    {
        "POSTHOPSTEP": (10.0, 14.83),  # ATD Post Hop Shot 0-20, cap 45
        "3POINTCENTERLEFTSHOT": (0.0, 11.6),
        "3POINTCENTERRIGHTSHOT": (0.0, 15.6),
        "3POINTCENTERSHOT": (0.0, 18.5),
        "3POINTLEFTSHOT": (0.0, 8.9),
        "3POINTOFFSCREENSHOT": (12.5, 11.12),  # ATD Off-Screen Three 5-20, cap 65
        "3POINTRIGHTSHOT": (0.0, 14.8),
        "3POINTSPOTUPSHOT": (40.0, 14.83),  # ATD Spot-Up Three 30-50, cap 75
        "ALLEYOOP": (25.0, 14.83),  # ATD Alley-Oop Finish 15-35, cap 85
        "BASKETUNDERSHOT": (32.5, 18.53),  # ATD Shot Under 20-45, cap 85
        "CENTERLEFTMIDSHOT": (17.0, 7.4),
        "CENTERMIDRIGHTSHOT": (18.0, 6.7),
        "CENTERMIDSHOT": (18.0, 8.2),
        "CLOSELEFTSHOT": (23.0, 14.1),
        "CLOSEMIDDLESHOT": (28.0, 17.8),
        "CLOSERIGHTSHOT": (24.0, 14.1),
        "CONTESTEDJUMPER3POINT": (12.5, 11.12),  # ATD Contested Jumper Three 5-20, cap 55
        "CONTESTEDJUMPERMID": (17.5, 11.12),  # ATD Contested Jumper Mid-Range 10-25, cap 55
        "CONTESTEDJUMPERMIDRANGE": (17.5, 11.12),  # ATD Contested Jumper Mid-Range 10-25, cap 55
        "DRIVEPULLUP3POINT": (12.5, 11.12),  # ATD Dribble Pull-Up Three 5-20, cap 50
        "DRIVEPULLUPMID": (20.0, 14.83),  # ATD Dribble Pull-Up Mid-Range 10-30, cap 70
        "DRIVEPULLUPMIDRANGE": (20.0, 14.83),  # ATD Dribble Pull-Up Mid-Range 10-30, cap 70
        "DRIVINGDUNK": (27.5, 18.53),  # ATD Driving Dunk 15-40, cap 80
        "DRIVINGLAYUP": (35.0, 22.24),  # ATD Driving Layup 20-50, cap 80
        "EUROSTEPLAYUP": (20.0, 14.83),  # ATD Eurostep Layup 10-30, cap 75
        "FLASHYDUNK": (10.0, 14.83),  # ATD Flashy Dunk 0-20, cap 70
        "FLOATER": (20.0, 14.83),  # ATD Floater 10-30, cap 75
        "FROMPOSTSHOT": (22.5, 18.53),  # ATD Shoot From Post 10-35, cap 75
        "HOPPOSTSHOT": (10.0, 14.83),  # ATD Post Hop Shot 0-20, cap 45
        "HOPSTEPLAYUP": (15.0, 14.83),  # ATD Hop Step Layup 5-25, cap 65
        "LEFTMIDSHOT": (19.0, 6.7),
        "MIDOFFSCREENSHOT": (5.0, 7.41),  # ATD Off-Screen Mid 0-10, cap 50
        "MIDRIGHTSHOT": (18.0, 6.7),
        "MIDSPOTUPSHOT": (10.0, 7.41),  # ATD Spot-Up Mid 5-15, cap 55
        "POSTDROPSTEP": (20.0, 14.83),  # ATD Post Drop Step 10-30, cap 60
        "POSTFADELEFT": (10.0, 14.83),  # ATD Post Fade Left 0-20, cap 50
        "POSTFADERIGHT": (10.0, 14.83),  # ATD Post Fade Right 0-20, cap 50
        "POSTHOOKLEFT": (7.5, 11.12),  # ATD Post Hook Left 0-15, cap 50
        "POSTHOOKRIGHT": (7.5, 11.12),  # ATD Post Hook Right 0-15, cap 50
        "POSTSHIMMYSHOT": (10.0, 14.83),  # ATD Post Shimmy 0-20, cap 45
        "POSTSTEPBACKSHOT": (10.0, 14.83),  # ATD Post Step Back 0-20, cap 50
        "POSTUPANDUNDER": (10.0, 14.83),  # ATD Post Up & Under 0-20, cap 45
        "SPINJUMPER": (10.0, 7.41),  # ATD Spin Jumper 5-15, cap 45
        "SPINLAYUP": (15.0, 14.83),  # ATD Spin Layup 5-25, cap 70
        "STANDINGDUNK": (12.5, 18.53),  # ATD Standing Dunk 0-25, cap 85
        "STEPBACKJUMPER3POINT": (12.5, 11.12),  # ATD Stepback Jumper Three 5-20, cap 60
        "STEPBACKJUMPERMID": (12.5, 11.12),  # ATD Stepback Jumper Mid-Range 5-20, cap 55
        "STEPBACKJUMPERMIDRANGE": (12.5, 11.12),  # ATD Stepback Jumper Mid-Range 5-20, cap 55
        "STEPTHROUGH": (17.5, 11.12),  # ATD Step Through Shot 10-25, cap 50
        "TRANSITIONPULLUP3POINT": (10.0, 7.41),  # ATD Transition Pull-Up Three 5-15, cap 45
        "USEGLASS": (10.0, 7.41),  # ATD Use Glass 5-15, cap 45
    }
)

_TENDENCY_RECIPES.update(
    {
        "POSTHOPSTEP": (_Recipe("post_hop_step_alias", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.20), ("identity.wt", 0.15), ("role.post", 0.10),), "post-hop-step events and a captured field-exact target", "post/drop-step context plus the captured Post Drop Step output distribution", "this live alias has no separate Pool label; source behavior is kept distinct from the hop-shot tendency"),),
        "3POINTCENTERLEFTSHOT": (_Recipe("center_left_three_location", (("derived.three_attempt_rate", 0.65), ("shooting.percent_corner_3s_of_3pa", -0.35)), "left-center three location events", "non-corner three-attempt share", "the source separates center from corner mass but not left from right; laterality remains uncertain"),),
        "3POINTCENTERRIGHTSHOT": (_Recipe("center_right_three_location", (("derived.three_attempt_rate", 0.65), ("shooting.percent_corner_3s_of_3pa", -0.35)), "right-center three location events", "non-corner three-attempt share", "the source separates center from corner mass but not left from right; laterality remains uncertain"),),
        "3POINTCENTERSHOT": (_Recipe("center_three_location", (("derived.three_attempt_rate", 0.60), ("shooting.percent_corner_3s_of_3pa", -0.40)), "center three location events", "recorded non-corner three-attempt share", "center mass is the complement of recorded corner share"),),
        "3POINTLEFTSHOT": (_Recipe("left_corner_three_location", (("derived.three_attempt_rate", 0.55), ("shooting.percent_corner_3s_of_3pa", 0.45)), "left-corner three events", "recorded corner share and total three-attempt rate", "public data has no left/right split; corner frequency is direct and laterality remains uncertain"),),
        "3POINTRIGHTSHOT": (_Recipe("right_corner_three_location", (("derived.three_attempt_rate", 0.55), ("shooting.percent_corner_3s_of_3pa", 0.45)), "right-corner three events", "recorded corner share and total three-attempt rate", "public data has no left/right split; corner frequency is direct and laterality remains uncertain"),),

        "ALLEYOOP": (_Recipe("alley_oop_finish", (("derived.dunk_rate", 0.45), ("derived.rim_attempt_rate", 0.25), ("role.interior", 0.10),), "alley-oop finish events", "dunk frequency, rim location, and interior role", "the target is finish selection, not dunk execution"), _Recipe("historical_alley_oop_finish", (("derived.attempt_share", 0.25), ("identity.ht_in_in", 0.20), ("role.interior", 0.10),), "alley-oop, dunk, and rim events", "continuous interior/reach context and offensive responsibility", "the low field calibration prevents a fixed big-man tendency")),
        "BASKETUNDERSHOT": (_Recipe("under_basket_attempt", (("derived.rim_attempt_rate", 0.55), ("derived.attempt_share", 0.10), ("role.interior", 0.10),), "under-basket events", "recorded rim frequency and continuous interior participation", "the source is location/frequency evidence"), _Recipe("historical_under_basket_attempt", (("derived.attempt_share", 0.30), ("identity.ht_in_in", 0.15), ("role.interior", 0.10),), "under-basket and rim-location events", "continuous interior/reach context and attempt responsibility", "no hard height or position gate is used")),
        "CENTERLEFTMIDSHOT": (_Recipe("center_left_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.10),), "left-center midrange events", "recorded midrange share and wing participation", "public data has no left/right split; lateral uncertainty is explicit"), _Recipe("historical_center_left_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "midrange and directional events", "shooting responsibility and continuous wing role", "the output remains a tendency")),
        "CENTERMIDRIGHTSHOT": (_Recipe("center_right_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.10),), "right-center midrange events", "recorded midrange share and wing participation", "public data has no left/right split; lateral uncertainty is explicit"), _Recipe("historical_center_right_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "midrange and directional events", "shooting responsibility and continuous wing role", "the output remains a tendency")),
        "CENTERMIDSHOT": (_Recipe("center_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.10),), "center-mid events", "recorded midrange share and wing participation", "the source captures range though not exact court coordinates"), _Recipe("historical_center_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "midrange location events", "shooting responsibility and continuous wing role", "no make percentage authors frequency")),
        "LEFTMIDSHOT": (_Recipe("left_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.10),), "left-mid events", "recorded midrange share and wing participation", "public data has no laterality split"), _Recipe("historical_left_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "midrange and directional events", "shooting responsibility and continuous wing role", "laterality remains uncertain")),

        "MIDRIGHTSHOT": (_Recipe("right_mid_location", (("derived.mid_attempt_rate", 0.75), ("role.wing", 0.10),), "right-mid events", "recorded midrange share and wing participation", "public data has no laterality split"), _Recipe("historical_right_mid", (("derived.attempt_share", 0.55), ("role.wing", 0.10),), "midrange and directional events", "shooting responsibility and continuous wing role", "laterality remains uncertain")),

        "CLOSELEFTSHOT": (_Recipe("left_close_location", (("derived.short_attempt_rate", 0.75), ("role.interior", 0.10),), "left-close events", "recorded short-shot share and interior participation", "public data has no left/right split"), _Recipe("historical_left_close", (("derived.attempt_share", 0.50), ("role.interior", 0.10),), "close-location events", "shooting responsibility and continuous interior role", "laterality remains uncertain")),
        "CLOSEMIDDLESHOT": (_Recipe("middle_close_location", (("derived.rim_attempt_rate", 0.65), ("role.interior", 0.10),), "middle-close events", "recorded rim share and interior participation", "central rim opportunity is the closest available location evidence"), _Recipe("historical_middle_close", (("derived.attempt_share", 0.45), ("role.interior", 0.10),), "close-location events", "continuous interior role and shooting responsibility", "no efficiency value authors frequency")),
        "CLOSERIGHTSHOT": (_Recipe("right_close_location", (("derived.short_attempt_rate", 0.75), ("role.interior", 0.10),), "right-close events", "recorded short-shot share and interior participation", "public data has no left/right split"), _Recipe("historical_right_close", (("derived.attempt_share", 0.50), ("role.interior", 0.10),), "close-location events", "shooting responsibility and continuous interior role", "laterality remains uncertain")),
        "CONTESTEDJUMPER3POINT": (_Recipe("contested_three", (("derived.three_attempt_rate", 0.35), ("shooting.percent_assisted_x3p_fg", -0.25), ("derived.attempt_share", 0.15), ("role.creator", 0.10),), "contested-three events", "three volume, self-created context, and shooting responsibility", "self-created high-volume threes are the narrowest season-level contested-shot substitute"),),
        "CONTESTEDJUMPERMID": (_Recipe("contested_midrange_frequency", (("derived.mid_attempt_rate", 0.40), ("derived.unassisted_two_rate", 0.30), ("derived.attempt_share", 0.10), ("role.creator", 0.10),), "contested midrange events", "recorded midrange mass plus self-created shot context and offensive responsibility", "the approved field-specific substitute estimates difficult self-created midrange attempts without using make efficiency"), _Recipe("historical_contested_midrange_frequency", (("derived.attempt_share", 0.35), ("derived.foul_pressure", 0.25), ("role.creator", 0.10),), "contested-shot and assisted-location events", "creator responsibility, shot load, and live-contact pressure", "these all-era signals estimate difficult self-created attempts; FT% does not author the action")),
        "CONTESTEDJUMPERMIDRANGE": (_Recipe("contested_midrange_frequency", (("derived.mid_attempt_rate", 0.40), ("derived.unassisted_two_rate", 0.30), ("derived.attempt_share", 0.10), ("role.creator", 0.10),), "contested midrange events", "recorded midrange mass plus self-created shot context and offensive responsibility", "this storage alias uses the same field-specific action rule and Pool scale as CONTESTEDJUMPERMID"), _Recipe("historical_contested_midrange_frequency", (("derived.attempt_share", 0.35), ("derived.foul_pressure", 0.25), ("role.creator", 0.10),), "contested-shot and assisted-location events", "creator responsibility, shot load, and live-contact pressure", "the aliases remain identical and FT% does not author the action")),
        "DRIVEPULLUP3POINT": (_Recipe("drive_pullup_three", (("derived.three_attempt_rate", 0.30), ("shooting.percent_assisted_x3p_fg", -0.30), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "pull-up-three events", "unassisted three context and live-dribble creator pressure", "the substitute separates pull-ups from spot-ups"),),
        "DRIVEPULLUPMID": (_Recipe("drive_pullup_midrange_frequency", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("derived.foul_pressure", 0.10), ("role.creator", 0.10),), "drive-pull-up midrange events", "self-created midrange mass, creator role, and drive pressure", "the approved action substitute separates pull-ups from assisted spot-up and off-screen attempts"), _Recipe("historical_drive_pullup_midrange_frequency", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "drive-pull-up and self-created location events", "creator responsibility and live-contact pressure", "the all-era rule estimates live-dribble frequency without using shooting efficiency")),
        "DRIVEPULLUPMIDRANGE": (_Recipe("drive_pullup_midrange_frequency", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("derived.foul_pressure", 0.10), ("role.creator", 0.10),), "drive-pull-up midrange events", "self-created midrange mass, creator role, and drive pressure", "this storage alias uses the same action rule and Pool scale as DRIVEPULLUPMID"), _Recipe("historical_drive_pullup_midrange_frequency", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "drive-pull-up and self-created location events", "creator responsibility and live-contact pressure", "the aliases remain identical and no make percentage authors frequency")),
        "DRIVINGDUNK": (_Recipe("driving_dunk_frequency", (("derived.dunk_rate", 0.50), ("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "driving-dunk attempt events", "dunk/rim frequency and drive pressure", "makes count as observed action frequency here, never execution"), _Recipe("historical_driving_dunk_frequency", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.20), ("identity.ht_in_in", 0.15), ("role.interior", 0.10),), "driving-dunk and rim events", "drive pressure, continuous role/reach, and attempt responsibility", "no fixed athlete template is used")),
        "DRIVINGLAYUP": (_Recipe("driving_layup_frequency", (("derived.rim_attempt_rate", 0.45), ("derived.foul_pressure", 0.25), ("derived.dunk_rate", -0.15), ("role.creator", 0.10),), "driving-layup events", "rim pressure excluding dunk share plus creator role", "the sources describe action selection"), _Recipe("historical_driving_layup_frequency", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.20), ("role.creator", 0.10), ("role.post", 0.10),), "driving-layup and rim events", "foul pressure and shooting responsibility allocated through continuous creator-versus-post role", "post finishes cannot become driving-layup frequency without on-ball creator participation")),
        "EUROSTEPLAYUP": (_Recipe("euro_step_frequency", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.10),), "Euro-step events", "self-created rim/foul pressure", "the field-exact low-frequency calibration distinguishes the move"), _Recipe("historical_euro_step", (("derived.foul_pressure", 0.40), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "Euro-step and drive events", "drive pressure and creator responsibility", "no constant move package is inserted")),
        "FLASHYDUNK": (_Recipe("flashy_dunk_frequency", (("derived.dunk_rate", 0.45), ("identity.ht_in_in", 0.20), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "flashy-dunk events", "dunk frequency with live-drive/reach context", "the target is behavior frequency"), _Recipe("historical_flashy_dunk", (("identity.ht_in_in", 0.20), ("derived.attempt_share", 0.20), ("role.interior", 0.10), ("role.creator", 0.10),), "flashy-dunk and dunk events", "continuous reach/role and responsibility", "the low calibration prevents body context from creating a fixed high value")),
        "FLOATER": (_Recipe("floater_frequency", (("derived.three_to_ten_attempt_rate", 0.55), ("derived.unassisted_two_rate", 0.20), ("role.guard", 0.10),), "floater events", "3-10 foot attempt share and self-created guard context", "3-10 feet is valid for floaters, not layup moves"), _Recipe("historical_floater", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.30), ("role.guard", 0.10),), "floater and 3-10 foot events", "continuous guard drive pressure and responsibility", "the substitute stays distinct from layup execution")),
        "FROMPOSTSHOT": (_Recipe("shoot_from_post", (("derived.short_attempt_rate", 0.25), ("derived.mid_attempt_rate", 0.25), ("derived.attempt_share", 0.15), ("role.post", 0.10),), "post-shot events", "post role and recorded short/mid attempt mass", "the target is post shot selection"), _Recipe("historical_shoot_from_post", (("derived.attempt_share", 0.30), ("identity.wt", 0.20), ("role.post", 0.10),), "post-shot and location events", "continuous post role, responsibility, and leverage", "no efficiency score authors the tendency")),
        "HOPPOSTSHOT": (_Recipe("hop_post_shot", (("derived.mid_attempt_rate", 0.30), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15), ("role.post", 0.10),), "post-hop-shot events", "self-created post/midrange behavior", "the exact low-frequency target keeps the move rare"), _Recipe("historical_hop_post_shot", (("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "post-hop and location events", "post role, touch, and responsibility", "no generic constant is used")),
        "HOPSTEPLAYUP": (_Recipe("hop_step_layup", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.10),), "hop-step layup events", "self-created rim/foul pressure", "3-10 foot attempts are deliberately excluded"), _Recipe("historical_hop_step_layup", (("derived.foul_pressure", 0.40), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "hop-step and drive events", "drive pressure and creator responsibility", "the field remains a behavior tendency")),
        "POSTDROPSTEP": (_Recipe("post_drop_step", (("derived.short_attempt_rate", 0.30), ("identity.wt", 0.20), ("derived.foul_pressure", 0.15), ("role.post", 0.10),), "drop-step events", "post role, short frequency, leverage, and foul pressure", "all inputs describe move opportunity"), _Recipe("historical_post_drop_step", (("identity.wt", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "drop-step and post-touch events", "continuous post role, leverage, and responsibility", "no hard big-man gate is used")),
        "POSTFADELEFT": (_Recipe("post_fade_left", (("derived.mid_attempt_rate", 0.35), ("per_game.ft_percent", 0.20), ("derived.unassisted_two_rate", 0.15), ("role.post", 0.10),), "left post-fade events", "post self-created midrange touch", "public data has no left/right split; laterality remains uncertain"), _Recipe("historical_post_fade_left", (("per_game.ft_percent", 0.35), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "post-fade and directional events", "post role, touch, and responsibility", "laterality is not fabricated")),
        "POSTFADERIGHT": (_Recipe("post_fade_right", (("derived.mid_attempt_rate", 0.35), ("per_game.ft_percent", 0.20), ("derived.unassisted_two_rate", 0.15), ("role.post", 0.10),), "right post-fade events", "post self-created midrange touch", "public data has no left/right split; laterality remains uncertain"), _Recipe("historical_post_fade_right", (("per_game.ft_percent", 0.35), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "post-fade and directional events", "post role, touch, and responsibility", "laterality is not fabricated")),
        "POSTHOOKLEFT": (_Recipe("post_hook_left", (("derived.three_to_ten_attempt_rate", 0.35), ("identity.ht_in_in", 0.15), ("derived.unassisted_two_rate", 0.15), ("role.post", 0.10),), "left post-hook events", "post short-area self-creation and reach", "public data has no left/right split"), _Recipe("historical_post_hook_left", (("identity.ht_in_in", 0.25), ("derived.attempt_share", 0.30), ("role.post", 0.10),), "post-hook and directional events", "post role, reach, and responsibility", "laterality remains uncertain")),
        "POSTHOOKRIGHT": (_Recipe("post_hook_right", (("derived.three_to_ten_attempt_rate", 0.35), ("identity.ht_in_in", 0.15), ("derived.unassisted_two_rate", 0.15), ("role.post", 0.10),), "right post-hook events", "post short-area self-creation and reach", "public data has no left/right split"), _Recipe("historical_post_hook_right", (("identity.ht_in_in", 0.25), ("derived.attempt_share", 0.30), ("role.post", 0.10),), "post-hook and directional events", "post role, reach, and responsibility", "laterality remains uncertain")),
        "POSTSHIMMYSHOT": (_Recipe("post_shimmy", (("derived.mid_attempt_rate", 0.30), ("derived.unassisted_two_rate", 0.25), ("per_game.ft_percent", 0.15), ("role.post", 0.10),), "post-shimmy events", "post self-created midrange touch", "the low target calibration distinguishes this rare move"), _Recipe("historical_post_shimmy", (("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "post-shimmy and location events", "post role, touch, and responsibility", "no fixed post package is used")),
        "POSTSTEPBACKSHOT": (_Recipe("post_stepback", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.25), ("role.post", 0.10), ("role.wing", 0.10),), "post-stepback events", "hybrid post/wing self-created midrange behavior", "the field-exact low target keeps the move rare"), _Recipe("historical_post_stepback", (("per_game.ft_percent", 0.20), ("derived.attempt_share", 0.20), ("role.post", 0.10), ("role.wing", 0.10),), "post-stepback and location events", "hybrid role, touch, and responsibility", "no generic move constant is used")),
        "POSTUPANDUNDER": (_Recipe("post_up_and_under", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.20), ("derived.unassisted_two_rate", 0.20), ("role.post", 0.10),), "up-and-under events", "post short-area self-creation and foul pressure", "the inputs identify move frequency"), _Recipe("historical_post_up_and_under", (("derived.foul_pressure", 0.30), ("derived.attempt_share", 0.25), ("role.post", 0.10),), "up-and-under and post-touch events", "post role, foul pressure, and responsibility", "no execution output is reused")),
        "SPINJUMPER": (_Recipe("spin_jumper", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.30), ("derived.foul_pressure", 0.15), ("role.creator", 0.10),), "spin-jumper events", "self-created midrange and live-drive pressure", "the tendency remains distinct from driving spin"), _Recipe("historical_spin_jumper", (("per_game.ft_percent", 0.30), ("derived.attempt_share", 0.35), ("role.creator", 0.10),), "spin-jumper and pull-up events", "creator role, touch, and responsibility", "no fixed move package is inserted")),
        "SPINLAYUP": (_Recipe("spin_layup", (("derived.rim_attempt_rate", 0.25), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.25), ("role.creator", 0.10),), "spin-layup events", "self-created rim/foul pressure", "3-10 foot location is deliberately excluded"), _Recipe("historical_spin_layup", (("derived.foul_pressure", 0.40), ("derived.attempt_share", 0.25), ("role.creator", 0.10),), "spin-layup and drive events", "drive pressure and creator responsibility", "no make efficiency authors frequency")),
        "STANDINGDUNK": (_Recipe("standing_dunk_frequency", (("derived.rim_attempt_rate", 0.30), ("identity.ht_in_in", 0.25), ("identity.wt", 0.15), ("role.interior", 0.10),), "literal stationary-dunk attempts", "under-rim opportunity plus continuous interior and leverage context", "broad or moving dunk totals are deliberately excluded; this approved substitute estimates stationary opportunity only"), _Recipe("historical_standing_dunk_frequency", (("identity.ht_in_in", 0.30), ("identity.wt", 0.20), ("derived.attempt_share", 0.10), ("role.interior", 0.10),), "stationary-dunk and exact rim-location events", "continuous interior/reach/leverage context and offensive responsibility", "the historical rule stays separate from moving-dunk evidence and remains subject to era dunk suppression")),
        "STEPBACKJUMPER3POINT": (_Recipe("stepback_three", (("derived.three_attempt_rate", 0.30), ("shooting.percent_assisted_x3p_fg", -0.30), ("derived.attempt_share", 0.15), ("role.creator", 0.10),), "stepback-three events", "self-created three frequency and creator responsibility", "the field-exact low target keeps the move rare"),),
        "STEPBACKJUMPERMID": (_Recipe("stepback_mid_alias", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("derived.attempt_share", 0.10), ("role.creator", 0.10),), "stepback-mid events and a captured field-exact alias", "self-created midrange behavior and the captured Stepback Jumper Mid-Range distribution", "the active alias has no separate Pool label"),),
        "STEPBACKJUMPERMIDRANGE": (_Recipe("stepback_midrange", (("derived.mid_attempt_rate", 0.35), ("derived.unassisted_two_rate", 0.35), ("derived.attempt_share", 0.10), ("role.creator", 0.10),), "stepback-midrange events", "self-created midrange and creator responsibility", "the target is attempt behavior"),),
        "STEPTHROUGH": (_Recipe("step_through", (("derived.short_attempt_rate", 0.30), ("derived.foul_pressure", 0.30), ("derived.unassisted_two_rate", 0.20), ("role.post", 0.10),), "step-through events", "short-area self-creation, foul pressure, and post participation", "the field is authored once from its exact action context"), _Recipe("historical_step_through", (("derived.foul_pressure", 0.35), ("derived.attempt_share", 0.15), ("role.post", 0.10), ("role.creator", 0.10),), "step-through and short-location events", "drive/post pressure and responsibility", "no shared shot-family output is redistributed")),
        "TRANSITIONPULLUP3POINT": (_Recipe("transition_pullup_three", (("derived.three_attempt_rate", 0.35), ("shooting.percent_assisted_x3p_fg", -0.20), ("derived.scoring_share", 0.20), ("role.creator", 0.10),), "transition-pull-up-three events", "self-created three volume and transition-capable creator load", "the low field-exact target preserves rarity"),),
        "USEGLASS": (_Recipe("use_glass", (("derived.three_to_ten_attempt_rate", 0.50), ("derived.rim_attempt_rate", 0.25), ("role.interior", 0.10), ("role.guard", 0.10),), "bank-shot events", "3-10 foot and rim attempt context", "3-10 feet is permitted for glass use and is not reused for layup moves"), _Recipe("historical_use_glass", (("derived.attempt_share", 0.20), ("per_game.ft_percent", 0.15), ("role.interior", 0.10), ("role.guard", 0.10),), "bank-shot and 3-10 foot events", "continuous close-shot role and weak touch/responsibility context", "the target remains a behavior tendency")),
    }
)


_SHOT_EXECUTION_FIELDS = {
    "IQSHOT",
    "CLOSESHOT",
    "DRIVINGDUNK",
    "MIDRANGE",
    # POSTCONTROL is deliberately absent: it is holding position and working the
    # block, which a player can do without ever scoring. The shots taken from there
    # -- POSTFADE, POSTHOOK -- are execution and do belong here.
    "POSTHOOK",
    "STANDINGDUNK",
}

def _attribute(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    return _derive(f"derive_attribute_{field.lower()}", field, evidence, league_player_rows, _ATTR_RECIPES[field])


_DUNK_ATTEMPT_TENDENCY_FIELDS = {"DRIVINGDUNK", "STANDINGDUNK"}

# Generator seasons are season-ending years. These cutoffs translate the
# earliest defensible historical use into that representation; before the
# cutoff the move did not exist in the modeled era, so its tendency is zero.
_HISTORICAL_MOVE_TENDENCY_FIRST_SEASON_ENDING_YEAR: dict[str, int] = {
    "SETUPWITHHESITATION": 1942,
    "SETUPWITHSIZEUP": 1967,
    "DRIVINGCROSSOVER": 1955,
    "DRIVINGDOUBLECROSSOVER": 1990,
    "DRIVINGSPIN": 1955,
    "DRIVINGHALFSPIN": 1999,
    "DRIVINGSTEPBACK": 1970,
    "DRIVINGBEHINDTHEBACK": 1955,
    "DRIVINGDRIBBLEHESITATION": 1942,
    "DRIVINGINANDOUT": 1989,
    "EUROSTEPLAYUP": 2002,
    "HOPSTEPLAYUP": 2002,
}


def _tendency(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    first_season = _HISTORICAL_MOVE_TENDENCY_FIRST_SEASON_ENDING_YEAR.get(field)
    season = _season(evidence)
    if first_season is not None and season < first_season:
        return {
            "value": 0,
            "source_rule": f"derive_tendency_{field.lower()}_historical_introduction_gate",
            "evidence_keys": (
                f"season_ending_year={season}",
                f"first_supported_season_ending_year={first_season}",
                "historically_unavailable_move_tendency=0",
                "post_threshold_formula_unchanged=true",
            ),
        }
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
    made = _estimated_total(evidence, "fg")
    if made is not None and made <= 0.0:
        return {
            "value": 25,
            "source_rule": "derive_attribute_midrange_no_recorded_makes",
            "evidence_keys": (
                "totals.fg",
                "totals.fga",
                f"recorded_FG=0;recorded_FGA={attempts:.6g}" if attempts is not None else "recorded_FG=0",
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
        base_target = max(0.0, min(1.0, ft_percent)) * 0.5
        era = player_era_context(evidence)
        if era.era_key == "pre_shot_clock" and _era_role_playstyle_on():
            # Free-throw touch alone rates a pure pivot's face-up jumper the same
            # as a set-shot guard's. Pre-clock, the pivot barely faced up while
            # the perimeter set shot *was* the jumper -- and the team's primary
            # scorer took (and made) more of them. Modulate the FT%-touch target
            # by role and scoring load before the response-map inversion.
            # Read off height, not the position label. Who played with his back to the
            # basket pre-clock was a question of size, and size is recorded: the term runs
            # from nothing at 6'0" to full at 6'10" instead of switching on "post" and
            # "interior" role weights that a hyphenated NBL position could swing by 20
            # points of MIDRANGE on its own.
            height = _basic_value(evidence, "identity.ht_in_in")
            pivot = 0.0 if height is None else max(0.0, min(1.0, (height - 72.0) / 10.0))
            attempt_share = _derived_value(evidence, "attempt_share")
            load = max(0.0, min(1.0, (attempt_share or 0.0) / 0.22))
            factor = max(0.45, min(1.15, 1.0 - 0.42 * pivot + 0.18 * load - 0.10))
            target = max(0.0, min(1.0, base_target * factor))
            rating = midrange_rating_for_make_probability(target, context="spot_up")
            return {
                "value": rating,
                "source_rule": "derive_attribute_midrange_pre_shot_clock_height_touch_spot_up_response_map",
                "evidence_keys": (
                    "per_game.ft_percent",
                    "identity.ht_in_in",
                    "derived.attempt_share",
                    *era.evidence_keys,
                    f"historical_ft_percent={ft_percent:.8f}",
                    f"base_open_spot_up_make_probability=0.5*FT%={base_target:.8f}",
                    f"back_to_basket_height_weight={pivot:.6f}",
                    f"scoring_load_weight={load:.6f}",
                    f"touch_factor=1-0.42*height_share+0.18*load-0.10={factor:.6f}",
                    f"target_open_spot_up_make_probability={target:.8f}",
                    "mapping=inverse_piecewise_linear_open_spot_up_response",
                    "ft_percent_does_not_author_action_tendencies=true",
                ),
            }
        rating = midrange_rating_for_make_probability(base_target, context="spot_up")
        return {
            "value": rating,
            "source_rule": "derive_attribute_midrange_historical_ft_half_open_spot_up_response_map",
            "evidence_keys": (
                "per_game.ft_percent",
                f"historical_ft_percent={ft_percent:.8f}",
                f"target_open_spot_up_make_probability=0.5*FT%={base_target:.8f}",
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


def derive_attribute_standingdunk(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    height_in = _basic_value(evidence, "identity.ht_in_in")
    weight_lb = _basic_value(evidence, "identity.wt")
    if height_in is None or weight_lb is None:
        return None

    # The raw leaping model, not the published VERTICAL rating. That rating is
    # height-adjusted -- it answers how well a player leaps for his size, so it falls
    # as height rises -- while a standing dunk is standing reach plus inches jumped and
    # has to rise with reach. Reading the adjusted rating here made standing dunk fall
    # as players got taller.
    vertical_result = derive_attribute_vertical_unadjusted(evidence, league_player_rows=league_player_rows)
    if vertical_result is None:
        return None
    vertical = int(vertical_result["value"])

    # Standing-dunk *ability* is a clearance problem: can this player, from a standstill,
    # get the ball far enough over a 10-foot rim to throw it down reliably in a game.
    # Standing reach (~1.33x height) plus the standing portion of the vertical, minus
    # the rim plus control margin. The response is an S-curve, not a line: below true
    # size you basically can't (25-30s for a 6-3 guard), above it real bigs sit high
    # (mid-80s for a legit 6-10 center), with a steep transition through 6-6 to 6-8.
    standing_reach_in = 1.33 * height_in
    standing_vert_in = 15.0 + 0.20 * vertical
    clearance_in = standing_reach_in + standing_vert_in - 126.0  # 120" rim + 6" ball control
    hops_potential = 25.0 + 62.0 / (1.0 + math.exp(-0.50 * (clearance_in - 7.0)))

    # Rim finishing is a one-way, big-men-only ceiling: a modern big who converts
    # 55-70% at the rim (with a competent playmaker feeding the roll) reads as a 99
    # STANDINGDUNK regardless of a merely-average vertical. It never subtracts -- a low
    # or jump-shot-heavy percentage says nothing about whether the player *can* stand
    # and dunk (Jim Pollard shot corner jumpers and dunked from the foul line). Needs
    # the recorded rim split, so it is a modern signal; pre-tracking bigs ride the
    # physical clearance number, and their star exceptions live in player_star_profiles.
    rim_fg = _basic_value(evidence, "shooting.fg_percent_from_x0_3_range")
    value = hops_potential
    is_frontcourt = height_in >= 80.0  # 6'8"+
    if rim_fg is not None and is_frontcourt:
        attempts = _estimated_total(evidence, "fga")
        reliability = attempts / (attempts + 60.0) if attempts is not None and attempts > 0.0 else 0.0
        finish_rating = rim_finish_rating_for_make_probability(rim_fg)
        # a full-season rotation big's rim sample stands on its own; a thin sample gets
        # shrunk back toward the physical number
        finish_signal = finish_rating if reliability >= 0.60 else (
            finish_rating * reliability + hops_potential * (1.0 - reliability)
        )
        value = max(hops_potential, finish_signal)
        finish_evidence = (
            f"shooting.fg_percent_from_x0_3_range={rim_fg:.6f}",
            "rim_finish_response_anchor=(25,0.05)->(65,0.32)->(99,0.55)_plateau",
            f"rim_finish_rating={finish_rating}",
            f"attempt_reliability=fga/(fga+60)={reliability:.6f}",
            f"finish_signal={finish_signal:.4f}",
        )
    else:
        finish_evidence = (
            "standing_dunk_rim_finish_signal=not_applied "
            + ("(no_recorded_rim_split)" if rim_fg is None else "(below_6-8_frontcourt_gate)"),
        )

    stored = max(25, min(99, round(value)))
    # Same body ceiling the driving dunk uses. This rule builds from reach and
    # spring and never reached the shared anchor, so a 5'11" player kept a 27.
    fit = _standing_dunk_height_fit(evidence)
    if fit is not None:
        stored = min(stored, _attribute_bounds(25.0 + 74.0 * fit))
    return {
        "value": stored,
        "source_rule": "derive_attribute_standingdunk_reach_clearance_with_rim_finish_ceiling",
        "evidence_keys": (
            "identity.ht_in_in",
            "identity.wt",
            *tuple(vertical_result["evidence_keys"]),
            f"height_in={height_in:.6f}",
            f"weight_lb={weight_lb:.6f}",
            f"generated_VERTICAL={vertical}",
            f"standing_reach_in=1.33*height_in={standing_reach_in:.4f}",
            f"standing_vert_in=15+0.20*VERTICAL={standing_vert_in:.4f}",
            f"clearance_in=standing_reach+standing_vert-126={clearance_in:.4f}",
            f"hops_potential=25+62/(1+exp(-0.50*(clearance_in-7.0)))={hops_potential:.4f}",
            *finish_evidence,
            "value=max(hops_potential, blend(finish_potential,hops by frontcourt_factor)) (rim finish is a one-way ceiling)",
            "unavailable_direct_source=literal_stationary_dunk_execution_measurement",
            "validity=standing_dunk_execution_potential_only; no foul pressure, broad dunk total, or moving action evidence",
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
            _Recipe("recorded_short_attempt_location", (("derived.short_attempt_rate", 0.80), ("role.interior", 0.10),)),
            _Recipe("historical_close_attempt_role", (("derived.attempt_share", 0.45), ("derived.foul_pressure", 0.15), ("role.interior", 0.10),), "0-10 foot attempt location", "shooting responsibility, continuous interior participation, and foul pressure", "the sources describe close-shot opportunity/frequency rather than execution"),
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
            _Recipe("recorded_midrange_attempt_location", (("derived.mid_attempt_rate", 0.80), ("role.wing", 0.10),)),
            _Recipe("historical_midrange_attempt", (("derived.attempt_share", 1.0),), "10-foot-to-line attempt location", "shooting responsibility", "attempt share authors frequency; free-throw percentage is execution evidence and is excluded, and position is not an input"),
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


def derive_tendency_driveright(evidence: Any, *, league_player_rows: Any = ()) -> None:
    """Remain unresolved until individual left/right drive evidence exists."""

    return None


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


def derive_tendency_crash(evidence: Any, *, league_player_rows: Any = ()) -> None:
    """Remain unresolved until individual contact-fall outcome evidence exists."""

    return None


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


_OFFSCREEN_ACTION_FIELDS = {"MIDOFFSCREENSHOT", "3POINTOFFSCREENSHOT"}
_SPOTUP_ACTION_FIELDS = {"MIDSPOTUPSHOT", "3POINTSPOTUPSHOT"}
_OFFBALL_ACTION_ANCHORS: dict[str, tuple[int, int]] = {
    "thompkl01": (95, 95),
    "hamilri01": (100, 5),
    "curryst01": (100, 25),
    "millere01": (100, 13),
    "onealsh01": (0, 0),
    "abdulka01": (0, 0),
}
_OFFSCREEN_ACTION_RECIPES = (
    _Recipe(
        "off_screen_shot_action",
        (("shooting.percent_assisted_x2p_fg", 0.20), ("shooting.percent_assisted_x3p_fg", 0.20), ("shooting.percent_corner_3s_of_3pa", -0.15), ("derived.scoring_share", 0.25), ("role.wing", 0.10),),
        "off-screen movement-shot events",
        "assisted-shot dependence, non-corner movement context, scoring responsibility, and wing role",
        "range frequency is deliberately excluded because MID versus 3PT is selected before the off-screen action trigger",
    ),
    _Recipe(
        "historical_off_screen_shot_action",
        (("derived.scoring_share", 0.35), ("derived.attempt_share", 0.15), ("role.wing", 0.10), ("role.creator", 0.10),),
        "off-screen movement-shot events",
        "continuous wing role and scoring responsibility with reduced primary-ballhandler dependence",
        "historical box scores lack screen-route events; the substitute never uses make percentage or shot range",
    ),
)
_SPOTUP_ACTION_RECIPES = (
    _Recipe(
        "spot_up_shot_action",
        (("shooting.percent_assisted_x2p_fg", 0.25), ("shooting.percent_assisted_x3p_fg", 0.25), ("shooting.percent_corner_3s_of_3pa", 0.25), ("role.creator", 0.10), ("role.wing", 0.10),),
        "stationary spot-up shot events",
        "assisted-shot dependence, corner stationary context, reduced primary creation, and wing role",
        "range frequency is deliberately excluded because MID versus 3PT is selected before the spot-up action trigger",
    ),
    _Recipe(
        "historical_spot_up_shot_action",
        (("derived.scoring_share", -0.20), ("derived.attempt_share", 0.10), ("role.wing", 0.10), ("role.creator", 0.10),),
        "stationary spot-up shot events",
        "off-ball wing role with reduced creation and movement-scorer load",
        "historical box scores lack stationary catch-and-shoot events; the substitute never uses make percentage or shot range",
    ),
)


def _identity_text(source: Any, key: str) -> str:
    if isinstance(source, Mapping):
        value = source.get(f"identity.{key}") or source.get(f"player_info.{key}") or source.get(key)
    else:
        identity = getattr(source, "identity", {})
        value = identity.get(key) if isinstance(identity, Mapping) else None
    return str(value or "").strip().lower()


_NORMAL_DISTRIBUTION = statistics.NormalDist()
# Keeps the probit finite when a rank lands on exactly 0.0 or 1.0.
_RANK_PROBIT_LIMIT = 0.9995


def _value_from_rank(field: str, rank: float) -> int:
    """Score a 0-1 population rank through the same center/scale every rule uses.

    A rank is not a rating. Multiplying it by 100 put the median player at 50
    whatever the tendency was, which is how Spot-Up Mid ended up around four times
    its calibrated center and every big's spot-up jumper beat the post-up branch.
    Converting the rank to a z-score first keeps it on the field's own scale.
    """
    center, scale = _TENDENCY_CALIBRATION[field]
    bounded = min(max(float(rank), 1.0 - _RANK_PROBIT_LIMIT), _RANK_PROBIT_LIMIT)
    return max(0, min(100, int(round(center + _NORMAL_DISTRIBUTION.inv_cdf(bounded) * scale))))


def _offball_action_tendency(field: str, evidence: Any, league_player_rows: Any) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    era = player_era_context(evidence)
    if field.startswith("3POINT") and not era.has_three_point_line:
        return {
            "value": 0,
            "source_rule": f"derive_tendency_{field.lower()}_pre_line",
            "evidence_keys": (*era.evidence_keys, f"pre_line_{field}=0"),
        }
    action = "offscreen" if field in _OFFSCREEN_ACTION_FIELDS else "spotup"
    player_id = _identity_text(evidence, "player_id")
    anchor = _OFFBALL_ACTION_ANCHORS.get(player_id)
    if anchor is not None:
        value = anchor[0 if action == "offscreen" else 1]
        return {
            "value": value,
            "score": value / 100.0,
            "source_rule": f"derive_tendency_{field.lower()}_approved_behavior_anchor",
            "evidence_keys": (
                "identity.player_id",
                f"player_id={player_id}",
                f"approved_{action}_anchor={value}",
                "anchor_source=user-specified off-ball movement versus stationary spot-up behavior",
                "range_decision_contract=MID_or_3PT_is_selected_before_offscreen_or_spotup",
                "names_are_display_only;exact_player_id_authors_the_anchor",
            ),
        }
    rows = _population(evidence, league_player_rows)
    recipes = _OFFSCREEN_ACTION_RECIPES if action == "offscreen" else _SPOTUP_ACTION_RECIPES
    for recipe in recipes:
        result = _recipe_rank_score(evidence, rows, recipe)
        if result is None:
            continue
        score, evidence_keys = result
        return {
            "value": _value_from_rank(field, score),
            "score": score,
            "source_rule": f"derive_tendency_{field.lower()}_{recipe.name}",
            "evidence_keys": (
                "per_game.g",
                *evidence_keys,
                "mapping=weighted_same_season_same_league_action_percentiles_through_field_center_scale",
                "range_decision_contract=MID_or_3PT_is_selected_before_offscreen_or_spotup",
                "shot_range_attempt_rates_and_make_percentages_excluded=true",
            ),
        }
    return None


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

def _install_tendency_rule(function_name: str, field: str) -> None:
    def rule(evidence: Any, *, league_player_rows: Any = (), _field: str = field) -> dict[str, Any] | None:
        if _field in _OFFSCREEN_ACTION_FIELDS or _field in _SPOTUP_ACTION_FIELDS:
            return _offball_action_tendency(_field, evidence, league_player_rows)
        if _field in _EXTRA_THREE_POINT_FIELDS:
            return _three_point_tendency(_field, evidence, league_player_rows)
        return _tendency(_field, evidence, league_player_rows)
    rule.__name__ = function_name
    rule.__qualname__ = function_name
    globals()[function_name] = rule


for _function_name, _field_name in _EXTRA_TENDENCY_FUNCTIONS.items():
    _install_tendency_rule(_function_name, _field_name)


__all__ = [name for name in globals() if name.startswith("derive_attribute_") or name.startswith("derive_tendency_")]