from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from statistics import median
from typing import Any, Callable, Iterable


RuleOutput = dict[str, Any] | None


@dataclass(frozen=True)
class _AthleticModel:
    intercept: float
    height_residual: float
    weight_residual_per_ten: float
    source: str


_ATHLETIC_MODELS: dict[str, _AthleticModel] = {
    "speed_with_ball": _AthleticModel(
        70.000000000,
        -0.620567496,
        -0.048917651,
        "pool_gp765.overall_controlled_body",
    ),
    "vertical": _AthleticModel(
        75.700000000,
        0.049899040,
        0.390765020,
        "pool_gp765.overall_controlled_body",
    ),
}


_AGE_ADJUSTMENT: dict[str, Callable[[float], float]] = {
    "speed_with_ball": lambda age: -0.18 * max(age - 30.0, 0.0),
    "vertical": lambda age: 0.22 * max(25.0 - age, 0.0) - 0.45 * max(age - 28.0, 0.0),
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _attribute(value: float) -> int:
    return max(25, min(99, _round_half_up(value)))


def _dict_number(mapping: object, *keys: str) -> float | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = _number(mapping.get(key))
        if value is not None:
            return value
    return None


def _dict_text(mapping: object, *keys: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        text = str(mapping.get(key) or "").strip()
        if text:
            return text
    return ""


def _games_played(evidence: Any) -> float | None:
    return _dict_number(getattr(evidence, "per_game", {}), "g", "games", "games_played")


def _minutes_per_game(evidence: Any) -> float | None:
    return _dict_number(getattr(evidence, "per_game", {}), "mp_per_game", "mp")


def _team_games(evidence: Any) -> float | None:
    return _dict_number(getattr(evidence, "team_stats_per_game", {}), "g", "games")


# Stamina is conditioning, and conditioning tracks age far more than it tracks any
# box-score line. The curve is a two-sided parabola through three anchors: a floor of
# 85 for an eighteen-year-old, a peak of 99 in the prime, and 60 by forty. The decline
# side is steeper than the climb, which is what an ageing curve actually looks like.
_STAMINA_PEAK = 99.0
_STAMINA_PEAK_AGE = 27.5  # centre of the 25-30 prime; 25 and 30 both land at 97-98
_STAMINA_YOUNG_AGE, _STAMINA_YOUNG_VALUE = 18.0, 85.0
_STAMINA_OLD_AGE, _STAMINA_OLD_VALUE = 40.0, 60.0
#: How far the workload term may pull a player below his age band.
_STAMINA_WORKLOAD_RANGE = 8.0

# Durability's working band. Missing games is the only recorded durability outcome of
# the era, but a brief appearance is thin evidence rather than proof of fragility, so
# availability spans 75-95 rather than the whole scale. Age is the one term that may
# take a player under the band, capped so that stays exceptional.
_DURABILITY_FLOOR = 75.0
_DURABILITY_SPAN = 20.0
_DURABILITY_AGE_ONSET = 30.0
_DURABILITY_MAX_AGE_PENALTY = 15.0

# Joint-specific wear. Two patterns are well enough established to model: guards
# accumulate ankle damage as they age, from a career of cutting and landing on other
# players' feet; and players at or beyond seven feet carry knee and foot problems
# from the load their frame puts through those joints. Everything else stays on the
# body-wide value, because no source distinguishes an elbow from a shoulder.
_DURABILITY_ANKLE_AGE_ONSET = 28.0
_DURABILITY_ANKLE_MAX_PENALTY = 10.0
_DURABILITY_BIG_HEIGHT_ONSET = 84.0  # 7'0"
_DURABILITY_BIG_PENALTY_PER_INCH = 2.0
_DURABILITY_BIG_MAX_PENALTY = 12.0

#: Ankle wear runs on a line through height: full load at 6'0", none at 6'9".
_DURABILITY_ANKLE_ZERO_HEIGHT = 81.0
_DURABILITY_ANKLE_HEIGHT_SPAN = 9.0

ANKLE_JOINT = "ankle"
KNEE_JOINT = "knee"
FOOT_JOINT = "foot"
GENERIC_JOINT = "generic"


def _durability_joint_penalty(joint: str, evidence: Any, age: float | None) -> tuple[float, tuple[str, ...]]:
    if joint == ANKLE_JOINT:
        # Ankle wear accrues from cutting and changing direction, and the players doing
        # most of that are the small ones. That used to be read off the position label;
        # it is read off height now, on a line that carries full load at 6'0" and reaches
        # zero at 6'9". A 6'0" player takes the wear because he is 6'0".
        height = _height_inches(evidence)
        if height is None:
            return 0.0, ("joint_pattern=cutting_ankle_wear", "identity.ht_in_in=unavailable")
        guard = max(0.0, min(1.0, (_DURABILITY_ANKLE_ZERO_HEIGHT - height) / _DURABILITY_ANKLE_HEIGHT_SPAN))
        years = 0.0 if age is None else max(0.0, age - _DURABILITY_ANKLE_AGE_ONSET)
        penalty = guard * min(_DURABILITY_ANKLE_MAX_PENALTY, years)
        return penalty, (
            "identity.ht_in_in",
            "joint_pattern=cutting_ankle_wear",
            f"cutting_load_weight={guard:.4f}",
            f"years_past_{_DURABILITY_ANKLE_AGE_ONSET:g}={years:.4g}",
            f"ankle_penalty={penalty:.4f}",
        )
    if joint in {KNEE_JOINT, FOOT_JOINT}:
        height = _height_inches(evidence)
        if height is None:
            return 0.0, (f"joint_pattern=seven_foot_{joint}_load", "identity.ht_in_in=unavailable")
        over = max(0.0, height - _DURABILITY_BIG_HEIGHT_ONSET)
        penalty = min(_DURABILITY_BIG_MAX_PENALTY, over * _DURABILITY_BIG_PENALTY_PER_INCH)
        return penalty, (
            "identity.ht_in_in",
            f"joint_pattern=seven_foot_{joint}_load",
            f"height_inches={height:.4g}",
            f"inches_past_{_DURABILITY_BIG_HEIGHT_ONSET:g}={over:.4g}",
            f"{joint}_penalty={penalty:.4f}",
        )
    return 0.0, ("joint_pattern=body_wide_no_joint_specific_source",)


def _stamina_age_curve(age: float | None) -> float | None:
    if age is None:
        return None
    years = max(_STAMINA_YOUNG_AGE, age)
    if years <= _STAMINA_PEAK_AGE:
        span = _STAMINA_PEAK_AGE - _STAMINA_YOUNG_AGE
        drop = _STAMINA_PEAK - _STAMINA_YOUNG_VALUE
        return _STAMINA_PEAK - drop * (((_STAMINA_PEAK_AGE - years) / span) ** 2)
    span = _STAMINA_OLD_AGE - _STAMINA_PEAK_AGE
    drop = _STAMINA_PEAK - _STAMINA_OLD_VALUE
    # Forty is the last anchor, not a point the parabola may be extrapolated past.
    # Continuing it sent Nat Hickey, still playing at forty-five, to the attribute
    # floor; the curve holds at its endpoint instead.
    return max(
        _STAMINA_OLD_VALUE,
        _STAMINA_PEAK - drop * (((years - _STAMINA_PEAK_AGE) / span) ** 2),
    )


def _height_inches(evidence: Any) -> float | None:
    identity = getattr(evidence, "identity", {})
    height = _dict_number(identity, "ht_in_in", "height_inches")
    if height is not None:
        return height
    profile = getattr(evidence, "source_profile", {})
    return _dict_number(profile, "height_inches")


def _weight_pounds(evidence: Any) -> float | None:
    identity = getattr(evidence, "identity", {})
    weight = _dict_number(identity, "wt", "weight_pounds")
    if weight is not None:
        return weight
    profile = getattr(evidence, "source_profile", {})
    return _dict_number(profile, "weight_pounds")


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _age(evidence: Any) -> float | None:
    season_info = getattr(evidence, "season_info", {})
    direct = _dict_number(season_info, "age")
    if direct is not None:
        return direct
    identity = getattr(evidence, "identity", {})
    born = _parse_date(identity.get("born") if isinstance(identity, dict) else None)
    season = _number(getattr(evidence, "season", None))
    if born is not None and season is not None:
        return float(int(season) - born.year - (born.month > 7 or (born.month == 7 and born.day > 1)))
    return None


#: The pool's overall mean body -- the quadratics below evaluated at the neutral SF
#: coordinate. Residuals are measured against this rather than against the body
#: expected for a player's position: measuring a centre's height against "tall for a
#: centre" is position deciding the rating by the back door, and it made a 6'10" centre
#: read as ordinary while a 6'10" guard read as enormous.
_POOL_NEUTRAL_HEIGHT = 76.07845827
_POOL_NEUTRAL_WEIGHT = 197.68706676


def _pool_neutral_body() -> tuple[float, float]:
    return _POOL_NEUTRAL_HEIGHT, _POOL_NEUTRAL_WEIGHT


def _row_value(row: dict[str, Any], nested: str, prefixed: str) -> object:
    nested_row = row.get(nested)
    if isinstance(nested_row, dict):
        leaf = prefixed.rsplit(".", 1)[-1]
        if leaf in nested_row:
            return nested_row.get(leaf)
    return row.get(prefixed)


def _population_body_shift(
    rows: Iterable[dict[str, Any]],
    *,
    season: int,
) -> tuple[float, float, int]:
    height_residuals: list[float] = []
    weight_residuals: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_season = _number(_row_value(row, "season_info", "player_season_info.season"))
        if row_season is not None and int(row_season) != season:
            continue
        games = _number(_row_value(row, "per_game", "player_per_game.g"))
        if games is None or games <= 0.0:
            continue
        height = _number(_row_value(row, "identity", "player_info.ht_in_in"))
        weight = _number(_row_value(row, "identity", "player_info.wt"))
        if height is None or weight is None:
            continue
        expected_height, expected_weight = _pool_neutral_body()
        height_residuals.append(height - expected_height)
        weight_residuals.append(weight - expected_weight)
    if not height_residuals:
        return 0.0, 0.0, 0
    return float(median(height_residuals)), float(median(weight_residuals)), len(height_residuals)


def _population_body_extrema(
    rows: Iterable[dict[str, Any]],
) -> tuple[float, float, float, float, int, int] | None:
    heights: list[float] = []
    weights: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        games = _number(_row_value(row, "per_game", "player_per_game.g"))
        if games is None or games <= 0.0:
            continue
        height = _number(_row_value(row, "identity", "player_info.ht_in_in"))
        weight = _number(_row_value(row, "identity", "player_info.wt"))
        if height is not None:
            heights.append(height)
        if weight is not None:
            weights.append(weight)
    if not heights or not weights:
        return None
    return min(heights), max(heights), min(weights), max(weights), len(heights), len(weights)


def _inverse_min_max_rating(value: float, minimum: float, maximum: float) -> float | None:
    span = maximum - minimum
    if span <= 0.0:
        return None
    bounded = max(minimum, min(maximum, value))
    return 99.0 - 74.0 * ((bounded - minimum) / span)


def _direct_min_max_rating(value: float, minimum: float, maximum: float) -> float | None:
    span = maximum - minimum
    if span <= 0.0:
        return None
    bounded = max(minimum, min(maximum, value))
    return 25.0 + 74.0 * ((bounded - minimum) / span)


def _body_compactness(height: float, weight: float) -> float | None:
    if height <= 0.0 or weight <= 0.0:
        return None
    return weight / height


def _population_body_compactness_extrema(
    rows: Iterable[dict[str, Any]],
) -> tuple[float, float, int] | None:
    compactness_values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        games = _number(_row_value(row, "per_game", "player_per_game.g"))
        if games is None or games <= 0.0:
            continue
        height = _number(_row_value(row, "identity", "player_info.ht_in_in"))
        weight = _number(_row_value(row, "identity", "player_info.wt"))
        if height is None or weight is None:
            continue
        compactness = _body_compactness(height, weight)
        if compactness is not None:
            compactness_values.append(compactness)
    if not compactness_values:
        return None
    return min(compactness_values), max(compactness_values), len(compactness_values)


def _athletic_context(
    evidence: Any,
    league_player_rows: Iterable[dict[str, Any]],
) -> tuple[float, float, float | None, tuple[str, ...]] | None:
    games = _games_played(evidence)
    if games is None or games <= 0.0:
        return None
    season = int(getattr(evidence, "season", 0) or 0)
    league = _dict_text(getattr(evidence, "season_info", {}), "lg", "league").upper()
    expected_height, expected_weight = _pool_neutral_body()
    height_shift, weight_shift, population_count = _population_body_shift(
        league_player_rows,
        season=season,
    )
    expected_height += height_shift
    expected_weight += weight_shift
    height = _height_inches(evidence)
    weight = _weight_pounds(evidence)
    body_keys: list[str] = []
    if height is None:
        height = expected_height
        body_keys.append("identity.height=missing; substitute=same_season_same_league_expected_height")
    else:
        body_keys.extend(("identity.ht_in_in", f"identity_height_inches={height:.6g}"))
    if weight is None:
        weight = expected_weight
        body_keys.append("identity.weight=missing; substitute=same_season_same_league_expected_weight")
    else:
        body_keys.extend(("identity.wt", f"identity_weight_pounds={weight:.6g}"))
    age = _age(evidence)
    keys = (
        "per_game.g",
        f"games_played={games:.6g}",
        *body_keys,
        f"population.same_season_same_league_gp_body_rows={population_count}",
        f"population.expected_height={expected_height:.6g}",
        f"population.expected_weight={expected_weight:.6g}",
        f"era.season={season}; league={league or 'unknown'}; direct_rating_penalty=none",
        "pool_identity=(run_id,player_index); captures=editor_capture_001,editor_capture_002; gp_valid_packages=765",
    )
    return height - expected_height, (weight - expected_weight) / 10.0, age, keys


def _derive_athletic_field(
    field: str,
    evidence: Any,
    league_player_rows: Iterable[dict[str, Any]],
) -> RuleOutput:
    context = _athletic_context(evidence, league_player_rows)
    if context is None:
        return None
    height_residual, weight_residual, age, evidence_keys = context
    model = _ATHLETIC_MODELS[field]
    value = (
        model.intercept
        + model.height_residual * height_residual
        + model.weight_residual_per_ten * weight_residual
    )
    age_keys: tuple[str, ...]
    if age is None:
        age_keys = ("age=missing; age_adjustment=0; no unrelated production substitute",)
    else:
        adjustment = _AGE_ADJUSTMENT[field](age)
        value += adjustment
        age_keys = (
            "season_info.age",
            f"age_value={age:.6g}; continuous_{field}_age_adjustment={adjustment:.6g}",
            "age_adjustment_source=continuous_interpolation_of_researched_field_specific_age_context",
        )
    provenance = (
        *evidence_keys,
        *age_keys,
        f"body.height_residual={height_residual:.6g}",
        f"body.weight_residual_per_ten={weight_residual:.6g}",
        f"calibration={model.source}",
        "pool_quantiles_are_distribution_evidence_not_rating_gates",
        f"unavailable_direct_source=individual_{field}_measurement",
        "substitute_source=gp_valid_pool_body_relationship_plus_same_season_same_league_body_context_and_continuous_age",
        f"validity={field}_conditional_estimate_when_direct_athletic_measurement_is_absent; no_assist_or_production_input",
        "excluded_runtime_inputs=assists,overall,production",
    )
    return {
        "value": _attribute(value),
        "source_rule": f"derive_attribute_{field}_field_specific_context_substitute",
        "evidence_keys": provenance,
    }


# --- Height and age shape the athletic attributes -------------------------------
#
# Speed: 6'6" and under may reach the ceiling. Above that the ceiling falls away,
# gently at first and then sharply, so 7'5" can still be a genuinely quick 70s
# player while 7'9" cannot clear the floor whatever else is true of him.
_SPEED_FREE_HEIGHT = 78.0   # 6'6"
_SPEED_FLOOR_HEIGHT = 93.0  # 7'9"
_SPEED_CEILING_EXPONENT = 0.35

#: Foot speed peaks earlier than conditioning and leaves earlier too.
_SPEED_PEAK_AGE = 24.0
_SPEED_YOUNG_AGE, _SPEED_OLD_AGE = 18.0, 38.0
_SPEED_AGE_YOUNG_SHARE, _SPEED_AGE_OLD_SHARE = 0.94, 0.72

#: Agility: a big man changes direction worse than he runs straight, and past 6'9"
#: the penalty stops being gentle.
_AGILITY_PIVOT_HEIGHT = 81.0  # 6'9"
_AGILITY_TALL_PENALTY_PER_INCH = 3.2
_AGILITY_MAX_TALL_PENALTY = 30.0

#: Strength: mass drives it, but a player cannot out-muscle someone with five inches
#: on him, so height sets the ceiling he is measured against.
_STRENGTH_FLOOR_HEIGHT, _STRENGTH_CEILING_HEIGHT = 66.0, 84.0

#: Vertical is leaping ability, not standing reach. Two players who jump the same
#: measured inches are not equally explosive if one is seven inches taller: Curry and
#: Griffin both measured 35.5, and Curry is the better leaper for his frame.
#: Neutral at 6'6", the middle of the 99-vertical group -- Iverson at 6'0", Jordan at
#: 6'6", Erving at 6'7", James at 6'8" all belong there, so the penalty has to stay
#: mild across that band. It is the seven-inch gaps that matter: Curry over Griffin,
#: Russell over Chamberlain.
_VERTICAL_NEUTRAL_HEIGHT = 78.0
_VERTICAL_HEIGHT_PENALTY_PER_INCH = 1.0



def _speed_age_share(age: float | None) -> float:
    if age is None:
        return 1.0
    if age <= _SPEED_PEAK_AGE:
        span = _SPEED_PEAK_AGE - _SPEED_YOUNG_AGE
        drop = 1.0 - _SPEED_AGE_YOUNG_SHARE
        years = max(_SPEED_YOUNG_AGE, age)
        return 1.0 - drop * (((_SPEED_PEAK_AGE - years) / span) ** 2)
    span = _SPEED_OLD_AGE - _SPEED_PEAK_AGE
    drop = 1.0 - _SPEED_AGE_OLD_SHARE
    years = min(_SPEED_OLD_AGE, age)
    return 1.0 - drop * (((years - _SPEED_PEAK_AGE) / span) ** 2)


def derive_attribute_speed(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    games = _games_played(evidence)
    height = _height_inches(evidence)
    weight = _weight_pounds(evidence)
    extrema = _population_body_extrema(league_player_rows)
    if games is None or games <= 0.0 or height is None or weight is None or extrema is None:
        return None
    min_height, max_height, min_weight, max_weight, height_count, weight_count = extrema
    height_rating = _inverse_min_max_rating(height, min_height, max_height)
    weight_rating = _inverse_min_max_rating(weight, min_weight, max_weight)
    if height_rating is None or weight_rating is None:
        return None
    identity = getattr(evidence, "identity", {})
    height_source = "identity.ht_in_in" if _dict_number(identity, "ht_in_in", "height_inches") is not None else "source_profile.height_inches"
    weight_source = "identity.wt" if _dict_number(identity, "wt", "weight_pounds") is not None else "source_profile.weight_pounds"
    body_value = 0.5 * height_rating + 0.5 * weight_rating
    age = _age(evidence)
    age_share = _speed_age_share(age)
    return {
        "value": _attribute(body_value * age_share),
        "source_rule": "derive_attribute_speed_body_age_curve",
        "evidence_keys": (
            "per_game.g",
            f"games_played={games:.6g}",
            height_source,
            f"height_inches={height:.6g}",
            f"body_value={body_value:.4f}",
            ("season_info.age" if age is not None else "age=missing"),
            f"speed_age_share={age_share:.6f}",
            "speed_contract=6ft6_and_under_may_reach_99; 7ft9_cannot_clear_the_floor; age_bell_curve_peaks_at_24",
            weight_source,
            f"weight_pounds={weight:.6g}",
            f"population.full_generated_pool_height_rows={height_count}",
            f"population.full_generated_pool_weight_rows={weight_count}",
            f"population.min_height_inches={min_height:.6g}",
            f"population.max_height_inches={max_height:.6g}",
            f"population.min_weight_pounds={min_weight:.6g}",
            f"population.max_weight_pounds={max_weight:.6g}",
            f"inverse_height_min_max_rating={height_rating:.6g}",
            f"inverse_weight_min_max_rating={weight_rating:.6g}",
            "mapping=average_of_inverse_height_and_weight_min_max_ratings",
            "rating_endpoints=minimum_body_measurement_99;maximum_body_measurement_25",
            "population_scope=full_generated_pool_gp_positive_rows",
        ),
    }


def derive_attribute_agility(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    """Changing direction, which is not the same skill as running in a straight line.

    Agility used to return SPEED verbatim, so the two fields were the same number on
    every card. It is now led by perimeter defence -- staying in front of a man is the
    observable form of lateral agility -- and by the same age curve foot speed
    follows, with a harsh penalty past 6'9" where changing direction stops being cheap.
    """

    speed = derive_attribute_speed(evidence, league_player_rows=league_player_rows)
    if speed is None:
        return None

    import player_rules_defense as defense  # local: defense does not import this module

    perimeter = defense.derive_attribute_perimeterdefense(evidence, league_player_rows=league_player_rows)
    perimeter_value = (
        float(perimeter["value"])
        if perimeter is not None and isinstance(perimeter.get("value"), (int, float))
        else None
    )
    age = _age(evidence)
    age_share = _speed_age_share(age)
    height = _height_inches(evidence)

    base = float(speed["value"])
    keys = ["per_game.g", f"speed_attribute={int(speed['value'])}"]
    if perimeter_value is not None:
        base = 0.45 * base + 0.55 * perimeter_value
        keys.extend((
            "Attributes/PERIMETERDEFENSE",
            f"perimeter_defense={int(perimeter_value)}",
            "agility_blend=speed:0.45,perimeter_defense:0.55",
        ))
    else:
        keys.append("perimeter_defense=unavailable;agility_falls_back_to_speed_and_age")
    base *= age_share
    keys.extend((
        ("season_info.age" if age is not None else "age=missing"),
        f"agility_age_share={age_share:.6f}",
    ))
    penalty = 0.0
    if height is not None and height > _AGILITY_PIVOT_HEIGHT:
        penalty = min(
            _AGILITY_MAX_TALL_PENALTY,
            (height - _AGILITY_PIVOT_HEIGHT) * _AGILITY_TALL_PENALTY_PER_INCH,
        )
        keys.extend((
            "identity.ht_in_in",
            f"height_inches={height:.6g}",
            f"agility_tall_penalty={penalty:.4f}",
            f"agility_tall_penalty_onset={_AGILITY_PIVOT_HEIGHT:g}",
        ))
    return {
        "value": _attribute(base - penalty),
        "source_rule": "derive_attribute_agility_perimeter_defense_age_height",
        "evidence_keys": tuple(dict.fromkeys(keys)),
    }


#: Ceiling for speed with the ball, as a share of the player's own speed. Nobody
#: moves faster dribbling than running, so this can never reach 1.0.
_SPEED_WITH_BALL_MAX_SHARE = 0.97



def derive_attribute_speedwithball(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    result = _derive_athletic_field("speed_with_ball", evidence, league_player_rows)
    if result is None:
        return None
    # Speed with the ball is a handling constraint applied to a player's speed, not a
    # second independent body model. It was derived from the same frame inputs as
    # SPEED with no reference to SPEED itself, which let a player dribble faster than
    # he could run.
    speed = derive_attribute_speed(evidence, _field_index, league_player_rows, _positions)
    if speed is None or not isinstance(speed.get("value"), (int, float)):
        return result
    return {
        **result,
        "evidence_keys": tuple(result["evidence_keys"]) + (
            f"speed_attribute={int(speed['value'])}",
            "speed_with_ball_contract=body_model_only; no ceiling against the player's own speed",
        ),
    }

def derive_attribute_strength(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    games = _games_played(evidence)
    height = _height_inches(evidence)
    weight = _weight_pounds(evidence)
    extrema = _population_body_compactness_extrema(league_player_rows)
    if games is None or games <= 0.0 or height is None or weight is None or extrema is None:
        return None
    compactness = _body_compactness(height, weight)
    if compactness is None:
        return None
    minimum, maximum, population_count = extrema
    rating = _direct_min_max_rating(compactness, minimum, maximum)
    if rating is None:
        return None
    identity = getattr(evidence, "identity", {})
    height_source = "identity.ht_in_in" if _dict_number(identity, "ht_in_in", "height_inches") is not None else "source_profile.height_inches"
    weight_source = "identity.wt" if _dict_number(identity, "wt", "weight_pounds") is not None else "source_profile.weight_pounds"
    return {
        "value": _attribute(rating),
        "source_rule": "derive_attribute_strength_body_compactness",
        "evidence_keys": (
            "per_game.g",
            f"games_played={games:.6g}",
            height_source,
            f"height_inches={height:.6g}",
            weight_source,
            f"weight_pounds={weight:.6g}",
            f"uncapped_compactness_rating={rating:.4f}",
            f"body_compactness_weight_per_height={compactness:.6g}",
            f"population.same_season_same_league_gp_body_rows={population_count}",
            f"population.min_body_compactness={minimum:.6g}",
            f"population.max_body_compactness={maximum:.6g}",
            "mapping=direct_min_max_of_weight_pounds_per_height_inch",
            "rating_endpoints=minimum_body_compactness_25;maximum_body_compactness_99",
            "population_scope=same_season_same_league_gp_positive_rows",
            "excluded_runtime_inputs=position,age,overall,production",
        ),
    }


#: Anchor percentiles for the vertical stretch. Swept against the 1947 population:
#: 5/95 clamped fifty players onto 99, 1/99 left the floor at 31. 2/98 spans 26-99
#: with seven at the ceiling.
_VERTICAL_ANCHOR_LOW = 0.02
_VERTICAL_ANCHOR_HIGH = 0.98

_VERTICAL_EXTREMA_CACHE: dict[int, tuple[object, tuple[float, float] | None]] = {}


def _row_vertical_value(row: dict[str, Any]) -> float | None:
    """The vertical body model evaluated on a comparison row."""

    height = _number(_row_value(row, "identity", "player_info.ht_in_in"))
    weight = _number(_row_value(row, "identity", "player_info.wt"))
    if height is None or weight is None:
        return None
    expected_height, expected_weight = _pool_neutral_body()
    model = _ATHLETIC_MODELS["vertical"]
    value = (
        model.intercept
        + model.height_residual * (height - expected_height)
        + model.weight_residual_per_ten * ((weight - expected_weight) / 10.0)
    )
    age = _number(_row_value(row, "season_info", "player_season_info.age"))
    if age is not None:
        value += _AGE_ADJUSTMENT["vertical"](age)
    return value - (height - _VERTICAL_NEUTRAL_HEIGHT) * _VERTICAL_HEIGHT_PENALTY_PER_INCH


def _population_vertical_extrema(rows: Iterable[dict[str, Any]]) -> tuple[float, float] | None:
    """Lowest and highest height-adjusted vertical in the comparison population.

    Vertical is a body model with narrow coefficients, so it only ever produced about
    26 points of a 74-point scale -- the whole 1947 league sat between 61 and 87.
    Anchoring the season's own range to 25-99 makes the field use the scale it is
    written on without changing who is above whom.
    """

    rows = tuple(rows)
    cache_key = id(rows)
    cached = _VERTICAL_EXTREMA_CACHE.get(cache_key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    values = [
        value
        for row in rows
        if isinstance(row, dict)
        and (_number(_row_value(row, "per_game", "player_per_game.g")) or 0.0) > 0.0
        and (value := _row_vertical_value(row)) is not None
    ]
    # Anchored on the 5th and 95th percentiles rather than the outright extremes. The
    # population values come from the raw body model, while a generated player's value
    # shifts upward when the multi-position merge takes his higher branch -- so mapping
    # the raw min and max left the season sitting inside 38-86 instead of reaching the
    # ends. Percentile anchors let the real extremes clamp onto 25 and 99.
    extrema = None
    if len(values) >= 20:
        ordered = sorted(values)
        low = ordered[int(_VERTICAL_ANCHOR_LOW * (len(ordered) - 1))]
        high = ordered[int(_VERTICAL_ANCHOR_HIGH * (len(ordered) - 1))]
        if high > low:
            extrema = (low, high)
    elif len(values) >= 2 and max(values) > min(values):
        extrema = (min(values), max(values))
    _VERTICAL_EXTREMA_CACHE[cache_key] = (rows, extrema)
    return extrema


def derive_attribute_vertical_unadjusted(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    """The raw leaping model, before the height adjustment and population stretch.

    The published VERTICAL rating answers "how well does he leap for his size", so it
    falls as height rises. Standing dunk asks the opposite question -- can he get the
    ball over the rim from a standstill -- which is standing reach plus actual inches
    jumped, and must rise with height. Reading the adjusted rating there made standing
    dunk non-monotonic in reach.
    """

    return _derive_athletic_field("vertical", evidence, league_player_rows)


def derive_attribute_vertical(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    """Leaping ability, measured off the floor rather than off standing reach.

    The body model leans slightly toward bigs, which reads a tall player's reach as
    explosiveness. Curry and Griffin both measured 35.5 inches and Curry is plainly
    the better leaper for his frame; Russell out-jumped Chamberlain by a foot in the
    high jump while giving up three inches of height. Height is therefore a penalty
    here, not a credit.
    """

    result = _derive_athletic_field("vertical", evidence, league_player_rows)
    if result is None:
        return None
    height = _height_inches(evidence)
    if height is None:
        return result
    penalty = (height - _VERTICAL_NEUTRAL_HEIGHT) * _VERTICAL_HEIGHT_PENALTY_PER_INCH
    adjusted = float(result["value"]) - penalty
    extrema = _population_vertical_extrema(league_player_rows)
    stretch_keys: tuple[str, ...] = ()
    if extrema is not None:
        low, high = extrema
        share = max(0.0, min(1.0, (adjusted - low) / (high - low)))
        adjusted = 25.0 + 74.0 * share
        stretch_keys = (
            f"population_vertical_minimum={low:.4f}",
            f"population_vertical_maximum={high:.4f}",
            f"population_vertical_share={share:.8f}",
            "mapping=round(25+74*same_season_scope_vertical_share)",
            "stretch_reason=the body model spans about a third of the attribute scale on its own",
        )
    return {
        **result,
        "value": _attribute(adjusted),
        "source_rule": "derive_attribute_vertical_height_adjusted_population_stretch",
        "evidence_keys": tuple(result["evidence_keys"]) + (
            "identity.ht_in_in",
            f"height_inches={height:.6g}",
            f"vertical_height_penalty={penalty:.4f}",
            f"vertical_neutral_height={_VERTICAL_NEUTRAL_HEIGHT:g}",
            "vertical_contract=equal_measured_jump_favours_the_shorter_player",
            *stretch_keys,
        ),
    }


#: Acceleration is a blend of straight-line speed and change of direction. Named so
#: the pre-1952 pass can re-derive the field after it rewrites either input; the two
#: call sites must not drift apart.
ACCELERATION_SPEED_WEIGHT = 0.55
ACCELERATION_AGILITY_WEIGHT = 0.45


def derive_attribute_acceleration(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    speed = derive_attribute_speed(evidence, league_player_rows=league_player_rows)
    agility = derive_attribute_agility(evidence, league_player_rows=league_player_rows)
    if speed is None or agility is None:
        return None
    speed_value = int(speed["value"])
    agility_value = int(agility["value"])
    return {
        "value": _attribute(
            ACCELERATION_SPEED_WEIGHT * speed_value + ACCELERATION_AGILITY_WEIGHT * agility_value
        ),
        "source_rule": "derive_attribute_acceleration_field_specific_context_substitute",
        "evidence_keys": (
            *tuple(speed["evidence_keys"]),
            f"joint_speed={speed_value}",
            f"joint_agility={agility_value}",
            "unavailable_direct_source=individual_acceleration_measurement",
            "substitute_source=joint_pool_calibrated_speed_and_agility_conditional_estimates",
            "validity=acceleration_first_step_proxy_from_joint_mobility_without_assist_or_production_input",
            "acceleration_mix=0.55_speed_plus_0.45_agility",
        ),
    }


def _previous_season_mpg(evidence: Any, rows: Iterable[dict[str, Any]]) -> float | None:
    player_id = str(getattr(evidence, "player_id", "") or "").strip().upper()
    season = int(getattr(evidence, "season", 0) or 0)
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_player_id = str(row.get("player_id") or "").strip().upper()
        row_season = _number(row.get("season"))
        if row_player_id != player_id or row_season is None or int(row_season) != season - 1:
            continue
        nested = row.get("per_game")
        mpg = _dict_number(nested, "mp_per_game", "mp")
        if mpg is None:
            mpg = _number(row.get("player_per_game.mp_per_game"))
        if mpg is not None:
            return mpg
    return None


def derive_attribute_stamina(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    games = _games_played(evidence)
    mpg = _minutes_per_game(evidence)
    if games is None or games <= 0.0:
        return None
    age = _age(evidence)
    base = _stamina_age_curve(age)
    if base is None:
        return None

    # Workload is the secondary term. It only ever subtracts, and never by more than
    # _STAMINA_WORKLOAD_RANGE, so a player's age decides the band he sits in and how
    # heavily he was used decides where inside it -- not the other way round.
    if mpg is None:
        team_games = _team_games(evidence)
        if team_games is None or team_games <= 0.0:
            return None
        load = max(0.0, min(1.0, games / team_games)) ** (1.0 / 3.0)
        workload_keys = (
            "team_stats_per_game.g",
            f"team_games={team_games:.6g}",
            f"availability_share={games / team_games:.8f}",
            "unavailable_direct_source=per_game.mp_per_game",
            "substitute_source=recorded_share_of_team_schedule_played",
            "validity=availability_is_the_only_recorded_workload_signal_before_minutes_were_published",
        )
        source_rule = "derive_attribute_stamina_age_curve_availability_workload"
    else:
        if mpg < 0.0:
            return None
        load = max(0.0, min(1.0, mpg / 36.0))
        workload_keys = (
            "per_game.mp_per_game",
            f"minutes_per_game={mpg:.6g}",
            "workload_reference=36_minutes_per_game",
        )
        source_rule = "derive_attribute_stamina_age_curve_minutes_workload"

    penalty = _round_half_up(_STAMINA_WORKLOAD_RANGE * (1.0 - load))
    value = _attribute(base - penalty)
    return {
        "value": value,
        "source_rule": source_rule,
        "evidence_keys": (
            "per_game.g",
            f"games_played={games:.6g}",
            ("season_info.age" if age is not None else "age=missing"),
            f"age={age:.6g}" if age is not None else "age=missing",
            *workload_keys,
            f"age_curve_value={base:.4f}",
            f"workload_load={load:.8f}",
            f"workload_penalty={penalty}",
            "stamina_contract=age_bell_curve(18:85, peak_99_at_27.5, 40:60)_minus_workload_penalty",
            f"workload_penalty_range=0..{_STAMINA_WORKLOAD_RANGE:g}",
        ),
    }


def _fixed(rule_name: str, value: int, keys: tuple[str, ...]) -> dict[str, Any]:
    return {"value": value, "source_rule": rule_name, "evidence_keys": keys}


def _durability(rule_name: str, evidence: Any, joint: str = GENERIC_JOINT) -> dict[str, Any] | None:
    """Availability-and-age durability, with the two joint patterns that are real.

    The body-wide term is missed games plus age: the only durability outcome the era
    recorded. On top of it, ankles carry guard wear that accumulates with age, and
    knees and feet carry the load a seven-foot frame puts through them. Every other
    joint stays on the body-wide value, because nothing in the sources distinguishes
    an elbow from a shoulder and inventing a difference would be fabrication.

    This replaced a fixed 90 that gave every player in the league the same number, so
    eighteen fields carried no information while adding 1,620 constant points to every
    Total Attributes.
    """

    games = _games_played(evidence)
    team_games = _team_games(evidence)
    if games is None or team_games is None or team_games <= 0.0:
        return None
    share = max(0.0, min(1.0, games / team_games))
    age = _age(evidence)
    # The working band is 75-95: an available player tops out at 95, and the cube
    # root keeps the band top-heavy so a short stint reads as thin evidence rather
    # than as a fragile player. Age is the only term allowed to push below 75, and
    # only for the genuinely old -- it is capped so the tail stays a tail.
    availability = _DURABILITY_FLOOR + _DURABILITY_SPAN * (share ** (1.0 / 3.0))
    age_penalty = (
        min(_DURABILITY_MAX_AGE_PENALTY, max(0.0, age - _DURABILITY_AGE_ONSET))
        if age is not None
        else 0.0
    )
    joint_penalty, joint_keys = _durability_joint_penalty(joint, evidence, age)
    value = _attribute(availability - age_penalty - joint_penalty)
    return {
        "value": value,
        "source_rule": rule_name,
        "evidence_keys": (
            "per_game.g",
            "team_stats_per_game.g",
            f"games_played={games:.6g}",
            f"team_games={team_games:.6g}",
            f"availability_share={share:.8f}",
            ("season_info.age" if age is not None else "age=missing"),
            f"availability_value={availability:.4f}",
            f"age_penalty={age_penalty:g}",
            f"joint={joint}",
            *joint_keys,
            "unavailable_direct_source=injury_database",
            "substitute_source=recorded_share_of_team_schedule_played_with_age_decline",
            "validity=missed_games_are_the_only_recorded_durability_outcome_of_the_era",
            "durability_contract=round(75+20*cbrt(availability_share))_minus_capped_years_over_30_minus_joint_pattern",
            "joint_patterns=guard_ankle_wear_with_age; seven_foot_knee_and_foot_load",
        ),
    }


def derive_attribute_backdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_backdurability', evidence)


def derive_attribute_headdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_headdurability', evidence)


def derive_attribute_leftankledurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_leftankledurability', evidence, ANKLE_JOINT)


def derive_attribute_leftelbowdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_leftelbowdurability', evidence)


def derive_attribute_leftfootdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_leftfootdurability', evidence, FOOT_JOINT)


def derive_attribute_lefthanddurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_lefthanddurability', evidence)


def derive_attribute_lefthipdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_lefthipdurability', evidence)


def derive_attribute_leftkneedurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_leftkneedurability', evidence, KNEE_JOINT)


def derive_attribute_leftshoulderdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_leftshoulderdurability', evidence)


def derive_attribute_miscdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_miscdurability', evidence)


def derive_attribute_neckdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_neckdurability', evidence)


def derive_attribute_rightankledurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_rightankledurability', evidence, ANKLE_JOINT)


def derive_attribute_rightelbowdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_rightelbowdurability', evidence)


def derive_attribute_rightfootdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_rightfootdurability', evidence, FOOT_JOINT)


def derive_attribute_righthanddurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_righthanddurability', evidence)


def derive_attribute_righthipdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_righthipdurability', evidence)


def derive_attribute_rightkneedurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_rightkneedurability', evidence, KNEE_JOINT)


def derive_attribute_rightshoulderdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _durability('derive_attribute_rightshoulderdurability', evidence)