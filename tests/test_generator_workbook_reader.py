from __future__ import annotations

import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget
from source_data import GeneratorSourceInventory
from workbook_reader import read_sheet_rows_for_season


class GeneratorWorkbookReaderTests(unittest.TestCase):
    def _contract(self) -> GeneratorInputContract:
        source_root = GeneratorSourceInventory.from_default().root
        return GeneratorInputContract(season=2025, source_root=source_root, output_target=OutputTarget.PROPOSAL).validate()

    def test_reads_player_stat_rows_for_selected_season_only(self) -> None:
        contract = self._contract()

        rows = read_sheet_rows_for_season(contract, "Player Per Game", limit=25)

        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["season"] == 2025 for row in rows))
        self.assertTrue(all(row.get("player_id") for row in rows))
        self.assertTrue(all("pts_per_game" in row for row in rows))

    def test_reads_team_stat_rows_for_selected_season_only(self) -> None:
        contract = self._contract()

        rows = read_sheet_rows_for_season(contract, "Team Stats Per Game", limit=25)

        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["season"] == 2025 for row in rows))
        self.assertTrue(all(row.get("team") for row in rows))
        self.assertTrue(all("pts_per_game" in row for row in rows))

    def test_blank_and_na_cells_are_normalized_to_none(self) -> None:
        contract = self._contract()

        rows = read_sheet_rows_for_season(contract, "Player Shooting", limit=200)

        self.assertGreater(len(rows), 0)
        self.assertTrue(any(value is None for row in rows for value in row.values()))

    def test_unknown_sheet_fails_loud(self) -> None:
        contract = self._contract()

        with self.assertRaises(KeyError):
            read_sheet_rows_for_season(contract, "No Such Sheet")


if __name__ == "__main__":
    unittest.main()
