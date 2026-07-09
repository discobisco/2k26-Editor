from __future__ import annotations

import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from field_value_normalizer import normalize_field_value  # type: ignore[import-not-found]


def test_attribute_value_is_adjusted_by_match_2k_vs_master_deviation() -> None:
    adjusted = normalize_field_value(
        field_key="Attributes/FREETHROW",
        value=50,
        initial_match_2k_features={"ft_pct": 0.75},
        initial_match_master_features={"ft_pct": 0.90},
        domain_master_feature_rows=({"ft_pct": 0.75}, {"ft_pct": 0.60}, {"ft_pct": 0.90}),
        feature_names=("ft_pct",),
        source_rule="position_stat_neighbor_section_top5_weighted",
        evidence_keys=("base",),
    )

    assert adjusted.value == 60
    assert adjusted.source_rule == "position_stat_neighbor_section_top5_weighted_match_deviation_adjusted"
    assert "normalization=league" in adjusted.evidence_keys
    assert "match_2k_to_master_percent_delta=0.200000" in adjusted.evidence_keys


def test_attribute_value_lowers_when_match_2k_stat_is_above_master_stat() -> None:
    adjusted = normalize_field_value(
        field_key="Attributes/FREETHROW",
        value=60,
        initial_match_2k_features={"ft_pct": 0.90},
        initial_match_master_features={"ft_pct": 0.75},
        domain_master_feature_rows=({"ft_pct": 0.75}, {"ft_pct": 0.90}),
        feature_names=("ft_pct",),
        source_rule="position_stat_neighbor_section_top5_weighted",
        evidence_keys=("base",),
    )

    assert adjusted.value == 50
    assert "match_2k_to_master_percent_delta=-0.166667" in adjusted.evidence_keys


def test_tendency_value_is_adjusted_by_team_normalized_match_deviation() -> None:
    adjusted = normalize_field_value(
        field_key="Tendencies/SPOTUP3PT",
        value=50,
        initial_match_2k_features={"x3pa_per100": 10.0, "team_3pa": 100.0, "team_poss": 100.0},
        initial_match_master_features={"x3pa_per100": 12.0, "team_3pa": 100.0, "team_poss": 100.0},
        domain_master_feature_rows=(),
        feature_names=("x3pa_per100",),
        source_rule="position_stat_neighbor_section_top5_weighted",
        evidence_keys=("base",),
    )

    assert adjusted.value == 60
    assert adjusted.source_rule == "position_stat_neighbor_section_top5_weighted_match_deviation_adjusted"
    assert "normalization=team" in adjusted.evidence_keys
    assert "match_2k_to_master_percent_delta=0.200000" in adjusted.evidence_keys


def test_normalizer_preserves_base_rule_when_no_match_deviation_exists() -> None:
    adjusted = normalize_field_value(
        field_key="Attributes/FREETHROW",
        value=50,
        initial_match_2k_features={"ft_pct": None},
        initial_match_master_features={"ft_pct": 0.75},
        domain_master_feature_rows=({"ft_pct": 0.75},),
        feature_names=("ft_pct",),
        source_rule="position_stat_neighbor_section_top5_weighted",
        evidence_keys=("base",),
    )

    assert adjusted.value == 50
    assert adjusted.source_rule == "position_stat_neighbor_section_top5_weighted"
    assert adjusted.evidence_keys == ("base",)


def test_normalizer_clamps_attribute_and_tendency_ranges() -> None:
    attribute = normalize_field_value(
        field_key="Attributes/FREETHROW",
        value=80,
        initial_match_2k_features={"ft_pct": 0.5},
        initial_match_master_features={"ft_pct": 2.0},
        domain_master_feature_rows=({"ft_pct": 1.0},),
        feature_names=("ft_pct",),
        source_rule="rule",
        evidence_keys=(),
    )
    tendency = normalize_field_value(
        field_key="Tendencies/SPOTUP3PT",
        value=80,
        initial_match_2k_features={"x3pa_per100": 0.5, "team_3pa": 100.0, "team_poss": 100.0},
        initial_match_master_features={"x3pa_per100": 2.0, "team_3pa": 100.0, "team_poss": 100.0},
        domain_master_feature_rows=(),
        feature_names=("x3pa_per100",),
        source_rule="rule",
        evidence_keys=(),
    )

    assert attribute.value == 99
    assert tendency.value == 100
