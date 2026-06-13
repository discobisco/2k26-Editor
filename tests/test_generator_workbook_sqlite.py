from __future__ import annotations

import inspect
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

import workbook_sqlite
from source_data import GeneratorSourceInventory
from workbook_sqlite import ensure_workbook_sqlite_database, query_rows_for_season, workbook_sqlite_tables


class GeneratorWorkbookSqliteTests(unittest.TestCase):
    def test_sqlite_database_is_required_generator_source(self) -> None:
        inventory = GeneratorSourceInventory.from_default()
        database_path = ensure_workbook_sqlite_database(inventory.root)

        self.assertEqual(database_path, inventory.database_path)
        self.assertTrue(database_path.is_file())
        tables = workbook_sqlite_tables(database_path)
        self.assertEqual(len(tables), 22)
        self.assertEqual(sum(table.row_count for table in tables), 263_619)
        table_by_sheet = {table.sheet_name: table for table in tables}
        self.assertEqual(table_by_sheet["Player Per Game"].table_name, "player_per_game")
        self.assertEqual(table_by_sheet["Team Stats Per 100 Pos"].table_name, "team_stats_per_100_pos")
        self.assertEqual(table_by_sheet["All team Voting"].table_name, "all_team_voting")

    def test_metadata_preserves_sheet_and_column_mappings(self) -> None:
        inventory = GeneratorSourceInventory.from_default()
        tables = workbook_sqlite_tables(inventory.database_path)
        table_by_sheet = {table.sheet_name: table for table in tables}
        self.assertEqual(table_by_sheet["Advanced"].table_name, "advanced")
        self.assertGreater(table_by_sheet["Advanced"].row_count, 30_000)

        with sqlite3.connect(inventory.database_path) as connection:
            columns = connection.execute(
                """
                SELECT source_column, column_name, storage_type
                FROM workbook_columns
                WHERE table_name = 'advanced'
                ORDER BY ordinal
                """
            ).fetchall()
        column_map = {source: (column, storage_type) for source, column, storage_type in columns}
        self.assertEqual(column_map["per"][0], "per")
        self.assertEqual(column_map["ts_percent"][0], "ts_percent")
        self.assertEqual(column_map["vorp"][0], "vorp")
        self.assertIn(column_map["season"][1], {"INTEGER", "REAL"})

    def test_selected_season_rows_are_queryable_without_workbook_reader(self) -> None:
        inventory = GeneratorSourceInventory.from_default()

        rows = query_rows_for_season(inventory.database_path, "player_per_game", 2025, limit=50)

        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["season"] == 2025 for row in rows))
        self.assertTrue(all(row["player_id"] for row in rows))
        self.assertTrue(all("pts_per_game" in row for row in rows))

    def test_missing_database_fails_loud_without_excel_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Player Portraits.txt").write_text("{}", encoding="utf-8")
            (root / "Team Logos.txt").write_text("{}", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                ensure_workbook_sqlite_database(root)

    def test_workbook_sqlite_runtime_has_no_excel_reader_dependency(self) -> None:
        source = inspect.getsource(workbook_sqlite)

        self.assertNotIn("workbook_reader", source)
        self.assertNotIn("NBA DATA Master.xlsx", source)
        self.assertNotIn("build_workbook_sqlite_database", source)


if __name__ == "__main__":
    unittest.main()
