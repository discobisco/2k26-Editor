from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_defense import (  # type: ignore[import-not-found]  # noqa: E402
    derive_tendency_blockshot,
    derive_tendency_contestshot,
    derive_tendency_foul,
    derive_tendency_onballsteal,
    derive_tendency_passinterception,
    derive_tendency_takecharge,
)


def _evidence(*, level: float, dcontest: float | None = None) -> SimpleNamespace:
    games = 82.0
    return SimpleNamespace(
        player_id="test01",
        team="AAA",
        season=2026,
        identity={"player_id": "test01", "pos": "SG", "ht_in_in": 77.0, "wt": 205.0},
        season_info={"lg": "NBA", "team": "AAA", "pos": "SG"},
        per_game={
            "g": games,
            "blk_per_game": 3.0 * level,
            "stl_per_game": 3.0 * level,
            "pf_per_game": 0.5 + 4.0 * level,
        },
        per_36={"pf_per_36_min": 0.5 + 4.0 * level},
        per_100={
            "blk_per_100_poss": 5.0 * level,
            "stl_per_100_poss": 5.0 * level,
        },
        advanced={
            "blk_percent": 8.0 * level,
            "stl_percent": 5.0 * level,
            "dws": 8.0 * level,
            "dbpm": -2.0 + 8.0 * level,
        },
        crafted={"disruption_per_100": 8.0 * level, "stock_percent": 8.0 * level},
        play_by_play={
            "shooting_foul_committed": games * (0.1 + level),
            "offensive_foul_drawn": games * level,
        },
        shotquality_contest={} if dcontest is None else {
            "dcontest": dcontest,
            "nba_id": "1",
            "season": 2026,
            "identity_contract": "crafted_player_id_map.status=mapped;nba_id_only;no_name_fallback",
        },
        team_summary={},
        team_stats_per_game={},
        opponent_stats_per_game={},
    )


def _rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "season": 2026,
            "player_season_info.lg": "NBA",
            "player_season_info.team": "AAA",
            "player_season_info.pos": "SG",
            "player_info.ht_in_in": 77.0,
            "player_info.wt": 205.0,
            "player_per_game.g": 82.0,
            "player_per_game.blk_per_game": 3.0 * level,
            "player_per_game.stl_per_game": 3.0 * level,
            "player_per_game.pf_per_game": 0.5 + 4.0 * level,
            "player_per_36_min.pf_per_36_min": 0.5 + 4.0 * level,
            "player_per_100_poss.blk_per_100_poss": 5.0 * level,
            "player_per_100_poss.stl_per_100_poss": 5.0 * level,
            "advanced.blk_percent": 8.0 * level,
            "advanced.stl_percent": 5.0 * level,
            "advanced.dws": 8.0 * level,
            "advanced.dbpm": -2.0 + 8.0 * level,
            "player_play_by_play.shooting_foul_committed": 82.0 * (0.1 + level),
            "player_play_by_play.offensive_foul_drawn": 82.0 * level,
            "crafted_source_shotquality.dcontest": -3.0 + 6.0 * level,
        }
        for level in (index / 12.0 for index in range(1, 12))
    )


def test_only_data_master_dcontest_authors_contest_shot() -> None:
    rows = _rows()
    low = _evidence(level=0.50, dcontest=-2.5)
    high = _evidence(level=0.50, dcontest=2.5)

    low_result = derive_tendency_contestshot(low, league_player_rows=rows)
    high_result = derive_tendency_contestshot(high, league_player_rows=rows)

    assert low_result is not None and high_result is not None
    assert low_result["value"] < high_result["value"]
    assert high_result["source_rule"] == "derive_tendency_contestshot_data_master_dcontest_rank"
    assert "shotquality_contest.dcontest" in high_result["evidence_keys"]
    assert "source_database=NBA_DATA_Master.sqlite" in high_result["evidence_keys"]
    assert "identity=crafted_player_id_map.status=mapped;nba_id_only;no_name_fallback" in high_result["evidence_keys"]
    assert all("Pool" not in key and "nba.sqlite" not in key for key in high_result["evidence_keys"])


def test_missing_dcontest_does_not_turn_skill_or_outcome_stats_into_contest_appetite() -> None:
    rows = _rows()
    low_skill = _evidence(level=0.05)
    high_skill = _evidence(level=0.95)

    assert derive_tendency_contestshot(low_skill, league_player_rows=rows) is None
    assert derive_tendency_contestshot(high_skill, league_player_rows=rows) is None


def test_block_and_steal_outcomes_do_not_author_attempt_tendencies() -> None:
    rows = _rows()
    low = _evidence(level=0.05, dcontest=-1.0)
    high = _evidence(level=0.95, dcontest=1.0)

    for derive in (
        derive_tendency_blockshot,
        derive_tendency_onballsteal,
        derive_tendency_passinterception,
    ):
        assert derive(low, league_player_rows=rows) is None
        assert derive(high, league_player_rows=rows) is None


def test_foul_and_take_charge_keep_their_data_master_event_values() -> None:
    rows = _rows()
    low = _evidence(level=0.05)
    high = _evidence(level=0.95)

    low_foul = derive_tendency_foul(low, league_player_rows=rows)
    high_foul = derive_tendency_foul(high, league_player_rows=rows)
    low_charge = derive_tendency_takecharge(low, league_player_rows=rows)
    high_charge = derive_tendency_takecharge(high, league_player_rows=rows)

    assert low_foul is not None and high_foul is not None
    assert low_charge is not None and high_charge is not None
    assert low_foul["value"] < high_foul["value"]
    assert low_charge["value"] < high_charge["value"]
    assert "derived.offensive_foul_drawn_per_game" in high_charge["evidence_keys"]
