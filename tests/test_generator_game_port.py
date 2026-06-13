from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from game_port import apply_generated_players_to_game, apply_generated_rows_to_game
from player_generator import authored_player_field_index


class FakeGameModel:
    def __init__(self, *, fail_field_key: str | None = None) -> None:
        self.fail_field_key = fail_field_key
        self.writes: list[tuple[str, int, object]] = []

    def write_entry_value(self, entry, *, index: int, value: object, stat_selector: object | None = None) -> dict[str, object]:
        field_key = f"{entry.section}/{entry.normalized_name}"
        if field_key == self.fail_field_key:
            raise RuntimeError("write blocked")
        self.writes.append((field_key, index, value))
        return {"display_value": value, "raw_value": value}


class GamePortTests(unittest.TestCase):
    def test_generated_rows_port_to_game_through_editor_write_entry_value(self) -> None:
        field_index = authored_player_field_index()
        rows = (
            SimpleNamespace(field_key="Vitals/FIRSTNAME", value="Jalen"),
            SimpleNamespace(field_key="Attributes/3POINT", value=88),
            SimpleNamespace(field_key="Tendencies/TOUCHES", value=91),
        )
        model = FakeGameModel()

        result = apply_generated_rows_to_game(model, rows, player_index=7, field_index=field_index)

        self.assertTrue(result.ok)
        self.assertEqual(result.player_index, 7)
        self.assertEqual(result.attempted, 3)
        self.assertEqual(result.succeeded, 3)
        self.assertEqual(result.failed, 0)
        self.assertEqual(
            model.writes,
            [
                ("Vitals/FIRSTNAME", 7, "Jalen"),
                ("Attributes/3POINT", 7, 88),
                ("Tendencies/TOUCHES", 7, 91),
            ],
        )
        self.assertEqual([field.readback_value for field in result.fields], ["Jalen", 88, 91])

    def test_generated_row_port_reports_failed_field_without_losing_successes(self) -> None:
        field_index = authored_player_field_index()
        rows = (
            SimpleNamespace(field_key="Attributes/3POINT", value=88),
            SimpleNamespace(field_key="Tendencies/TOUCHES", value=91),
        )
        model = FakeGameModel(fail_field_key="Tendencies/TOUCHES")

        result = apply_generated_rows_to_game(model, rows, player_index=4, field_index=field_index)

        self.assertFalse(result.ok)
        self.assertEqual(result.attempted, 2)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(model.writes, [("Attributes/3POINT", 4, 88)])
        self.assertEqual(result.fields[1].field_key, "Tendencies/TOUCHES")
        self.assertIn("write blocked", result.fields[1].error or "")

    def test_generated_players_port_to_game_by_explicit_player_index_mapping(self) -> None:
        field_index = authored_player_field_index()
        generated_players = (
            SimpleNamespace(rows=(SimpleNamespace(field_key="Vitals/FIRSTNAME", value="One"),)),
            SimpleNamespace(rows=(SimpleNamespace(field_key="Vitals/FIRSTNAME", value="Two"),)),
        )
        model = FakeGameModel()

        result = apply_generated_players_to_game(model, generated_players, player_indices=(10, 11, 12), field_index=field_index)

        self.assertTrue(result.ok)
        self.assertEqual(result.applied_players, 2)
        self.assertEqual(result.generated_count, 2)
        self.assertEqual(result.target_count, 3)
        self.assertEqual(result.unused_targets, 1)
        self.assertEqual(result.unapplied_generated, 0)
        self.assertEqual(model.writes, [("Vitals/FIRSTNAME", 10, "One"), ("Vitals/FIRSTNAME", 11, "Two")])

    def test_generated_batch_result_reports_unapplied_generated_players(self) -> None:
        field_index = authored_player_field_index()
        generated_players = (
            SimpleNamespace(rows=(SimpleNamespace(field_key="Vitals/FIRSTNAME", value="One"),)),
            SimpleNamespace(rows=(SimpleNamespace(field_key="Vitals/FIRSTNAME", value="Two"),)),
            SimpleNamespace(rows=(SimpleNamespace(field_key="Vitals/FIRSTNAME", value="Three"),)),
        )
        model = FakeGameModel()

        result = apply_generated_players_to_game(model, generated_players, player_indices=(10, 11), field_index=field_index)

        self.assertFalse(result.ok)
        self.assertEqual(result.applied_players, 2)
        self.assertEqual(result.generated_count, 3)
        self.assertEqual(result.target_count, 2)
        self.assertEqual(result.unapplied_generated, 1)
        self.assertEqual(result.unused_targets, 0)

    def test_generated_row_port_has_no_direct_memory_or_clipboard_path(self) -> None:
        import game_port

        source = inspect.getsource(game_port)
        for banned in ("GameMemory", "write_value(", "write_and_readback", "clipboard", "subprocess"):
            self.assertNotIn(banned, source)
        self.assertIn("write_entry_value", source)


if __name__ == "__main__":
    unittest.main()
