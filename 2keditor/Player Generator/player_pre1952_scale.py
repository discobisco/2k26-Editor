"""Selected-population scale helpers for the pre-1952 fallback ratings.

Seasons 1947-51 record body, basic box scores, and -- outside the NBL -- win shares.
The UI league selection owns the comparison population: a specific league stays inside
that league, while ``All leagues`` supplies the mixed same-season population.

Requested composites are built in 0-1 magnitude space and then mapped to the legal
25-99 Attribute range. Exact ``(player_id, team)`` identity is retained for operations
whose tie-breaking or within-height ordering must address a player rather than a label.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: Key under which the UI-selected same-season population snapshot is stamped.
POOLED_POPULATION_KEY = "pre_1952_pooled_same_season_population"

#: Key under which the NBL-only season totals are stamped, for the NBL intangibles
#: recipe. Intangibles is the one field the operator scoped to the NBL alone.
NBL_TOTALS_KEY = "pre_1952_nbl_same_season_totals"

#: Key under which the season's spread of already-generated field values is stamped,
#: for the fields that keep their existing shape and only need their range opened up.
FIELD_DISTRIBUTIONS_KEY = "pre_1952_same_season_field_distributions"

#: Exact pre-fallback owner values keyed by ``(player_id, team)``. This prevents an
#: intervening sparse-era projection from changing the value being stretched.
FIELD_BASE_VALUES_KEY = "pre_1952_same_season_field_base_values"

#: Final selected-population Speed rating attached to each compact population row so
#: Agility and Steal can enforce their cross-field contracts from the same value.
SPEED_RATING_KEY = "pre_1952_speed_rating"

#: Exact ``(player_id, team)`` identities selected as the Hustle top 25.  Values alone
#: cannot resolve a tie at the cutoff without accidentally assigning more than 25 99s.
HUSTLE_TOP_KEYS_KEY = "pre_1952_hustle_top_25_exact_keys"

#: The last season covered by these fallbacks.
LAST_PRE_1952_SEASON = 1951

ATTRIBUTE_FLOOR = 25.0
ATTRIBUTE_CEILING = 99.0

_ROW_PATHS: dict[str, tuple[str, ...]] = {
    "height": ("player_info.ht_in_in", "identity.ht_in_in", "ht_in_in"),
    "weight": ("player_info.wt", "identity.wt", "wt"),
    "ows": ("player_advanced.ows", "advanced.ows", "ows"),
    "dws": ("player_advanced.dws", "advanced.dws", "dws"),
    "games": ("player_per_game.g", "per_game.g", "g"),
    "age": ("player_season_info.age", "season_info.age", "age"),
    "points_per_game": ("player_per_game.pts_per_game", "per_game.pts_per_game"),
    "ft_per_game": ("player_per_game.ft_per_game", "per_game.ft_per_game"),
    "fta_per_game": ("player_per_game.fta_per_game", "per_game.fta_per_game"),
    "field_goal_percent": ("player_per_game.fg_percent", "per_game.fg_percent", "shooting.fg_percent"),
    "free_throw_percent": ("player_per_game.ft_percent", "per_game.ft_percent"),
    "field_goal_attempts_per_game": ("player_per_game.fga_per_game", "per_game.fga_per_game"),
    "field_goals_made": ("player_totals.fg", "totals.fg"),
    "points_total": ("player_totals.pts", "totals.pts"),
    "free_throws_total": ("player_totals.ft", "totals.ft"),
}

_EVIDENCE_SECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "height": (("identity", "ht_in_in"),),
    "weight": (("identity", "wt"),),
    "ows": (("advanced", "ows"),),
    "dws": (("advanced", "dws"),),
    "games": (("per_game", "g"),),
    "age": (("season_info", "age"),),
    "points_per_game": (("per_game", "pts_per_game"),),
    "ft_per_game": (("per_game", "ft_per_game"),),
    "fta_per_game": (("per_game", "fta_per_game"),),
    "field_goal_percent": (("per_game", "fg_percent"), ("shooting", "fg_percent")),
    "free_throw_percent": (("per_game", "ft_percent"),),
    "field_goal_attempts_per_game": (("per_game", "fga_per_game"),),
    "field_goals_made": (("totals", "fg"),),
    "points_total": (("totals", "pts"),),
    "free_throws_total": (("totals", "ft"),),
}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def row_signal(row: Mapping[str, Any], name: str) -> float | None:
    """Read one signal from a comparison row, nested or dotted."""

    for path in _ROW_PATHS.get(name, ()):
        value = _number(row.get(path))
        if value is not None:
            return value
        section, _, leaf = path.partition(".")
        nested = row.get(section)
        if isinstance(nested, Mapping):
            value = _number(nested.get(leaf))
            if value is not None:
                return value
    return None


def evidence_signal(evidence: Any, name: str) -> float | None:
    """Read one signal for the player being rated."""

    for section, leaf in _EVIDENCE_SECTIONS.get(name, ()):
        container = getattr(evidence, section, None)
        if container is None and isinstance(evidence, Mapping):
            container = evidence.get(section)
        if isinstance(container, Mapping):
            value = _number(container.get(leaf))
            if value is not None:
                return value
    source_context = getattr(evidence, "source_context", None)
    if isinstance(source_context, Mapping):
        return row_signal(source_context, name)
    if isinstance(evidence, Mapping):
        return row_signal(evidence, name)
    return None


def season_of(evidence: Any) -> int:
    season = _number(getattr(evidence, "season", None))
    if season is not None:
        return int(season)
    season_info = getattr(evidence, "season_info", None)
    if isinstance(season_info, Mapping):
        value = _number(season_info.get("season"))
        if value is not None:
            return int(value)
    if isinstance(evidence, Mapping):
        value = _number(evidence.get("season"))
        if value is not None:
            return int(value)
    return 0


def applies(evidence: Any) -> bool:
    """Whether the pre-1952 fallback scale governs this player."""

    season = season_of(evidence)
    return 0 < season <= LAST_PRE_1952_SEASON


def _stamped(evidence: Any, key: str) -> Any:
    source_context = getattr(evidence, "source_context", None)
    if not isinstance(source_context, Mapping):
        source_context = evidence if isinstance(evidence, Mapping) else {}
    return source_context.get(key)


def pooled_population(evidence: Any) -> tuple[dict[str, float | str], ...]:
    """The UI-selected same-season players stamped by the generator."""

    pooled = _stamped(evidence, POOLED_POPULATION_KEY)
    return tuple(pooled) if isinstance(pooled, (list, tuple)) else ()


def nbl_totals(evidence: Any) -> tuple[dict[str, float | str], ...]:
    """The season's NBL players and their recorded totals."""

    totals = _stamped(evidence, NBL_TOTALS_KEY)
    return tuple(totals) if isinstance(totals, (list, tuple)) else ()


def field_distributions(evidence: Any) -> dict[str, tuple[float, ...]]:
    """The season's spread of values for fields that are restretched, not rebuilt."""

    stamped = _stamped(evidence, FIELD_DISTRIBUTIONS_KEY)
    if not isinstance(stamped, Mapping):
        return {}
    return {
        str(key): tuple(values)
        for key, values in stamped.items()
        if isinstance(values, (list, tuple)) and values
    }


def field_base_values(evidence: Any) -> dict[tuple[str, str], dict[str, float]]:
    """Return exact owner values used to build the selected-population spreads."""

    stamped = _stamped(evidence, FIELD_BASE_VALUES_KEY)
    if not isinstance(stamped, (list, tuple)):
        return {}
    resolved: dict[tuple[str, str], dict[str, float]] = {}
    for item in stamped:
        if not isinstance(item, Mapping):
            continue
        key = (
            str(item.get("player_id") or "").strip().upper(),
            str(item.get("team") or "").strip().upper(),
        )
        raw_values = item.get("values")
        if not all(key) or not isinstance(raw_values, Mapping):
            continue
        values: dict[str, float] = {}
        for field_key, raw_value in raw_values.items():
            value = _number(raw_value)
            if value is not None:
                values[str(field_key)] = value
        resolved[key] = values
    return resolved


def hustle_top_keys(evidence: Any) -> tuple[tuple[str, str], ...]:
    """Return the exact identities selected for the pre-1952 Hustle ceiling."""

    stamped = _stamped(evidence, HUSTLE_TOP_KEYS_KEY)
    if not isinstance(stamped, (list, tuple)):
        return ()
    keys: list[tuple[str, str]] = []
    for item in stamped:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        keys.append((str(item[0]).strip().upper(), str(item[1]).strip().upper()))
    return tuple(keys)


def build_population_snapshot(rows: Iterable[Mapping[str, Any]]) -> tuple[dict[str, float | str], ...]:
    """Compact projection of a season's rows: only the signals these rules read.

    A projection rather than the rows themselves. Stamping the rows onto the rows would
    make every row contain itself, and the snapshot is read hundreds of times per run.
    """

    snapshot: list[dict[str, float | str]] = []
    for row in rows:
        games = row_signal(row, "games")
        if games is None or games <= 0.0:
            continue
        entry: dict[str, float | str] = {
            # Upper-cased here because the evidence side upper-cases too; the two were
            # compared raw and every rebound lookup missed silently.
            "player_id": str(row.get("player_id") or "").strip().upper(),
            "team": str(row.get("team") or row.get("player_season_info.team") or "").strip().upper(),
            "league": str(row.get("player_season_info.lg") or row.get("lg") or "").strip().upper(),
        }
        for name in _ROW_PATHS:
            value = row_signal(row, name)
            if value is not None:
                entry[name] = value
        snapshot.append(entry)
    return tuple(snapshot)


#: The pooled snapshot is one shared tuple per season, so every signal vector drawn
#: from it is the same for every player rated against it. Without this the population
#: was re-scanned and re-sorted once per player per component, which is quadratic in a
#: 333-player season and made a run take minutes instead of seconds.
_VALUES_CACHE: dict[tuple[int, str, str | None], tuple[float, ...]] = {}
_CACHE_GUARD: dict[int, Any] = {}


def _cache_key(population: Sequence[Mapping[str, Any]], name: str, league: str | None) -> tuple[int, str, str | None]:
    identity = id(population)
    # Hold a reference to the population so its id cannot be reused by a later object
    # while the cache still answers for it.
    _CACHE_GUARD.setdefault(identity, population)
    return identity, name, league


def values_of(
    population: Sequence[Mapping[str, Any]],
    name: str,
    *,
    league: str | None = None,
) -> tuple[float, ...]:
    key = _cache_key(population, name, league)
    cached = _VALUES_CACHE.get(key)
    if cached is not None:
        return cached
    collected = [
        value
        for entry in population
        if (league is None or str(entry.get("league") or "") == league)
        and (value := _number(entry.get(name))) is not None
    ]
    values = tuple(sorted(collected))
    _VALUES_CACHE[key] = values
    return values


#: The ends of every population scale. Anchoring on the outright minimum and maximum
#: handed one player control of the whole season: the single 7.3-free-throw-per-game
#: shooter set the Draw Foul scale for all 333 players and left the median at 35. The
#: 2nd and 98th percentiles keep the magnitude spacing that the win-share fields need
#: while making a lone extreme clamp instead of rescale. ``player_rules_athleticism``
#: already anchors its vertical population the same way.
POPULATION_ANCHOR_LOW = 0.02
POPULATION_ANCHOR_HIGH = 0.98

#: Below this many values the percentiles are the extremes anyway, so use them directly.
ANCHOR_MIN_POPULATION = 20


def population_anchors(values: Sequence[float]) -> tuple[float, float]:
    """The low and high ends of the scale this population defines."""

    count = len(values)
    if count < ANCHOR_MIN_POPULATION:
        return values[0], values[-1]
    return (
        values[int(POPULATION_ANCHOR_LOW * (count - 1))],
        values[int(POPULATION_ANCHOR_HIGH * (count - 1))],
    )


def stretch(
    value: float | None,
    values: Sequence[float],
    *,
    invert: bool = False,
    low_anchor: float | None = None,
    high_anchor: float | None = None,
) -> float | None:
    """Map a value onto 25-99 by where it sits between the population's anchors.

    This is a *magnitude* scale, not a rank: the distance between two players is the
    distance between their numbers. That is deliberate and the 1947 benchmark depends
    on it -- win shares of 18.6, 16.3 and 11.8 are far apart in contributed wins, and a
    rank would print them side by side. Replacing this with a percentile rank was tried
    and pushed the benchmark's defensive reproduction from 0.015 to 0.235 against a
    0.19 tolerance.

    The ends are the population's 2nd and 98th percentiles rather than its outright
    extremes, so one outlier cannot compress everybody else. Values outside the anchors
    clamp. Under the raw min/max a single player at 7.3 free throws a game set the scale
    for all 333, and the season's Draw Foul median sat at 35.

    ``low_anchor``/``high_anchor`` pin an end to a fixed number instead -- Draw Foul
    anchors its bottom at zero free throws, which is a real floor rather than whatever
    the least-used player happened to attempt.
    """

    if value is None or not values:
        return None
    anchor_low, anchor_high = population_anchors(values)
    minimum = anchor_low if low_anchor is None else low_anchor
    maximum = anchor_high if high_anchor is None else high_anchor
    span = maximum - minimum
    if span <= 0.0:
        return None
    share_value = max(0.0, min(1.0, (value - minimum) / span))
    if invert:
        share_value = 1.0 - share_value
    return ATTRIBUTE_FLOOR + (ATTRIBUTE_CEILING - ATTRIBUTE_FLOOR) * share_value


def share(
    value: float | None,
    values: Sequence[float],
    *,
    invert: bool = False,
    low_anchor: float | None = None,
    high_anchor: float | None = None,
) -> float | None:
    """Where a value sits between its population's anchors, on 0-1.

    A magnitude position, not a rank -- see :func:`stretch` for why the distinction is
    load-bearing. Composites are blended here and stretched once at the end, so the
    blend can still reach both ends of the scale.
    """

    if value is None or not values:
        return None
    anchor_low, anchor_high = population_anchors(values)
    minimum = anchor_low if low_anchor is None else low_anchor
    maximum = anchor_high if high_anchor is None else high_anchor
    span = maximum - minimum
    if span <= 0.0:
        return None
    magnitude_share = max(0.0, min(1.0, (value - minimum) / span))
    return 1.0 - magnitude_share if invert else magnitude_share


def composite_share(components: Sequence[tuple[float | None, float]]) -> float | None:
    """Weighted blend of 0-1 component shares, renormalised over what is present.

    A missing component is dropped and the remaining weights are rescaled. Missing is
    never zero: a player with no recorded win shares is unmeasured, not worthless.
    """

    present = [(value, weight) for value, weight in components if value is not None and weight > 0.0]
    total = sum(weight for _value, weight in present)
    if not present or total <= 0.0:
        return None
    return sum(value * weight for value, weight in present) / total


#: Explicit offense-only substitute used by Post Control, Post Hook, and Post Fade when
#: OWS was not recorded. Defensive fields never consume this signal as a DWS substitute.
WIN_SHARE_SUBSTITUTE = "points_per_game"


def win_share_share(
    entry_or_evidence: Any,
    population: Sequence[Mapping[str, Any]],
    side: str,
    *,
    from_row: bool = False,
    fallback_to_points: bool = False,
) -> tuple[float | None, str]:
    """The player's win-share magnitude share.

    ``side`` is "ows" or "dws". Returns the 0-1 share and the name of the signal that
    produced it.  Points per game is used only when the calling offense rule explicitly
    authorizes that fallback; missing DWS never silently becomes scoring.
    """

    read = (lambda name: _number(entry_or_evidence.get(name))) if from_row else (
        lambda name: evidence_signal(entry_or_evidence, name)
    )
    recorded = read(side)
    if recorded is not None:
        values = values_of(population, side)
        rank_share = share(
            recorded,
            values,
            low_anchor=values[0] if values else None,
            high_anchor=values[-1] if values else None,
        )
        if rank_share is not None:
            return rank_share, side
    if not fallback_to_points:
        return None, ""
    substitute = read(WIN_SHARE_SUBSTITUTE)
    values = values_of(population, WIN_SHARE_SUBSTITUTE)
    rank_share = share(
        substitute,
        values,
        low_anchor=values[0] if values else None,
        high_anchor=values[-1] if values else None,
    )
    return rank_share, WIN_SHARE_SUBSTITUTE if rank_share is not None else ""


__all__ = [
    "ATTRIBUTE_CEILING",
    "ATTRIBUTE_FLOOR",
    "FIELD_BASE_VALUES_KEY",
    "FIELD_DISTRIBUTIONS_KEY",
    "HUSTLE_TOP_KEYS_KEY",
    "LAST_PRE_1952_SEASON",
    "NBL_TOTALS_KEY",
    "POOLED_POPULATION_KEY",
    "SPEED_RATING_KEY",
    "WIN_SHARE_SUBSTITUTE",
    "applies",
    "population_anchors",
    "build_population_snapshot",
    "composite_share",
    "evidence_signal",
    "field_base_values",
    "field_distributions",
    "hustle_top_keys",
    "nbl_totals",
    "pooled_population",
    "row_signal",
    "season_of",
    "share",
    "stretch",
    "values_of",
    "win_share_share",
]
