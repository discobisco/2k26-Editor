from __future__ import annotations

import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sql_sources import SqlSourceInventory, selected_sql_base_table_roles


class GeneratorSqlSourceTests(unittest.TestCase):
    def test_default_sql_inventory_uses_archive_sql_and_archive_one_sqlite(self) -> None:
        inventory = SqlSourceInventory.from_default()

        self.assertEqual(inventory.archive_sql_dump_path.name, "NBA_Database.sql")
        self.assertEqual(inventory.archive_sql_dump_path.parent.name, "archive")
        self.assertEqual(inventory.archive_sqlite_path.name, "nba.sqlite")
        self.assertEqual(inventory.archive_sqlite_path.parent.name, "archive (1)")
        self.assertGreater(inventory.archive_sql_dump_path.stat().st_size, 300_000_000)
        self.assertGreater(inventory.archive_sqlite_path.stat().st_size, 2_000_000_000)

    def test_archive_sql_dump_exposes_selected_base_tables_and_columns(self) -> None:
        inventory = SqlSourceInventory.from_default()

        tables = set(inventory.sql_dump_tables())
        self.assertEqual(
            {
                "Coaches",
                "CoachHistory",
                "CommonPlayerInfo",
                "Games",
                "LeagueSchedule24_25",
                "Players",
                "PlayerStatistics",
                "Teams",
                "TeamStatistics",
            }
            - tables,
            set(),
        )

        player_stat_columns = {column.name for column in inventory.sql_dump_columns("PlayerStatistics")}
        self.assertIn("gameId", player_stat_columns)
        self.assertIn("personId", player_stat_columns)
        self.assertIn("points", player_stat_columns)
        self.assertIn("assists", player_stat_columns)
        self.assertIn("reboundsTotal", player_stat_columns)

    def test_archive_one_sqlite_is_queryable_base_database(self) -> None:
        inventory = SqlSourceInventory.from_default()

        tables = set(inventory.sqlite_tables())
        self.assertEqual(
            {
                "common_player_info",
                "draft_combine_stats",
                "draft_history",
                "game",
                "player",
                "play_by_play",
                "team",
                "team_history",
            }
            - tables,
            set(),
        )

        common_columns = set(inventory.sqlite_columns("common_player_info"))
        self.assertIn("person_id", common_columns)
        self.assertIn("display_first_last", common_columns)
        self.assertIn("draft_year", common_columns)
        self.assertGreater(inventory.sqlite_row_count("player"), 4_000)
        self.assertEqual(inventory.sqlite_row_count("team"), 30)

    def test_selected_sql_base_roles_document_starting_sources(self) -> None:
        roles = selected_sql_base_table_roles()
        role_keys = {(role.source, role.table) for role in roles}

        self.assertIn(("archive_sql_dump", "PlayerStatistics"), role_keys)
        self.assertIn(("archive_sql_dump", "TeamStatistics"), role_keys)
        self.assertIn(("archive_sql_dump", "LeagueSchedule24_25"), role_keys)
        self.assertIn(("archive_sqlite", "draft_combine_stats"), role_keys)
        self.assertIn(("archive_sqlite", "play_by_play"), role_keys)


if __name__ == "__main__":
    unittest.main()
