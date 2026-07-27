from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_athleticism import (  # type: ignore[import-not-found]  # noqa: E402
    derive_attribute_acceleration,
    derive_attribute_agility,
    derive_attribute_speed,
)


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
        "per_game": {"g": games},
        "identity": {"ht_in_in": height, "wt": weight},
    }


POOL_ROWS = (
    _row(height=60.0, weight=120.0),
    _row(height=75.0, weight=210.0),
    _row(height=90.0, weight=300.0),
)


@pytest.mark.parametrize(
    ("height", "weight", "expected"),
    (
        (60.0, 120.0, 99),
        (90.0, 300.0, 25),
        (75.0, 210.0, 62),
        (60.0, 300.0, 62),
        (90.0, 120.0, 62),
    ),
)
def test_speed_uses_inverse_full_pool_height_and_weight_min_max(
    height: float,
    weight: float,
    expected: int,
) -> None:
    result = derive_attribute_speed(
        _evidence(height=height, weight=weight),
        league_player_rows=POOL_ROWS,
    )

    assert result is not None
    assert result["value"] == expected
    assert result["source_rule"] == "derive_attribute_speed_full_generated_pool_body_min_max"
    assert "population.min_height_inches=60" in result["evidence_keys"]
    assert "population.max_height_inches=90" in result["evidence_keys"]
    assert "population.min_weight_pounds=120" in result["evidence_keys"]
    assert "population.max_weight_pounds=300" in result["evidence_keys"]


def test_speed_body_mapping_does_not_use_position_or_age() -> None:
    young_guard = derive_attribute_speed(
        _evidence(height=75.0, weight=210.0, position="PG", age=20.0),
        league_player_rows=POOL_ROWS,
    )
    old_center = derive_attribute_speed(
        _evidence(height=75.0, weight=210.0, position="C", age=40.0),
        league_player_rows=POOL_ROWS,
    )

    assert young_guard is not None
    assert old_center is not None
    assert young_guard["value"] == old_center["value"] == 62


@pytest.mark.parametrize(("height", "weight"), ((60.0, 120.0), (75.0, 210.0), (90.0, 300.0)))
def test_agility_uses_the_same_body_min_max_value_as_speed(height: float, weight: float) -> None:
    evidence = _evidence(height=height, weight=weight)
    speed = derive_attribute_speed(evidence, league_player_rows=POOL_ROWS)
    agility = derive_attribute_agility(evidence, league_player_rows=POOL_ROWS)

    assert speed is not None
    assert agility is not None
    assert agility["value"] == speed["value"]
    assert agility["source_rule"] == "derive_attribute_agility_full_generated_pool_body_min_max"


def test_speed_ignores_non_gp_population_rows_when_finding_extrema() -> None:
    rows = (*POOL_ROWS, _row(height=40.0, weight=50.0, games=0.0))
    result = derive_attribute_speed(
        _evidence(height=60.0, weight=120.0),
        league_player_rows=rows,
    )

    assert result is not None
    assert result["value"] == 99
    assert "population.min_height_inches=60" in result["evidence_keys"]
    assert "population.min_weight_pounds=120" in result["evidence_keys"]


def test_speed_is_unresolved_without_a_usable_full_pool_span() -> None:
    result = derive_attribute_speed(
        _evidence(height=75.0, weight=210.0),
        league_player_rows=(_row(height=75.0, weight=210.0),),
    )

    assert result is None


def test_acceleration_uses_the_min_max_speed_result() -> None:
    result = derive_attribute_acceleration(
        _evidence(height=90.0, weight=300.0, position="PG", age=25.0),
        league_player_rows=POOL_ROWS,
    )

    assert result is not None
    assert result["source_rule"] == "derive_attribute_acceleration_field_specific_context_substitute"
    assert "joint_speed=25" in result["evidence_keys"]
