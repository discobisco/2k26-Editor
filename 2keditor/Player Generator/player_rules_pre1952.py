"""Authored fallback ratings for the 1947-51 seasons.

These seasons record body, the box score, and -- in the BAA and the early NBA only --
win shares. There are no steals, blocks, turnovers, split rebounds or shot locations to
rate anyone on, so each field here is built from the evidence that does exist and says
so in its provenance.

The UI league selection owns the comparison population. ``All leagues`` supplies one
mixed BAA/NBL population; a specific league supplies only that league. Weighted source
components are combined in 0-1 magnitude space and the completed field composite is
stretched to the legal 25-99 Attribute range.

Close Shot, Midrange and Driving Layup retain their captured-pool execution curves.
Post Hook and Post Fade instead follow the explicitly authored pre-1952 body,
production, and field-goal-percentage blend. Points per game substitutes for missing
OWS only in the three post fields that explicitly authorize it; missing DWS never
becomes scoring.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

import player_pre1952_scale as scale

#: Number of players per season pinned to the ceiling on Hustle.
HUSTLE_CEILING_PLAYERS = 25

#: The only position-authored Attribute helper in this fallback.  A generated point
#: guard's existing Ball Control and Pass Accuracy are remapped monotonically from the
#: legal 25-99 domain into 60-99.  No other position changes an Attribute.
POINT_GUARD_FLOOR = 60.0
POINT_GUARD_FIELDS = ("Attributes/BALLCONTROL", "Attributes/PASSACCURACY")

#: Speed and Vertical retain the ordering from their direct athleticism owners; only the
#: selected-population range is opened to 25-99.
RESTRETCHED_FIELDS = (
    "Attributes/VERTICAL",
    "Attributes/SPEED",
)

#: A player who made no field goal all season has no shooting evidence of any kind, so
#: every shot-execution field drops to the floor rather than inheriting a body estimate.
ZERO_MAKE_FLOOR_FIELDS = (
    "Attributes/DRIVINGLAYUP",
    "Attributes/CLOSESHOT",
    "Attributes/MIDRANGE",
    "Attributes/POSTHOOK",
    "Attributes/POSTFADE",
)

#: field -> ((signal, weight, invert), ...) blended as shares, then stretched to 25-99.
#: ``ows_or_ppg`` is the one explicit missing-OWS substitute.  Missing DWS never becomes
#: offense; components that require DWS remain absent when that statistic was not kept.
_COMPOSITES: dict[str, tuple[tuple[str, float, bool], ...]] = {
    # Reach decides a block and the defensive record confirms it.
    "Attributes/BLOCK": (("height", 0.50, False), ("dws", 0.50, False)),

    # Staying in front of a man is what the defensive record actually measures, so it
    # leads here and the body follows.
    "Attributes/PERIMETERDEFENSE": (("height", 0.25, True), ("weight", 0.15, True), ("dws", 0.60, False)),
    # Guarding the interior rewards the large end of it.
    "Attributes/INTERIORDEFENSE": (("height", 0.30, False), ("weight", 0.20, False), ("dws", 0.50, False)),
    # Help defence is team defence, and the defensive record is the only measure of it
    # the era kept.
    "Attributes/HELPDEFENSE": (("dws", 1.00, False),),
    # Seeing the floor is a defensive-awareness signal; the smallest players see the
    # passing lanes the era's centres never had to.
    "Attributes/PASSPERCEPTION": (("dws", 0.80, False), ("height", 0.20, True)),
    # Shot selection is offensive value, which is what OWS measures.
    "Attributes/IQSHOT": (("ows", 1.00, False),),
    # Post play is leverage plus offensive production.
    "Attributes/POSTCONTROL": (("height", 0.35, False), ("weight", 0.25, False), ("ows_or_ppg", 0.40, False)),
    # Hook and fade keep the same body/production shape as Post Control, with one quarter
    # reserved for demonstrated field-goal execution.  The original three-term ratios
    # remain in the other 75%: height .2625, weight .1875, production .30.
    "Attributes/POSTHOOK": (("height", 0.2625, False), ("weight", 0.1875, False), ("ows_or_ppg", 0.30, False), ("field_goal_percent", 0.25, False)),
    "Attributes/POSTFADE": (("height", 0.2625, False), ("weight", 0.1875, False), ("ows_or_ppg", 0.30, False), ("field_goal_percent", 0.25, False)),
}

_AGILITY_COMPONENTS = (
    ("height", 0.40, True),
    ("weight", 0.20, True),
    ("dws", 0.40, False),
)
_STEAL_AGILITY_WEIGHT = 0.65
_STEAL_DWS_WEIGHT = 0.35

#: Captured-pool p25/median/p75 bands retained only for Close Shot, Midrange, and
#: Driving Layup. Post Hook and Post Fade are owned by the authored composite above.
#: These three retained execution curves are not stretched to 25-99.
_SHOT_BAND_ANCHORS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "Attributes/CLOSESHOT": (
        (69.417, 46.0, 56.0, 66.5), (71.625, 46.0, 55.0, 63.2), (72.750, 55.0, 55.0, 65.0),
        (73.750, 56.5, 62.0, 65.2), (74.250, 59.0, 62.0, 65.2), (75.000, 62.0, 67.0, 76.2),
        (76.000, 62.0, 73.5, 83.0), (76.708, 65.0, 74.5, 83.0), (78.417, 69.0, 83.0, 93.2),
        (80.625, 71.8, 81.0, 95.0),
    ),

    "Attributes/MIDRANGE": (
        (0.428, 51.0, 53.0, 55.5), (0.504, 54.0, 55.0, 58.0), (0.549, 55.0, 59.0, 60.2),
        (0.580, 59.0, 61.0, 62.2), (0.616, 62.0, 63.0, 64.0), (0.665, 64.8, 65.5, 67.0),
        (0.697, 66.0, 67.0, 69.0), (0.719, 67.0, 68.0, 69.2), (0.746, 69.0, 69.0, 71.0),
        (0.812, 73.0, 74.0, 77.0),
    ),
    "Attributes/DRIVINGLAYUP": (
        (0.275, 50.0, 53.0, 57.2), (0.318, 55.0, 57.0, 60.2), (0.336, 59.8, 61.0, 63.2),
        (0.354, 57.8, 62.0, 64.0), (0.373, 63.5, 66.0, 67.2), (0.395, 64.8, 66.5, 71.5),
        (0.418, 68.8, 77.0, 84.2), (0.450, 75.5, 83.0, 93.8), (0.487, 85.8, 96.5, 99.0),
        (0.524, 98.0, 98.0, 99.0),
    ),

}

#: field -> (band signal, placement signal, captured-pool r for each).
_SHOT_SIGNALS: dict[str, tuple[str, str, float, float]] = {
    "Attributes/CLOSESHOT": ("height", "field_goal_percent", 0.60, 0.29),

    "Attributes/MIDRANGE": ("free_throw_percent", "field_goal_percent", 0.93, 0.23),
    "Attributes/DRIVINGLAYUP": ("field_goal_percent", "points_per_game", 0.91, 0.68),

}

#: Estimated season field goal attempts below which a player's shooting percentage is
#: not evidence about him. At 100 attempts the standard error on a .300 percentage is
#: still .046; at the three attempts the pool's unfloored bottom decile averaged it is
#: .265, which is the entire width of the era. 45% of the 1947 season falls under 200
#: attempts and 34% under 100, so this is not a rare branch -- it is a third of the
#: league, and it is why the rule has to say "unmeasured" rather than "poor".
SHOT_EVIDENCE_MIN_ATTEMPTS = 100.0

#: A fallback is what you use when nothing better is known, so it must never overwrite
#: something that *is* known. A rule carrying one of these markers is a finding about a
#: named player or a cap the era research established -- Mikan's researched interior
#: defence, the NBL centre scoring caps, the close-shot response cap -- and it outranks
#: anything derived here from body and box score.
_PROTECTED_RULE_MARKERS = (
    "_researched_exact_player_override",
    "_fixed_nbl_center_cap",
    "_same_season_baa_center_cap",
)

#: Some of those findings identify themselves in the evidence rather than in the rule
#: name -- the close-range response cap is a mapping key, not a suffix -- so the
#: provenance is checked as well as the rule.
_PROTECTED_EVIDENCE_MARKERS = (
    "historical_close_response_rating=",
    "reliability_shrunk_close_range_response",
)


def _is_protected(current: Any) -> bool:
    rule = str(getattr(current, "source_rule", "") or "")
    if any(marker in rule for marker in _PROTECTED_RULE_MARKERS):
        return True
    keys = getattr(current, "evidence_keys", ()) or ()
    return any(
        marker in str(key)
        for key in keys
        for marker in _PROTECTED_EVIDENCE_MARKERS
    )


#: Free throws drawn per game, floored at a real zero rather than at whatever the
#: least-used player in the season managed.
_DRAW_FOUL_SIGNAL = "ft_per_game"

#: Total points, field goals and free throws -- the three counting totals the NBL kept
#: for every player. Intangibles is scoped to the NBL; the BAA keeps its own rule.
_NBL_INTANGIBLES = (
    ("points_total", 0.40, False),
    ("field_goals_made", 0.30, False),
    ("free_throws_total", 0.30, False),
)


#: Body signals are spread harder than the rest. A straight magnitude position puts
#: most of a season inside a narrow middle, because most players are ordinary sized --
#: this is not what a percentile rank would do, which is uniform by construction; it
#: is what min-max scaling on a clustered signal does. So the
#: 6'9" man and the 5'11" man ended up much closer together than they play. This pushes
#: shares away from the centre and toward both ends, so reach and mass separate the way
#: they actually do on a floor. Above 1.0 widens; 1.0 would be the plain position.
_BODY_EXTREMITY = 1.75
_BODY_SIGNALS = ("height", "weight")

#: Reach is measured against a fixed span, not against whoever turned up this season.
#: 1947 runs 5'6" to 7'1", but the same season has to be able to hold a 5'3" guard and
#: a 7'9" centre -- a franchise or fantasy draft can put either on a roster. Ranking
#: against the observed extremes would re-scale every player in the league the moment
#: one of them arrived, and would also hand the tallest man in a short season the same
#: reach score a genuine seven-footer gets. The span is the scale; the season sits
#: somewhere inside it.
HEIGHT_SCALE_FLOOR = 63.0    # 5'3"
HEIGHT_SCALE_CEILING = 93.0  # 7'9"


def _fixed_span_share(value: float | None, floor: float, ceiling: float) -> float | None:
    if value is None or ceiling <= floor:
        return None
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))


def _extremise(rank_share: float) -> float:
    """Push a 0-1 rank away from the middle, keeping 0, 0.5 and 1 where they are."""

    centred = 2.0 * rank_share - 1.0
    stretched = abs(centred) ** (1.0 / _BODY_EXTREMITY)
    return 0.5 * (1.0 + (stretched if centred >= 0.0 else -stretched))


def _entry_share(
    entry: Mapping[str, Any],
    population: Sequence[Mapping[str, Any]],
    name: str,
    invert: bool,
    *,
    from_row: bool,
) -> tuple[float | None, str]:
    if name == "ows_or_ppg":
        value, signal = scale.win_share_share(
            entry,
            population,
            "ows",
            from_row=from_row,
            fallback_to_points=True,
        )
        return value, signal or name
    if name in ("ows", "dws"):
        value, signal = scale.win_share_share(entry, population, name, from_row=from_row)
        return value, signal or name
    read = (lambda key: entry.get(key)) if from_row else (lambda key: scale.evidence_signal(entry, key))
    raw = read(name)
    try:
        number = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        number = None
    if name == "height":
        # Against the fixed 5'3"-7'9" span, never against the season's own extremes.
        rank_share = _fixed_span_share(number, HEIGHT_SCALE_FLOOR, HEIGHT_SCALE_CEILING)
        if rank_share is None:
            return None, name
        if invert:
            rank_share = 1.0 - rank_share
        return (
            _extremise(rank_share),
            f"height_span{HEIGHT_SCALE_FLOOR:.0f}_{HEIGHT_SCALE_CEILING:.0f}_extremity{_BODY_EXTREMITY:g}",
        )
    values = scale.values_of(population, name)
    rank_share = scale.share(
        number,
        values,
        invert=invert,
        low_anchor=values[0] if values else None,
        high_anchor=values[-1] if values else None,
    )
    if rank_share is not None and name in _BODY_SIGNALS:
        return _extremise(rank_share), f"{name}_extremity{_BODY_EXTREMITY:g}"
    return rank_share, name


def _composite_for(
    entry: Mapping[str, Any],
    population: Sequence[Mapping[str, Any]],
    components: Sequence[tuple[str, float, bool]],
    *,
    from_row: bool,
) -> tuple[float | None, tuple[str, ...]]:
    parts: list[tuple[float | None, float]] = []
    signals: list[str] = []
    for name, weight, invert in components:
        value, signal = _entry_share(entry, population, name, invert, from_row=from_row)
        if name in ("ows", "dws") and value is not None and invert:
            value = 1.0 - value
        parts.append((value, weight))
        signals.append(f"{signal}{'_inverse' if invert else ''}@{weight:.2f}")
    return scale.composite_share(parts), tuple(signals)


#: Each of these is one answer per season, not one per player: the pooled snapshot is a
#: single shared tuple, so the whole-population composite and the rebound ladder are
#: identical for every player rated against it. Recomputing them per player made a
#: season quadratic in its own size.
_COMPOSITE_CACHE: dict[tuple[int, tuple[tuple[str, float, bool], ...], str | None], tuple[float, ...]] = {}
_STEAL_CACHE: dict[int, tuple[float, ...]] = {}
_REBOUND_CACHE: dict[tuple[int, str], dict[tuple[str, str], float]] = {}
_CACHE_GUARD: dict[int, Any] = {}


def _population_composite(
    population: Sequence[Mapping[str, Any]],
    components: Sequence[tuple[str, float, bool]],
    *,
    league: str | None = None,
) -> tuple[float, ...]:
    key = (id(population), tuple(components), league)
    cached = _COMPOSITE_CACHE.get(key)
    if cached is not None:
        return cached
    _CACHE_GUARD.setdefault(id(population), population)
    scores: list[float] = []
    for entry in population:
        if league is not None and str(entry.get("league") or "") != league:
            continue
        blended, _signals = _composite_for(entry, population, components, from_row=True)
        if blended is not None:
            scores.append(blended)
    values = tuple(sorted(scores))
    _COMPOSITE_CACHE[key] = values
    return values


def _population_composite_winner(
    population: Sequence[Mapping[str, Any]],
    components: Sequence[tuple[str, float, bool]],
) -> tuple[str, str] | None:
    scored = [
        (score, _entry_identity(entry))
        for entry in population
        if all(_entry_identity(entry))
        and (score := _composite_for(entry, population, components, from_row=True)[0]) is not None
    ]
    if not scored:
        return None
    maximum = max(score for score, _identity in scored)
    return min(identity for score, identity in scored if score == maximum)


def _speed_rating_for(
    entry: Mapping[str, Any],
    *,
    from_row: bool,
) -> float | None:
    if from_row:
        value = entry.get(scale.SPEED_RATING_KEY)
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return float(round(number)) if number is not None else None
    identity = _player_identity(entry)
    raw = scale.field_base_values(entry).get(identity, {}).get("Attributes/SPEED")
    spread = scale.field_distributions(entry).get("Attributes/SPEED", ())
    rating = scale.stretch(
        raw,
        spread,
        low_anchor=spread[0] if spread else None,
        high_anchor=spread[-1] if spread else None,
    )
    return float(round(rating)) if rating is not None else None


def _agility_rating_for(
    entry: Mapping[str, Any],
    population: Sequence[Mapping[str, Any]],
    *,
    from_row: bool,
) -> tuple[float | None, tuple[str, ...]]:
    raw, signals = _composite_for(
        entry,
        population,
        _AGILITY_COMPONENTS,
        from_row=from_row,
    )
    spread = _population_composite(population, _AGILITY_COMPONENTS)
    rating = scale.stretch(
        raw,
        spread,
        low_anchor=spread[0] if spread else None,
        high_anchor=spread[-1] if spread else None,
    )
    if rating is None:
        return None, signals
    speed = _speed_rating_for(entry, from_row=from_row)
    capped = False
    if speed is not None and rating > speed + 5.0:
        rating = speed + 5.0
        capped = True
    rating = float(round(max(scale.ATTRIBUTE_FLOOR, min(scale.ATTRIBUTE_CEILING, rating))))
    return rating, signals + (
        f"Attributes/SPEED={speed:.2f}" if speed is not None else "Attributes/SPEED=unavailable",
        "agility_contract=AGILITY<=SPEED+5",
        f"agility_speed_cap_applied={str(capped).lower()}",
    )


def _steal_composite_for(
    entry: Mapping[str, Any],
    population: Sequence[Mapping[str, Any]],
    *,
    from_row: bool,
) -> tuple[float | None, tuple[str, ...]]:
    agility_rating, _agility_signals = _agility_rating_for(
        entry,
        population,
        from_row=from_row,
    )
    agility_share = (
        (agility_rating - scale.ATTRIBUTE_FLOOR)
        / (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR)
        if agility_rating is not None
        else None
    )
    dws_share, dws_signal = _entry_share(entry, population, "dws", False, from_row=from_row)
    score = scale.composite_share((
        (agility_share, _STEAL_AGILITY_WEIGHT),
        (dws_share, _STEAL_DWS_WEIGHT),
    ))
    return score, (
        f"Attributes/AGILITY={agility_rating:.2f}@{_STEAL_AGILITY_WEIGHT:.2f}"
        if agility_rating is not None
        else f"Attributes/AGILITY=unavailable@{_STEAL_AGILITY_WEIGHT:.2f}",
        f"{dws_signal or 'dws'}@{_STEAL_DWS_WEIGHT:.2f}",
    )


def _population_steal_composite(
    population: Sequence[Mapping[str, Any]],
) -> tuple[float, ...]:
    key = id(population)
    cached = _STEAL_CACHE.get(key)
    if cached is not None:
        return cached
    _CACHE_GUARD.setdefault(key, population)
    values = tuple(sorted(
        score
        for entry in population
        if (score := _steal_composite_for(entry, population, from_row=True)[0]) is not None
    ))
    _STEAL_CACHE[key] = values
    return values


def _entry_identity(entry: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(entry.get("player_id") or "").strip().upper(),
        str(entry.get("team") or "").strip().upper(),
    )


def _rebound_values(
    population: Sequence[Mapping[str, Any]],
    side: str,
) -> dict[tuple[str, str], float]:
    """Height sets the value; win shares separate the players who share a height.

    Height is the rating -- shortest in the season 25, tallest 99. Every player at one
    height would otherwise be given the identical number, so the win-share side (OWS for
    the offensive board, DWS for the defensive) orders them inside the gap to the next
    height up or down: positives climb toward the taller neighbour in magnitude order,
    negatives fall toward the shorter one. Nobody is moved by more than the distance to
    the height either side of him.
    """

    key = (id(population), side)
    cached = _REBOUND_CACHE.get(key)
    if cached is not None:
        return cached
    _CACHE_GUARD.setdefault(id(population), population)
    heights = scale.values_of(population, "height")
    if not heights:
        return {}
    distinct = sorted(set(heights))
    height_span = distinct[-1] - distinct[0]
    base_by_height = {
        height: (
            scale.ATTRIBUTE_FLOOR
            + (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR)
            * ((height - distinct[0]) / height_span)
            if height_span > 0.0
            else (scale.ATTRIBUTE_FLOOR + scale.ATTRIBUTE_CEILING) / 2.0
        )
        for height in distinct
    }
    by_height: dict[float, list[tuple[float, tuple[str, str]]]] = {}
    for entry in population:
        height = entry.get("height")
        identity = _entry_identity(entry)
        if height is None or not all(identity):
            continue
        raw_win_shares = entry.get(side)
        try:
            magnitude = float(raw_win_shares) if raw_win_shares is not None else 0.0
        except (TypeError, ValueError):
            magnitude = 0.0
        by_height.setdefault(float(height), []).append((magnitude, identity))

    resolved: dict[tuple[str, str], float] = {}
    for height, members in by_height.items():
        base = base_by_height[height]
        index = distinct.index(height)
        upper = base_by_height[distinct[index + 1]] if index + 1 < len(distinct) else scale.ATTRIBUTE_CEILING
        lower = base_by_height[distinct[index - 1]] if index > 0 else scale.ATTRIBUTE_FLOOR
        positives = sorted(
            (item for item in members if item[0] > 0.0),
            key=lambda item: (item[0], item[1]),
        )
        negatives = sorted(
            (item for item in members if item[0] < 0.0),
            key=lambda item: (abs(item[0]), item[1]),
        )
        neutral = [item for item in members if item[0] == 0.0]
        for identity in (item[1] for item in neutral):
            resolved[identity] = base
        for rank, (_magnitude, identity) in enumerate(positives, start=1):
            step = rank / (len(positives) + 1)
            resolved[identity] = base + (upper - base) * step
        for rank, (_magnitude, identity) in enumerate(negatives, start=1):
            step = rank / (len(negatives) + 1)
            resolved[identity] = base - (base - lower) * step
    _REBOUND_CACHE[key] = resolved
    return resolved


def _interpolate_band(
    anchors: Sequence[tuple[float, float, float, float]],
    percent: float,
) -> tuple[float, float, float]:
    """The pool's p25/median/p75 for this shooting percentage, read absolutely.

    Not by rank. Shooting is an absolute skill: a man who shot .280 is a .280 shooter
    whether or not he led his league, and leading a league that shot .268 does not make
    him a rim finisher. Ranking within the season instead put the best 1947 shooter --
    .401 -- onto the pool's top decile, whose players shoot .619 because they only
    shoot at the rim, and handed him their 95-98 layup band.

    The era's ratings therefore come out low, which is the point: this is what these
    percentages buy anywhere in the pool.
    """

    if percent <= anchors[0][0]:
        return anchors[0][1], anchors[0][2], anchors[0][3]
    if percent >= anchors[-1][0]:
        return anchors[-1][1], anchors[-1][2], anchors[-1][3]
    for lower, upper in zip(anchors, anchors[1:]):
        if lower[0] <= percent <= upper[0]:
            span = upper[0] - lower[0]
            step = (percent - lower[0]) / span if span > 0.0 else 0.0
            return tuple(low + (high - low) * step for low, high in zip(lower[1:], upper[1:]))  # type: ignore[return-value]
    return anchors[-1][1], anchors[-1][2], anchors[-1][3]


#: The NBL was the weaker league and its shooting cannot buy a better rating than the
#: BAA's own best. These three are capped at the highest value any BAA player in the
#: same season reaches, so ranking the two leagues together never lifts an NBL shooter
#: above the league he was worse than.
_BAA_CEILING_FIELDS = ("Attributes/DRIVINGLAYUP", "Attributes/CLOSESHOT", "Attributes/MIDRANGE")

_BAA_CEILING_CACHE: dict[tuple[int, str], float | None] = {}



def _shot_attempts(read: Any) -> float | None:
    """Estimated season field goal attempts -- the weight behind a shooting percentage."""

    per_game = read("field_goal_attempts_per_game")
    games = read("games")
    if per_game is None or games is None:
        return None
    return float(per_game) * float(games)


def _band_input(
    read: Any,
    population: Sequence[Mapping[str, Any]],
    signal: str,
    *,
    measured_shooting: bool,
) -> float | None:
    """The raw value the band is read at, in that signal's own units."""

    if signal == "field_goal_percent" and not measured_shooting:
        # No shooting evidence worth the name. Read the band at the season's own median
        # rather than at a percentage built from a handful of attempts: an unmeasured
        # player is unremarkable, not bad.
        values = scale.values_of(population, "field_goal_percent")
        if not values:
            return None
        return values[len(values) // 2]
    return read(signal)


def _placement_share(
    read: Any,
    population: Sequence[Mapping[str, Any]],
    signal: str,
    *,
    measured_shooting: bool,
) -> float | None:
    """Where the player sits on the secondary signal, on 0-1."""

    if signal == "field_goal_percent" and not measured_shooting:
        return None
    value = read(signal)
    if signal == "height":
        # The fixed 5'3"-7'9" span, exactly as the composites use it, so a roster move
        # cannot re-place a whole league. Placing against the season's own extremes gave
        # the tallest man in a short season the spot a genuine seven-footer belongs in.
        return _fixed_span_share(value, HEIGHT_SCALE_FLOOR, HEIGHT_SCALE_CEILING)
    return scale.share(value, scale.values_of(population, signal))


def _shot_value(
    read: Any,
    population: Sequence[Mapping[str, Any]],
    field_key: str,
) -> tuple[float, tuple[str, ...]] | None:
    """Place a shot-execution field on the pool's curve for this player.

    The band comes from the signal the pool says actually moves the field, read
    absolutely rather than by rank -- a man who shot .280 is a .280 shooter whether or
    not he led his league, and a 6'10" man is 6'10" in any season. The placement inside
    the band comes from the secondary signal. The value stays within the quartiles the
    pool recorded, so the field never reaches a ceiling the pool itself does not show.
    """

    anchors = _SHOT_BAND_ANCHORS.get(field_key)
    signals = _SHOT_SIGNALS.get(field_key)
    if anchors is None or signals is None:
        return None
    band_signal, place_signal, band_r, place_r = signals

    attempts = _shot_attempts(read)
    measured_shooting = attempts is None or attempts >= SHOT_EVIDENCE_MIN_ATTEMPTS
    band_signal_value = _band_input(
        read, population, band_signal, measured_shooting=measured_shooting
    )
    if band_signal_value is None:
        return None

    low, median, high = _interpolate_band(anchors, float(band_signal_value))
    band_keys = (
        f"pre_1952_shot_band={band_signal}={float(band_signal_value):.4f}",
        f"pre_1952_shot_band_source=pool_curve[{band_signal};r={band_r:+.2f}]",
        "pre_1952_shot_band_reason=the_band_signal_is_whichever_one_the_pool_says_moves_this_field",
        f"pre_1952_shot_band_p25_median_p75={low:.1f},{median:.1f},{high:.1f}",
        "pre_1952_shot_scale=captured_pool_curve_not_25_to_99",
        f"pre_1952_shot_pool_min_attempts={SHOT_EVIDENCE_MIN_ATTEMPTS:.0f}",
    )
    if attempts is not None:
        band_keys += (f"pre_1952_shot_season_attempts={attempts:.0f}",)
    if not measured_shooting:
        band_keys += (
            "pre_1952_shot_shooting_unmeasured=too_few_attempts_for_a_percentage_to_be_evidence",
        )

    rank_share = _placement_share(
        read, population, place_signal, measured_shooting=measured_shooting
    )
    if rank_share is None:
        return median, band_keys + (
            f"pre_1952_shot_placement={place_signal}_unavailable_band_median",
        )
    # Bounded by the quartiles the pool actually recorded, rather than extrapolated
    # past them.
    if rank_share <= 0.5:
        value = low + (median - low) * (rank_share / 0.5)
    else:
        value = median + (high - median) * ((rank_share - 0.5) / 0.5)
    return value, band_keys + (
        f"pre_1952_shot_placement={place_signal};pool_r={place_r:+.2f};share={rank_share:.4f}",
    )


def _shot_execution_rating(
    evidence: Any,
    population: Sequence[Mapping[str, Any]],
    field_key: str,
) -> tuple[float, tuple[str, ...]] | None:
    return _shot_value(lambda name: scale.evidence_signal(evidence, name), population, field_key)


def _baa_shot_ceiling(
    population: Sequence[Mapping[str, Any]],
    field_key: str,
) -> float | None:
    """The best value any BAA player in this season reaches on a shot field."""

    key = (id(population), field_key)
    if key in _BAA_CEILING_CACHE:
        return _BAA_CEILING_CACHE[key]
    _CACHE_GUARD.setdefault(id(population), population)
    best: float | None = None
    for entry in population:
        if str(entry.get("league") or "") != "BAA":
            continue
        placed = _shot_value(entry.get, population, field_key)
        if placed is not None and (best is None or placed[0] > best):
            best = placed[0]
    _BAA_CEILING_CACHE[key] = best
    return best


def _player_identity(evidence: Any) -> tuple[str, str]:
    value = getattr(evidence, "player_id", None)
    if not value:
        identity = getattr(evidence, "identity", None)
        if isinstance(identity, Mapping):
            value = identity.get("player_id")
    team = getattr(evidence, "team", None)
    if not team:
        season_info = getattr(evidence, "season_info", None)
        if isinstance(season_info, Mapping):
            team = season_info.get("team")
    return str(value or "").strip().upper(), str(team or "").strip().upper()


def _primary_position(positions: Any) -> str:
    return str(getattr(positions, "primary", "") or "").strip().upper()


def _made_no_field_goals(evidence: Any) -> bool:
    made = scale.evidence_signal(evidence, "field_goals_made")
    return made is not None and made <= 0.0


def _field_goal_percent_provenance(evidence: Any) -> tuple[str, ...]:
    per_game = getattr(evidence, "per_game", None)
    if not isinstance(per_game, Mapping):
        return ("pre_1952_field_goal_percent_source=unresolved",)
    source = str(
        per_game.get("fg_percent_source")
        or "recorded_player_per_game_fg_percent"
    )
    return (
        f"pre_1952_field_goal_percent_source={source}",
        f"pre_1952_field_goal_percent_imputed={str(per_game.get('fg_percent_imputed') is True).lower()}",
    )


def apply_pre_1952_ratings(
    evidence: Any,
    values: dict[str, Any],
    *,
    positions: Any = None,
) -> dict[str, Any]:
    """Rebuild the authored fallback fields for a 1947-51 player.

    Fields the operator has not specified are left exactly as the ordinary rules
    produced them, and a field whose evidence is missing is left alone rather than
    guessed at.
    """

    if not scale.applies(evidence):
        return values
    population = scale.pooled_population(evidence)
    if not population:
        return values

    updated = dict(values)
    player_identity = _player_identity(evidence)
    season_info = getattr(evidence, "season_info", {}) or {}
    league = str(season_info.get("lg") or "").strip().upper()

    def write(
        field_key: str,
        number: float,
        rule: str,
        keys: tuple[str, ...],
        *,
        lowering_cap: bool = False,
        force: bool = False,
    ) -> None:
        current = updated.get(field_key)
        if current is None:
            return
        # A protected value is a finding this pass must not re-derive. A cap is not a
        # re-derivation: it only ever lowers, so it may still apply on top of one. The
        # 1949 NBL midrange leader was pinned by the BAA centre cap at 72 -- above the
        # best midrange shooter in the BAA -- and protection alone left him there.
        if not force and _is_protected(current) and not (
            lowering_cap and isinstance(current.value, (int, float)) and number < float(current.value)
        ):
            return
        value = int(round(max(scale.ATTRIBUTE_FLOOR, min(scale.ATTRIBUTE_CEILING, number))))
        provenance = keys + (
            "pre_1952_scale_scope=ui_selected_same_season_population",
            f"pre_1952_scale_population={len(population)}",
        )
        updated[field_key] = replace(
            current,
            value=value,
            source_rule=rule,
            evidence_keys=tuple(current.evidence_keys) + provenance + (
                f"pre_1952_replaced_value={current.value}",
                f"pre_1952_replaced_rule={current.source_rule}",
            ),
        )

    # --- composites -------------------------------------------------------------
    for field_key, components in _COMPOSITES.items():
        if field_key not in updated:
            continue
        blended, signals = _composite_for(evidence, population, components, from_row=False)
        if blended is None:
            continue
        spread = _population_composite(population, components)
        value = scale.stretch(
            blended,
            spread,
            low_anchor=spread[0] if spread else None,
            high_anchor=spread[-1] if spread else None,
        )
        if value is None:
            continue
        shooting_keys = (
            _field_goal_percent_provenance(evidence)
            if field_key in {"Attributes/POSTHOOK", "Attributes/POSTFADE"}
            else ()
        )
        write(
            field_key,
            value,
            f"pre_1952_{field_key.split('/')[-1].lower()}_authored_fallback",
            tuple(f"pre_1952_component={signal}" for signal in signals)
            + shooting_keys
            + (f"pre_1952_composite_share={blended:.8f}",),
        )

    # --- agility: body plus DWS, capped against final Speed -----------------------
    if "Attributes/AGILITY" in updated:
        value, signals = _agility_rating_for(evidence, population, from_row=False)
        if value is not None:
            write(
                "Attributes/AGILITY",
                value,
                "pre_1952_agility_authored_fallback",
                tuple(f"pre_1952_component={signal}" for signal in signals),
            )

    # --- steal: final agility plus defensive win shares --------------------------
    if "Attributes/STEAL" in updated:
        blended, signals = _steal_composite_for(evidence, population, from_row=False)
        spread = _population_steal_composite(population)
        value = scale.stretch(
            blended,
            spread,
            low_anchor=spread[0] if spread else None,
            high_anchor=spread[-1] if spread else None,
        )
        if value is not None:
            write(
                "Attributes/STEAL",
                value,
                "pre_1952_steal_agility_and_dws",
                tuple(f"pre_1952_component={signal}" for signal in signals)
                + (f"pre_1952_composite_share={blended:.8f}",),
            )

    # --- rebounding: height first, win shares inside the height ------------------
    for field_key, side in (("Attributes/OFFENSIVEREBOUND", "ows"), ("Attributes/DEFENSEREBOUND", "dws")):
        if field_key not in updated or not all(player_identity):
            continue
        resolved_rebounds = _rebound_values(population, side)
        value = resolved_rebounds.get(player_identity)
        if value is None:
            continue
        write(
            field_key,
            value,
            f"pre_1952_{field_key.split('/')[-1].lower()}_height_then_win_shares",
            (
                "pre_1952_rebound_base=height_shortest_25_tallest_99",
                f"pre_1952_rebound_spread={side}_within_the_gap_to_the_next_height",
            ),
        )

    # --- shot execution: the captured pool's curve, never a 25-99 stretch ---------
    for field_key in _SHOT_BAND_ANCHORS:
        if field_key not in updated:
            continue
        placed = _shot_execution_rating(evidence, population, field_key)
        if placed is None:
            continue
        value, keys = placed
        write(
            field_key,
            value,
            f"pre_1952_{field_key.split('/')[-1].lower()}_pool_band_curve",
            keys,
        )

    # --- the NBL cannot out-shoot the BAA ----------------------------------------
    # Applied to whatever the field ended up holding, not only to the curve rule above.
    # An NBL player with no recorded field goal percentage never reaches that rule at
    # all, so his ordinary value stood uncapped -- which is exactly how the 1949 NBL
    # came out four points above the best midrange shooter in the BAA.
    if league == "NBL":
        for field_key in _BAA_CEILING_FIELDS:
            current = updated.get(field_key)
            if current is None or not isinstance(current.value, (int, float)):
                continue
            ceiling = _baa_shot_ceiling(population, field_key)
            if ceiling is None or float(current.value) <= ceiling:
                continue
            write(
                field_key,
                ceiling,
                f"{current.source_rule}_nbl_capped_at_baa_best",
                (
                    f"pre_1952_nbl_capped_at_baa_best={ceiling:.2f}",
                    f"pre_1952_nbl_uncapped_value={float(current.value):.2f}",
                    "pre_1952_nbl_cap_reason=the_weaker_league_cannot_out_shoot_the_stronger_one",
                ),
                lowering_cap=True,
            )

    # --- draw foul: zero is 25 and the selected population maximum is 99 ----------
    if "Attributes/DRAWFOUL" in updated:
        ft_per_game = scale.evidence_signal(evidence, _DRAW_FOUL_SIGNAL)
        ft_population = scale.values_of(population, _DRAW_FOUL_SIGNAL)
        value = (
            scale.ATTRIBUTE_FLOOR
            if ft_per_game == 0.0
            else scale.stretch(
                ft_per_game,
                ft_population,
                low_anchor=0.0,
                high_anchor=ft_population[-1] if ft_population else None,
            )
        )
        if value is not None:
            write(
                "Attributes/DRAWFOUL",
                value,
                "pre_1952_drawfoul_free_throws_per_game",
                (
                    "pre_1952_component=ft_per_game",
                    "pre_1952_low_anchor=0_free_throws_is_25",
                    "pre_1952_high_anchor=selected_population_max_is_99",
                ),
            )

    # --- intangibles: NBL only, on the three totals the league kept ---------------
    if league == "NBL" and "Attributes/INTANGIBLES" in updated:
        nbl_population = scale.nbl_totals(evidence)
        blended, signals = _composite_for(
            evidence,
            nbl_population,
            _NBL_INTANGIBLES,
            from_row=False,
        )
        if blended is not None:
            spread = _population_composite(nbl_population, _NBL_INTANGIBLES)
            winner = _population_composite_winner(nbl_population, _NBL_INTANGIBLES)
            value = scale.stretch(
                blended,
                spread,
                low_anchor=spread[0] if spread else None,
                high_anchor=spread[-1] if spread else None,
            )
            if value is not None and winner is not None:
                value = scale.ATTRIBUTE_CEILING if player_identity == winner else min(
                    scale.ATTRIBUTE_CEILING - 1.0,
                    value,
                )
                write(
                    "Attributes/INTANGIBLES",
                    value,
                    "pre_1952_nbl_intangibles_recorded_totals",
                    tuple(f"pre_1952_component={signal}" for signal in signals)
                    + (
                        "pre_1952_intangibles_scope=NBL_only",
                        f"pre_1952_intangibles_population={len(nbl_population)}",
                        f"pre_1952_intangibles_winner={winner[0]}:{winner[1]}",
                        f"pre_1952_intangibles_unique_99={str(player_identity == winner).lower()}",
                        f"pre_1952_composite_share={blended:.8f}",
                    ),
                )

    # --- restretched body fields --------------------------------------------------
    distributions = scale.field_distributions(evidence)
    field_base_values = scale.field_base_values(evidence).get(player_identity, {})
    for field_key in RESTRETCHED_FIELDS:
        current = updated.get(field_key)
        spread = distributions.get(field_key)
        base_value = field_base_values.get(field_key)
        if current is None or not spread or base_value is None:
            continue
        value = scale.stretch(
            base_value,
            spread,
            low_anchor=spread[0],
            high_anchor=spread[-1],
        )
        if value is None:
            continue
        write(
            field_key,
            value,
            f"{current.source_rule}_pre_1952_season_stretch",
            ("pre_1952_stretch=selected_population_min_to_25_max_to_99",),
        )

    # --- hustle: exactly the selected population's top twenty-five are 99 --------
    hustle = updated.get("Attributes/HUSTLE")
    hustle_top_keys = scale.hustle_top_keys(evidence)
    if hustle is not None and hustle_top_keys and isinstance(hustle.value, (int, float)):
        if player_identity in hustle_top_keys:
            rank = hustle_top_keys.index(player_identity) + 1
            write(
                "Attributes/HUSTLE",
                scale.ATTRIBUTE_CEILING,
                f"{hustle.source_rule}_pre_1952_top_25_ceiling",
                (
                    f"pre_1952_hustle_ceiling_players={HUSTLE_CEILING_PLAYERS}",
                    f"pre_1952_hustle_exact_rank={rank}",
                    "pre_1952_hustle_ties=exact_player_id_team_tie_break",
                ),
            )
        elif float(hustle.value) >= scale.ATTRIBUTE_CEILING:
            write(
                "Attributes/HUSTLE",
                scale.ATTRIBUTE_CEILING - 1.0,
                f"{hustle.source_rule}_pre_1952_outside_top_25_cap",
                (
                    f"pre_1952_hustle_ceiling_players={HUSTLE_CEILING_PLAYERS}",
                    "pre_1952_hustle_exact_rank=outside_top_25",
                    "pre_1952_hustle_non_top_max=98",
                ),
                lowering_cap=True,
            )

    # --- point guards alone use the 60-99 handling/passing band ------------------
    if _primary_position(positions) == "PG":
        for field_key in POINT_GUARD_FIELDS:
            current = updated.get(field_key)
            if current is None or not isinstance(current.value, (int, float)):
                continue
            legal_share = (
                (float(current.value) - scale.ATTRIBUTE_FLOOR)
                / (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR)
            )
            remapped = POINT_GUARD_FLOOR + (
                scale.ATTRIBUTE_CEILING - POINT_GUARD_FLOOR
            ) * max(0.0, min(1.0, legal_share))
            write(
                field_key,
                remapped,
                f"{current.source_rule}_pre_1952_point_guard_60_99",
                (
                    "pre_1952_position_helper=PG_only",
                    f"pre_1952_point_guard_band={POINT_GUARD_FLOOR:.0f}_to_99",
                    f"pre_1952_pre_band_value={float(current.value):.2f}",
                ),
            )

    # --- no made field goal: nothing to rate a shot on ----------------------------
    if _made_no_field_goals(evidence):
        for field_key in ZERO_MAKE_FLOOR_FIELDS:
            current = updated.get(field_key)
            if current is None:
                continue
            write(
                field_key,
                scale.ATTRIBUTE_FLOOR,
                f"{current.source_rule}_pre_1952_no_made_field_goal",
                ("pre_1952_zero_makes=no_field_goal_made_all_season",),
                force=True,
            )

    # --- acceleration follows its own inputs --------------------------------------
    # Acceleration is a blend of SPEED and AGILITY, and both are rewritten above -- so
    # the value the ordinary pass computed describes inputs that no longer exist. It was
    # coming out a mean 8.6 points below its own formula and topping out at 82 while both
    # of its inputs reached 99. Re-derived rather than restretched: it is defined by the
    # other two, so once they are right it is arithmetic, not a fresh estimate.
    acceleration = updated.get("Attributes/ACCELERATION")
    speed = updated.get("Attributes/SPEED")
    agility = updated.get("Attributes/AGILITY")
    if (
        acceleration is not None
        and speed is not None
        and agility is not None
        and isinstance(speed.value, (int, float))
        and isinstance(agility.value, (int, float))
    ):
        import player_rules_athleticism as athleticism  # local: athleticism imports nothing here

        write(
            "Attributes/ACCELERATION",
            athleticism.ACCELERATION_SPEED_WEIGHT * float(speed.value)
            + athleticism.ACCELERATION_AGILITY_WEIGHT * float(agility.value),
            "pre_1952_acceleration_rederived_from_final_speed_and_agility",
            (
                f"Attributes/SPEED={int(speed.value)}",
                f"Attributes/AGILITY={int(agility.value)}",
                f"pre_1952_acceleration_blend=speed:{athleticism.ACCELERATION_SPEED_WEIGHT:g},"
                f"agility:{athleticism.ACCELERATION_AGILITY_WEIGHT:g}",
                "pre_1952_acceleration_reason=both_inputs_were_rewritten_by_this_pass",
            ),
        )

    return updated


__all__ = [
    "HUSTLE_CEILING_PLAYERS",
    "POINT_GUARD_FIELDS",
    "POINT_GUARD_FLOOR",
    "RESTRETCHED_FIELDS",
    "ZERO_MAKE_FLOOR_FIELDS",
    "apply_pre_1952_ratings",
]
