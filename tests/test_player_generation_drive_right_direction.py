from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_offense import (  # type: ignore[import-not-found]  # noqa: E402
    _TENDENCY_CALIBRATION,
    _TENDENCY_RECIPES,
    derive_tendency_driveright,
)


def _evidence(*, rim_share: float, foul_pressure: float, attempts: float, position: str) -> SimpleNamespace:
    return SimpleNamespace(
        season=2025,
        identity={"pos": position},
        season_info={"lg": "NBA", "pos": position},
        per_game={"g": 82.0, "fga_per_game": attempts},
        totals={"g": 82.0, "fga": 82.0 * attempts},
        advanced={"f_tr": foul_pressure},
        shooting={"percent_fga_from_x0_3_range": rim_share},
        play_by_play={},
    )


def test_drive_volume_and_creator_role_do_not_invent_drive_right_direction() -> None:
    low_volume = _evidence(rim_share=0.05, foul_pressure=0.05, attempts=2.0, position="C")
    high_volume = _evidence(rim_share=0.90, foul_pressure=0.80, attempts=25.0, position="PG")

    assert derive_tendency_driveright(low_volume, league_player_rows=()) is None
    assert derive_tendency_driveright(high_volume, league_player_rows=()) is None


def test_drive_right_has_no_volume_based_recipe_or_calibration() -> None:
    assert "DRIVERIGHT" not in _TENDENCY_RECIPES
    assert "DRIVERIGHT" not in _TENDENCY_CALIBRATION

