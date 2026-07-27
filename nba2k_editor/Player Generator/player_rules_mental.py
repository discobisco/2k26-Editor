from __future__ import annotations

import bisect
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from player_era_context import filter_same_league_rows


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
}


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
    "assist_share": ("totals.ast", "team_stats_per_game.ast_per_game", "team_stats_per_game.g"),
    "foul_pressure": ("advanced.f_tr", "totals.fta", "totals.fga"),
    "turnover_rate": ("advanced.tov_percent", "per_36.tov_per_36_min", "per_game.tov_per_game"),
    "lost_ball_security": ("play_by_play.lost_ball_turnover", "totals.fga", "totals.ast", "totals.tov"),
    "secure_possession_rate": ("per_36.trb_per_36_min", "per_36.stl_per_36_min"),
    "orb_rate": ("advanced.orb_percent", "per_36.orb_per_36_min"),
    "stl_rate": ("per_36.stl_per_36_min",),
    "blk_rate": ("per_36.blk_per_36_min",),
    "charge_rate": ("play_by_play.offensive_foul_drawn", "per_game.g"),
    "foul_rate": ("per_36.pf_per_36_min",),
    "trb_rate": ("per_36.trb_per_36_min",),
    "games_share": ("per_game.g", "team_stats_per_game.g"),
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
    "HUSTLE": (65.0, 20.756),
    "ISOVSPOOR": (30.0, 17.791),
    "ISOVSAVERAGE": (25.0, 14.826),
    "ISOVSGOOD": (18.0, 11.861),
    "ISOVSELITE": (14.0, 13.343),
    "PLAYDISCIPLINE": (74.0, 14.826),
    "ROLLVSPOP": (46.0, 17.791),
    "TRANSITIONSPOTUP": (8.0, 11.861),
}


_HANDS_RECIPES = (
    _Recipe("tracked_catch_and_ball_security", (("lost_ball_security", 0.55), ("turnover_rate", -0.30), ("secure_possession_rate", 0.15)), ("lost_ball_security", "turnover_rate")),
    _Recipe("historical_hand_eye_and_secure_possession", (("ft_percent", 0.40), ("assist_share", 0.35), ("secure_possession_rate", 0.25)), ("ft_percent", "assist_share", "secure_possession_rate"), "tracked lost-ball and catch outcomes", "recorded FT touch, team assist responsibility, and secured-possession activity", "the substitute estimates hand-eye control and possession security without using height or names"),
)
_HUSTLE_RECIPES = (
    _Recipe("recorded_effort_event_activity", (("orb_rate", 0.35), ("stl_rate", 0.25), ("blk_rate", 0.15), ("charge_rate", 0.15), ("foul_rate", 0.10)), ("orb_rate", "stl_rate", "blk_rate", "charge_rate")),
    _Recipe("historical_rebound_foul_availability_activity", (("trb_rate", 0.65), ("foul_rate", 0.25), ("games_share", 0.10)), ("trb_rate", "foul_rate"), "offensive boards, steals, blocks, charges, and loose-ball recoveries", "recorded total-rebound activity, foul activity, and schedule availability", "these all-era events measure repeated pursuit and physical activity; no body or name template authors HUSTLE"),
)
_ISO_RECIPES = (
    _Recipe("self_created_isolation_load", (("assisted_two_rate", -0.35), ("attempt_share", 0.25), ("foul_pressure", 0.25), ("role.creator", 0.15)), ("assisted_two_rate",)),
    _Recipe("historical_creator_isolation_load", (("attempt_share", 0.40), ("foul_pressure", 0.30), ("role.creator", 0.30)), ("attempt_share", "scoring_share"), "isolation play-type and unassisted-shot event counts", "offensive responsibility, live-contact pressure, and continuous creator role", "the substitute estimates self-created possession load and the four defender classes share one base score"),
)
_PLAY_DISCIPLINE_RECIPES = (
    _Recipe("assisted_structure_and_decision_security", (("assisted_two_rate", 0.35), ("turnover_rate", -0.25), ("attempt_share", -0.20), ("role.creator", -0.20)), ("assisted_two_rate", "turnover_rate")),
    _Recipe("historical_team_role_discipline", (("attempt_share", -0.45), ("assist_share", 0.30), ("role.creator", -0.25)), ("attempt_share", "assist_share"), "play-call adherence and freelance possession events", "lower self-directed shot load, team assist responsibility, and reduced primary-creator role", "the substitute describes structured team-role behavior rather than shooting execution"),
)
_ROLL_POP_RECIPES = (
    _Recipe("screen_pop_spacing_preference", (("mid_attempt_rate", 0.30), ("three_attempt_rate", 0.30), ("rim_attempt_rate", -0.20), ("role.wing", 0.10), ("role.interior", -0.10)), ("mid_attempt_rate", "three_attempt_rate", "rim_attempt_rate")),
    _Recipe("historical_screen_pop_touch_role", (("ft_percent", 0.40), ("role.wing", 0.25), ("role.interior", -0.20), ("foul_pressure", -0.15)), ("ft_percent", "role.wing", "role.interior"), "screen roll/pop event destinations and shot locations", "recorded shooting touch plus continuous spacing-versus-interior role", "higher output means pop preference; the all-era substitute separates spacing from rim pressure"),
)
_TRANSITION_SPOTUP_RECIPES = (
    _Recipe("transition_perimeter_receiver_context", (("three_attempt_rate", 0.30), ("mid_attempt_rate", 0.25), ("assisted_two_rate", 0.25), ("role.creator", -0.20)), ("three_attempt_rate", "mid_attempt_rate", "assisted_two_rate")),
    _Recipe("historical_transition_receiver_role", (("role.wing", 0.35), ("role.creator", -0.25), ("attempt_share", 0.20), ("ft_percent", 0.20)), ("role.wing", "role.creator"), "transition spot-up event and assisted-location counts", "off-ball wing role, reduced primary creation, shooting responsibility, and recorded touch", "the substitute estimates running to a receiving spot rather than transition pull-up creation"),
)


def _population(evidence: Any, rows: Any) -> tuple[Any, ...]:
    season = _season(evidence)
    league = _league(evidence)
    return tuple(
        row
        for row in filter_same_league_rows(evidence, rows)
        if _gp(row) is not None
        and (not season or not _season(row) or _season(row) == season)
        and (not league or not _league(row) or _league(row) == league)
    )


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


def _recipe_score(evidence: Any, population: tuple[Any, ...], recipe: _Recipe) -> tuple[float, tuple[str, ...]] | None:
    if recipe.required and not any(_signal(evidence, name) is not None for name in recipe.required):
        return None
    components: list[tuple[float, float, str]] = []
    provenance: list[str] = []
    for name, weight in recipe.signals:
        current = _signal(evidence, name)
        if current is None:
            continue
        summary = _robust_summary([value for row in population if (value := _signal(row, name)) is not None])
        if summary is None:
            continue
        median, scale = summary
        z_value = (current - median) / scale
        components.append((z_value, weight, name))
        provenance.extend(_SIGNAL_PROVENANCE.get(name, (name,)))
        provenance.append(f"same_season_same_league_z[{name}]={z_value:.8f}")
    total_weight = sum(abs(weight) for _z, weight, _name in components)
    if total_weight <= 0.0:
        return None
    score = sum(z_value * weight for z_value, weight, _name in components) / total_weight
    return score, tuple(dict.fromkeys(provenance))


def _derive(field: str, evidence: Any, rows: Any, recipes: tuple[_Recipe, ...], *, tendency: bool) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    population = _population(evidence, rows)
    for recipe in recipes:
        scored = _recipe_score(evidence, population, recipe)
        if scored is None:
            continue
        score, evidence_keys = scored
        center, scale = _CALIBRATION[field]
        low, high = (0, 100) if tendency else (25, 99)
        value = max(low, min(high, int(round(center + score * scale))))
        source_rule = f"derive_{'tendency' if tendency else 'attribute'}_{field.lower()}"
        if recipe.unavailable:
            source_rule += "_field_specific_context_substitute"
        provenance = (
            *evidence_keys,
            "population=same-season,same-league,GP>0",
            "pool_calibration=editor_capture_001+002;765 GP-valid packages;identity=(run_id,player_index);output-scale-only",
            f"recipe={recipe.name}",
            f"formula=center({center:.3f})+robust_weighted_z({score:.8f})*scale({scale:.3f})",
        )
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


def derive_attribute_hands(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("HANDS", evidence, league_player_rows, _HANDS_RECIPES, tendency=False)


def derive_attribute_hustle(evidence: Any, *, league_player_rows: Any = ()) -> dict[str, Any] | None:
    return _derive("HUSTLE", evidence, league_player_rows, _HUSTLE_RECIPES, tendency=False)


def derive_attribute_intangibles(
    evidence: Any,
    *,
    league_player_rows: Any = (),
) -> dict[str, Any] | None:
    if _gp(evidence) is None:
        return None
    raw_vorp = _source_value(evidence, "advanced", "vorp")
    rating = _intangibles_rating_from_vorp(raw_vorp)
    state = "missing" if raw_vorp is None else "nonpositive" if raw_vorp <= 0.0 else "observed"
    return {
        "value": rating,
        "source_rule": "derive_attribute_intangibles",
        "evidence_keys": (
            "per_game.g",
            "advanced.vorp",
            f"raw_vorp_state={state}",
            f"raw_vorp={raw_vorp if raw_vorp is not None else 'missing'}",
            "mapping=integer_inverse_of_approved_0_12.47_vorp_curve",
        ),
    }


def derive_attribute_cachcedovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_maxovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_minovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


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
        "value": round(score * 100),
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
    "derive_attribute_cachcedovr",
    "derive_attribute_maxovr",
    "derive_attribute_minovr",
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
