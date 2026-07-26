from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import derive_player_rule_values  # type: ignore[import-not-found]
from player_rules_athleticism import derive_attribute_speed  # type: ignore[import-not-found]
from player_rules_defense import derive_attribute_steal  # type: ignore[import-not-found]
from player_rules_offense import derive_attribute_closeshot, derive_attribute_passiq  # type: ignore[import-not-found]


def _namespace_evidence(
    *,
    season: int = 2026,
    league: str = "NBA",
    position: str = "PG",
    height: float = 73.0,
    weight: float = 180.0,
    age: float = 25.0,
    assists: float | None = None,
    total_assists: float | None = None,
    team_assists_per_game: float | None = None,
    team_games: float | None = None,
    steals: float | None = None,
    steal_percent: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        season=season,
        identity={"pos": position, "ht_in_in": height, "wt": weight},
        season_info={"lg": league, "pos": position, "age": age},
        per_game={"ast_per_game": assists, "stl_per_game": steals},
        totals={"ast": total_assists},
        per_36={},
        per_100={},
        advanced={"stl_percent": steal_percent},
        shooting={},
        play_by_play={},
        team_stats_per_game={"ast_per_game": team_assists_per_game, "g": team_games},
        team_summary={},
        opponent_stats_per_game={},
    )


def test_athletic_formula_can_move_past_captured_q75_without_a_band_gate() -> None:
    result = derive_attribute_speed(
        _namespace_evidence(position="PG", height=65.0, weight=120.0),
    )

    assert result is not None
    assert result["value"] > 85  # editor_capture_003 PG Speed q75
    assert result["value"] <= 99
    assert "pool_quantiles_are_distribution_evidence_not_rating_gates" in result["evidence_keys"]


def test_defense_calibration_can_move_past_its_old_field_maximum() -> None:
    rows = tuple(
        {
            "advanced.stl_percent": float(value),
            "per_game.stl_per_game": float(value),
        }
        for value in range(100)
    )
    result = derive_attribute_steal(
        _namespace_evidence(steals=99.0, steal_percent=99.0),
        league_player_rows=rows,
    )

    assert result is not None
    assert result["value"] > 90  # old non-domain Steal maximum
    assert result["value"] <= 99


def test_pre_shot_clock_pass_iq_blends_inputs_without_the_old_absolute_cap() -> None:
    result = derive_attribute_passiq(
        _namespace_evidence(
            season=1947,
            league="BAA",
            position="G",
            assists=10.0,
            total_assists=600.0,
            team_assists_per_game=20.0,
            team_games=60.0,
        ),
    )

    assert result is not None
    assert result["value"] > 78  # old absolute-AST ceiling
    assert result["value"] <= 99
    assert "neither input gates the other" in " ".join(result["evidence_keys"])


def test_pre_shot_clock_attribute_without_source_is_not_filled_from_a_role_block() -> None:
    result = derive_attribute_closeshot(
        _namespace_evidence(season=1947, league="BAA", position="G"),
        league_player_rows=(),
    )

    assert result is None


def test_intangibles_formula_is_not_overwritten_with_fixed_25() -> None:
    evidence = PlayerEvidence(
        player_id="impact-player",
        season=2026,
        team="TST",
        identity={"pos": "SF"},
        season_info={"lg": "NBA", "pos": "SF", "age": 27},
        per_game={"g": 82.0},
        totals={},
        per_36={},
        per_100={},
        advanced={"ws": 12.0, "per": 24.0, "bpm": 7.0, "vorp": 5.0},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={"srs": 6.0},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )
    rows = (
        {"player_season_info.lg": "NBA", "player_advanced.ws": 1.0, "player_advanced.per": 10.0, "player_advanced.bpm": -2.0, "team_summary.srs": -4.0},
        {"player_season_info.lg": "NBA", "player_advanced.ws": 12.0, "player_advanced.per": 24.0, "player_advanced.bpm": 7.0, "team_summary.srs": 6.0},
    )

    result = derive_player_rule_values(
        evidence,
        league_player_rows=rows,
        active_field_keys={"Attributes/INTANGIBLES"},
    ).values["Attributes/INTANGIBLES"]

    assert result.value > 25
    assert result.source_rule == "hybrid_formula_only"
    assert "fixed_intangibles_25" not in result.evidence_keys
