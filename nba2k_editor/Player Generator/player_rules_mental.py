from __future__ import annotations

import bisect
from math import isfinite
from typing import Any


_INTANGIBLES_VORP_MAX = 12.47
_INTANGIBLES_LINEAR_WEIGHT = 0.1318558994
_INTANGIBLES_TAIL_WEIGHT = 0.8681331006
_INTANGIBLES_TAIL_EXPONENT = 22.89826001


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if not text or text.upper() in {"NA", "N/A", "NONE", "NULL"}:
            return None
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _usable_games_played(evidence: Any) -> float | None:
    per_game = getattr(evidence, "per_game", {})
    games = _optional_number(per_game.get("g")) if isinstance(per_game, dict) else None
    return games if games is not None and games > 0.0 else None


def _advanced_value(evidence: Any, key: str) -> float | None:
    advanced = getattr(evidence, "advanced", {})
    return _optional_number(advanced.get(key)) if isinstance(advanced, dict) else None


def _source_value(source: Any, namespace: str, key: str) -> float | None:
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


def _team_total(source: Any, field: str) -> float | None:
    per_game = _source_value(source, "team_stats_per_game", f"{field}_per_game")
    games = _source_value(source, "team_stats_per_game", "g")
    if per_game is None or games is None or games <= 0.0:
        return None
    return per_game * games


def _team_share(source: Any, field: str) -> float | None:
    player_total = _source_value(source, "totals", field)
    team_total = _team_total(source, field)
    if player_total is None or team_total is None or team_total <= 0.0:
        return None
    return player_total / team_total


def _touch_component(source: Any, name: str) -> float | None:
    if name == "fga_share":
        return _team_share(source, "fga")
    if name == "ast_share":
        return _team_share(source, "ast")
    if name == "usg_percent":
        return _source_value(source, "advanced", "usg_percent")
    if name == "fgm_share":
        return _team_share(source, "fg")
    if name == "fta_share":
        return _team_share(source, "fta")
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


# These semantic Attributes have no approved NBA-stat-to-2K rating calibration in
# the current source contract. Assists/rebounds/height do not calibrate Hands;
# rebounds/steals/win shares do not calibrate Hustle; age plus current production
# does not measure future Potential. They remain unresolved rather than converting
# a same-season rank directly to 25..99.
def derive_attribute_hands(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_hustle(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_intangibles(
    evidence: Any,
    *,
    league_player_rows: Any = (),
) -> dict[str, Any] | None:
    games = _usable_games_played(evidence)
    if games is None:
        return None

    raw_vorp = _advanced_value(evidence, "vorp")
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


# CACHCED_OVR, MAX_OVR, and MIN_OVR are game storage fields, not independent
# basketball abilities. Authoring them from PER/WS/points would be a direct OVR
# override, so this rule module deliberately has no formula owner for them.
def derive_attribute_cachcedovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_maxovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_minovr(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_attribute_potential(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


# The current NBA Master contract has no isolation-opportunity, defender-quality,
# play-call adherence, screen-action choice, or transition spot-up rows. Broad
# efficiency, team pace, position, and modern shot-location data are not exact
# substitutes for those behaviors, especially historically. Preserve each field
# as independently unresolved instead of emitting four nearly identical ISO
# values or applying modern tracking semantics to older seasons.
def derive_tendency_isovsaveragedefender(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_tendency_isovselitedefender(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_tendency_isovsgooddefender(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_tendency_isovspoordefender(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_tendency_playdiscipline(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


def derive_tendency_rollvspop(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


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


def derive_tendency_transitionspotup(evidence: Any, *, league_player_rows: Any = ()) -> None:
    return None


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