from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_defense import (  # type: ignore[import-not-found]
    derive_attribute_interiordefense,
    derive_attribute_perimeterdefense,
)
from stat_neighbor_framework import (  # type: ignore[import-not-found]
    PositionSelection,
    StatNeighborModel,
    _features_for_field,
    _field_match_blend_groups,
    select_positions_from_evidence,
)


INTERIOR = "Attributes/INTERIORDEFENSE"
PERIMETER = "Attributes/PERIMETERDEFENSE"


def _formula_evidence(
    *,
    block: float,
    block_percent: float,
    steal: float,
    steal_percent: float,
    dws: float | None = 0.0,
    dbpm: float = 99.0,
    position: str | None = None,
    player_id: str = "test01",
    league: str = "BAA",
    team: str = "AAA",
    wins: float = 5.0,
    losses: float = 5.0,
    points_per_game: float = 100.0,
    opponent_points_per_game: float = 100.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        player_id=player_id,
        season=1947,
        team=team,
        identity={"player_id": player_id, "ht_in_in": 77.0, "pos": position},
        season_info={"season": 1947, "lg": league, "team": team, "pos": position},
        per_game={
            "g": 10.0,
            "blk_per_game": block,
            "stl_per_game": steal,
            "drb_per_game": 5.0,
        },
        advanced={
            "blk_percent": block_percent,
            "stl_percent": steal_percent,
            "dws": dws,
            "dbpm": dbpm,
        },
        team_summary={"w": wins, "l": losses},
        team_stats_per_game={"pts_per_game": points_per_game},
        opponent_stats_per_game={"opp_pts_per_game": opponent_points_per_game},
    )


def _formula_row(
    *,
    team: str,
    dws: float | None,
    wins: float,
    losses: float,
    points_per_game: float,
    opponent_points_per_game: float,
    league: str = "BAA",
) -> dict[str, object]:
    return {
        "season": 1947,
        "player_season_info.lg": league,
        "player_season_info.team": team,
        "player_per_game.g": 10.0,
        "advanced.dws": dws,
        "team_summaries.w": wins,
        "team_summaries.l": losses,
        "team_stats_per_game.pts_per_game": points_per_game,
        "opponent_stats_per_game.opp_pts_per_game": opponent_points_per_game,
    }


def test_formula_defense_ratings_ignore_block_and_steal() -> None:
    rows = (
        _formula_row(team="AAA", dws=0.0, wins=5.0, losses=5.0, points_per_game=100.0, opponent_points_per_game=100.0),
        _formula_row(team="BBB", dws=10.0, wins=8.0, losses=2.0, points_per_game=110.0, opponent_points_per_game=90.0),
    )
    low = _formula_evidence(block=0.0, block_percent=0.0, steal=0.0, steal_percent=0.0)
    high = _formula_evidence(block=99.0, block_percent=99.0, steal=99.0, steal_percent=99.0)

    low_interior = derive_attribute_interiordefense(low, league_player_rows=rows)
    high_interior = derive_attribute_interiordefense(high, league_player_rows=rows)
    low_perimeter = derive_attribute_perimeterdefense(low, league_player_rows=rows)
    high_perimeter = derive_attribute_perimeterdefense(high, league_player_rows=rows)

    assert low_interior == high_interior
    assert low_perimeter == high_perimeter
    for result in (low_interior, low_perimeter):
        assert "advanced.dws" in result["evidence_keys"]
        assert "team_summary.w" in result["evidence_keys"]
        assert "team_summary.l" in result["evidence_keys"]
        assert "team_stats_per_game.pts_per_game" in result["evidence_keys"]
        assert "opponent_stats_per_game.opp_pts_per_game" in result["evidence_keys"]

    poor = _formula_evidence(block=99.0, block_percent=99.0, steal=99.0, steal_percent=99.0, dws=0.0, dbpm=99.0)
    strong = _formula_evidence(block=0.0, block_percent=0.0, steal=0.0, steal_percent=0.0, dws=10.0, dbpm=-99.0)
    poor_interior = derive_attribute_interiordefense(poor, league_player_rows=rows)
    poor_perimeter = derive_attribute_perimeterdefense(poor, league_player_rows=rows)
    strong_interior = derive_attribute_interiordefense(strong, league_player_rows=rows)
    strong_perimeter = derive_attribute_perimeterdefense(strong, league_player_rows=rows)

    assert poor_interior["value"] == poor_perimeter["value"]
    assert poor_interior["score"] == poor_perimeter["score"]
    assert strong_interior["value"] == strong_perimeter["value"]
    assert strong_interior["score"] == strong_perimeter["score"]
    assert poor_interior["value"] < strong_interior["value"]


def test_formula_dws_quality_is_routed_by_position() -> None:
    rows = (
        _formula_row(team="AAA", dws=0.0, wins=2.0, losses=8.0, points_per_game=90.0, opponent_points_per_game=110.0),
        _formula_row(team="BBB", dws=10.0, wins=8.0, losses=2.0, points_per_game=110.0, opponent_points_per_game=90.0),
    )
    center = _formula_evidence(
        block=99.0,
        block_percent=99.0,
        steal=99.0,
        steal_percent=99.0,
        dws=10.0,
        position="C",
        team="BBB",
        wins=8.0,
        losses=2.0,
        points_per_game=110.0,
        opponent_points_per_game=90.0,
    )
    guard = _formula_evidence(
        block=99.0,
        block_percent=99.0,
        steal=99.0,
        steal_percent=99.0,
        dws=10.0,
        position="PG",
        team="BBB",
        wins=8.0,
        losses=2.0,
        points_per_game=110.0,
        opponent_points_per_game=90.0,
    )

    center_interior = derive_attribute_interiordefense(center, league_player_rows=rows)
    center_perimeter = derive_attribute_perimeterdefense(center, league_player_rows=rows)
    guard_interior = derive_attribute_interiordefense(guard, league_player_rows=rows)
    guard_perimeter = derive_attribute_perimeterdefense(guard, league_player_rows=rows)

    assert center_interior["value"] == guard_perimeter["value"] == 99
    assert center_perimeter["value"] == guard_interior["value"] == 36
    assert center_interior["value"] > center_perimeter["value"]
    assert guard_perimeter["value"] > guard_interior["value"]
    for result in (center_interior, center_perimeter, guard_interior, guard_perimeter):
        assert result["evidence_keys"][0] == "advanced.dws"
        assert any(key.startswith("position_side_multiplier=") for key in result["evidence_keys"])
        assert not any("blk" in key or "block" in key or "steal" in key or "dbpm" in key for key in result["evidence_keys"])


def test_team_record_and_point_differential_each_affect_both_main_defense_attributes() -> None:
    rows = (
        _formula_row(team="BASE", dws=5.0, wins=2.0, losses=8.0, points_per_game=100.0, opponent_points_per_game=100.0),
        _formula_row(team="WIN", dws=5.0, wins=8.0, losses=2.0, points_per_game=100.0, opponent_points_per_game=100.0),
        _formula_row(team="DIFF", dws=5.0, wins=2.0, losses=8.0, points_per_game=110.0, opponent_points_per_game=90.0),
    )

    def evidence(*, team: str, wins: float, losses: float, points: float, opponent_points: float) -> SimpleNamespace:
        return _formula_evidence(
            block=0.0,
            block_percent=0.0,
            steal=0.0,
            steal_percent=0.0,
            dws=5.0,
            position="SF",
            team=team,
            wins=wins,
            losses=losses,
            points_per_game=points,
            opponent_points_per_game=opponent_points,
        )

    baseline = evidence(team="BASE", wins=2.0, losses=8.0, points=100.0, opponent_points=100.0)
    better_record = evidence(team="WIN", wins=8.0, losses=2.0, points=100.0, opponent_points=100.0)
    better_diff = evidence(team="DIFF", wins=2.0, losses=8.0, points=110.0, opponent_points=90.0)

    for derive in (derive_attribute_interiordefense, derive_attribute_perimeterdefense):
        baseline_result = derive(baseline, league_player_rows=rows)
        record_result = derive(better_record, league_player_rows=rows)
        diff_result = derive(better_diff, league_player_rows=rows)
        assert baseline_result is not None and record_result is not None and diff_result is not None
        assert record_result["value"] > baseline_result["value"]
        assert diff_result["value"] > baseline_result["value"]


def test_nbl_team_context_resolves_missing_dws_and_mikan_uses_exact_research_override() -> None:
    rows = (
        _formula_row(team="DTG", dws=None, wins=4.0, losses=40.0, points_per_game=48.6, opponent_points_per_game=63.0, league="NBL"),
        _formula_row(team="CAG", dws=None, wins=26.0, losses=18.0, points_per_game=58.4, opponent_points_per_game=54.3, league="NBL"),
    )
    ordinary_center = _formula_evidence(
        block=0.0,
        block_percent=0.0,
        steal=0.0,
        steal_percent=0.0,
        dws=None,
        position="C",
        player_id="ordinary01",
        league="NBL",
        team="CAG",
        wins=26.0,
        losses=18.0,
        points_per_game=58.4,
        opponent_points_per_game=54.3,
    )
    mikan = _formula_evidence(
        block=0.0,
        block_percent=0.0,
        steal=0.0,
        steal_percent=0.0,
        dws=None,
        position="C",
        player_id="mikange01",
        league="NBL",
        team="CAG",
        wins=26.0,
        losses=18.0,
        points_per_game=58.4,
        opponent_points_per_game=54.3,
    )

    ordinary_interior = derive_attribute_interiordefense(ordinary_center, league_player_rows=rows)
    ordinary_perimeter = derive_attribute_perimeterdefense(ordinary_center, league_player_rows=rows)
    mikan_interior = derive_attribute_interiordefense(mikan, league_player_rows=rows)
    mikan_perimeter = derive_attribute_perimeterdefense(mikan, league_player_rows=rows)

    assert ordinary_interior is not None and ordinary_interior["value"] > 25
    assert ordinary_perimeter is not None and ordinary_perimeter["value"] > 25
    assert mikan_interior is not None and mikan_interior["value"] == 99
    assert mikan_perimeter is not None and mikan_perimeter["value"] == 36
    assert mikan_interior["source_rule"].endswith("_researched_exact_player_override")
    assert "researched_player_id=MIKANGE01" in mikan_interior["evidence_keys"]
    assert "researched_team=CAG" in mikan_interior["evidence_keys"]
    assert "research_source=https://probasketballencyclopedia.com/seasons/1946-1947/" in mikan_interior["evidence_keys"]


def _candidate(*, label: str, value: float, interior: int, perimeter: int, position: str = "PG") -> dict[str, object]:
    return {
        "run_id": label,
        "master_player_id": label,
        "player_label": label,
        "position": position,
        "features": {
            "drb_percent": value,
            "dws": value,
            "pf_per100": value,
            "height_inches": 70.0 + value,
            "weight_pounds": 180.0 + value,
            "all_defense": value,
            "dpoy_share": value,
            "stl_percent": value,
            "stl_per36": value,
            "stl_per100": value,
            "blk_percent": value,
            "blk_per36": value,
            "blk_per100": value,
        },
        "fields": {INTERIOR: interior, PERIMETER: perimeter},
    }


def _target(*, block_steal_value: float) -> dict[str, float]:
    return {
        "drb_percent": 0.0,
        "dws": 0.0,
        "pf_per100": 0.0,
        "height_inches": 70.0,
        "weight_pounds": 180.0,
        "all_defense": 0.0,
        "dpoy_share": 0.0,
        "stl_percent": block_steal_value,
        "stl_per36": block_steal_value,
        "stl_per100": block_steal_value,
        "blk_percent": block_steal_value,
        "blk_per36": block_steal_value,
        "blk_per100": block_steal_value,
    }


def test_neighbor_defense_ratings_ignore_block_and_steal() -> None:
    candidates = (
        _candidate(label="allowed-match", value=0.0, interior=35, perimeter=40),
        _candidate(label="block-steal-match", value=99.0, interior=95, perimeter=90),
    )
    feature_names = set(_target(block_steal_value=0.0))
    model = StatNeighborModel(
        path=GENERATOR_DIR / "NBA Player Data" / "statistical_growth_model" / "test-model",
        candidates_by_position={"PG": candidates},
        scales_by_position={"PG": {feature: (0.0, 1.0) for feature in feature_names}},
    )

    low = model.suggestions_for_features(target_features=_target(block_steal_value=0.0), position="PG")
    high = model.suggestions_for_features(target_features=_target(block_steal_value=99.0), position="PG")

    assert low[INTERIOR].value == high[INTERIOR].value == 35
    assert low[PERIMETER].value == high[PERIMETER].value == 40
    for field_key in (INTERIOR, PERIMETER):
        features = _features_for_field(field_key)
        assert features == ("dws",)
        assert not any("stl" in feature or "blk" in feature for feature in features)
        assert _field_match_blend_groups(features, field_key=field_key) == ()
        assert not any("stl" in key or "blk" in key for key in low[field_key].evidence_keys)


def test_researched_pre_clock_position_continuum_routes_dws_defense() -> None:
    position_values = {
        "PG": (35, 90),
        "SG": (45, 80),
        "SF": (60, 60),
        "PF": (80, 45),
        "C": (90, 35),
    }
    candidates_by_position = {
        position: (
            _candidate(
                label=position,
                value=0.0,
                interior=interior,
                perimeter=perimeter,
                position=position,
            ),
        )
        for position, (interior, perimeter) in position_values.items()
    }
    feature_names = set(_target(block_steal_value=0.0))
    model = StatNeighborModel(
        path=GENERATOR_DIR / "NBA Player Data" / "statistical_growth_model" / "test-model",
        candidates_by_position=candidates_by_position,
        scales_by_position={
            position: {feature: (0.0, 1.0) for feature in feature_names}
            for position in position_values
        },
    )

    target = _target(block_steal_value=99.0)
    for position, (interior, perimeter) in position_values.items():
        suggestions = model.suggestions_for_position_selection(
            target_features=target,
            positions=PositionSelection(position, None, (position,)),
        )
        assert suggestions[INTERIOR].value == interior
        assert suggestions[PERIMETER].value == perimeter

    expected_historical_continuum = {
        "G": ("PG", "SG"),
        "G-F": ("SG", "SF"),
        "F-G": ("SF", "SG"),
        "F": ("SF", "PF"),
        "F-C": ("PF", "C"),
        "C-F": ("C", "PF"),
        "C": ("C",),
    }
    for source_label, expected_positions in expected_historical_continuum.items():
        assert select_positions_from_evidence({}, source_label).all_positions == expected_positions
