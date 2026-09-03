"""Population-level diagnostics for generated season cards.

Every rule in the generator is validated one field at a time. Nothing checked what
the rules produce *as a population*, which is how a season could ship with 45
constant fields, five bit-identical field pairs and a failing documented benchmark
while the whole test suite passed.

This module runs a real season through ``generate_player_proposals_from_index`` and
measures the result:

  * :func:`ranking_benchmark` implements ``Docs/1947 PlayerGen Ranking Benchmark.md``
    exactly -- the eligible-BAA population, the three win-share magnitude
    reproductions, and the named-NBL floor against Bob Feerick.
  * :func:`population_shape` reports constant fields, bit-identical field pairs,
    fields missing from some cards, and the effective dimensionality of the card.

Both are diagnostic. Nothing here feeds back into a proposal; production values are
never post-processed to satisfy a benchmark.

Standard library only, matching the rest of the repository.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence

ATTRIBUTE_SECTION = "Attributes"
OFFENSE_GROUP = "Offense"
DEFENSE_GROUP = "Defense"
DURABILITY_GROUP = "Durability"


# ---------------------------------------------------------------------------
# Constant-field contract
#
# A field that never varies across a season is either a deliberate era statement
# or a defect. The difference has to be written down, not inferred from the value.
# ---------------------------------------------------------------------------

#: Actions that did not exist in the era. Constant is the correct output.
ERA_GATE_CONSTANT_FIELDS: frozenset[str] = frozenset({
    # No three-point line before 1968 (ABA) / 1980 (NBA).
    "Attributes/3POINT",
    "Tendencies/3POINTCENTERLEFTSHOT",
    "Tendencies/3POINTCENTERRIGHTSHOT",
    "Tendencies/3POINTCENTERSHOT",
    "Tendencies/3POINTLEFTSHOT",
    "Tendencies/3POINTOFFSCREENSHOT",
    "Tendencies/3POINTRIGHTSHOT",
    "Tendencies/3POINTSHOT",
    "Tendencies/3POINTSPOTUPSHOT",
    "Tendencies/CONTESTEDJUMPER3POINT",
    "Tendencies/DRIVEPULLUP3POINT",
    "Tendencies/STEPBACKJUMPER3POINT",
    "Tendencies/TRANSITIONPULLUP3POINT",
    # Dribble moves postdating the era, gated by historical_introduction_gate.
    "Tendencies/DRIBBLECROSSOVER",
    "Tendencies/DRIBBLESPIN",
    "Tendencies/DRIVINGDOUBLECROSSOVER",
    "Tendencies/DRIVINGHALFSPIN",
    "Tendencies/DRIVINGINANDOUT",
    "Tendencies/DRIVINGSTEPBACK",
    "Tendencies/EUROSTEPLAYUP",
    "Tendencies/HOPSTEPLAYUP",
    "Tendencies/SETUPWITHSIZEUP",
})

#: Fields that used to be excused for defaulting every player to one number. They
#: are NOT excused: a rating the whole league shares carries no information and
#: still occupies space in every total. Listed here only so the guard's failure
#: message can name what kind of default each one was.
FORMERLY_EXCUSED_CONSTANT_FIELDS: frozenset[str] = frozenset({
    # derive_tendency_hardfoul_universal_pre_1960_maximum.
    "Tendencies/HARDFOUL",
    # gp_valid_pool_stamina_median_90, with games played available and unused.
    "Attributes/STAMINA",
    # Collapsed to a floor by the pre-shot-clock era playstyle pass.
    "Tendencies/ALLEYOOP",
    "Tendencies/POSTFACEUP",
    "Tendencies/POSTSPIN",
    # durability.default_90_pending_injury_database.
    "Attributes/BACKDURABILITY",
    "Attributes/HEADDURABILITY",
    "Attributes/LEFTANKLEDURABILITY",
    "Attributes/LEFTELBOWDURABILITY",
    "Attributes/LEFTFOOTDURABILITY",
    "Attributes/LEFTHANDDURABILITY",
    "Attributes/LEFTHIPDURABILITY",
    "Attributes/LEFTKNEEDURABILITY",
    "Attributes/LEFTSHOULDERDURABILITY",
    "Attributes/MISCDURABILITY",
    "Attributes/NECKDURABILITY",
    "Attributes/RIGHTANKLEDURABILITY",
    "Attributes/RIGHTELBOWDURABILITY",
    "Attributes/RIGHTFOOTDURABILITY",
    "Attributes/RIGHTHANDDURABILITY",
    "Attributes/RIGHTHIPDURABILITY",
    "Attributes/RIGHTKNEEDURABILITY",
    "Attributes/RIGHTSHOULDERDURABILITY",
})

#: The only excuse for a rating field never varying: the action did not exist yet.
#: Nothing else may default the whole league to one number -- not a placeholder
#: awaiting a data source, not an authored era regime, not an era pass that scaled
#: a field flat. Every one of those is a field carrying no information.
ALLOWED_CONSTANT_FIELDS: frozenset[str] = ERA_GATE_CONSTANT_FIELDS

#: Groups of fields that intentionally carry one derived value written to several
#: keys. Two fields matching each other is only acceptable inside one of these.
DECLARED_MIRROR_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"Tendencies/POSTFADELEFT", "Tendencies/POSTFADERIGHT"}),
    frozenset({"Tendencies/POSTHOOKLEFT", "Tendencies/POSTHOOKRIGHT"}),
    # Storage aliases: the layout carries two offsets for one action, and the rules
    # say so themselves ("this storage alias uses the same field-specific action rule
    # and Pool scale as ...").
    frozenset({"Tendencies/CONTESTEDJUMPERMID", "Tendencies/CONTESTEDJUMPERMIDRANGE"}),
    frozenset({"Tendencies/DRIVEPULLUPMID", "Tendencies/DRIVEPULLUPMIDRANGE"}),
    # Not aliases -- two real zones that public data cannot separate. Both rules
    # record the limitation ("public data has no laterality split"), so both read the
    # same midrange share and land on the same number. Splitting them would be
    # invention, not measurement.
    frozenset({
        "Tendencies/MIDRIGHTSHOT",
        "Tendencies/CENTERMIDRIGHTSHOT",
        "Tendencies/CENTERMIDSHOT",
    }),
    # Durability carries two joint patterns -- guard ankle wear with age, and knee
    # and foot load at seven feet and beyond -- so ankles, knees and feet each sit
    # apart from the body-wide value. Within a pattern the two sides match: nothing
    # in the sources distinguishes a left ankle from a right one.
    frozenset({"Attributes/LEFTANKLEDURABILITY", "Attributes/RIGHTANKLEDURABILITY"}),
    frozenset({"Attributes/LEFTKNEEDURABILITY", "Attributes/RIGHTKNEEDURABILITY"}),
    frozenset({"Attributes/LEFTFOOTDURABILITY", "Attributes/RIGHTFOOTDURABILITY"}),
    # Knees and feet share one pattern, so they match each other too.
    frozenset({
        "Attributes/LEFTKNEEDURABILITY",
        "Attributes/RIGHTKNEEDURABILITY",
        "Attributes/LEFTFOOTDURABILITY",
        "Attributes/RIGHTFOOTDURABILITY",
    }),
    # The joints no source distinguishes stay on the body-wide value.
    frozenset({
        "Attributes/BACKDURABILITY",
        "Attributes/HEADDURABILITY",
        "Attributes/LEFTELBOWDURABILITY",
        "Attributes/LEFTHANDDURABILITY",
        "Attributes/LEFTHIPDURABILITY",
        "Attributes/LEFTSHOULDERDURABILITY",
        "Attributes/MISCDURABILITY",
        "Attributes/NECKDURABILITY",
        "Attributes/RIGHTELBOWDURABILITY",
        "Attributes/RIGHTHANDDURABILITY",
        "Attributes/RIGHTHIPDURABILITY",
        "Attributes/RIGHTSHOULDERDURABILITY",
    }),
)


def _is_declared_mirror(left: str, right: str) -> bool:
    return any({left, right} <= group for group in DECLARED_MIRROR_GROUPS)


# ---------------------------------------------------------------------------
# Season population
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeasonCard:
    """One generated proposal reduced to what a population check needs."""

    player_id: str
    team: str
    name: str
    league: str
    games: float | None
    points_per_game: float | None
    field_goal_percent: float | None
    offensive_win_shares: float | None
    defensive_win_shares: float | None
    win_shares: float | None
    position: str
    height_inches: float | None
    values: dict[str, Any]
    groups: dict[str, tuple[str, str]]

    def numeric_items(self) -> Iterable[tuple[str, float]]:
        for key, value in self.values.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                yield key, float(value)

    def attribute_total(self, group: str | None = None, *, exclude_groups: Sequence[str] = ()) -> float:
        total = 0.0
        for key, value in self.numeric_items():
            placement = self.groups.get(key)
            if placement is None or placement[0] != ATTRIBUTE_SECTION:
                continue
            if group is not None and placement[1] != group:
                continue
            if placement[1] in exclude_groups:
                continue
            total += value
        return total


def season_cards(season: int, *, selected_league: str = "All leagues") -> tuple[SeasonCard, ...]:
    """Generate a full season through the real proposal path."""

    from player_generator import generate_player_proposals_from_index, season_context_index

    context = season_context_index(season, selected_league=selected_league)
    batch = generate_player_proposals_from_index(context)
    cards: list[SeasonCard] = []
    for proposal in batch.proposals:
        evidence = context.evidence_for(player_id=proposal.player_id, team=proposal.team)
        cards.append(
            SeasonCard(
                player_id=str(proposal.player_id),
                team=str(proposal.team),
                name=str(evidence.identity.get("player") or ""),
                league=str(evidence.season_info.get("lg") or "").strip().upper(),
                games=_number(evidence.per_game.get("g")),
                points_per_game=_number(evidence.per_game.get("pts_per_game")),
                field_goal_percent=_number(evidence.per_game.get("fg_percent")),
                offensive_win_shares=_number(evidence.advanced.get("ows")),
                defensive_win_shares=_number(evidence.advanced.get("dws")),
                win_shares=_number(evidence.advanced.get("ws")),
                position=str(evidence.season_info.get("pos") or evidence.identity.get("pos") or "").strip().upper(),
                height_inches=_number(evidence.identity.get("ht_in_in")),
                values={c.field_key: c.display_value for c in proposal.field_candidates},
                groups={c.field_key: (c.section, c.group) for c in proposal.field_candidates},
            )
        )
    return tuple(cards)


@lru_cache(maxsize=4)
def cached_season_cards(season: int, selected_league: str = "All leagues") -> tuple[SeasonCard, ...]:
    """Season cards memoised for repeated diagnostic passes in one process."""

    return season_cards(season, selected_league=selected_league)


# ---------------------------------------------------------------------------
# Rank statistics
# ---------------------------------------------------------------------------

def normalised_shares(values: Sequence[float]) -> tuple[float, ...]:
    """Min-max shares in 0..1, which keep the gaps between values intact.

    Feerick's 18.6, Fulks' 16.3 and Sadowski's 11.8 become 1.000, 0.895 and 0.691 --
    the spacing a rank throws away by calling them first, second and third.
    """

    if not values:
        return ()
    low = min(values)
    high = max(values)
    span = high - low
    if span <= 0.0:
        return tuple(0.0 for _ in values)
    return tuple((value - low) / span for value in values)


def magnitude_error(generated: Sequence[float], referenced: Sequence[float]) -> tuple[float, float]:
    """Mean and worst absolute gap between two value sets, compared as shares."""

    if len(generated) != len(referenced) or not generated:
        return 0.0, 0.0
    left = normalised_shares(generated)
    right = normalised_shares(referenced)
    deltas = [abs(a - b) for a, b in zip(left, right)]
    return sum(deltas) / len(deltas), max(deltas)


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


# ---------------------------------------------------------------------------
# Ranking benchmark -- Docs/1947 PlayerGen Ranking Benchmark.md
# ---------------------------------------------------------------------------

#: Bob Feerick is the BAA reference; the rest are the named NBL floor population.
BENCHMARK_BAA_REFERENCE_PLAYER_ID = "feeribo01"
BENCHMARK_NBL_FLOOR_PLAYER_IDS: tuple[str, ...] = (
    "mikange01",
    "mcderro01",
    "daviebo01",
    "lewisfr01",
    "cervial01",
    "tidriha01",
    "risenar01",
    "holzmre01",
    "carpebo01",
    "calihro01",
)


@dataclass(frozen=True)
class MagnitudeCheck:
    """How closely a generated total reproduces a win-share magnitude, not its rank.

    A rank correlation cannot see that Feerick is 2.3 win shares clear of Fulks and
    Fulks 4.5 clear of Sadowski. Both sides are min-max normalised to shares of their
    own league, so the gaps survive and the error is directly readable: 0.05 means the
    average player's card sits five per cent of the league's range away from where his
    win shares put him.
    """

    label: str
    reference: str
    population: int
    mean_share_error: float
    worst_share_error: float


@dataclass(frozen=True)
class FloorCheck:
    player_id: str
    name: str
    generated_total: float
    reference_total: float

    @property
    def delta(self) -> float:
        return self.generated_total - self.reference_total

    @property
    def passed(self) -> bool:
        return self.generated_total >= self.reference_total


@dataclass(frozen=True)
class BenchmarkReport:
    season: int
    eligible_baa: int
    offense: MagnitudeCheck
    defense: MagnitudeCheck
    total: MagnitudeCheck
    reference_total: float
    floors: tuple[FloorCheck, ...]

    @property
    def floors_passed(self) -> int:
        return sum(1 for floor in self.floors if floor.passed)


def eligible_baa_cards(cards: Sequence[SeasonCard]) -> tuple[SeasonCard, ...]:
    """G > 10 with recorded OWS, DWS and WS, per the benchmark's exact wording."""

    return tuple(
        card
        for card in cards
        if card.league == "BAA"
        and card.games is not None
        and card.games > 10
        and card.offensive_win_shares is not None
        and card.defensive_win_shares is not None
        and card.win_shares is not None
    )


def _magnitude_check(
    label: str,
    reference: str,
    generated: Sequence[float],
    referenced: Sequence[float],
) -> MagnitudeCheck:
    mean_error, worst_error = magnitude_error(generated, referenced)
    return MagnitudeCheck(
        label=label,
        reference=reference,
        population=len(generated),
        mean_share_error=mean_error,
        worst_share_error=worst_error,
    )


def ranking_benchmark(
    cards: Sequence[SeasonCard],
    *,
    season: int = 1947,
    exclude_groups: Sequence[str] = (),
) -> BenchmarkReport:
    """Run the documented benchmark over an already-generated season."""

    eligible = eligible_baa_cards(cards)
    offense = _magnitude_check(
        "Attributes/Offense",
        "OWS",
        [c.attribute_total(OFFENSE_GROUP) for c in eligible],
        [float(c.offensive_win_shares or 0.0) for c in eligible],
    )
    defense = _magnitude_check(
        "Attributes/Defense",
        "DWS",
        [c.attribute_total(DEFENSE_GROUP) for c in eligible],
        [float(c.defensive_win_shares or 0.0) for c in eligible],
    )
    total = _magnitude_check(
        "Attributes",
        "WS",
        [c.attribute_total(exclude_groups=exclude_groups) for c in eligible],
        [float(c.win_shares or 0.0) for c in eligible],
    )

    by_player = {card.player_id: card for card in cards}
    reference_card = by_player.get(BENCHMARK_BAA_REFERENCE_PLAYER_ID)
    reference_total = (
        reference_card.attribute_total(exclude_groups=exclude_groups) if reference_card else 0.0
    )
    floors: list[FloorCheck] = []
    for player_id in BENCHMARK_NBL_FLOOR_PLAYER_IDS:
        card = by_player.get(player_id)
        if card is None:
            continue
        floors.append(
            FloorCheck(
                player_id=player_id,
                name=card.name,
                generated_total=card.attribute_total(exclude_groups=exclude_groups),
                reference_total=reference_total,
            )
        )
    return BenchmarkReport(
        season=season,
        eligible_baa=len(eligible),
        offense=offense,
        defense=defense,
        total=total,
        reference_total=reference_total,
        floors=tuple(floors),
    )


# ---------------------------------------------------------------------------
# Population shape
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PopulationShape:
    season: int
    players: int
    numeric_fields: int
    numeric_field_keys: tuple[str, ...]
    constant_fields: dict[str, float]
    undeclared_constant_fields: dict[str, float]
    identical_field_pairs: tuple[tuple[str, str], ...]
    undeclared_identical_pairs: tuple[tuple[str, str], ...]
    missing_field_counts: dict[str, int]
    varying_fields: int
    effective_rank: int


#: Rating sections. Vitals carry identity, not ratings, and are not shape-checked.
RATING_SECTIONS: tuple[str, ...] = (ATTRIBUTE_SECTION, "Tendencies")


def _numeric_field_keys(cards: Sequence[SeasonCard], sections: Sequence[str]) -> tuple[str, ...]:
    keys: dict[str, None] = {}
    for card in cards:
        for key, _value in card.numeric_items():
            placement = card.groups.get(key)
            if placement is None or placement[0] not in sections:
                continue
            keys.setdefault(key, None)
    return tuple(keys)


def population_shape(
    cards: Sequence[SeasonCard],
    *,
    season: int,
    variance: float = 0.90,
    sections: Sequence[str] = RATING_SECTIONS,
) -> PopulationShape:
    keys = _numeric_field_keys(cards, sections)
    columns: dict[str, list[float]] = {}
    missing: dict[str, int] = {}
    for key in keys:
        column: list[float] = []
        absent = 0
        for card in cards:
            value = card.values.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                absent += 1
                continue
            column.append(float(value))
        columns[key] = column
        if absent:
            missing[key] = absent

    constant: dict[str, float] = {}
    for key, column in columns.items():
        if column and len(set(column)) == 1:
            constant[key] = column[0]
    undeclared_constant = {k: v for k, v in constant.items() if k not in ALLOWED_CONSTANT_FIELDS}

    complete = [key for key in keys if key not in missing and key not in constant]
    identical: list[tuple[str, str]] = []
    for index, left in enumerate(complete):
        for right in complete[index + 1:]:
            if columns[left] == columns[right]:
                identical.append((left, right))
    undeclared_identical = tuple(
        pair for pair in identical if not _is_declared_mirror(*pair)
    )

    return PopulationShape(
        season=season,
        players=len(cards),
        numeric_fields=len(keys),
        numeric_field_keys=keys,
        constant_fields=constant,
        undeclared_constant_fields=undeclared_constant,
        identical_field_pairs=tuple(identical),
        undeclared_identical_pairs=undeclared_identical,
        missing_field_counts=missing,
        varying_fields=len(complete),
        effective_rank=_effective_rank([columns[key] for key in complete], variance),
    )


def _effective_rank(columns: Sequence[Sequence[float]], variance: float) -> int:
    """Principal components needed to reach ``variance`` of standardised variance."""

    if len(columns) < 2:
        return len(columns)
    standardised: list[list[float]] = []
    for column in columns:
        mean = sum(column) / len(column)
        spread = math.sqrt(sum((v - mean) ** 2 for v in column) / len(column))
        if spread == 0.0:
            continue
        standardised.append([(v - mean) / spread for v in column])
    width = len(standardised)
    if width < 2:
        return width
    rows = len(standardised[0])
    correlation = [
        [sum(standardised[i][r] * standardised[j][r] for r in range(rows)) / rows for j in range(width)]
        for i in range(width)
    ]
    eigenvalues = sorted(_jacobi_eigenvalues(correlation), reverse=True)
    total = sum(eigenvalues)
    if total <= 0.0:
        return width
    running = 0.0
    for count, value in enumerate(eigenvalues, start=1):
        running += value
        if running / total >= variance:
            return count
    return width


def _jacobi_eigenvalues(matrix: list[list[float]], *, sweeps: int = 60) -> list[float]:
    """Eigenvalues of a symmetric matrix by cyclic Jacobi rotation."""

    size = len(matrix)
    work = [row[:] for row in matrix]
    for _sweep in range(sweeps):
        off = math.sqrt(sum(work[i][j] ** 2 for i in range(size) for j in range(size) if i != j))
        if off < 1e-9:
            break
        for p in range(size - 1):
            for q in range(p + 1, size):
                if abs(work[p][q]) < 1e-12:
                    continue
                theta = (work[q][q] - work[p][p]) / (2.0 * work[p][q])
                sign = 1.0 if theta >= 0.0 else -1.0
                t = sign / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(size):
                    akp = work[k][p]
                    akq = work[k][q]
                    work[k][p] = c * akp - s * akq
                    work[k][q] = s * akp + c * akq
                for k in range(size):
                    apk = work[p][k]
                    aqk = work[q][k]
                    work[p][k] = c * apk - s * aqk
                    work[q][k] = s * apk + c * aqk
    return [work[i][i] for i in range(size)]


# ---------------------------------------------------------------------------
# Cross-league parity
# ---------------------------------------------------------------------------

def top_players(
    cards: Sequence[SeasonCard],
    field_key: str,
    *,
    count: int = 9,
) -> tuple[tuple[float, str, str, str], ...]:
    """Highest values for one field: (value, name, league, position family).

    The calibration review reads a season this way -- the top of each attribute is
    where a miscalibrated rule shows itself, because that is where the wrong player
    type surfaces.
    """

    ranked = [
        (float(card.values[field_key]), card.name, card.league, card.position or "")
        for card in cards
        if isinstance(card.values.get(field_key), (int, float))
        and not isinstance(card.values.get(field_key), bool)
    ]
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return tuple(ranked[:count])


def league_medians(cards: Sequence[SeasonCard], field_key: str) -> dict[str, float]:
    """Median of one field per league, for data-availability bias checks."""

    buckets: dict[str, list[float]] = {}
    for card in cards:
        value = card.values.get(field_key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        buckets.setdefault(card.league, []).append(float(value))
    return {league: median(values) for league, values in buckets.items()}


def league_median_gap(cards: Sequence[SeasonCard], field_key: str, left: str, right: str) -> float | None:
    medians = league_medians(cards, field_key)
    if left not in medians or right not in medians:
        return None
    return medians[left] - medians[right]


def evidence_correlation(cards: Sequence[SeasonCard], league: str, first: str, second: str) -> float | None:
    """How closely two evidence statistics move together inside one league.

    Compared as min-max shares so the gaps between values count, which is the whole
    point: the FG% imputation check needs to see that a scoring leader is far clear of
    the pack, not merely ahead of it.
    """

    pairs = [
        (float(getattr(card, first)), float(getattr(card, second)))
        for card in cards
        if card.league == league
        and getattr(card, first) is not None
        and getattr(card, second) is not None
    ]
    if len(pairs) < 2:
        return None
    left = normalised_shares([p[0] for p in pairs])
    right = normalised_shares([p[1] for p in pairs])
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left) * sum((b - mean_right) ** 2 for b in right)
    )
    return numerator / denominator if denominator > 0.0 else 0.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
