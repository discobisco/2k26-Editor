from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_rules_defense import derive_attribute_defenseconsistency  # type: ignore[import-not-found]
from player_rules_offense import derive_attribute_offensiveconsistency  # type: ignore[import-not-found]
from player_rules_rebounding import (  # type: ignore[import-not-found]
    derive_attribute_defensiverebound,
    derive_attribute_offensiverebound,
)


MAPPING = "mapping=round(25+74*same_season_same_league_rank_score)"


def _evidence() -> SimpleNamespace:
    return SimpleNamespace(
        player_id="target01",
        season=2025,
        team="TST",
        identity={"player_id": "target01", "pos": "SF", "ht_in_in": 78.0, "wt": 210.0},
        season_info={"season": 2025, "lg": "NBA", "team": "TST", "pos": "SF"},
        per_game={"g": 20.0, "pts_per_game": 15.0},
        totals={"pts": 300.0, "fga": 250.0},
        per_36={"pts_per_36_min": 20.0},
        per_100={},
        advanced={
            "ts_percent": 0.58,
            "tov_percent": 12.0,
            "orb_percent": 8.0,
            "drb_percent": 20.0,
        },
        shooting={},
        play_by_play={},
        team_totals={"pts": 2000.0, "fga": 1700.0},
        team_stats_per_game={},
        team_summary={},
        opponent_stats_per_game={},
        source_context={},
    )


def _row(*, position: str, height: float, weight: float, pts36: float, ts: float, tov: float, orb: float, drb: float) -> dict[str, object]:
    return {
        "season": 2025,
        "player_season_info.season": 2025,
        "player_season_info.lg": "NBA",
        "player_season_info.pos": position,
        "player_per_game.g": 20.0,
        "player_per_36_min.pts_per_36_min": pts36,
        "player_totals.pts": pts36 * 15.0,
        "team_totals.pts": 2000.0,
        "advanced.ts_percent": ts,
        "advanced.tov_percent": tov,
        "advanced.orb_percent": orb,
        "advanced.drb_percent": drb,
        "player_info.ht_in_in": height,
        "player_info.wt": weight,
    }


def _rows() -> tuple[dict[str, object], ...]:
    return (
        _row(position="PG", height=72.0, weight=180.0, pts36=10.0, ts=0.50, tov=18.0, orb=2.0, drb=8.0),
        _row(position="SF", height=78.0, weight=210.0, pts36=20.0, ts=0.58, tov=12.0, orb=8.0, drb=20.0),
        _row(position="C", height=84.0, weight=250.0, pts36=30.0, ts=0.65, tov=8.0, orb=15.0, drb=30.0),
    )


def test_rebound_attributes_map_rank_score_directly_to_25_99() -> None:
    evidence = _evidence()
    for derive in (derive_attribute_offensiverebound, derive_attribute_defensiverebound):
        result = derive(evidence, league_player_rows=_rows())
        assert result is not None
        assert result["value"] == round(25 + 74 * result["score"])
        assert MAPPING in result["evidence_keys"]


def test_offensive_consistency_maps_weighted_rank_score_directly_to_25_99() -> None:
    result = derive_attribute_offensiveconsistency(_evidence(), league_player_rows=_rows())
    assert result is not None
    rank_entry = next(key for key in result["evidence_keys"] if key.startswith("rank_score="))
    score = float(rank_entry.split("=", 1)[1])
    assert result["value"] == round(25 + 74 * score)
    assert MAPPING in result["evidence_keys"]


def test_defense_consistency_maps_context_rank_directly_to_25_99() -> None:
    result = derive_attribute_defenseconsistency(_evidence(), league_player_rows=_rows())
    assert result is not None
    assert result["value"] == round(25 + 74 * result["score"])
    assert MAPPING in result["evidence_keys"]
