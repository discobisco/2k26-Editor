from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules import derive_player_profile_values  # type: ignore[import-not-found]
from stat_neighbor_framework import PositionSelection, StatNeighborModel, select_positions_from_evidence  # type: ignore[import-not-found]


def _match_candidate(label: str, position: str, features: dict[str, float]) -> dict[str, object]:
    return {
        "run_id": label,
        "player_index": label,
        "player_label": label,
        "master_player_id": label.upper().replace(" ", ""),
        "position": position,
        "features": features,
        "fields": {"Attributes/FREETHROW": 70.0},
    }


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

    assert suggestions["Attributes/FREETHROW"].value == 75
    assert suggestions["Attributes/FREETHROW"].source_rule == "position_percent_weighted_neighbor"


def test_listed_multi_position_without_percentages_uses_best_matching_position_pool() -> None:
    positions = select_positions_from_evidence({}, "SF/SG")
    model = _model({"SF": 75, "SG": 55}, ft_pct_by_position={"SF": 0.40, "SG": 0.75})

    suggestions = model.suggestions_for_position_selection(target_features={"ft_pct": 0.75}, positions=positions)

    assert positions.primary == "SF"
    assert positions.secondary == "SG"
    assert positions.position_weights == ()
    assert suggestions["Attributes/FREETHROW"].value == 75
    assert suggestions["Attributes/FREETHROW"].source_rule == "listed_position_best_neighbor"


def test_player_match_groups_include_best_plus_players_within_point005() -> None:
    root = Path(__file__).resolve().parents[1]
    model = StatNeighborModel(
        path=root / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "player_generation_pool" / "POSITION_STAT_NEIGHBOR_MODEL.sqlite",
        suggestions_by_player_position={},
        suggestions_by_player_team_position={},
        candidates_by_position={
            "SG": (
                _match_candidate("Exact Overall", "SG", {"per": 20.0, "pts_per36": 10.0, "dbpm": 2.0}),
                _match_candidate("Within Overall", "SG", {"per": 20.004, "pts_per36": 10.004, "dbpm": 2.004}),
                _match_candidate("Outside Overall", "SG", {"per": 20.006, "pts_per36": 10.006, "dbpm": 2.006}),
            )
        },
        scales_by_position={"SG": {"per": (0.0, 1.0), "pts_per36": (0.0, 1.0), "dbpm": (0.0, 1.0)}},
    )
    positions = PositionSelection(primary="SG", secondary=None, all_positions=("SG",))

    matches = model.player_matches_for_position_selection(
        target_features={"per": 20.0, "pts_per36": 10.0, "dbpm": 2.0},
        positions=positions,
    )

    assert [match.player_label for match in matches["player"]] == ["Exact Overall", "Within Overall"]
    assert [match.player_label for match in matches["offensive"]] == ["Exact Overall", "Within Overall"]
    assert [match.player_label for match in matches["defensive"]] == ["Exact Overall", "Within Overall"]


def test_field_suggestion_blends_individual_full_and_offensive_match_values() -> None:
    root = Path(__file__).resolve().parents[1]
    model = StatNeighborModel(
        path=root / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "player_generation_pool" / "POSITION_STAT_NEIGHBOR_MODEL.sqlite",
        suggestions_by_player_position={},
        suggestions_by_player_team_position={},
        candidates_by_position={
            "SG": (
                _match_candidate("Free Throw Twin", "SG", {"ft_pct": 0.90, "per": 100.0, "pts_per36": 100.0}),
                _match_candidate("Offensive Twin", "SG", {"ft_pct": 0.50, "per": 20.0, "pts_per36": 10.0}),
            )
        },
        scales_by_position={"SG": {"ft_pct": (0.0, 1.0), "per": (0.0, 1.0), "pts_per36": (0.0, 1.0)}},
    )
    model.candidates_by_position["SG"][0]["fields"]["Attributes/FREETHROW"] = 30.0
    model.candidates_by_position["SG"][0]["sim_features"] = {"ft_pct": 0.50}
    model.candidates_by_position["SG"][0]["master_features"] = {"ft_pct": 0.75}
    model.candidates_by_position["SG"][1]["fields"]["Attributes/FREETHROW"] = 90.0
    model.candidates_by_position["SG"][1]["sim_features"] = {"ft_pct": 0.50}
    model.candidates_by_position["SG"][1]["master_features"] = {"ft_pct": 0.25}

    suggestions = model.suggestions_for_position_selection(
        target_features={"ft_pct": 0.90, "per": 20.0, "pts_per36": 10.0},
        positions=PositionSelection(primary="SG", secondary=None, all_positions=("SG",)),
    )

    assert suggestions["Attributes/FREETHROW"].value == 90
    assert "field_source=ft_percent_direct" in suggestions["Attributes/FREETHROW"].evidence_keys
    assert "player_match_blend=individual,player,offensive" not in suggestions["Attributes/FREETHROW"].evidence_keys

def test_field_without_section_neighbors_uses_exact_player_match_rows_before_omit() -> None:
    root = Path(__file__).resolve().parents[1]
    model = StatNeighborModel(
        path=root / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "player_generation_pool" / "POSITION_STAT_NEIGHBOR_MODEL.sqlite",
        suggestions_by_player_position={},
        suggestions_by_player_team_position={},
        candidates_by_position={
            "SG": (
                _match_candidate("Overall Exact Field", "SG", {"per": 20.0, "pts_per36": 10.0, "ft_pct": None}),
                _match_candidate("Offensive Exact Field", "SG", {"per": 20.004, "pts_per36": 10.004, "ft_pct": None}),
            )
        },
        scales_by_position={"SG": {"per": (0.0, 1.0), "pts_per36": (0.0, 1.0), "ft_pct": (0.0, 1.0)}},
    )
    model.candidates_by_position["SG"][0]["fields"] = {"Attributes/MIDRANGE": 30.0}
    model.candidates_by_position["SG"][1]["fields"] = {"Attributes/MIDRANGE": 90.0}

    suggestions = model.suggestions_for_position_selection(
        target_features={"per": 20.0, "pts_per36": 10.0, "ft_pct": None},
        positions=PositionSelection(primary="SG", secondary=None, all_positions=("SG",)),
    )

    suggestion = suggestions["Attributes/MIDRANGE"]
    assert suggestion.value != 25
    assert suggestion.source_rule == "listed_position_best_neighbor"
    assert "field_source=exact_player_match_rows" in suggestion.evidence_keys
    assert "player_match_blend=individual,player,offensive" in suggestion.evidence_keys

def test_single_position_profile_writes_secondary_position_na() -> None:
    evidence = SimpleNamespace(
        identity={"player": "Single Position", "ht_in_in": 74, "wt": 190},
        season_info={},
        play_by_play={},
        source_context={},
        player_id="single01",
        season=1947,
    )

    result = derive_player_profile_values(
        evidence,
        positions=PositionSelection(primary="C", secondary=None, all_positions=("C",)),
    )

    assert result.values["Vitals/POSITION"].value == "C"
    assert result.values["Vitals/SECONDARYPOSITION"].value == "N/A"


def test_multi_position_profile_writes_actual_secondary_position() -> None:
    evidence = SimpleNamespace(
        identity={"player": "Multi Position", "ht_in_in": 74, "wt": 190},
        season_info={},
        play_by_play={},
        source_context={},
        player_id="multi01",
        season=1947,
    )

    result = derive_player_profile_values(
        evidence,
        positions=PositionSelection(primary="SF", secondary="SG", all_positions=("SF", "SG")),
    )

    assert result.values["Vitals/POSITION"].value == "SF"
    assert result.values["Vitals/SECONDARYPOSITION"].value == "SG"
