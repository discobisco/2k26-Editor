from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
REPO_DIR = GENERATOR_DIR.parents[1]
for path in (REPO_DIR, GENERATOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from player_generation_1947_alignment import (  # type: ignore[import-not-found]
    ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS,
    align_pre_per_proposals,
)
from player_generator import GeneratedPlayerFieldCandidate, GeneratedPlayerProposal  # type: ignore[import-not-found]
from player_rules_offense import _recorded_assists_available  # type: ignore[import-not-found]


def _candidate(
    field_key: str,
    value: int,
    *,
    group: str,
    ordinal: int,
    source_rule: str = "original_rule",
) -> GeneratedPlayerFieldCandidate:
    return GeneratedPlayerFieldCandidate(
        domain="Players",
        section="Attributes",
        group=group,
        normalized_name=field_key.rsplit("/", 1)[-1],
        display_name=field_key.rsplit("/", 1)[-1],
        field_key=field_key,
        display_value=value,
        source_rule=source_rule,
        evidence_keys=("original_evidence",),
        ordinal=ordinal,
    )


def _proposal(
    player_id: str,
    team: str,
    *,
    mapped_value: int,
    season: int = 1947,
    hands_rule: str = "required_active_field_set_value",
) -> GeneratedPlayerProposal:
    mapped_fields = (
        ("Attributes/FREETHROW", "Offense"),
        ("Attributes/CLOSESHOT", "Offense"),
        ("Attributes/BALLCONTROL", "Offense"),
        ("Attributes/PASSACCURACY", "Offense"),
        ("Attributes/INTERIORDEFENSE", "Defense"),
        ("Attributes/PERIMETERDEFENSE", "Defense"),
        ("Attributes/BLOCK", "Defense"),
        ("Attributes/STEAL", "Defense"),
        ("Attributes/PASSPERCEPTION", "Defense"),
        ("Attributes/SPEED", "Athleticism"),
        ("Attributes/STAMINA", "Athleticism"),
        ("Attributes/INTANGIBLES", "Mental"),
        ("Attributes/OFFENSIVEREBOUND", "Rebounding"),
        ("Attributes/DEFENSIVEREBOUND", "Rebounding"),
    )
    candidates = [
        _candidate(field_key, mapped_value, group=group, ordinal=ordinal)
        for ordinal, (field_key, group) in enumerate(mapped_fields)
    ]
    candidates.extend(
        (
            _candidate("Attributes/3POINT", 25, group="Offense", ordinal=20),
            _candidate("Attributes/HANDS", 25, group="Mental", ordinal=21, source_rule=hands_rule),
            _candidate(
                "Attributes/HUSTLE",
                25,
                group="Mental",
                ordinal=22,
                source_rule="required_active_field_set_value",
            ),
            _candidate(
                "Attributes/POTENTIAL",
                25,
                group="Misc",
                ordinal=23,
                source_rule="required_active_field_set_value",
            ),
            _candidate(
                "Attributes/CACHCEDOVR",
                25,
                group="Misc",
                ordinal=24,
                source_rule="required_active_field_set_value",
            ),
            _candidate(
                "Attributes/MAXOVR",
                25,
                group="Misc",
                ordinal=25,
                source_rule="required_active_field_set_value",
            ),
            _candidate(
                "Attributes/MINOVR",
                25,
                group="Misc",
                ordinal=26,
                source_rule="required_active_field_set_value",
            ),
        )
    )
    return GeneratedPlayerProposal(
        player_id=player_id,
        season=season,
        team=team,
        identity={"player": player_id},
        field_candidates=tuple(candidates),
    )


def _evidence(*, fg_percent: float, ows: float, dws: float, ws: float, league: str = "BAA") -> SimpleNamespace:
    return SimpleNamespace(
        season_info={"lg": league},
        per_game={"g": 20, "fg_percent": fg_percent, "x3pa_per_game": 0.0},
        advanced={"ows": ows, "dws": dws, "ws": ws},
    )


def test_alignment_changes_only_allowlisted_underdetermined_attributes() -> None:
    assert ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS == frozenset({"Attributes/HANDS", "Attributes/HUSTLE"})
    proposals = (
        _proposal("a", "AAA", mapped_value=30),
        _proposal("b", "BBB", mapped_value=80),
    )
    evidence = {
        ("A", "AAA"): _evidence(fg_percent=0.500, ows=5.0, dws=3.0, ws=8.0),
        ("B", "BBB"): _evidence(fg_percent=0.300, ows=1.0, dws=1.0, ws=2.0),
    }

    aligned = align_pre_per_proposals(proposals, evidence)

    original = proposals[0].by_field_key()
    adjusted = aligned[0].by_field_key()
    changed = {
        field_key
        for field_key, candidate in adjusted.items()
        if candidate.display_value != original[field_key].display_value
    }
    assert changed == ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS
    for field_key, candidate in adjusted.items():
        if field_key in ALIGNMENT_ADJUSTABLE_ATTRIBUTE_KEYS:
            assert candidate.source_rule == "pre_per_1947_1951_rank_alignment"
            continue
        assert candidate == original[field_key]


def test_formula_authored_allowlisted_field_is_protected() -> None:
    proposals = (
        _proposal("a", "AAA", mapped_value=30, hands_rule="derive_attribute_hands"),
        _proposal("b", "BBB", mapped_value=80),
    )
    evidence = {
        ("A", "AAA"): _evidence(fg_percent=0.500, ows=5.0, dws=3.0, ws=8.0),
        ("B", "BBB"): _evidence(fg_percent=0.300, ows=1.0, dws=1.0, ws=2.0),
    }

    aligned = align_pre_per_proposals(proposals, evidence)

    hands = aligned[0].by_field_key()["Attributes/HANDS"]
    assert hands.display_value == 25
    assert hands.source_rule == "derive_attribute_hands"
    assert aligned[0].by_field_key()["Attributes/HUSTLE"].display_value > 25


def test_1951_nba_uses_only_narrow_underdetermined_alignment() -> None:
    proposals = (
        _proposal("a", "AAA", mapped_value=30, season=1951),
        _proposal("b", "BBB", mapped_value=80, season=1951),
    )
    evidence = {
        ("A", "AAA"): _evidence(fg_percent=0.500, ows=5.0, dws=3.0, ws=8.0, league="NBA"),
        ("B", "BBB"): _evidence(fg_percent=0.300, ows=1.0, dws=1.0, ws=2.0, league="NBA"),
    }

    aligned = align_pre_per_proposals(proposals, evidence)

    assert aligned[0].by_field_key()["Attributes/HANDS"].display_value > 25
    assert aligned[0].by_field_key()["Attributes/BALLCONTROL"].display_value == 30
    assert aligned[1].by_field_key()["Attributes/BALLCONTROL"].display_value == 80


def test_1952_nba_does_not_use_pre_per_alignment() -> None:
    proposals = (
        _proposal("a", "AAA", mapped_value=30, season=1952),
        _proposal("b", "BBB", mapped_value=80, season=1952),
    )
    evidence = {
        ("A", "AAA"): _evidence(fg_percent=0.500, ows=5.0, dws=3.0, ws=8.0, league="NBA"),
        ("B", "BBB"): _evidence(fg_percent=0.300, ows=1.0, dws=1.0, ws=2.0, league="NBA"),
    }

    assert align_pre_per_proposals(proposals, evidence) == proposals


def test_nbl_assist_absence_uses_the_same_1952_stat_boundary() -> None:
    assert not _recorded_assists_available(SimpleNamespace(season=1949, season_info={"lg": "NBL"}, per_game={}))
    assert _recorded_assists_available(SimpleNamespace(season=1952, season_info={"lg": "NBL"}, per_game={}))
