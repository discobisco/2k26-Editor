from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(GENERATOR_ROOT))

from player_rules_offense import (  # noqa: E402
    derive_attribute_drivingdunk,
    derive_attribute_drivinglayup,
    derive_attribute_standingdunk,
    derive_tendency_alleyoop,
    derive_tendency_drivingdunk,
    derive_tendency_drivinglayup,
    derive_tendency_eurosteplayup,
    derive_tendency_flashydunk,
    derive_tendency_hopsteplayup,
    derive_tendency_spinlayup,
    derive_tendency_standingdunk,
)


class FakeRankings:
    def __init__(self, ranks: dict[str, float]) -> None:
        self.ranks = ranks

    def rank(self, _value: float, path: str) -> float:
        return self.ranks.get(path, 0.0)


def evidence(
    *,
    dunk_share: float,
    dunks: int,
    orb: float = 0.0,
    rim_fg: float = 0.0,
    short_fg: float = 0.0,
    assisted_x2p: float = 0.0,
    f_tr: float = 0.0,
    usage: float = 0.0,
    and1: int = 0,
    shooting_foul_drawn: int = 0,
    short_share: float = 0.0,
    rim_share: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        identity={"ht_in_in": 85, "wt": 260},
        shooting={
            "percent_dunks_of_fga": dunk_share,
            "num_of_dunks": dunks,
            "fg_percent_from_x0_3_range": rim_fg,
            "fg_percent_from_x3_10_range": short_fg,
            "percent_assisted_x2p_fg": assisted_x2p,
            "percent_fga_from_x0_3_range": rim_share,
            "percent_fga_from_x3_10_range": short_share,
        },
        per_game={"orb_per_game": orb},
        season_info={},
        totals={},
        per_36={},
        per_100={},
        advanced={"f_tr": f_tr, "usg_percent": usage},
        play_by_play={"and1": and1, "shooting_foul_drawn": shooting_foul_drawn},
        team_stats_per_game={},
        team_summary={},
        opponent_stats_per_game={},
    )


class PlayerGeneratorDunkRuleTests(unittest.TestCase):
    def test_driving_layup_uses_self_created_advanced_splits_not_raw_big_finishing(self) -> None:
        class ValueRankings:
            def rank(self, value: float, path: str) -> float:
                divisors = {
                    "advanced.usg_percent": 40.0,
                    "play_by_play.and1": 60.0,
                    "play_by_play.shooting_foul_drawn": 220.0,
                }
                if path in divisors:
                    return min(max(value / divisors[path], 0.0), 1.0)
                return min(max(value, 0.0), 1.0)

        creator = evidence(
            dunk_share=0.01,
            dunks=3,
            rim_fg=0.75,
            short_fg=0.55,
            assisted_x2p=0.20,
            f_tr=0.45,
            usage=32.0,
            and1=50,
            shooting_foul_drawn=180,
            short_share=0.24,
            rim_share=0.22,
        )
        assisted_dunk_big = evidence(
            dunk_share=0.45,
            dunks=160,
            rim_fg=0.80,
            short_fg=0.60,
            assisted_x2p=0.85,
            f_tr=0.55,
            usage=18.0,
            and1=15,
            shooting_foul_drawn=110,
            short_share=0.10,
            rim_share=0.55,
        )

        creator_attribute = derive_attribute_drivinglayup(creator, league_player_rows=ValueRankings())
        big_attribute = derive_attribute_drivinglayup(assisted_dunk_big, league_player_rows=ValueRankings())
        self.assertGreater(creator_attribute["value"], big_attribute["value"])
        self.assertIn("advanced.f_tr", creator_attribute["evidence_keys"])
        self.assertIn("shooting.percent_fga_from_x0_3_range", creator_attribute["evidence_keys"])
        self.assertIn("shooting.percent_fga_from_x3_10_range", creator_attribute["evidence_keys"])
        self.assertIn("play_by_play.shooting_foul_drawn", creator_attribute["evidence_keys"])
        self.assertIn("shooting.percent_assisted_x2p_fg", creator_attribute["evidence_keys"])
        self.assertIn("shooting.percent_dunks_of_fga", creator_attribute["evidence_keys"])
        self.assertNotIn("per_game.x2p_percent", creator_attribute["evidence_keys"])
        self.assertNotIn("per_game.fg_percent", creator_attribute["evidence_keys"])
        self.assertNotIn("per_game.fta_per_game", creator_attribute["evidence_keys"])

        creator_tendencies = (
            derive_tendency_drivinglayup(creator, league_player_rows=ValueRankings()),
            derive_tendency_eurosteplayup(creator, league_player_rows=ValueRankings()),
            derive_tendency_hopsteplayup(creator, league_player_rows=ValueRankings()),
            derive_tendency_spinlayup(creator, league_player_rows=ValueRankings()),
        )
        big_tendencies = (
            derive_tendency_drivinglayup(assisted_dunk_big, league_player_rows=ValueRankings()),
            derive_tendency_eurosteplayup(assisted_dunk_big, league_player_rows=ValueRankings()),
            derive_tendency_hopsteplayup(assisted_dunk_big, league_player_rows=ValueRankings()),
            derive_tendency_spinlayup(assisted_dunk_big, league_player_rows=ValueRankings()),
        )
        for creator_tendency, big_tendency in zip(creator_tendencies, big_tendencies, strict=True):
            self.assertGreater(creator_tendency["value"], big_tendency["value"])
            self.assertIn("advanced.f_tr", creator_tendency["evidence_keys"])
            self.assertNotIn("per_game.fta_per_game", creator_tendency["evidence_keys"])
            self.assertNotIn("per_game.x2pa_per_game", creator_tendency["evidence_keys"])

    def test_dunk_rules_are_driven_by_actual_dunk_stats_not_height_identity(self) -> None:
        rankings = FakeRankings({
            "shooting.percent_dunks_of_fga": 1.0,
            "shooting.num_of_dunks": 1.0,
            "per_game.orb_per_game": 1.0,
            "advanced.usg_percent": 1.0,
            "play_by_play.shooting_foul_drawn": 1.0,
            "play_by_play.and1": 1.0,
            "advanced.f_tr": 1.0,
            "shooting.percent_fga_from_x0_3_range": 1.0,
            "shooting.fg_percent_from_x0_3_range": 1.0,
            "shooting.percent_assisted_x2p_fg": 0.0,
        })
        player = evidence(dunk_share=0.45, dunks=180, orb=4.0)

        results = (
            derive_attribute_drivingdunk(player, league_player_rows=rankings),
            derive_attribute_standingdunk(player, league_player_rows=rankings),
            derive_tendency_drivingdunk(player, league_player_rows=rankings),
            derive_tendency_flashydunk(player, league_player_rows=rankings),
            derive_tendency_standingdunk(player, league_player_rows=rankings),
            derive_tendency_alleyoop(player, league_player_rows=rankings),
        )

        for result in results:
            self.assertNotIn("identity.ht_in_in", result["evidence_keys"])
            self.assertNotIn("identity.wt", result["evidence_keys"])
        self.assertGreaterEqual(results[0]["value"], 88)
        self.assertGreaterEqual(results[1]["value"], 88)
        self.assertGreaterEqual(results[2]["value"], 85)
        self.assertGreaterEqual(results[4]["value"], 85)

    def test_no_actual_dunk_stats_keeps_dunk_values_low_even_for_tall_players(self) -> None:
        driving_rankings = FakeRankings({
            "shooting.percent_dunks_of_fga": 0.0,
            "shooting.num_of_dunks": 0.0,
            "advanced.usg_percent": 0.0,
            "play_by_play.shooting_foul_drawn": 0.0,
            "play_by_play.and1": 0.0,
            "advanced.f_tr": 0.0,
            "shooting.percent_fga_from_x0_3_range": 0.0,
            "shooting.fg_percent_from_x0_3_range": 0.0,
            "shooting.percent_assisted_x2p_fg": 1.0,
            "per_game.orb_per_game": 1.0,
        })
        standing_rankings = FakeRankings({
            "shooting.percent_dunks_of_fga": 0.0,
            "shooting.num_of_dunks": 0.0,
            "per_game.orb_per_game": 0.0,
            "advanced.f_tr": 0.0,
            "shooting.percent_fga_from_x0_3_range": 0.0,
            "shooting.fg_percent_from_x0_3_range": 0.0,
        })
        player = evidence(dunk_share=0.0, dunks=0, orb=0.0)

        self.assertEqual(25, derive_attribute_drivingdunk(player, league_player_rows=driving_rankings)["value"])
        self.assertEqual(25, derive_attribute_standingdunk(player, league_player_rows=standing_rankings)["value"])
        self.assertEqual(0, derive_tendency_drivingdunk(player, league_player_rows=driving_rankings)["value"])
        self.assertEqual(0, derive_tendency_standingdunk(player, league_player_rows=standing_rankings)["value"])


if __name__ == "__main__":
    unittest.main()
