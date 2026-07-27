from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import derive_formula_rule_values, derive_neighbor_rule_values  # type: ignore[import-not-found]
from stat_neighbor_framework import PositionSelection  # type: ignore[import-not-found]


def _evidence(*, player_fga: object, team_fga_per_game: object, team_games: object) -> PlayerEvidence:
    return PlayerEvidence(
        player_id="test",
        season=2025,
        team="TST",
        identity={},
        season_info={"pos": "PG"},
        per_game={"fga_per_game": 99.0},
        totals={"fga": player_fga},
        per_36={},
        per_100={},
        advanced={"usg_percent": 99.0},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={"fga_per_game": team_fga_per_game, "g": team_games},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )


def _row(*, player_fga: float, team_fga_per_game: float = 100.0, team_games: float = 80.0) -> dict[str, float]:
    return {
        "player_totals.fga": player_fga,
        "team_stats_per_game.fga_per_game": team_fga_per_game,
        "team_stats_per_game.g": team_games,
    }


def test_shot_tendency_is_unresolved_without_player_or_team_totals() -> None:
    rows = (_row(player_fga=80),)

    assert "Tendencies/SHOT" not in derive_formula_rule_values(
        _evidence(player_fga=None, team_fga_per_game=100, team_games=80),
        league_player_rows=rows,
    )
    assert "Tendencies/SHOT" not in derive_formula_rule_values(
        _evidence(player_fga=200, team_fga_per_game=None, team_games=80),
        league_player_rows=rows,
    )
    assert "Tendencies/SHOT" not in derive_formula_rule_values(
        _evidence(player_fga=200, team_fga_per_game=100, team_games=None),
        league_player_rows=rows,
    )


@dataclass(frozen=True)
class _Suggestion:
    value: int
    source_rule: str
    evidence_keys: tuple[str, ...]


class _NeighborModel:
    def suggestions_for_evidence(self, *, evidence: Any, positions: Any) -> dict[str, _Suggestion]:
        return {
            "Tendencies/SHOT": _Suggestion(99, "neighbor_shot", ("neighbor",)),
            "Tendencies/DRIVE": _Suggestion(45, "neighbor_drive", ("neighbor",)),
        }
