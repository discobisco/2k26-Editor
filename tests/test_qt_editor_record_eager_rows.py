from __future__ import annotations

import inspect
import os
import unittest
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class EagerRecordModel:
    def __init__(self) -> None:
        self.refresh_history_calls = 0
        self.refresh_record_calls = 0
        self.clear_history_calls = 0
        self.clear_record_calls = 0
        self.loaded_items = {"NBA History": {}, "NBA Records": {}, "Teams": {}, "Players": {}, "Staff": {}, "Stadiums": {}, "Jerseys": {}, "Shoes": {}}
        self.selected_items = {domain: None for domain in self.loaded_items}

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[tuple[str, str], ...]:
        return (("All Players", "All Players"),)

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name", "City Name", "City Abbrev")

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR", "Team", "Position")

    def selected_player_detail_values(self) -> dict[str, str]:
        return {}

    def domain_item_labels(self, domain: str) -> list[str]:
        return []

    def domain_items(self, domain: str) -> list[Any]:
        return []

    def player_items_for_team_filter(self, _team_filter: str | int | None, _search_text: str | None = None) -> dict[int, Any]:
        return {}

    def domain_item_count(self, domain: str) -> int:
        return 0

    def selected_item(self, domain: str) -> Any:
        return None

    def select_item_by_index(self, domain: str, selected_index: int | None, **_kwargs) -> Any:
        return None

    def domain_status(self, domain: str) -> str:
        return "loaded"

    def selected_detail_title(self, domain: str, label: str) -> str:
        return ""

    def selected_record_address_text(self, domain: str) -> str:
        return "--"

    def selected_team_summary_values(self) -> dict[str, str]:
        return {}

    def clear_history_screen_rows(self) -> None:
        self.clear_history_calls += 1

    def clear_record_screen_rows(self) -> None:
        self.clear_record_calls += 1

    def refresh_history_screen_rows(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
        self.refresh_history_calls += 1
        return []

    def refresh_record_screen_rows(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
        self.refresh_record_calls += 1
        return []


class QtEditorRecordEagerRowsTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_history_and_records_list_sync_builds_table_rows(self) -> None:
        model = EagerRecordModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]

        app._sync_domain_list("NBA History")
        app._sync_domain_list("NBA Records")

        self.assertEqual(0, model.clear_history_calls)
        self.assertEqual(0, model.clear_record_calls)
        self.assertEqual(1, model.refresh_history_calls)
        self.assertEqual(1, model.refresh_record_calls)

    def test_history_and_records_screens_keep_explicit_edit_actions(self) -> None:
        history_source = inspect.getsource(QtEditorApp._build_history_screen)
        records_source = inspect.getsource(QtEditorApp._build_records_screen)

        self.assertIn('"Edit Selected History Row"', history_source)
        self.assertIn('"Edit Selected Record"', records_source)
        self.assertIn("_load_history_screen_rows", history_source)
        self.assertIn("_show_record_screen_rows", records_source)


if __name__ == "__main__":
    unittest.main()
