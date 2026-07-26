from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_offense import (  # type: ignore[import-not-found]  # noqa: E402
    derive_tendency_contestedjumpermid,
    derive_tendency_contestedjumpermidrange,
    derive_tendency_drivepullupmid,
    derive_tendency_drivepullupmidrange,
    derive_tendency_midoffscreenshot,
    derive_tendency_midspotupshot,
)


def _generic_midrange_evidence() -> SimpleNamespace:
    return SimpleNamespace(
        season=1949,
        identity={"pos": "F-C", "ht_in_in": 79.0, "wt": 225.0},
        season_info={"lg": "BAA", "pos": "F-C"},
        per_game={
            "g": 60.0,
            "fga_per_game": 18.0,
            "fg_percent": 0.420,
            "ft_percent": 0.800,
        },
        totals={"g": 60.0, "fga": 1080.0, "ft": 240.0, "fta": 300.0},
        per_36={},
        per_100={},
        advanced={"f_tr": 0.278},
        shooting={
            "percent_fga_from_x10_16_range": 0.30,
            "percent_fga_from_x16_3p_range": 0.25,
            "percent_assisted_x2p_fg": 0.65,
        },
        play_by_play={},
        team_stats_per_game={"g": 60.0, "fga_per_game": 80.0},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
    )


def test_generic_midrange_data_cannot_manufacture_exact_action_tendencies() -> None:
    evidence = _generic_midrange_evidence()
    rules = (
        derive_tendency_contestedjumpermid,
        derive_tendency_contestedjumpermidrange,
        derive_tendency_drivepullupmid,
        derive_tendency_drivepullupmidrange,
        derive_tendency_midoffscreenshot,
        derive_tendency_midspotupshot,
    )

    for rule in rules:
        assert rule(evidence, league_player_rows=()) is None
