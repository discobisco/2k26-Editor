from __future__ import annotations

import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from stat_neighbor_framework import PositionSelection, StatNeighborModel, select_positions_from_evidence  # type: ignore[import-not-found]


def _candidate(position: str, value: int, ft_pct: float = 0.75) -> dict[str, object]:
    return {
        "run_id": position,
        "player_index": "1",
        "player_label": f"{position} Match",
        "master_player_id": position,
        "position": position,
        "features": {"ft_pct": ft_pct},
        "fields": {"Attributes/FREETHROW": float(value)},
    }


def _model(values_by_position: dict[str, int], *, ft_pct_by_position: dict[str, float] | None = None) -> StatNeighborModel:
    root = Path(__file__).resolve().parents[1]
    return StatNeighborModel(
        path=root / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "player_generation_pool" / "POSITION_STAT_NEIGHBOR_MODEL.sqlite",
        suggestions_by_player_position={},
        suggestions_by_player_team_position={},
        candidates_by_position={
            position: (_candidate(position, value, (ft_pct_by_position or {}).get(position, 0.75)),)
            for position, value in values_by_position.items()
        },
        scales_by_position={position: {"ft_pct": (0.0, 1.0)} for position in values_by_position},
    )


def test_play_by_play_position_percentages_are_preserved_as_weights() -> None:
    positions = select_positions_from_evidence(
        {"sf_percent": 58, "pf_percent": 10, "c_percent": 1, "pg_percent": 2, "sg_percent": 29},
        "SF",
    )

    assert positions.primary == "SF"
    assert positions.secondary == "SG"
    assert positions.all_positions == ("SF", "SG", "PF", "PG", "C")
    assert positions.position_weights == (("SF", 0.58), ("SG", 0.29), ("PF", 0.10), ("PG", 0.02), ("C", 0.01))


def test_position_percentages_blend_model_suggestions_for_all_played_positions() -> None:
    positions = PositionSelection(
        primary="SF",
        secondary="SG",
        all_positions=("SF", "SG", "PF", "PG", "C"),
        position_weights=(("SF", 0.58), ("SG", 0.29), ("PF", 0.10), ("PG", 0.02), ("C", 0.01)),
    )
    model = _model({"SF": 80, "SG": 60, "PF": 50, "PG": 40, "C": 30})

    suggestions = model.suggestions_for_position_selection(target_features={"ft_pct": 0.75}, positions=positions)

    assert suggestions["Attributes/FREETHROW"].value == 70
    assert suggestions["Attributes/FREETHROW"].source_rule == "position_percent_weighted_neighbor"


def test_listed_multi_position_without_percentages_uses_best_matching_position_pool() -> None:
    positions = select_positions_from_evidence({}, "SF/SG")
    model = _model({"SF": 75, "SG": 55}, ft_pct_by_position={"SF": 0.40, "SG": 0.75})

    suggestions = model.suggestions_for_position_selection(target_features={"ft_pct": 0.75}, positions=positions)

    assert positions.primary == "SF"
    assert positions.secondary == "SG"
    assert positions.position_weights == ()
    assert suggestions["Attributes/FREETHROW"].value == 55
    assert suggestions["Attributes/FREETHROW"].source_rule == "listed_position_best_neighbor"
