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


def test_pre_shot_clock_attribute_without_source_is_not_filled_from_a_role_block() -> None:
    result = derive_attribute_closeshot(
        _namespace_evidence(season=1947, league="BAA", position="G"),
        league_player_rows=(),
    )

    assert result is None
