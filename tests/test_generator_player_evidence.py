from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget
from player_evidence import PlayerEvidence, build_player_evidence
from source_data import GeneratorSourceInventory


class GeneratorPlayerEvidenceTests(unittest.TestCase):
    def _contract(self, season: int) -> GeneratorInputContract:
        source_root = GeneratorSourceInventory.from_default().root
        return GeneratorInputContract(season=season, source_root=source_root, output_target=OutputTarget.PROPOSAL).validate()

    def test_2025_player_evidence_includes_player_and_team_context(self) -> None:
        evidence = build_player_evidence(self._contract(2025), player_id="achiupr01", team="NYK")

        self.assertIsInstance(evidence, PlayerEvidence)
        self.assertEqual(evidence.season, 2025)
        self.assertEqual(evidence.player_id, "achiupr01")
        self.assertEqual(evidence.team, "NYK")
        self.assertEqual(evidence.identity["player"], "Precious Achiuwa")
        self.assertEqual(evidence.season_info["team"], "NYK")
        self.assertEqual(len(evidence.team_roster), 21)
        self.assertIn("Jalen Brunson", {row["player"] for row in evidence.team_roster})
        self.assertIn("Karl-Anthony Towns", {row["player"] for row in evidence.team_roster})
        self.assertTrue(all(row["season"] == 2025 and row["team"] == "NYK" for row in evidence.team_roster))
        self.assertEqual(evidence.per_game["pts_per_game"], 6.6)
        self.assertEqual(evidence.per_100["pts_per_100_poss"], 16.1)
        self.assertIn("per", evidence.advanced)
        self.assertIn("avg_dist_fga", evidence.shooting)
        self.assertIn("pg_percent", evidence.play_by_play)
        self.assertEqual(evidence.team_stats_per_game["abbreviation"], "NYK")
        self.assertIn("pts_per_game", evidence.team_stats_per_game)
        self.assertEqual(evidence.team_summary["abbreviation"], "NYK")
        self.assertIn("o_rtg", evidence.team_summary)
        self.assertEqual(evidence.opponent_stats_per_game["abbreviation"], "NYK")
        self.assertIn("opp_pts_per_game", evidence.opponent_stats_per_game)
        self.assertEqual(evidence.missing_sources, ())

    def test_1947_player_evidence_keeps_partial_stats_and_missing_source_markers(self) -> None:
        evidence = build_player_evidence(self._contract(1947), player_id="abramjo01", team="PIT")

        self.assertEqual(evidence.season, 1947)
        self.assertEqual(evidence.player_id, "abramjo01")
        self.assertEqual(evidence.team, "PIT")
        self.assertEqual(evidence.identity["player"], "John Abramovic")
        self.assertEqual(evidence.per_game["pts_per_game"], 11.2)
        self.assertGreater(len(evidence.team_roster), 0)
        self.assertTrue(all(row["season"] == 1947 and row["team"] == "PIT" for row in evidence.team_roster))
        self.assertEqual(evidence.team_stats_per_game["abbreviation"], "PIT")
        self.assertEqual(evidence.per_100, {})
        self.assertEqual(evidence.shooting, {})
        self.assertEqual(evidence.play_by_play, {})
        self.assertIn("Player Per 100 Poss", evidence.missing_sources)
        self.assertIn("Player Shooting", evidence.missing_sources)
        self.assertIn("Player Play by Play", evidence.missing_sources)
        self.assertIn("Team Stats Per 100 Pos", evidence.missing_sources)
        self.assertIn("Opponent Stats Per 100 Poss", evidence.missing_sources)

    def test_missing_player_team_row_fails_for_wrong_identity_not_missing_modern_data(self) -> None:
        with self.assertRaises(KeyError):
            build_player_evidence(self._contract(2025), player_id="achiupr01", team="BOS")

    def test_player_evidence_module_has_no_random_excel_or_live_memory_dependency(self) -> None:
        import player_evidence

        source = inspect.getsource(player_evidence)
        for banned in ("import random", "openpyxl", "pandas", "xlrd", "xlsxwriter", "GameMemory"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
