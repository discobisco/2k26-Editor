from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

import player_rules_offense  # type: ignore[import-not-found]
from player_rules_offense import derive_attribute_standingdunk  # type: ignore[import-not-found]


def _evidence(height_in: float) -> SimpleNamespace:
    return SimpleNamespace(
        season=2026,
        identity={"pos": "C", "ht_in_in": height_in, "wt": 220.0},
        season_info={"lg": "NBA", "pos": "C", "age": 25.0},
        per_game={"g": 82.0, "fg_percent": 0.60, "fga_per_game": 10.0},
        totals={"g": 82.0, "fga": 820.0},
        per_36={},
        per_100={},
        advanced={"f_tr": 0.50},
        shooting={},
        play_by_play={},
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
    )


def _population_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "season": 2026,
            "player_season_info.lg": "NBA",
            "player_season_info.pos": "C",
            "player_info.pos": "C",
            "player_info.ht_in_in": float(70 + index),
            "player_info.wt": 220.0,
            "player_per_game.g": 82.0,
            "player_per_game.fg_percent": 0.35 + 0.03 * index,
            "player_per_game.fga_per_game": 10.0,
            "player_totals.g": 82.0,
            "player_totals.fga": 820.0,
            "advanced.f_tr": 0.20 + 0.03 * index,
        }
        for index in range(10)
    )


def test_standing_dunk_is_25_below_six_foot_four() -> None:
    result = derive_attribute_standingdunk(
        _evidence(75.0),
        league_player_rows=_population_rows(),
    )

    assert result is not None
    assert result["value"] == 25
    assert result["source_rule"] == "derive_attribute_standingdunk_under_6_4_height_gate"
    assert "standing_dunk_height_threshold_in=76" in result["evidence_keys"]


def test_standing_dunk_height_gate_stops_at_exactly_six_foot_four() -> None:
    result = derive_attribute_standingdunk(
        _evidence(76.0),
        league_player_rows=_population_rows(),
    )

    assert result is not None
    assert result["source_rule"] != "derive_attribute_standingdunk_under_6_4_height_gate"


def test_lower_height_generated_vertical_gate_resolves_to_floor(monkeypatch) -> None:
    monkeypatch.setattr(
        player_rules_offense,
        "derive_attribute_vertical",
        lambda *args, **kwargs: {"value": 40, "source_rule": "controlled_vertical", "evidence_keys": ("controlled.VERTICAL",)},
    )
    for height in (77.0, 79.0):
        result = derive_attribute_standingdunk(_evidence(height), league_player_rows=_population_rows())
        assert result is not None
        assert result["value"] == 25
        assert result["source_rule"] == "derive_attribute_standingdunk_lower_height_vertical_gate"


def test_clearing_vertical_40_does_not_create_high_standing_dunk(monkeypatch) -> None:
    monkeypatch.setattr(
        player_rules_offense,
        "derive_attribute_vertical",
        lambda *args, **kwargs: {"value": 41, "source_rule": "controlled_vertical", "evidence_keys": ("controlled.VERTICAL",)},
    )
    result = derive_attribute_standingdunk(_evidence(77.0), league_player_rows=_population_rows())
    assert result is not None
    assert 25 <= result["value"] <= 41
    assert "lower_height_vertical_cap=active" in result["evidence_keys"]


def test_standing_dunk_attribute_excludes_generic_finishing_statistics(monkeypatch) -> None:
    monkeypatch.setattr(
        player_rules_offense,
        "derive_attribute_vertical",
        lambda *args, **kwargs: {"value": 70, "source_rule": "controlled_vertical", "evidence_keys": ("controlled.VERTICAL",)},
    )
    low = _evidence(84.0)
    high = _evidence(84.0)
    low.per_game.update({"fg_percent": 0.20, "fga_per_game": 1.0})
    low.totals.update({"fga": 82.0})
    high.per_game.update({"fg_percent": 0.90, "fga_per_game": 30.0})
    high.totals.update({"fga": 2460.0})

    low_result = derive_attribute_standingdunk(low, league_player_rows=_population_rows())
    high_result = derive_attribute_standingdunk(high, league_player_rows=_population_rows())
    assert low_result is not None and high_result is not None
    assert low_result["value"] == high_result["value"]
    assert "no FG%, foul pressure, broad dunk total, or moving action evidence" in low_result["evidence_keys"][-2]
