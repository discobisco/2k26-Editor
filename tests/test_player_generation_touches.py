from __future__ import annotations

import sys
from pathlib import Path


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import derive_formula_rule_values  # type: ignore[import-not-found]
from player_rules_mental import derive_tendency_touches  # type: ignore[import-not-found]


def _evidence(
    *,
    player_fga: object,
    player_ast: object,
    team_fga_per_game: object,
    team_ast_per_game: object,
    team_games: object = 10.0,
    usg_percent: object = 20.0,
) -> PlayerEvidence:
    return PlayerEvidence(
        player_id="test",
        season=2025,
        team="TST",
        identity={},
        season_info={"season": 2025, "lg": "NBA", "team": "TST", "pos": "PG"},
        per_game={"g": 10.0},
        totals={"fga": player_fga, "ast": player_ast},
        per_36={},
        per_100={},
        advanced={"usg_percent": usg_percent},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={
            "g": team_games,
            "fga_per_game": team_fga_per_game,
            "ast_per_game": team_ast_per_game,
        },
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )


def _row(
    *,
    team: str,
    player_fga: float,
    player_ast: float,
    team_fga_per_game: float,
    team_ast_per_game: float,
    usg_percent: float = 20.0,
) -> dict[str, object]:
    return {
        "season": 2025,
        "player_season_info.lg": "NBA",
        "player_season_info.team": team,
        "player_per_game.g": 10.0,
        "player_totals.fga": player_fga,
        "player_totals.ast": player_ast,
        "player_advanced.usg_percent": usg_percent,
        "team_stats_per_game.g": 10.0,
        "team_stats_per_game.fga_per_game": team_fga_per_game,
        "team_stats_per_game.ast_per_game": team_ast_per_game,
    }


def test_touches_uses_player_share_of_team_fga_and_assists() -> None:
    rows = (
        _row(team="LOW", player_fga=100.0, player_ast=20.0, team_fga_per_game=100.0, team_ast_per_game=20.0),
        _row(team="HIGH", player_fga=100.0, player_ast=20.0, team_fga_per_game=50.0, team_ast_per_game=10.0),
    )
    low_share = _evidence(
        player_fga=100.0,
        player_ast=20.0,
        team_fga_per_game=100.0,
        team_ast_per_game=20.0,
    )
    high_share = _evidence(
        player_fga=100.0,
        player_ast=20.0,
        team_fga_per_game=50.0,
        team_ast_per_game=10.0,
    )

    low = derive_tendency_touches(low_share, league_player_rows=rows)
    high = derive_tendency_touches(high_share, league_player_rows=rows)

    assert low is not None and high is not None
    assert high["value"] > low["value"]
    assert "fga_share=0.20000000" in high["evidence_keys"]
    assert "ast_share=0.20000000" in high["evidence_keys"]


def test_touches_is_invariant_to_raw_scale_when_team_shares_match() -> None:
    rows = (
        _row(team="A", player_fga=100.0, player_ast=20.0, team_fga_per_game=100.0, team_ast_per_game=20.0),
        _row(team="B", player_fga=200.0, player_ast=40.0, team_fga_per_game=200.0, team_ast_per_game=40.0),
    )
    first = derive_tendency_touches(
        _evidence(player_fga=100.0, player_ast=20.0, team_fga_per_game=100.0, team_ast_per_game=20.0),
        league_player_rows=rows,
    )
    second = derive_tendency_touches(
        _evidence(player_fga=200.0, player_ast=40.0, team_fga_per_game=200.0, team_ast_per_game=40.0),
        league_player_rows=rows,
    )

    assert first is not None and second is not None
    assert first["value"] == second["value"]


def test_touches_survives_formula_assembly_instead_of_receiving_set_zero() -> None:
    rows = (
        _row(team="LOW", player_fga=100.0, player_ast=20.0, team_fga_per_game=100.0, team_ast_per_game=20.0),
        _row(team="TST", player_fga=200.0, player_ast=40.0, team_fga_per_game=100.0, team_ast_per_game=20.0),
    )
    evidence = _evidence(
        player_fga=200.0,
        player_ast=40.0,
        team_fga_per_game=100.0,
        team_ast_per_game=20.0,
    )

    result = derive_formula_rule_values(evidence, league_player_rows=rows)["Tendencies/TOUCHES"]

    assert result.value > 0
    assert result.source_rule == "derive_tendency_touches_team_offensive_share"
    assert "totals.fga" in result.evidence_keys
    assert "totals.ast" in result.evidence_keys
    assert "advanced.usg_percent" in result.evidence_keys


def test_historical_touches_uses_fgm_and_fta_team_shares_when_fga_ast_usg_are_unrecorded() -> None:
    evidence = PlayerEvidence(
        player_id="mikange01",
        season=1947,
        team="CAG",
        identity={},
        season_info={"season": 1947, "lg": "NBL", "team": "CAG", "pos": "C"},
        per_game={"g": 44.0},
        totals={"fg": 147.0, "fta": 164.0},
        per_36={},
        per_100={},
        advanced={},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={"g": 44.0, "fg_per_game": 22.4, "fta_per_game": 20.1},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )
    rows = (
        {
            "season": 1947,
            "player_season_info.lg": "NBL",
            "player_per_game.g": 44.0,
            "player_totals.fg": 50.0,
            "player_totals.fta": 40.0,
            "team_stats_per_game.g": 44.0,
            "team_stats_per_game.fg_per_game": 22.4,
            "team_stats_per_game.fta_per_game": 20.1,
        },
        {
            "season": 1947,
            "player_season_info.lg": "NBL",
            "player_per_game.g": 44.0,
            "player_totals.fg": 147.0,
            "player_totals.fta": 164.0,
            "team_stats_per_game.g": 44.0,
            "team_stats_per_game.fg_per_game": 22.4,
            "team_stats_per_game.fta_per_game": 20.1,
        },
    )

    direct = derive_tendency_touches(evidence, league_player_rows=rows)
    integrated = derive_formula_rule_values(evidence, league_player_rows=rows)["Tendencies/TOUCHES"]

    assert direct is not None and direct["value"] > 0
    assert direct["source_rule"] == "derive_tendency_touches_historical_team_scoring_opportunity_share"
    assert "fgm_share=0.14914773" in direct["evidence_keys"]
    assert "fta_share=0.18543645" in direct["evidence_keys"]
    assert integrated.value == direct["value"]
    assert integrated.source_rule == direct["source_rule"]


def test_touches_remains_unresolved_when_no_team_share_or_usage_evidence_exists() -> None:
    evidence = _evidence(
        player_fga=None,
        player_ast=None,
        team_fga_per_game=None,
        team_ast_per_game=None,
        usg_percent=None,
    )
    assert derive_tendency_touches(evidence, league_player_rows=()) is None
