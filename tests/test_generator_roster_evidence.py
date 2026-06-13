from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget
from roster_evidence import TeamRosterEvidence, build_team_roster_evidence
from source_data import GeneratorSourceInventory


class GeneratorRosterEvidenceTests(unittest.TestCase):
    def _contract(self, season: int) -> GeneratorInputContract:
        source_root = GeneratorSourceInventory.from_default().root
        return GeneratorInputContract(season=season, source_root=source_root, output_target=OutputTarget.PROPOSAL).validate()

    def test_2025_team_roster_evidence_preserves_full_selected_team_roster(self) -> None:
        evidence = build_team_roster_evidence(self._contract(2025), team="NYK")

        self.assertIsInstance(evidence, TeamRosterEvidence)
        self.assertEqual(evidence.season, 2025)
        self.assertEqual(evidence.team, "NYK")
        self.assertEqual(evidence.player_count, 21)
        self.assertEqual(len(evidence.roster_rows), 21)
        self.assertEqual(len(evidence.player_ids), 21)
        self.assertIn("brunsja01", evidence.player_ids)
        self.assertIn("townska01", evidence.player_ids)
        self.assertIn("Jalen Brunson", {row["player"] for row in evidence.roster_rows})
        self.assertTrue(all(row["season"] == 2025 and row["team"] == "NYK" for row in evidence.roster_rows))
        self.assertEqual(evidence.missing_sources, ())

    def test_1947_team_roster_evidence_keeps_roster_and_records_era_limited_sources(self) -> None:
        evidence = build_team_roster_evidence(self._contract(1947), team="PIT")

        self.assertEqual(evidence.season, 1947)
        self.assertEqual(evidence.team, "PIT")
        self.assertGreater(evidence.player_count, 0)
        self.assertIn("abramjo01", evidence.player_ids)
        self.assertTrue(all(row["season"] == 1947 and row["team"] == "PIT" for row in evidence.roster_rows))
        self.assertIn("Player Shooting", evidence.missing_sources)
        self.assertIn("Player Play by Play", evidence.missing_sources)
        self.assertIn("Team Stats Per 100 Pos", evidence.missing_sources)

    def test_unknown_team_roster_fails_because_selected_team_identity_is_absent(self) -> None:
        with self.assertRaises(KeyError):
            build_team_roster_evidence(self._contract(2025), team="XXX")

    def test_roster_evidence_module_has_no_random_excel_or_live_memory_dependency(self) -> None:
        import roster_evidence

        source = inspect.getsource(roster_evidence)
        for banned in ("import random", "openpyxl", "pandas", "xlrd", "xlsxwriter", "GameMemory"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
