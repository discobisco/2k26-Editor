from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTabWidget

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.models.team_record_routing import team_record_rows
from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class RecordsModel:
    def __init__(self) -> None:
        self.history_a = RecordListItem("NBA History", 4, 0x4000, "History A")
        self.team_a = RecordListItem("Teams", 0, 0x2000, "Team A")
        self.team_b = RecordListItem("Teams", 1, 0x3000, "Team B")
        self.loaded_items = {
            "Players": {},
            "Teams": {self.team_a.display_label: self.team_a, self.team_b.display_label: self.team_b},
            "Staff": {},
            "Stadiums": {},
            "Jerseys": {},
            "Shoes": {},
            "NBA History": {self.history_a.display_label: self.history_a},
            "NBA Records": {},
        }
        self.selected_items = {domain: None for domain in self.loaded_items}
        self.saved_values: dict[int, str] = {}
        self.zero_writes: list[tuple[int, str]] = []
        self.data_entry = FieldEntry("NBA Records", "Records", "Records", 0, {"normalized_name": "DATA", "display_name": "Data"})
        self.team_entry = FieldEntry("Teams", "Vitals", "Info", 0, {"normalized_name": "TEAMNAME", "display_name": "Team Name"})
        self.background_refresh_domains: tuple[str, ...] | None = None

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[str, ...]:
        return ("All Players",)

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name", "City Name", "City Abbrev")

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR",)

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def domain_status(self, domain: str) -> str:
        return "loaded"

    def start_background_refresh(self, domains: tuple[str, ...]) -> bool:
        self.background_refresh_domains = domains
        return True

    def pop_refresh_events(self):
        return []

    def player_item_labels_for_team_filter(self, _team_filter: str | None, _search_text: str | None = None) -> list[str]:
        return []

    def selected_item(self, domain: str):
        return self.selected_items.get(domain)

    def select_item(self, domain: str, item: RecordListItem | None):
        self.selected_items[domain] = item
        return item

    def select_item_by_label(self, domain: str, selected_label: str | None):
        return self.select_item(domain, self.loaded_items[domain].get(str(selected_label or "")))

    def selected_detail_title(self, domain: str, label: str) -> str:
        item = self.selected_items.get(domain)
        return "" if item is None else item.display_label

    def selected_record_address_text(self, domain: str) -> str:
        item = self.selected_items.get(domain)
        return "--" if item is None else f"0x{item.address:X}"

    def selected_team_summary_values(self) -> dict[str, str]:
        return {}

    def selected_player_detail_values(self) -> dict[str, str]:
        return {}

    def refresh_history_screen_rows(self, section: str, tab: str, history_type: int | None):
        return [{"Rank": "1", "Season": "2026", "First Name": "Alpha"}]

    def record_address(self, domain: str, index: int) -> int:
        return 0x9000 + index

    def refresh_record_screen_rows(self, section: str, stat: str, *, record_row_start: int, record_row_count: int):
        return [
            {"Rank": "1", "First Name": "Alpha", "Last Name": "One", "Data": "50"},
            {"Rank": "2", "First Name": "Beta", "Last Name": "Two", "Data": "45"},
        ]

    def save_record_data_values(self, values: dict[int, str]):
        self.saved_values = dict(values)
        return {"succeeded": len(values)}

    def zero_record_data_values_removed_from_fake(self, indexes):
        raise AssertionError("Qt Records zero must use write_entry_value, not fake model zero_record_data_values")

    def _field_by_normalized_name(self, domain: str, name: str):
        if domain == "NBA Records" and name == "DATA":
            return self.data_entry
        return None

    def write_entry_value(self, entry: FieldEntry, *, index: int, value):
        self.zero_writes.append((index, str(value)))

    def grouped_fields(self, domain: str):
        if domain == "Teams":
            return {"Vitals": {"Info": [self.team_entry]}}
        if domain == "NBA Records":
            return {"Records": {"Records": [self.data_entry]}}
        return {}

    def is_player_selected_stat_detail_entry(self, _entry: FieldEntry) -> bool:
        return False

    def is_player_season_id_selector_entry(self, _entry: FieldEntry) -> bool:
        return False

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector=None):
        return {"display_value": f"{entry.display_name} {index}"}

    def field_options(self, _entry: FieldEntry):
        return []


class QtEditorRecordsScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_records_save_uses_data_column_values_by_active_record_index(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app._show_record_screen_rows()
        data_column = app.record_table.columnCount() - 1
        app.record_table.item(0, data_column).setText("61")
        app.record_table.item(1, data_column).setText("59")

        with patch("nba2k_editor.ui.qt_app.QMessageBox.information"):
            app._save_record_data_values()

        indexes = app._active_record_indexes()
        self.assertEqual({indexes[0]: "61", indexes[1]: "59"}, model.saved_values)

    def test_records_zero_writes_zero_to_all_authored_record_rows_and_team_records(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app._show_record_screen_rows()

        def fake_team_record_indexes(_model, team):
            return [9000 + team.index * 2, 9001 + team.index * 2]

        with patch("nba2k_editor.ui.qt_app.team_record_indexes", fake_team_record_indexes), patch("nba2k_editor.ui.qt_app.QMessageBox.information"):
            app._zero_record_data_values()

        record_indexes = app._all_record_indexes()
        team_indexes = (9000, 9001, 9002, 9003)
        expected = tuple(dict.fromkeys((*record_indexes, *team_indexes)))
        self.assertGreater(len(record_indexes), app.record_table.rowCount())
        self.assertEqual([(index, "0") for index in expected], model.zero_writes)

    def test_team_records_zero_uses_existing_team_record_indexes(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        model.select_item("Teams", model.team_b)

        def fake_team_record_indexes(_model, team):
            return [9100 + team.index * 2, 9101 + team.index * 2]

        with patch("nba2k_editor.ui.qt_app.team_record_indexes", fake_team_record_indexes), patch("nba2k_editor.ui.qt_app.QMessageBox.information"):
            app._zero_all_team_record_data_values()

        self.assertEqual([(9102, "0"), (9103, "0")], model.zero_writes)

    def test_team_records_live_in_team_popout_not_main_team_screen(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.assertIsNone(app.team_record_table)

        def fake_team_record_rows(_model, team, section, stat):
            self.assertIs(model.team_b, team)
            self.assertEqual("Single Game (Regular)", section)
            self.assertEqual("Points", stat)
            return [{"Rank": "1", "First Name": "Team", "Data": "44"}]

        captured: dict[str, bool] = {}

        def capture_exec(dialog):
            captured["team_records_tab"] = any(
                tabs.tabText(index) == "Team Records"
                for tabs in dialog.findChildren(QTabWidget)
                for index in range(tabs.count())
            )
            return 0

        with patch("nba2k_editor.ui.qt_app.team_record_rows", fake_team_record_rows), patch("nba2k_editor.ui.qt_app.team_record_indexes", return_value=[9100 + index for index in range(510)]), patch("nba2k_editor.ui.qt_app.QDialog.exec", capture_exec):
            app._open_editor_window(model.team_b)

        self.assertTrue(captured["team_records_tab"])
        self.assertIsNotNone(app.team_record_table)
        table = app.team_record_table
        assert table is not None
        self.assertEqual(1, table.rowCount())
        self.assertEqual("44", table.item(0, table.columnCount() - 1).text())
        self.assertEqual(9100, app.table_row_items["Team Records"][0].index)

    def test_team_record_table_save_writes_visible_data_values_to_team_record_indexes(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        model.select_item("Teams", model.team_b)

        rows = [
            {"Rank": "1", "First Name": "Team", "Data": "44"},
            {"Rank": "2", "First Name": "Team", "Data": "43"},
        ]
        with patch("nba2k_editor.ui.qt_app.team_record_rows", return_value=rows), patch("nba2k_editor.ui.qt_app.team_record_indexes", return_value=[9100 + index for index in range(510)]), patch("nba2k_editor.ui.qt_app.QDialog.exec", return_value=0):
            app._open_editor_window(model.team_b)
            table = app.team_record_table
            assert table is not None
            table.item(0, table.columnCount() - 1).setText("61")
            table.item(1, table.columnCount() - 1).setText("59")
            with patch("nba2k_editor.ui.qt_app.QMessageBox.information"):
                app._save_team_record_data_values()

        self.assertEqual([(9100, "61"), (9101, "59")], model.zero_writes)

    def test_team_record_rows_delegates_with_nba_records_stride(self) -> None:
        test = self

        class TeamRecordModel:
            target_executable = "NBA2K26.exe"

            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def _layout_entries(self, domain: str):
                test.assertEqual("Teams", domain)
                return [
                    FieldEntry(
                        "Teams",
                        "History",
                        "Records",
                        0,
                        {
                            "normalized_name": "CURRENTYEARSTATS",
                            "display_name": "CURRENT_YEAR_STATS",
                            "selected_record_source": {
                                "role": "team_record_start",
                                "target_domain": "NBA Records",
                                "versions": ["2K26"],
                                "start_index": 3100,
                                "row_count": 510,
                            },
                        },
                    )
                ]

            def record_summary_rows(self, domain: str, **kwargs):
                test.assertEqual("NBA Records", domain)
                self.kwargs = dict(kwargs)
                return [{"Rank": "1", "Data": "1"}]

            def domain_stride(self, domain: str) -> int:
                test.assertEqual("NBA Records", domain)
                return 123

        model = TeamRecordModel()
        rows = team_record_rows(model, RecordListItem("Teams", 2, 0x3000, "Team B"), "Single Game (Regular)", "Points")

        self.assertEqual([{"Rank": "1", "Data": "1"}], rows)
        self.assertEqual(3100 + 2 * 510, model.kwargs["record_row_start"])
        self.assertEqual(5, model.kwargs["record_row_count"])
        self.assertEqual(123, model.kwargs["record_row_stride"])

    def test_history_table_selection_sets_loaded_history_item(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]

        app._show_history_screen_rows()
        app.history_table.selectRow(0)

        self.assertEqual(model.history_a, model.selected_items["NBA History"])

    def test_history_load_rows_scans_when_history_items_are_not_loaded(self) -> None:
        model = RecordsModel()
        model.loaded_items["NBA History"] = {}
        app = QtEditorApp(model)  # type: ignore[arg-type]

        app._load_history_screen_rows()

        self.assertEqual(("NBA History",), model.background_refresh_domains)

    def test_history_nav_click_does_not_reload_rows(self) -> None:
        model = RecordsModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        called = 0

        def refresh_history_screen_rows(*args, **kwargs):
            nonlocal called
            called += 1
            return []

        model.refresh_history_screen_rows = refresh_history_screen_rows  # type: ignore[method-assign]
        app._show_screen("NBA History")

        self.assertEqual(0, called)


if __name__ == "__main__":
    unittest.main()
