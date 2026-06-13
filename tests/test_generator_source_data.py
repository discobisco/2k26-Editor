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
    def test_default_source_inventory_requires_only_sqlite_database(self) -> None:
        inventory = GeneratorSourceInventory.from_default()

        self.assertEqual(inventory.root.name, "NBA Player Data")
        self.assertEqual(inventory.root.parent.name, "Player Generator")
        self.assertTrue(inventory.database_path.is_file())
        self.assertEqual(inventory.database_path.name, "NBA_DATA_Master.sqlite")
        self.assertFalse(hasattr(inventory, "portraits_path"))
        self.assertFalse(hasattr(inventory, "logos_path"))

    def test_sheet_inventory_reads_sqlite_metadata(self) -> None:
        inventory = GeneratorSourceInventory.from_default()
        sheets = inventory.workbook_sheets()

        self.assertIn("Player Per Game", sheets)
        self.assertIn("Team Stats Per Game", sheets)
        self.assertIn("Advanced", sheets)
        self.assertIn("Team Summaries", sheets)

    def test_phase_zero_required_sheets_are_present_in_current_sqlite_database(self) -> None:
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

    def test_missing_sqlite_database_fails_loud_without_note_files_requirement(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Player Portraits.txt").write_text("notes", encoding="utf-8")
            (root / "Team Logos.txt").write_text("notes", encoding="utf-8")

            with self.assertRaises(FileNotFoundError) as raised:
                GeneratorSourceInventory.from_root(root)

        self.assertIn("NBA_DATA_Master.sqlite", str(raised.exception))
        self.assertNotIn("Player Portraits.txt", str(raised.exception))
        self.assertNotIn("Team Logos.txt", str(raised.exception))

    def test_generator_source_data_has_no_excel_notes_or_random_runtime_dependency(self) -> None:
        source = inspect.getsource(source_data)

        for banned in (
            "import random",
            "openpyxl",
            "pandas",
            "xlrd",
            "xlsxwriter",
            "GameMemory",
            "zipfile",
            "ElementTree",
            "NBA DATA Master.xlsx",
            "Player Portraits.txt",
            "Team Logos.txt",
            "sidecar_counts",
        ):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
