from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_attribute_rank_adjuster import align_attribute_totals_to_metric_ranks  # type: ignore[import-not-found]


@dataclass(frozen=True)
class Candidate:
    section: str
    normalized_name: str
    field_key: str
    display_value: int
    source_rule: str = "test_rule"
    evidence_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class Proposal:
    player_id: str
    season: int
    team: str
    field_candidates: tuple[Candidate, ...]


def _proposal(player_id: str, season: int, total: int, *, team: str = "AAA") -> Proposal:
    first = total // 2
    second = total - first
    return Proposal(
        player_id=player_id,
        season=season,
        team=team,
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", first),
            Candidate("Attributes", "PASSIQ", "Attributes/PASSIQ", second),
            Candidate("Attributes", "FREETHROW", "Attributes/FREETHROW", 77),
            Candidate("Attributes", "POTENTIAL", "Attributes/POTENTIAL", 99),
            Candidate("Tendencies", "SHOT", "Tendencies/SHOT", 50),
        ),
    )


def _attribute_total(proposal: Proposal) -> int:
    return sum(
        candidate.display_value
        for candidate in proposal.field_candidates
        if candidate.section == "Attributes" and candidate.normalized_name not in {"POTENTIAL", "FREETHROW"}
    )


def test_align_attribute_totals_uses_real_per_when_available() -> None:
    low_attr_high_per = _proposal("HIGH", 1952, 70)
    high_attr_low_per = _proposal("LOW", 1952, 130)

    result = align_attribute_totals_to_metric_ranks(
        (low_attr_high_per, high_attr_low_per),
        {
            ("HIGH", "AAA"): {"advanced.per": 25.0},
            ("LOW", "AAA"): {"advanced.per": 5.0},
        },
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    assert _attribute_total(by_player["HIGH"]) == 90
    assert _attribute_total(by_player["LOW"]) == 130
    assert by_player["HIGH"].field_candidates[2].display_value == 77
    assert by_player["LOW"].field_candidates[2].display_value == 77
    changed = by_player["HIGH"].field_candidates[0]
    assert changed.source_rule == "attribute_rank_alignment"
    assert "attribute_rank_metric=advanced.per" in changed.evidence_keys


def test_align_attribute_totals_uses_source_table_pseudo_per_before_real_per_coverage() -> None:
    efficient = _proposal("fulksjo01", 1947, 70, team="PHW")
    inefficient = _proposal("mikange01", 1947, 130, team="CAG")

    result = align_attribute_totals_to_metric_ranks(
        (efficient, inefficient),
        {
            ("FULKSJO01", "PHW"): {"advanced.per": None},
            ("MIKANGE01", "CAG"): {"advanced.per": None},
        },
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    assert _attribute_total(by_player["fulksjo01"]) == 90
    assert _attribute_total(by_player["mikange01"]) == 150
    changed = by_player["fulksjo01"].field_candidates[0]
    assert "attribute_rank_metric=generated_pseudo_per_1947_1951.generated_pseudo_per" in changed.evidence_keys


def test_alignment_skips_durability_potential_and_tendencies() -> None:
    top_metric = Proposal(
        player_id="TOP",
        season=1952,
        team="AAA",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 25),
            Candidate("Attributes", "BACKDURABILITY", "Attributes/BACKDURABILITY", 99),
            Candidate("Attributes", "POTENTIAL", "Attributes/POTENTIAL", 99),
            Candidate("Tendencies", "SHOT", "Tendencies/SHOT", 99),
        ),
    )
    low_metric = Proposal(
        player_id="LOW",
        season=1952,
        team="AAA",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 80),
            Candidate("Attributes", "BACKDURABILITY", "Attributes/BACKDURABILITY", 25),
            Candidate("Attributes", "POTENTIAL", "Attributes/POTENTIAL", 25),
            Candidate("Tendencies", "SHOT", "Tendencies/SHOT", 25),
        ),
    )

    result = align_attribute_totals_to_metric_ranks(
        (top_metric, low_metric),
        {("TOP", "AAA"): {"advanced.per": 30.0}, ("LOW", "AAA"): {"advanced.per": 1.0}},
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    top_fields = {candidate.field_key: candidate.display_value for candidate in by_player["TOP"].field_candidates}
    assert top_fields["Attributes/SPEED"] == 35
    assert top_fields["Attributes/BACKDURABILITY"] == 99
    assert top_fields["Attributes/POTENTIAL"] == 99
    assert top_fields["Tendencies/SHOT"] == 99


def test_alignment_skips_three_point_before_1969() -> None:
    top_metric = Proposal(
        player_id="fulksjo01",
        season=1947,
        team="PHW",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 25),
            Candidate("Attributes", "3POINT", "Attributes/3POINT", 25),
        ),
    )
    low_metric = Proposal(
        player_id="mikange01",
        season=1947,
        team="CAG",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 80),
            Candidate("Attributes", "3POINT", "Attributes/3POINT", 99),
        ),
    )

    result = align_attribute_totals_to_metric_ranks(
        (top_metric, low_metric),
        {
            ("FULKSJO01", "PHW"): {},
            ("MIKANGE01", "CAG"): {},
        },
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    top_fields = {candidate.field_key: candidate.display_value for candidate in by_player["fulksjo01"].field_candidates}
    low_fields = {candidate.field_key: candidate.display_value for candidate in by_player["mikange01"].field_candidates}
    assert top_fields["Attributes/SPEED"] == 35
    assert low_fields["Attributes/SPEED"] == 90
    assert top_fields["Attributes/3POINT"] == 25
    assert low_fields["Attributes/3POINT"] == 99


def test_alignment_can_shift_three_point_from_1969_onward() -> None:
    top_metric = Proposal(
        player_id="TOP",
        season=1969,
        team="AAA",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 25),
            Candidate("Attributes", "3POINT", "Attributes/3POINT", 25),
        ),
    )
    low_metric = Proposal(
        player_id="LOW",
        season=1969,
        team="AAA",
        field_candidates=(
            Candidate("Attributes", "SPEED", "Attributes/SPEED", 80),
            Candidate("Attributes", "3POINT", "Attributes/3POINT", 99),
        ),
    )

    result = align_attribute_totals_to_metric_ranks(
        (top_metric, low_metric),
        {("TOP", "AAA"): {"advanced.per": 20.0}, ("LOW", "AAA"): {"advanced.per": 1.0}},
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    top_total = sum(candidate.display_value for candidate in by_player["TOP"].field_candidates if candidate.section == "Attributes")
    low_total = sum(candidate.display_value for candidate in by_player["LOW"].field_candidates if candidate.section == "Attributes")
    assert top_total == 70
    assert low_total == 179


def test_alignment_does_not_floor_moderate_low_pseudo_per_players() -> None:
    top = _proposal("fulksjo01", 1947, 130, team="PHW")
    moderate_low = _proposal("gardnbe01", 1947, 130, team="FWZ")

    result = align_attribute_totals_to_metric_ranks(
        (top, moderate_low),
        {
            ("FULKSJO01", "PHW"): {},
            ("GARDNBE01", "FWZ"): {},
        },
    )

    by_player = {proposal.player_id: proposal for proposal in result.proposals}
    assert _attribute_total(by_player["fulksjo01"]) == 150
    assert _attribute_total(by_player["gardnbe01"]) == 130
    assert all(
        candidate.display_value > 25
        for candidate in by_player["gardnbe01"].field_candidates
        if candidate.section == "Attributes" and candidate.normalized_name not in {"POTENTIAL", "FREETHROW"}
    )
