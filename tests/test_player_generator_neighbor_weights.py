from __future__ import annotations

import importlib
import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

stat_neighbor_framework = importlib.import_module("stat_neighbor_framework")
StatNeighborModel = stat_neighbor_framework.StatNeighborModel


def _candidate(label: str, feature_value: float, field_value: int) -> dict[str, object]:
    return {
        "player_label": label,
        "features": {"fg_percent_from_x10_16_range": feature_value, "fg_percent_from_x16_3p_range": feature_value, "fg_pct": feature_value},
        "fields": {"Attributes/MIDRANGE": field_value},
    }


def test_top_five_neighbor_values_use_fixed_rank_weights() -> None:
    model = StatNeighborModel(
        path=GENERATOR_DIR / "NBA Player Data" / "player_generation_pool" / "TEST_MODEL.sqlite",
        suggestions_by_player_position={},
        suggestions_by_player_team_position={},
        candidates_by_position={
            "PG": (
                _candidate("first", 0.0, 100),
                _candidate("second", 1.0, 80),
                _candidate("third", 2.0, 60),
                _candidate("fourth", 3.0, 40),
                _candidate("fifth", 4.0, 20),
            )
        },
        scales_by_position={"PG": {"fg_percent_from_x10_16_range": (0.0, 1.0), "fg_percent_from_x16_3p_range": (0.0, 1.0), "fg_pct": (0.0, 1.0)}},
    )

    suggestions = model.suggestions_for_features(
        target_features={"fg_percent_from_x10_16_range": 0.0, "fg_percent_from_x16_3p_range": 0.0, "fg_pct": 0.0},
        position="PG",
    )

    suggestion = suggestions["Attributes/MIDRANGE"]
    assert suggestion.value == 85
    assert suggestion.source_rule == "position_stat_neighbor_section_top5_weighted"
    assert "rank_weights=54,25,15,5,1" in suggestion.evidence_keys
