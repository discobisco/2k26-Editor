from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from statistics import median
from typing import Any, Callable, Iterable


RuleOutput = dict[str, Any] | None


_POSITION_COORDINATE: dict[str, float] = {
    "PG": 0.0,
    "G": 0.5,
    "SG": 1.0,
    "G-F": 1.5,
    "F-G": 1.5,
    "SF": 2.0,
    "F": 2.5,
    "PF": 3.0,
    "F-C": 3.25,
    "C-F": 3.5,
    "C": 4.0,
}


# Exact GP-valid calibration. The absolute 2K scale is a continuous quadratic
# fit to editor_capture_003's no-stat primary-position medians; these are
# distribution anchors, not output bands. Body response uses the 765-package
# Overall-controlled coefficients from editor_capture_001/002 at observed mean
# Overall. Overall is deliberately not a runtime input.
_POOL_BODY_HEIGHT = (72.610940780, 1.672155160, 0.031797407)
_POOL_BODY_WEIGHT = (178.365457631, 8.699552963, 0.478873439)


@dataclass(frozen=True)
class _AthleticModel:
    intercept: float
    position: float
    position_squared: float
    height_residual: float
    weight_residual_per_ten: float
    source: str


_ATHLETIC_MODELS: dict[str, _AthleticModel] = {
    "speed_with_ball": _AthleticModel(
        81.914285714,
        -2.671428571,
        -1.642857143,
        -0.620567496,
        -0.048917651,
        "pool_run3_no_stats.position_median_quadratic.speed_with_ball+pool_gp765.overall_controlled_body",
    ),
    "strength": _AthleticModel(
        51.714285714,
        -0.542857143,
        1.571428571,
        0.120647982,
        0.968179445,
        "pool_run3_no_stats.position_median_quadratic.strength+pool_gp765.overall_controlled_body",
    ),
    "vertical": _AthleticModel(
        74.600000000,
        3.050000000,
        -1.250000000,
        0.049899040,
        0.390765020,
        "pool_run3_no_stats.position_median_quadratic.vertical+pool_gp765.overall_controlled_body",
    ),
}


_AGE_ADJUSTMENT: dict[str, Callable[[float], float]] = {
    "speed_with_ball": lambda age: -0.18 * max(age - 30.0, 0.0),
    "strength": lambda age: 0.22 * (min(max(age, 22.0), 30.0) - 22.0) - 0.10 * max(age - 32.0, 0.0),
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


def _raw_position_coordinate(value: object) -> float | None:
    text = str(value or "").strip().upper().replace("/", "-")
    if not text:
        return None
    if text in _POSITION_COORDINATE:
        return _POSITION_COORDINATE[text]
    pieces = tuple(piece for piece in text.replace(",", "-").split("-") if piece)
    values = tuple(_POSITION_COORDINATE[piece] for piece in pieces if piece in _POSITION_COORDINATE)
    return sum(values) / len(values) if values else None


def _position_coordinate(evidence: Any) -> tuple[float, tuple[str, ...]] | None:
    play_by_play = getattr(evidence, "play_by_play", {})
    weighted: list[tuple[float, float, str]] = []
    if isinstance(play_by_play, dict):
        for position, column in (("PG", "pg_percent"), ("SG", "sg_percent"), ("SF", "sf_percent"), ("PF", "pf_percent"), ("C", "c_percent")):
            share = _number(play_by_play.get(column))
            if share is not None and share > 0.0:
                weighted.append((_POSITION_COORDINATE[position], share, column))
    total = sum(share for _position, share, _column in weighted)
    if total > 0.0:
        coordinate = sum(position * share for position, share, _column in weighted) / total
        keys = tuple(f"play_by_play.{column}" for _position, _share, column in weighted)
        return coordinate, keys

    season_info = getattr(evidence, "season_info", {})
    identity = getattr(evidence, "identity", {})
    raw = _dict_text(season_info, "pos", "position") or _dict_text(identity, "pos", "position")
    coordinate = _raw_position_coordinate(raw)
    if coordinate is None:
        return None
    return coordinate, ("season_info.pos", f"position_label={raw}")


def _pool_expected_body(position: float) -> tuple[float, float]:
    height = _POOL_BODY_HEIGHT[0] + _POOL_BODY_HEIGHT[1] * position + _POOL_BODY_HEIGHT[2] * position * position
    weight = _POOL_BODY_WEIGHT[0] + _POOL_BODY_WEIGHT[1] * position + _POOL_BODY_WEIGHT[2] * position * position
    return height, weight


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
    league: str,
) -> tuple[float, float, int]:
    height_residuals: list[float] = []
    weight_residuals: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_season = _number(_row_value(row, "season_info", "player_season_info.season"))
        row_league = str(_row_value(row, "season_info", "player_season_info.lg") or "").strip().upper()
        if row_season is not None and int(row_season) != season:
            continue
        if row_league and league and row_league != league:
            continue
        games = _number(_row_value(row, "per_game", "player_per_game.g"))
        if games is None or games <= 0.0:
            continue
        raw_position = _row_value(row, "season_info", "player_season_info.pos")
        position = _raw_position_coordinate(raw_position)
        height = _number(_row_value(row, "identity", "player_info.ht_in_in"))
        weight = _number(_row_value(row, "identity", "player_info.wt"))
        if position is None or height is None or weight is None:
            continue
        expected_height, expected_weight = _pool_expected_body(position)
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


def _athletic_context(
    evidence: Any,
    league_player_rows: Iterable[dict[str, Any]],
) -> tuple[float, float, float, float | None, tuple[str, ...]] | None:
    games = _games_played(evidence)
    if games is None or games <= 0.0:
        return None
    selected = _position_coordinate(evidence)
    if selected is None:
        return None
    position, position_keys = selected
    season = int(getattr(evidence, "season", 0) or 0)
    league = _dict_text(getattr(evidence, "season_info", {}), "lg", "league").upper()
    expected_height, expected_weight = _pool_expected_body(position)
    height_shift, weight_shift, population_count = _population_body_shift(
        league_player_rows,
        season=season,
        league=league,
    )
    expected_height += height_shift
    expected_weight += weight_shift
    height = _height_inches(evidence)
    weight = _weight_pounds(evidence)
    body_keys: list[str] = []
    if height is None:
        height = expected_height
        body_keys.append("identity.height=missing; substitute=same_season_same_league_position_expected_height")
    else:
        body_keys.extend(("identity.ht_in_in", f"identity_height_inches={height:.6g}"))
    if weight is None:
        weight = expected_weight
        body_keys.append("identity.weight=missing; substitute=same_season_same_league_position_expected_weight")
    else:
        body_keys.extend(("identity.wt", f"identity_weight_pounds={weight:.6g}"))
    age = _age(evidence)
    keys = (
        "per_game.g",
        f"games_played={games:.6g}",
        *position_keys,
        *body_keys,
        f"population.same_season_same_league_gp_body_rows={population_count}",
        f"population.expected_height={expected_height:.6g}",
        f"population.expected_weight={expected_weight:.6g}",
        f"era.season={season}; league={league or 'unknown'}; direct_rating_penalty=none",
        "pool_identity=(run_id,player_index); captures=editor_capture_001,editor_capture_002; gp_valid_packages=765",
    )
    return position, height - expected_height, (weight - expected_weight) / 10.0, age, keys


def _derive_athletic_field(
    field: str,
    evidence: Any,
    league_player_rows: Iterable[dict[str, Any]],
) -> RuleOutput:
    context = _athletic_context(evidence, league_player_rows)
    if context is None:
        return None
    position, height_residual, weight_residual, age, evidence_keys = context
    model = _ATHLETIC_MODELS[field]
    value = (
        model.intercept
        + model.position * position
        + model.position_squared * position * position
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
        "substitute_source=gp_valid_pool_position_body_relationship_plus_same_season_same_league_body_context_and_continuous_age",
        f"validity={field}_conditional_estimate_when_direct_athletic_measurement_is_absent; no_assist_or_production_input",
        "excluded_runtime_inputs=assists,overall,production",
    )
    return {
        "value": _attribute(value),
        "source_rule": f"derive_attribute_{field}_field_specific_context_substitute",
        "evidence_keys": provenance,
    }


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
    return {
        "value": _attribute(0.5 * height_rating + 0.5 * weight_rating),
        "source_rule": "derive_attribute_speed_full_generated_pool_body_min_max",
        "evidence_keys": (
            "per_game.g",
            f"games_played={games:.6g}",
            height_source,
            f"height_inches={height:.6g}",
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
    result = derive_attribute_speed(evidence, league_player_rows=league_player_rows)
    if result is None:
        return None
    return {
        "value": result["value"],
        "source_rule": "derive_attribute_agility_full_generated_pool_body_min_max",
        "evidence_keys": tuple(result["evidence_keys"]),
    }


def derive_attribute_speedwithball(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    return _derive_athletic_field("speed_with_ball", evidence, league_player_rows)


def derive_attribute_strength(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    return _derive_athletic_field("strength", evidence, league_player_rows)


def derive_attribute_vertical(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    return _derive_athletic_field("vertical", evidence, league_player_rows)


def derive_attribute_acceleration(evidence: Any, _field_index: Any = None, league_player_rows: Iterable[dict[str, Any]] = (), _positions: Any = None) -> RuleOutput:
    speed = derive_attribute_speed(evidence, league_player_rows=league_player_rows)
    agility = derive_attribute_agility(evidence, league_player_rows=league_player_rows)
    if speed is None or agility is None:
        return None
    speed_value = int(speed["value"])
    agility_value = int(agility["value"])
    return {
        "value": _attribute(0.55 * speed_value + 0.45 * agility_value),
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
    if mpg is None:
        return {
            "value": 90,
            "source_rule": "derive_attribute_stamina_field_specific_context_substitute",
            "evidence_keys": (
                "per_game.g",
                f"games_played={games:.6g}",
                "unavailable_direct_source=per_game.mp_per_game",
                "substitute_source=gp_valid_pool_stamina_median_90",
                "validity=historical_minutes_unavailable_and_pool_stamina_is_independent_of_unrelated_production",
                "pool_identity=(run_id,player_index); gp_valid_packages=765; every_primary_position_median=90",
            ),
        }
    if mpg < 0.0:
        return None
    age = _age(evidence)
    if mpg == 0.0:
        value = 25
    elif mpg >= 36.0:
        value = 99
    else:
        value = min(99, 90 + _round_half_up(mpg / 4.0))
    previous_mpg = _previous_season_mpg(evidence, league_player_rows)
    penalty = 0
    if age is not None and age >= 30.0 and previous_mpg is not None and previous_mpg > mpg:
        decline = previous_mpg - mpg
        age_factor = 1.0 + max(age - 30.0, 0.0) / 20.0
        penalty = _round_half_up(decline * age_factor)
        value = max(25, value - penalty)
    previous_key = (
        f"previous_season.mp_per_game={previous_mpg:.6g}; yoy_penalty={penalty}"
        if previous_mpg is not None
        else "previous_season.mp_per_game=unavailable_in_same_season_rows; yoy_penalty=0"
    )
    return {
        "value": value,
        "source_rule": "derive_attribute_stamina_current_mpg",
        "evidence_keys": (
            "per_game.g",
            "per_game.mp_per_game",
            f"games_played={games:.6g}",
            f"minutes_per_game={mpg:.6g}",
            "season_info.age" if age is not None else "age=missing",
            previous_key,
            "stamina_contract=0mpg:25; positive_mpg:90_plus_round(mpg/4); 36plus:99",
        ),
    }


def _fixed(rule_name: str, value: int, keys: tuple[str, ...]) -> dict[str, Any]:
    return {"value": value, "source_rule": rule_name, "evidence_keys": keys}


def derive_attribute_backdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_backdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_headdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_headdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_leftankledurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_leftankledurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_leftelbowdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_leftelbowdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_leftfootdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_leftfootdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_lefthanddurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_lefthanddurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_lefthipdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_lefthipdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_leftkneedurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_leftkneedurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_leftshoulderdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_leftshoulderdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_miscdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_miscdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_neckdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_neckdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_rightankledurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_rightankledurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_rightelbowdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_rightelbowdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_rightfootdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_rightfootdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_righthanddurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_righthanddurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_righthipdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_righthipdurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_rightkneedurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_rightkneedurability', 90, ('durability.default_90_pending_injury_database',))


def derive_attribute_rightshoulderdurability(evidence: Any, _field_index: Any = None, league_player_rows: Any = (), _positions: Any = None) -> dict[str, Any]:
    return _fixed('derive_attribute_rightshoulderdurability', 90, ('durability.default_90_pending_injury_database',))