from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_athleticism import derive_attribute_strength  # type: ignore[import-not-found]  # noqa: E402
from player_evidence import PlayerEvidence  # type: ignore[import-not-found]  # noqa: E402
from player_rules import derive_formula_rule_values  # type: ignore[import-not-found]  # noqa: E402


def _evidence(*, height: float, weight: float, position: str = "SF", age: float = 25.0) -> SimpleNamespace:
    return SimpleNamespace(
        season=2025,
        identity={"ht_in_in": height, "wt": weight, "pos": position},
        source_profile={},
        season_info={"lg": "NBA", "pos": position, "age": age},
        per_game={"g": 1.0},
        play_by_play={},
    )


def _row(*, height: float, weight: float, games: float = 1.0) -> dict[str, object]:
    return {
        "season": 2025,
        "lg": "NBA",
        "g": games,
        "per_game": {"g": games},
        "identity": {"ht_in_in": height, "wt": weight},
    }


POOL_ROWS = (
    _row(height=72.0, weight=180.0),
    _row(height=73.0, weight=216.0),
    _row(height=77.0, weight=240.0),
    _row(height=84.0, weight=300.0),
)


def _strength(*, height: float, weight: float, position: str = "SF", age: float = 25.0) -> dict[str, Any]:
    result = derive_attribute_strength(
        _evidence(height=height, weight=weight, position=position, age=age),
        league_player_rows=POOL_ROWS,
    )
    assert result is not None
    return result


def test_strength_rates_more_compact_bodies_higher_at_equal_weight() -> None:
    shorter = _strength(height=74.0, weight=220.0)
    taller = _strength(height=81.0, weight=220.0)

    assert int(shorter["value"]) > int(taller["value"])


def test_strength_rates_heavier_bodies_higher_at_equal_height() -> None:
    heavier = _strength(height=77.0, weight=240.0)
    lighter = _strength(height=77.0, weight=216.0)

    assert int(heavier["value"]) > int(lighter["value"])


def test_strength_rates_six_five_240_above_six_one_216() -> None:
    six_five_240 = _strength(height=77.0, weight=240.0)
    six_one_216 = _strength(height=73.0, weight=216.0)

    assert int(six_five_240["value"]) > int(six_one_216["value"])


def test_generation_registry_uses_body_compactness_strength_rule() -> None:
    evidence = PlayerEvidence(
        player_id="strength-test",
        season=2025,
        team="TST",
        identity={"ht_in_in": 77.0, "wt": 240.0, "pos": "SF"},
        season_info={"season": 2025, "lg": "NBA", "pos": "SF", "age": 25.0},
        per_game={"g": 1.0},
        totals={},
        per_36={},
        per_100={},
        advanced={},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )

    generated = derive_formula_rule_values(evidence, league_player_rows=POOL_ROWS)

    assert generated["Attributes/STRENGTH"].value == 68
    assert generated["Attributes/STRENGTH"].source_rule == "derive_attribute_strength_same_season_same_league_body_compactness"


def test_strength_does_not_use_position_or_age() -> None:
    young_guard = _strength(height=77.0, weight=240.0, position="PG", age=20.0)
    old_center = _strength(height=77.0, weight=240.0, position="C", age=40.0)

    assert young_guard["value"] == old_center["value"]
    assert young_guard["source_rule"] == "derive_attribute_strength_same_season_same_league_body_compactness"
    assert "excluded_runtime_inputs=position,age,overall,production" in young_guard["evidence_keys"]


def test_strength_ignores_non_gp_population_rows() -> None:
    rows = (*POOL_ROWS, _row(height=60.0, weight=400.0, games=0.0))
    result = derive_attribute_strength(
        _evidence(height=84.0, weight=300.0),
        league_player_rows=rows,
    )

    assert result is not None
    assert result["value"] == 99
    assert "population.same_season_same_league_gp_body_rows=4" in result["evidence_keys"]


def test_strength_is_unresolved_without_a_usable_compactness_span() -> None:
    result = derive_attribute_strength(
        _evidence(height=75.0, weight=210.0),
        league_player_rows=(_row(height=75.0, weight=210.0),),
    )

    assert result is None