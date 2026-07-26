from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

import player_rules_offense  # type: ignore[import-not-found]  # noqa: E402
from player_era_context import player_era_context  # type: ignore[import-not-found]  # noqa: E402
from player_rules_offense import (  # type: ignore[import-not-found]  # noqa: E402
    derive_tendency_drivingdunk,
    derive_tendency_standingdunk,
)


def _evidence(*, dunks: float, season: int = 2025) -> SimpleNamespace:
    return SimpleNamespace(
        season=season,
        identity={"pos": "C", "ht_in_in": 84.0, "wt": 250.0},
        season_info={"lg": "NBA", "pos": "C"},
        per_game={"g": 82.0, "fga_per_game": 10.0, "fg_percent": 0.650},
        totals={"g": 82.0, "fga": 820.0},
        per_36={},
        per_100={},
        advanced={"f_tr": 0.60},
        shooting={
            "num_of_dunks": dunks,
            "percent_dunks_of_fga": dunks / 820.0,
            "percent_fga_from_x0_3_range": 0.70,
        },
        play_by_play={},
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
    )


def test_generic_dunk_totals_do_not_author_literal_standing_dunk_tendency() -> None:
    assert derive_tendency_standingdunk(_evidence(dunks=0.0), league_player_rows=()) is None
    assert derive_tendency_standingdunk(_evidence(dunks=300.0), league_player_rows=()) is None


def test_dunk_attempt_era_regimes_are_separate_and_never_universally_zero() -> None:
    expected = {1949: 0.15, 1959: 0.30, 1969: 0.65, 1970: 1.0}
    for season, multiplier in expected.items():
        context = player_era_context(_evidence(dunks=20.0, season=season))
        assert context.dunk_attempt_multiplier == multiplier
        assert context.dunk_attempt_multiplier > 0.0


def test_historical_dunk_context_suppresses_tendency_not_attribute(monkeypatch) -> None:
    def fake_derive(*args, **kwargs):
        return {
            "value": 100,
            "source_rule": "base_driving_dunk_tendency",
            "evidence_keys": ("base_action_evidence",),
        }

    monkeypatch.setattr(player_rules_offense, "_derive", fake_derive)

    expected = {1949: 15, 1959: 30, 1969: 65, 1970: 100}
    for season, value in expected.items():
        result = derive_tendency_drivingdunk(_evidence(dunks=20.0, season=season), league_player_rows=())
        assert result is not None
        assert result["value"] == value
        if season < 1970:
            assert result["source_rule"].endswith("_historical_dunk_attempt_suppression")
            assert "attribute_unchanged=true" in result["evidence_keys"]
            assert "hard_foul_model_is_separate=true" in result["evidence_keys"]
