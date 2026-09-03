"""Authored fallback ratings for the 1947-51 seasons.

These seasons record body, the box score, and -- in the BAA and the early NBA only --
win shares. There are no steals, blocks, turnovers, split rebounds or shot locations to
rate anyone on, so each field here is built from the evidence that does exist and says
so in its provenance.

Three rules govern the module:

*Everyone is scaled against his own season, both leagues.* Rating inside one league gave
the 1947 NBL and the 1947 BAA a 99 apiece, so the two sets of cards could not be read
against each other. The pooled population is stamped by the generator before the league
filter, so the scale does not move when the operator changes the selected league.

*The composite is stretched, not its parts.* Averaging several 25-99 components can
never reach either end -- a player would have to be the season's extreme on every term
at once -- which is what held SPEED to a single 99 and STEAL to a 28-81 band. Components
are blended as 0-1 shares and only the blend is stretched onto 25-99, so both ends of
every field belong to a real player.

*Shot execution is never stretched at all.* Those fields go on the captured pool's own
curve for a player's shooting percentage. A 1947 shooter who led his league is not a 99
layup finisher, and the pool's own 99th percentile for Post Fade is 62.

Where a rule wants win shares and the player is NBL, his points per game carries that
term instead: the NBL kept no win shares for anyone, and scoring is the production it
did record. The provenance names whichever signal was used.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

import player_pre1952_scale as scale

#: Number of players per season pinned to the ceiling on Hustle.
HUSTLE_CEILING_PLAYERS = 25

#: A small man in this era handled and passed, because nothing else kept him on the
#: floor -- and the box score cannot show it, since the NBL recorded no assists at all
#: and the BAA's are thin. Height says it without the position label: under 6'2" is the
#: measurement the label was standing in for, and it is a floor rather than a rating,
#: lifting the bottom of the band to 60 and leaving the order inside it to the evidence.
SMALL_HANDLER_HEIGHT = 74.0  # 6'2"
SMALL_HANDLER_FLOOR = 60.0
SMALL_HANDLER_FIELDS = ("Attributes/BALLCONTROL", "Attributes/PASSACCURACY")

#: Fields restretched from the value the ordinary rule produced, rather than rebuilt.
#: The shape of these is wanted; only their range was short. Speed with the ball is the
#: same narrow body model as SPEED and has to move with it -- restretching SPEED alone
#: left it topping out at 75 against SPEED's 99, so the 0.97 handling ceiling stopped
#: binding and the ratio between them silently fell to 0.74.
RESTRETCHED_FIELDS = (
    "Attributes/VERTICAL",
    "Attributes/SPEED",
    "Attributes/SPEEDWITHBALL",
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
#: "ows"/"dws" fall back to points per game for players whose league kept no win shares.
_COMPOSITES: dict[str, tuple[tuple[str, float, bool], ...]] = {
    # Reach decides a block and the defensive record confirms it.
    "Attributes/BLOCK": (("height", 0.50, False), ("dws", 0.50, False)),
    # A steal is a quick man's play, so the body leads it: hands and first step, which
    # in this era only the frame can show. Weighted apart from perimeter defence on
    # purpose -- given one set of weights the two were the same number on every card.
    "Attributes/STEAL": (("height", 0.40, True), ("weight", 0.25, True), ("dws", 0.35, False)),
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
    "Attributes/POSTCONTROL": (("height", 0.35, False), ("weight", 0.25, False), ("ows", 0.40, False)),
    # Agility is a body field, but the defensive record moves it further than it did:
    # a quick player shows up in what his team gave up.
    "Attributes/AGILITY": (("height", 0.45, True), ("weight", 0.25, True), ("dws", 0.30, False)),
    # Post Hook and Post Fade are shot execution, so they are not blended and stretched
    # here at all -- they go on the captured pool's own fg% curve below, which is the
    # only thing that keeps them at the level the pool actually records.
}

#: What the captured pool actually pays a shot-execution attribute, as
#: ``(band signal value, p25, median, p75)`` per decile of the *band* signal, from
#: **editor_capture_001** only.
#:
#: That capture only, deliberately. Captures 002-004 are recaptures taken after
#: generated cards had been written back to the roster, so calibrating against them
#: would be reading this module's own output back in as evidence. It shows in the data:
#: median field goal percentage runs .370, .327, .304, .335 across the four, and by 004
#: the within-decile interquartile width -- the room the placement signal has to move a
#: player -- has fallen to 1.5 points on Post Fade and 2.7 on Post Hook, against 5.8
#: and 16.6 in 001. Capture 001 is the least contaminated, not clean: it is the same
#: 1947 roster, so these anchors are an earlier generation of this generator's own
#: output. They are a defensible proxy, not ground truth, and a genuine reference
#: roster would replace them.
#:
#: Only packages with at least 200 field goal attempts are used. Unfloored, the pool's
#: shooting percentage carries almost no signal -- ``r(fg%, Driving Layup)`` is +0.40
#: over all 306 packages, because the bottom decile was thirty players with a *median
#: of three attempts*, whose noise inverted the bottom of the curve where 71% of the
#: 1947 season sits. The break is a cliff rather than a slope and it sits low: the
#: correlation is +0.90 by 25 attempts and +0.91 by 150, so 200 is a conservative floor
#: on the safe side of it, not a fitted threshold. Lowering it buys nothing -- the pool
#: has no rotation player shooting below .223 at any floor.
#:
#: That last fact is the real limit here, and no threshold fixes it. The median 1947
#: player shot .267 and the season's lower quartile .220, while the floored pool's
#: lowest decile sits at .275 -- so for the two fields still banded on fg%, 60% of the
#: 1947 season is at or below the lowest shooting level the pool has any evidence for
#: and shares one clamped band. Ordering inside it comes from the placement signal,
#: which is real for Driving Layup (points per game, r=+0.68) and negligible for Post
#: Fade (height, r=+0.10) -- so Post Fade lands near-constant at about 47 for the
#: league. That is honest rather than modelled: it is what "no evidence at this
#: shooting level" looks like, and it still prevents the 99s that stretching produced.
#:
#: The band signal is whichever signal the pool says actually moves the field, and it
#: is not the same signal for all five. Close Shot and Post Hook are size fields
#: (height r=+0.60 and +0.72, against fg%'s +0.29 and +0.13), Midrange tracks
#: free-throw shooting (r=+0.93 against fg%'s +0.23), and only Driving Layup is really
#: bought with field goal percentage (+0.91). Banding all five on fg% held the whole
#: 1947 season between 42 and 57 on Post Hook -- a 6'10" Mikan scored 54 where the pool
#: pays a 6'10" player 74 -- because fg% barely moves that field and 1947 shoots low.
#:
#: These are not stretched onto 25-99. A 1947 shooter who led his league is not a 99
#: layup finisher; the pool says his percentage buys what it buys anywhere.
_SHOT_BAND_ANCHORS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "Attributes/CLOSESHOT": (
        (69.417, 46.0, 56.0, 66.5), (71.625, 46.0, 55.0, 63.2), (72.750, 55.0, 55.0, 65.0),
        (73.750, 56.5, 62.0, 65.2), (74.250, 59.0, 62.0, 65.2), (75.000, 62.0, 67.0, 76.2),
        (76.000, 62.0, 73.5, 83.0), (76.708, 65.0, 74.5, 83.0), (78.417, 69.0, 83.0, 93.2),
        (80.625, 71.8, 81.0, 95.0),
    ),
    "Attributes/POSTHOOK": (
        (69.417, 31.8, 42.0, 52.5), (71.625, 36.0, 40.5, 45.5), (72.750, 42.8, 45.5, 48.0),
        (73.750, 45.2, 50.0, 54.0), (74.250, 48.0, 50.5, 53.0), (75.000, 51.8, 55.0, 59.2),
        (76.000, 53.8, 61.5, 66.2), (76.708, 56.0, 61.0, 66.0), (78.417, 61.0, 67.5, 70.2),
        (80.625, 62.5, 68.0, 77.0),
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
    "Attributes/POSTFADE": (
        (0.275, 46.0, 47.0, 49.0), (0.318, 47.0, 50.0, 52.0), (0.336, 47.0, 49.5, 54.0),
        (0.354, 48.0, 49.5, 51.2), (0.373, 49.0, 52.5, 55.0), (0.395, 47.0, 49.0, 52.8),
        (0.418, 49.8, 53.0, 56.0), (0.450, 50.8, 52.5, 56.5), (0.487, 51.8, 53.5, 55.0),
        (0.524, 50.0, 54.5, 57.0),
    ),
}

#: field -> (band signal, placement signal, pool r for each). The band sets the range
#: the pool pays at that level of the leading signal; the placement puts the player
#: inside it on the secondary one. Post Fade is weak on both (its real driver is the
#: post-fade *tendency* at r=+0.49, and 1947 recorded no shot-location data at all), so
#: it stays narrow on purpose rather than being handed false resolution.
_SHOT_SIGNALS: dict[str, tuple[str, str, float, float]] = {
    "Attributes/CLOSESHOT": ("height", "field_goal_percent", 0.60, 0.29),
    "Attributes/POSTHOOK": ("height", "field_goal_percent", 0.72, 0.13),
    "Attributes/MIDRANGE": ("free_throw_percent", "field_goal_percent", 0.93, 0.23),
    "Attributes/DRIVINGLAYUP": ("field_goal_percent", "points_per_game", 0.91, 0.68),
    "Attributes/POSTFADE": ("field_goal_percent", "height", 0.32, 0.10),
}

#: Estimated season field goal attempts below which a player's shooting percentage is
#: not evidence about him. At 100 attempts the standard error on a .300 percentage is
#: still .046; at the three attempts the pool's unfloored bottom decile averaged it is
#: .265, which is the entire width of the era. 45% of the 1947 season falls under 200
#: attempts and 34% under 100, so this is not a rare branch -- it is a third of the
#: league, and it is why the rule has to say "unmeasured" rather than "poor".
SHOT_EVIDENCE_MIN_ATTEMPTS = 100.0

#: Fields whose win-share term is the offensive side rather than the defensive one.
_OFFENSIVE_WIN_SHARE_FIELDS = frozenset({
    "Attributes/IQSHOT",
    "Attributes/POSTCONTROL",
})

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
    if name in ("ows", "dws"):
        return scale.win_share_share(entry, population, name, from_row=from_row)
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
    rank_share = scale.share(number, scale.values_of(population, name), invert=invert)
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
_REBOUND_CACHE: dict[tuple[int, str], dict[str, float]] = {}
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


def _rebound_values(
    population: Sequence[Mapping[str, Any]],
    side: str,
) -> dict[str, float]:
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
    # The same fixed 5'3"-7'9" span the height component uses, so a roster move cannot
    # re-rank a whole league's boards. The tallest man in a short season therefore sits
    # below 99 on reach alone; the win-share spread below is what carries him the rest
    # of the way, and the top height's ladder still runs to the ceiling.
    base_by_height = {
        height: scale.ATTRIBUTE_FLOOR
        + (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR)
        * (_fixed_span_share(height, HEIGHT_SCALE_FLOOR, HEIGHT_SCALE_CEILING) or 0.0)
        for height in distinct
    }
    by_height: dict[float, list[tuple[float, str]]] = {}
    for entry in population:
        height = entry.get("height")
        player_id = str(entry.get("player_id") or "")
        if height is None or not player_id:
            continue
        weight, _signal = scale.win_share_share(entry, population, side, from_row=True)
        # Centred so "positive" means above the season's midpoint of whichever signal
        # carried the term, not above a raw zero the NBL substitute never crosses.
        by_height.setdefault(float(height), []).append(((weight - 0.5) if weight is not None else 0.0, player_id))

    resolved: dict[str, float] = {}
    for height, members in by_height.items():
        base = base_by_height[height]
        index = distinct.index(height)
        upper = base_by_height[distinct[index + 1]] if index + 1 < len(distinct) else scale.ATTRIBUTE_CEILING
        lower = base_by_height[distinct[index - 1]] if index > 0 else scale.ATTRIBUTE_FLOOR
        positives = sorted((item for item in members if item[0] > 0.0), key=lambda item: item[0])
        negatives = sorted((item for item in members if item[0] < 0.0), key=lambda item: -item[0])
        neutral = [item for item in members if item[0] == 0.0]
        for player_id in (item[1] for item in neutral):
            resolved[player_id] = base
        for rank, (_weight, player_id) in enumerate(positives, start=1):
            step = rank / (len(positives) + 1)
            resolved[player_id] = base + (upper - base) * step
        for rank, (_weight, player_id) in enumerate(negatives, start=1):
            step = rank / (len(negatives) + 1)
            resolved[player_id] = base - (base - lower) * step

    # The fixed span decides the order; this puts that order on the range the captured
    # pool actually occupies. Both rebound attributes run the full 25-99 there -- min
    # 25, median 55, max 99, with height the dominant driver at r=0.82 -- so a season
    # should use the whole scale even though nobody in it is 7'9". Ordering still comes
    # from the fixed span, so a new extreme re-ranks nobody.
    ordered = sorted(resolved.values())
    if len(ordered) >= 2 and ordered[-1] > ordered[0]:
        low_value, high_value = ordered[0], ordered[-1]
        span = high_value - low_value
        resolved = {
            player_id: scale.ATTRIBUTE_FLOOR
            + (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR) * ((value - low_value) / span)
            for player_id, value in resolved.items()
        }
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


def _player_id(evidence: Any) -> str:
    value = getattr(evidence, "player_id", None)
    if not value:
        identity = getattr(evidence, "identity", None)
        if isinstance(identity, Mapping):
            value = identity.get("player_id")
    return str(value or "").strip().upper()


def _is_small_handler(evidence: Any) -> bool:
    height = scale.evidence_signal(evidence, "height")
    return height is not None and height < SMALL_HANDLER_HEIGHT


def _made_no_field_goals(evidence: Any) -> bool:
    made = scale.evidence_signal(evidence, "field_goals_made")
    return made is not None and made <= 0.0


def apply_pre_1952_ratings(evidence: Any, values: dict[str, Any]) -> dict[str, Any]:
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
    player_id = _player_id(evidence)
    season_info = getattr(evidence, "season_info", {}) or {}
    league = str(season_info.get("lg") or "").strip().upper()

    def write(
        field_key: str,
        number: float,
        rule: str,
        keys: tuple[str, ...],
        *,
        lowering_cap: bool = False,
    ) -> None:
        current = updated.get(field_key)
        if current is None:
            return
        # A protected value is a finding this pass must not re-derive. A cap is not a
        # re-derivation: it only ever lowers, so it may still apply on top of one. The
        # 1949 NBL midrange leader was pinned by the BAA centre cap at 72 -- above the
        # best midrange shooter in the BAA -- and protection alone left him there.
        if _is_protected(current) and not (
            lowering_cap and isinstance(current.value, (int, float)) and number < float(current.value)
        ):
            return
        value = int(round(max(scale.ATTRIBUTE_FLOOR, min(scale.ATTRIBUTE_CEILING, number))))
        provenance = keys + (
            "pre_1952_scale_scope=same_season_all_leagues",
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
        side = "ows" if field_key in _OFFENSIVE_WIN_SHARE_FIELDS else "dws"
        resolved = tuple(
            (side if name in ("ows", "dws") else name, weight, invert)
            for name, weight, invert in components
        )
        blended, signals = _composite_for(evidence, population, resolved, from_row=False)
        if blended is None:
            continue
        spread = _population_composite(population, resolved)
        value = scale.stretch(blended, spread)
        if value is None:
            continue
        write(
            field_key,
            value,
            f"pre_1952_{field_key.split('/')[-1].lower()}_authored_fallback",
            tuple(f"pre_1952_component={signal}" for signal in signals)
            + (f"pre_1952_composite_share={blended:.8f}",),
        )

    # --- rebounding: height first, win shares inside the height ------------------
    for field_key, side in (("Attributes/OFFENSIVEREBOUND", "ows"), ("Attributes/DEFENSEREBOUND", "dws")):
        if field_key not in updated or not player_id:
            continue
        resolved_rebounds = _rebound_values(population, side)
        value = resolved_rebounds.get(player_id)
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

    # --- draw foul: a real zero at the bottom ------------------------------------
    if "Attributes/DRAWFOUL" in updated:
        value = scale.stretch(
            scale.evidence_signal(evidence, _DRAW_FOUL_SIGNAL),
            scale.values_of(population, _DRAW_FOUL_SIGNAL),
            low_anchor=0.0,
        )
        if value is not None:
            write(
                "Attributes/DRAWFOUL",
                value,
                "pre_1952_drawfoul_free_throws_per_game",
                ("pre_1952_component=ft_per_game", "pre_1952_low_anchor=0_free_throws_is_25"),
            )

    # --- intangibles: NBL only, on the three totals the league kept ---------------
    if league == "NBL" and "Attributes/INTANGIBLES" in updated:
        blended, signals = _composite_for(evidence, population, _NBL_INTANGIBLES, from_row=False)
        if blended is not None:
            spread = _population_composite(population, _NBL_INTANGIBLES, league="NBL")
            value = scale.stretch(blended, spread)
            if value is not None:
                write(
                    "Attributes/INTANGIBLES",
                    value,
                    "pre_1952_nbl_intangibles_recorded_totals",
                    tuple(f"pre_1952_component={signal}" for signal in signals)
                    + ("pre_1952_intangibles_scope=NBL_only", f"pre_1952_composite_share={blended:.8f}"),
                )

    # --- restretched body fields --------------------------------------------------
    distributions = scale.field_distributions(evidence)
    for field_key in RESTRETCHED_FIELDS:
        current = updated.get(field_key)
        spread = distributions.get(field_key)
        if current is None or not spread or not isinstance(current.value, (int, float)):
            continue
        value = scale.stretch(float(current.value), spread)
        if value is None:
            continue
        write(
            field_key,
            value,
            f"{current.source_rule}_pre_1952_season_stretch",
            ("pre_1952_stretch=season_min_to_25_season_max_to_99",),
        )

    # --- hustle: the season's top twenty-five stand at the ceiling ----------------
    hustle = updated.get("Attributes/HUSTLE")
    hustle_spread = distributions.get("Attributes/HUSTLE")
    if hustle is not None and hustle_spread and isinstance(hustle.value, (int, float)):
        if len(hustle_spread) >= HUSTLE_CEILING_PLAYERS:
            threshold = hustle_spread[-HUSTLE_CEILING_PLAYERS]
            if float(hustle.value) >= threshold:
                write(
                    "Attributes/HUSTLE",
                    scale.ATTRIBUTE_CEILING,
                    f"{hustle.source_rule}_pre_1952_season_ceiling",
                    (
                        f"pre_1952_hustle_ceiling_players={HUSTLE_CEILING_PLAYERS}",
                        f"pre_1952_hustle_ceiling_threshold={threshold:.8f}",
                        "pre_1952_hustle_ties=a_tie_on_the_threshold_keeps_every_tied_player",
                    ),
                )

    # --- small men handled the ball -----------------------------------------------
    if _is_small_handler(evidence):
        height = scale.evidence_signal(evidence, "height")
        for field_key in SMALL_HANDLER_FIELDS:
            current = updated.get(field_key)
            if current is None or not isinstance(current.value, (int, float)):
                continue
            if float(current.value) >= SMALL_HANDLER_FLOOR:
                continue
            lifted = SMALL_HANDLER_FLOOR + (scale.ATTRIBUTE_CEILING - SMALL_HANDLER_FLOOR) * (
                (float(current.value) - scale.ATTRIBUTE_FLOOR)
                / (scale.ATTRIBUTE_CEILING - scale.ATTRIBUTE_FLOOR)
            )
            write(
                field_key,
                lifted,
                f"{current.source_rule}_pre_1952_small_handler_floor",
                (
                    f"pre_1952_small_handler_band={SMALL_HANDLER_FLOOR:.0f}_to_99",
                    f"pre_1952_small_handler_height_under={SMALL_HANDLER_HEIGHT:.0f}",
                    f"identity.ht_in_in={height:.0f}" if height is not None else "identity.ht_in_in",
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
    "RESTRETCHED_FIELDS",
    "SMALL_HANDLER_FIELDS",
    "SMALL_HANDLER_FLOOR",
    "SMALL_HANDLER_HEIGHT",
    "ZERO_MAKE_FLOOR_FIELDS",
    "apply_pre_1952_ratings",
]
