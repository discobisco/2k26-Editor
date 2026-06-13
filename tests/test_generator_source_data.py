from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

import source_data
from source_data import GeneratorSourceInventory


class GeneratorSourceDataTests(unittest.TestCase):
    def test_default_source_inventory_uses_current_player_generator_folder(self) -> None:
        inventory = GeneratorSourceInventory.from_default()

        self.assertEqual(inventory.root.name, "NBA Player Data")
        self.assertEqual(inventory.root.parent.name, "Player Generator")
        self.assertTrue(inventory.workbook_path.is_file())
        self.assertTrue(inventory.portraits_path.is_file())
        self.assertTrue(inventory.logos_path.is_file())
        self.assertEqual(inventory.workbook_path.name, "NBA DATA Master.xlsx")
        self.assertEqual(inventory.portraits_path.name, "Player Portraits.txt")
        self.assertEqual(inventory.logos_path.name, "Team Logos.txt")

    def test_workbook_sheet_inventory_reads_xlsx_metadata_with_stdlib(self) -> None:
        inventory = GeneratorSourceInventory.from_default()
        sheets = inventory.workbook_sheets()

        self.assertIn("Player Per Game", sheets)
        self.assertIn("Team Stats Per Game", sheets)
        self.assertIn("Advanced", sheets)
        self.assertIn("Team Summaries", sheets)

    def test_sidecar_inventory_reads_portraits_and_logos(self) -> None:
        inventory = GeneratorSourceInventory.from_default()
        sidecars = inventory.sidecar_counts()

        self.assertGreater(sidecars["portraits"], 1000)
        self.assertGreater(sidecars["logos"], 30)

    def test_phase_zero_required_sheets_are_present_in_current_workbook(self) -> None:
        inventory = GeneratorSourceInventory.from_default()

        self.assertEqual(inventory.missing_required_sheets(), [])
        self.assertLessEqual(
            {
                "Player Info",
                "Player Season Info",
                "Player Per Game",
                "Player Per 100 Poss",
                "Advanced",
                "Player Shooting",
                "Player Play by Play",
                "Team Stats Per Game",
                "Team Stats Per 100 Pos",
                "Team Summaries",
                "Opponent Stats Per Game",
                "Opponent Stats Per 100 Poss",
            },
            set(inventory.required_phase_zero_sheets()),
        )

    def test_missing_source_root_fails_loud(self) -> None:
        missing_root = Path("/tmp/does-not-exist-for-nba2k-generator")

        with self.assertRaises(FileNotFoundError):
            GeneratorSourceInventory.from_root(missing_root)

    def test_generator_source_data_has_no_excel_or_random_runtime_dependency(self) -> None:
        source = inspect.getsource(source_data)

        for banned in ("import random", "openpyxl", "pandas", "xlrd", "xlsxwriter", "GameMemory"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
