from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules import (  # type: ignore[import-not-found]
    RuleValue,
    derive_neighbor_rule_values,
    derive_player_rule_values,
    merge_rule_sources,
)
from stat_neighbor_framework import NeighborFieldSuggestion, PositionSelection  # type: ignore[import-not-found]


def test_formula_value_is_used_when_neighbor_missing() -> None:
    result = merge_rule_sources(
        formula_values={
            "Attributes/MIDRANGE": RuleValue(
                value=62,
                source_rule="derive_attribute_midrange",
                evidence_keys=("formula_source=old_midrange",),
            )
        },
        neighbor_values={},
    )

    value = result["Attributes/MIDRANGE"]
    assert value.value == 62
    assert value.source_rule == "hybrid_formula_only"
    assert "formula_value=62" in value.evidence_keys
    assert "formula_source=derive_attribute_midrange" in value.evidence_keys


def test_neighbor_value_is_used_when_formula_missing() -> None:
    result = merge_rule_sources(
        formula_values={},
        neighbor_values={
            "Attributes/MIDRANGE": RuleValue(
                value=80,
                source_rule="listed_position_best_neighbor",
                evidence_keys=("field_source=exact_player_match_rows",),
            )
        },
    )

    value = result["Attributes/MIDRANGE"]
    assert value.value == 80
    assert value.source_rule == "hybrid_neighbor_only"
    assert "neighbor_value=80" in value.evidence_keys
    assert "neighbor_source=listed_position_best_neighbor" in value.evidence_keys


def test_formula_and_neighbor_values_are_merged_with_evidence() -> None:
    result = merge_rule_sources(
        formula_values={
            "Attributes/MIDRANGE": RuleValue(
                value=60,
                source_rule="derive_attribute_midrange",
                evidence_keys=("formula_source=old_midrange",),
            )
        },
        neighbor_values={
            "Attributes/MIDRANGE": RuleValue(
                value=80,
                source_rule="listed_position_best_neighbor",
                evidence_keys=("best_distance=0.100000", "common_features=3"),
            )
        },
    )

    value = result["Attributes/MIDRANGE"]
    assert 60 < value.value < 80
    assert value.source_rule == "hybrid_formula_neighbor_merge"
    assert "formula_value=60" in value.evidence_keys
    assert "neighbor_value=80" in value.evidence_keys
    assert "formula_source=derive_attribute_midrange" in value.evidence_keys
    assert "neighbor_source=listed_position_best_neighbor" in value.evidence_keys
    assert any(key.startswith("merge_policy=") for key in value.evidence_keys)


def test_derive_neighbor_rule_values_preserves_current_model_suggestions(monkeypatch) -> None:
    class FakeModel:
        def suggestions_for_evidence(self, *, evidence, positions):
            return {
                "Attributes/MIDRANGE": NeighborFieldSuggestion(
                    field_key="Attributes/MIDRANGE",
                    value=77,
                    source_rule="listed_position_best_neighbor",
                    evidence_keys=("field_source=exact_player_match_rows",),
                )
            }

    import player_rules  # type: ignore[import-not-found]

    monkeypatch.setattr(player_rules, "load_latest_stat_neighbor_model", lambda: FakeModel())

    values = derive_neighbor_rule_values(
        SimpleNamespace(),
        PositionSelection(primary="SG", secondary=None, all_positions=("SG",)),
    )

    assert values["Attributes/MIDRANGE"].value == 77
    assert values["Attributes/MIDRANGE"].source_rule == "listed_position_best_neighbor"
    assert values["Attributes/MIDRANGE"].evidence_keys == ("field_source=exact_player_match_rows",)


def test_pre_1969_three_point_fields_are_fixed_and_intangibles_are_25(monkeypatch) -> None:
    class EmptyModel:
        def suggestions_for_evidence(self, *, evidence, positions):
            return {}

    import player_rules  # type: ignore[import-not-found]

    monkeypatch.setattr(player_rules, "load_latest_stat_neighbor_model", lambda: EmptyModel())

    result = derive_player_rule_values(
        SimpleNamespace(
            season=1947,
            season_info={"season": 1947, "pos": "G"},
            identity={"player": "Pre 1969 Guard"},
            per_game={"ft_percent": 0.75},
            totals={},
            per_36={},
            per_100={},
            advanced={},
            shooting={},
            play_by_play={},
            team_stats_per_game={},
            team_summary={},
            opponent_stats_per_game={},
        ),
        positions=PositionSelection(primary="SG", secondary=None, all_positions=("SG",)),
        active_field_keys={
            "Attributes/3POINT",
            "Attributes/INTANGIBLES",
            "Tendencies/3POINTSHOT",
            "Tendencies/CENTER3",
        },
    )

    assert result.values["Attributes/3POINT"].value == 25
    assert result.values["Tendencies/3POINTSHOT"].value == 0
    assert result.values["Tendencies/CENTER3"].value == 0
    assert result.values["Attributes/INTANGIBLES"].value == 25
    assert result.values["Attributes/3POINT"].source_rule == "fixed_pre_1969_no_three_point_line"
    assert result.values["Attributes/INTANGIBLES"].source_rule == "fixed_intangibles_25"


def test_1969_three_point_fields_are_not_pre_1969_fixed(monkeypatch) -> None:
    class EmptyModel:
        def suggestions_for_evidence(self, *, evidence, positions):
            return {}

    import player_rules  # type: ignore[import-not-found]

    monkeypatch.setattr(player_rules, "load_latest_stat_neighbor_model", lambda: EmptyModel())

    result = derive_player_rule_values(
        SimpleNamespace(
            season=1969,
            season_info={"season": 1969, "pos": "G"},
            identity={"player": "1969 Guard"},
            per_game={"x3p_percent": 0.5, "x3pa_per_game": 4.0, "ft_percent": 0.75},
            totals={},
            per_36={},
            per_100={},
            advanced={"x3p_ar": 0.4},
            shooting={},
            play_by_play={},
            team_stats_per_game={},
            team_summary={},
            opponent_stats_per_game={},
        ),
        positions=PositionSelection(primary="SG", secondary=None, all_positions=("SG",)),
        league_player_rows=(
            {"per_game.x3p_percent": 0.25, "per_game.x3pa_per_game": 1.0, "advanced.x3p_ar": 0.1},
            {"per_game.x3p_percent": 0.5, "per_game.x3pa_per_game": 4.0, "advanced.x3p_ar": 0.4},
        ),
        active_field_keys={"Attributes/3POINT", "Tendencies/3POINTSHOT", "Attributes/INTANGIBLES"},
    )

    assert result.values["Attributes/3POINT"].source_rule != "fixed_pre_1969_no_three_point_line"
    assert result.values["Tendencies/3POINTSHOT"].source_rule != "fixed_pre_1969_no_three_point_line"
    assert result.values["Attributes/INTANGIBLES"].value == 25
