from __future__ import annotations

import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QPoint, Qt
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QMenu, QMessageBox, QPushButton, QWidget

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.models.view_data import DomainRefreshView, PlayerListView
from nba2k_editor.ui.qt_app import QtEditorApp
from nba2k_editor.ui.qt_theme import editor_stylesheet
from nba2k_editor.ui.qt_widgets import COMBO_BOX_MAX_VISIBLE_ITEMS, COMBO_BOX_POPUP_MAX_HEIGHT, configure_combo_box


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class PlayerScreenModel:
    def __init__(self) -> None:
        self.player = RecordListItem("Players", 7, 0x1700, "Alpha Guard")
        self.team_a = RecordListItem("Teams", 0, 0x2000, "Team A")
        self.team_b = RecordListItem("Teams", 1, 0x3000, "Team B")
        self.loaded_items = {
            "Players": {self.player.index: self.player},
            "Teams": {self.team_a.index: self.team_a, self.team_b.index: self.team_b},
            "Staff": {},
            "Stadiums": {},
            "Jerseys": {},
            "Shoes": {},
            "NBA History": {},
            "NBA Records": {},
        }
        self.selected_items: dict[str, RecordListItem | None] = {domain: None for domain in self.loaded_items}
        self.slot_requests: list[list[RecordListItem]] = []
        self.player_positions: dict[int, str] = {self.player.index: "PG"}
        self.editor_entry = FieldEntry("Players", "Vitals", "Identity", 1, {"normalized_name": "POSITION", "display_name": "Position"})

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[tuple[str, str | int], ...]:
        return (("All Players", "All Players"), (self.team_a.display_label, self.team_a.index), (self.team_b.display_label, self.team_b.index))

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name", "City Name", "City Abbrev")

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR", "Team", "Position")

    def selected_player_detail_values(self) -> dict[str, str]:
        return {"OVR": "91", "Team": "Team A", "Position": "PG"}

    def selected_team_summary_values(self) -> dict[str, str]:
        return {}

    def selected_detail_title(self, domain: str, label: str) -> str:
        item = self.selected_items.get(domain)
        return item.display_label if item is not None else ""

    def selected_record_address_text(self, domain: str) -> str:
        item = self.selected_items.get(domain)
        return "--" if item is None else f"0x{item.address:X}"

    def selected_item(self, domain: str):
        return self.selected_items.get(domain)

    def select_item(self, domain: str, item: RecordListItem | None):
        self.selected_items[domain] = item
        return item

    def select_item_by_index(self, domain: str, selected_index: int | None, **_kwargs):
        if selected_index is None:
            self.selected_items[domain] = None
        else:
            self.selected_items[domain] = self.loaded_items[domain][selected_index]
        return self.selected_items[domain]

    def domain_item_labels(self, domain: str) -> list[str]:
        return [item.display_label for item in self.loaded_items[domain].values()]

    def domain_items(self, domain: str) -> list[RecordListItem]:
        return list(self.loaded_items[domain].values())

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def domain_status(self, domain: str) -> str:
        return "loaded"

    def player_item_labels_for_team_filter(self, _team_filter: str | None, _search_text: str | None = None) -> list[str]:
        return [item.display_label for item in self.loaded_items["Players"].values()]

    def player_items_for_team_filter(
        self,
        _team_filter: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ):
        items = self.loaded_items["Players"]
        if primary_position in {"PG", "SG", "SF", "PF", "C"}:
            items = {index: item for index, item in items.items() if self.player_positions.get(index) == primary_position}
        if not search_text:
            return items
        query = search_text.lower()
        return {index: item for index, item in items.items() if query in item.display_label.lower()}

    def prepare_player_list_view(
        self,
        team_filter: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> PlayerListView:
        return self.player_list_view(team_filter, search_text, primary_position)

    def player_list_view(
        self,
        team_filter: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> PlayerListView:
        items = tuple(self.player_items_for_team_filter(team_filter, search_text, primary_position).values())
        return PlayerListView(team_filter or "All Players", str(search_text or "").casefold(), items, 1)

    def player_roster_slot_items_for_team_items(self, teams):
        team_list = list(teams)
        self.slot_requests.append(team_list)
        return [(self.player, {"team_index": team_list[0].index, "team_label": team_list[0].label, "team_slot": 1, "team_slot_field": "PLAYER1"})]

    def grouped_fields(self, domain: str):
        if domain == "Players":
            return {"Vitals": {"Identity": [self.editor_entry]}}
        return {}

    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return False

    def is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool:
        return False

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector=None):
        return {"raw_value": 0, "display_value": "PG"}

    def read_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, stat_selector=None):
        return self.read_entry_value(entry, index=item.index, stat_selector=stat_selector)

    def field_options(self, entry: FieldEntry) -> list[str]:
        if entry is self.editor_entry:
            return ["PG", "SG", "SF"]
        return []


class QtEditorPlayersScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def apply_loaded_players(self, app: QtEditorApp, model: PlayerScreenModel) -> None:
        app._apply_domain_refresh_views(
            (
                DomainRefreshView(
                    "Players",
                    tuple(model.loaded_items["Players"].values()),
                    "loaded",
                    1,
                ),
            )
        )

    def test_selected_player_detail_values_render_in_player_detail_panel(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.apply_loaded_players(app, model)

        app.domain_lists["Players"].setCurrentRow(0)
        qt_app().processEvents()

        self.assertEqual("91", app.player_detail_rows["OVR"].value.text())
        self.assertEqual("Team A", app.player_detail_rows["Team"].value.text())
        self.assertEqual("PG", app.player_detail_rows["Position"].value.text())
        self.assertEqual("0x1700", app.detail_addresses["Players"].text())

    def test_player_right_click_menu_wires_add_remove_and_trade_actions(self) -> None:
        model = PlayerScreenModel()
        second_player = RecordListItem("Players", 8, 0x1800, "Beta Forward")
        model.loaded_items["Players"][second_player.index] = second_player
        app = QtEditorApp(model)  # type: ignore[arg-type]
        calls: list[tuple[object, ...]] = []

        class MovementRecorder:
            def add_player(self, player, team):
                calls.append(("add", player, team))
                return type("Placement", (), {"slot": 3})()

            def remove_player(self, player):
                calls.append(("remove", player))
                return type("Placement", (), {"team": model.team_a, "slot": 1})()

            def trade_players(self, first, second):
                calls.append(("trade", first, second))
                return ()

        app.player_movement = MovementRecorder()
        app.state.selected_item_indexes["Players"] = {model.player.index, second_player.index}
        self.apply_loaded_players(app, model)
        model.select_item("Players", model.player)

        menu_calls = 0

        def trigger_actions(menu: QMenu, _position: QPoint) -> None:
            nonlocal menu_calls
            menu_calls += 1
            actions = {action.text(): action for action in menu.actions()}
            if menu_calls == 1:
                add_menu = actions["Add to Team"].menu()
                assert add_menu is not None
                self.assertEqual(
                    [model.team_a.display_label, model.team_b.display_label],
                    [action.text() for action in add_menu.actions()],
                )
                next(action for action in add_menu.actions() if action.data() == model.team_b.index).trigger()
                actions["Remove from Team"].trigger()
                trade_menu = actions["Trade Player"].menu()
                assert trade_menu is not None
                self.assertEqual(
                    [model.team_a.display_label, model.team_b.display_label],
                    [action.text() for action in trade_menu.actions()],
                )
                next(action for action in trade_menu.actions() if action.data() == model.team_b.index).trigger()
                return
            self.assertIsNone(actions["Trade Player"].menu())
            actions["Trade Player"].trigger()

        record_list = app.domain_lists["Players"]
        first_item = next(
            record_list.item(row)
            for row in range(record_list.count())
            if int(record_list.item(row).data(Qt.ItemDataRole.UserRole)) == model.player.index
        )
        first_position = record_list.visualItemRect(first_item).center()
        first_event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, first_position, record_list.mapToGlobal(first_position))
        with patch.object(QMessageBox, "information"), patch("nba2k_editor.ui.qt_app.QMenu.exec", trigger_actions):
            record_list.contextMenuEvent(first_event)
            self.assertEqual(model.team_b.index, app.state.player_team_filter)
            assert app.player_filter_combo is not None
            self.assertEqual(model.team_b.index, app.player_filter_combo.currentData())
            self.assertEqual(model.player.index, app.state.pending_trade_player_index)
            second_item = next(
                record_list.item(row)
                for row in range(record_list.count())
                if int(record_list.item(row).data(Qt.ItemDataRole.UserRole)) == second_player.index
            )
            second_position = record_list.visualItemRect(second_item).center()
            second_event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, second_position, record_list.mapToGlobal(second_position))
            record_list.contextMenuEvent(second_event)

        self.assertIsNone(app.state.pending_trade_player_index)
        self.assertIsNone(app.state.pending_trade_team_index)

        self.assertEqual(
            [
                ("add", model.player, model.team_b),
                ("remove", model.player),
                ("trade", model.player, second_player),
            ],
            calls,
        )
        self.assertIsNone(app.findChild(QPushButton, "AddPlayerToTeamButton"))
        self.assertIsNone(app.findChild(QPushButton, "RemovePlayerFromTeamButton"))
        self.assertIsNone(app.findChild(QPushButton, "TradeSelectedPlayersButton"))

    def test_single_team_roster_export_uses_selected_team_filter_not_start_range(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app.state.player_team_filter = model.team_b.index
        app.roster_start_input.setText("0")
        app.roster_end_input.setText("0")

        mode, items, placements = app._player_roster_export_items("Players From Single Team")

        self.assertEqual("Players From Single Team", mode)
        self.assertEqual([model.player], items)
        self.assertEqual([model.team_b], model.slot_requests[-1])
        self.assertEqual([{"team_index": 1, "team_label": "Team B", "team_slot": 1, "team_slot_field": "PLAYER1"}], list(placements or ()))

    def test_background_domain_event_populates_players_list(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]

        self.apply_loaded_players(app, model)

        self.assertEqual("Players: 1", app.count_labels["Players"].text())
        self.assertEqual([model.player.display_label], [app.domain_lists["Players"].item(index).text() for index in range(app.domain_lists["Players"].count())])

    def test_player_search_runs_on_worker_and_only_changes_item_visibility(self) -> None:
        model = PlayerScreenModel()
        second = RecordListItem("Players", 8, 0x1800, "Beta Forward")
        model.loaded_items["Players"][second.index] = second
        worker_threads: list[int] = []
        original_player_list_view = model.player_list_view

        def player_list_view(team_filter, search_text=None, primary_position=None):
            worker_threads.append(threading.get_ident())
            return original_player_list_view(team_filter, search_text, primary_position)

        model.player_list_view = player_list_view  # type: ignore[method-assign]
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.apply_loaded_players(app, model)
        record_list = app.domain_lists["Players"]
        item_ids = [id(record_list.item(row)) for row in range(record_list.count())]

        app._set_player_search_text("guard")
        deadline = time.monotonic() + 2.0
        while app.operation_worker.is_running() and time.monotonic() < deadline:
            time.sleep(0.01)
            app._poll_background_operation()

        self.assertEqual([model.player.index], [
            int(record_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(record_list.count())
            if not record_list.item(row).isHidden()
        ])
        self.assertEqual(item_ids, [id(record_list.item(row)) for row in range(record_list.count())])
        self.assertEqual("Players: 1", app.count_labels["Players"].text())
        self.assertTrue(worker_threads)
        self.assertTrue(all(thread_id != threading.get_ident() for thread_id in worker_threads))

    def test_primary_position_filter_refines_the_loaded_player_list(self) -> None:
        model = PlayerScreenModel()
        shooting_guard = RecordListItem("Players", 8, 0x1800, "Beta Shooting Guard")
        model.loaded_items["Players"][shooting_guard.index] = shooting_guard
        model.player_positions[shooting_guard.index] = "SG"
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.apply_loaded_players(app, model)

        assert app.player_position_filter_combo is not None
        self.assertEqual(
            ["All Positions", "PG", "SG", "SF", "PF", "C"],
            [app.player_position_filter_combo.itemData(index) for index in range(app.player_position_filter_combo.count())],
        )
        app.player_position_filter_combo.setCurrentIndex(app.player_position_filter_combo.findData("SG"))
        deadline = time.monotonic() + 2.0
        while app.operation_worker.is_running() and time.monotonic() < deadline:
            time.sleep(0.01)
            app._poll_background_operation()

        record_list = app.domain_lists["Players"]
        self.assertEqual("SG", app.state.player_position_filter)
        self.assertEqual(
            [shooting_guard.index],
            [
                int(record_list.item(row).data(Qt.ItemDataRole.UserRole))
                for row in range(record_list.count())
                if not record_list.item(row).isHidden()
            ],
        )
        self.assertEqual("Players: 1", app.count_labels["Players"].text())

    def test_player_refresh_preserves_filtered_visibility_until_refreshed_filter_result_is_applied(self) -> None:
        model = PlayerScreenModel()
        second = RecordListItem("Players", 8, 0x1800, "Beta Forward")
        model.loaded_items["Players"][second.index] = second
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.apply_loaded_players(app, model)

        app._set_player_search_text("guard")
        deadline = time.monotonic() + 2.0
        while app.operation_worker.is_running() and time.monotonic() < deadline:
            time.sleep(0.01)
            app._poll_background_operation()

        refreshed = RecordListItem("Players", 9, 0x1900, "Gamma Center")
        model.loaded_items["Players"][refreshed.index] = refreshed
        app._apply_domain_refresh_views(
            (
                DomainRefreshView(
                    "Players",
                    tuple(model.loaded_items["Players"].values()),
                    "loaded",
                    2,
                ),
            )
        )

        record_list = app.domain_lists["Players"]
        self.assertEqual(
            [model.player.index],
            [
                int(record_list.item(row).data(Qt.ItemDataRole.UserRole))
                for row in range(record_list.count())
                if not record_list.item(row).isHidden()
            ],
        )
        self.assertEqual("Players: 1", app.count_labels["Players"].text())

    def test_player_range_selection_updates_model_once_for_selection_snapshot(self) -> None:
        model = PlayerScreenModel()
        for index in range(30):
            player = RecordListItem("Players", index + 100, 0x4000 + index, f"Bench {index}")
            model.loaded_items["Players"][player.index] = player
        detail_reads = 0

        def selected_player_detail_values() -> dict[str, str]:
            nonlocal detail_reads
            detail_reads += 1
            return {"OVR": "80", "Team": "Team A", "Position": "SG"}

        model.selected_player_detail_values = selected_player_detail_values  # type: ignore[method-assign]
        app = QtEditorApp(model)  # type: ignore[arg-type]
        self.apply_loaded_players(app, model)

        record_list = app.domain_lists["Players"]
        record_list.setCurrentRow(record_list.count() - 1, QItemSelectionModel.SelectionFlag.NoUpdate)
        selection = QItemSelection(record_list.model().index(0, 0), record_list.model().index(record_list.count() - 1, 0))
        record_list.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        qt_app().processEvents()

        self.assertEqual(1, detail_reads)
        self.assertEqual(record_list.count(), len(app.state.selected_item_indexes["Players"]))

    def test_player_popout_starts_smaller_and_can_shrink(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        captured: dict[str, tuple[int, int]] = {}

        def capture_exec(dialog):
            captured["size"] = (dialog.width(), dialog.height())
            captured["minimum"] = (dialog.minimumWidth(), dialog.minimumHeight())
            return 0

        with patch("nba2k_editor.ui.qt_app.QDialog.show", capture_exec):
            app._open_editor_window(model.player)

        self.assertEqual((820, 560), captured["size"])
        self.assertEqual((520, 360), captured["minimum"])

    def test_player_popout_option_field_uses_combo_box(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        captured: dict[str, list[str]] = {}

        def capture_exec(dialog):
            combo = next(combo for combo in dialog.findChildren(QComboBox) if combo.currentText() == "PG")
            captured["options"] = [combo.itemText(index) for index in range(combo.count())]
            return 0

        with patch("nba2k_editor.ui.qt_app.QDialog.show", capture_exec):
            app._open_editor_window(model.player)

        self.assertEqual(["PG", "SG", "SF"], captured["options"])

    def test_editor_reset_button_is_only_present_for_players(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        sources = [
            model.player,
            RecordListItem("Teams", 1, 0x2000, "Team Test"),
            RecordListItem("Staff", 2, 0x3000, "Staff Test"),
            RecordListItem("Stadiums", 3, 0x4000, "Stadium Test"),
            RecordListItem("Jerseys", 4, 0x5000, "Jersey Test"),
            RecordListItem("Shoes", 5, 0x6000, "Shoe Test"),
            RecordListItem("NBA History", 6, 0x7000, "History Test"),
            RecordListItem("NBA Records", 7, 0x8000, "Record Test"),
        ]
        buttons_by_domain: dict[str, set[str]] = {}

        def capture_exec(dialog):
            buttons_by_domain[current_domain] = {button.text() for button in dialog.findChildren(QPushButton)}
            return 0

        app._build_team_records_widget = lambda: QWidget()  # type: ignore[method-assign]
        app._show_team_record_rows = lambda: None  # type: ignore[method-assign]
        with patch("nba2k_editor.ui.qt_app.QDialog.show", capture_exec):
            for source in sources:
                current_domain = source.domain
                app._open_editor_window(source)

        self.assertIn("Reset", buttons_by_domain["Players"])
        for source in sources[1:]:
            with self.subTest(domain=source.domain):
                self.assertNotIn("Reset", buttons_by_domain[source.domain])

    def test_generic_staff_edit_button_preserves_domain_when_clicked_signal_sends_checked_arg(self) -> None:
        model = PlayerScreenModel()
        staff = RecordListItem("Staff", 3, 0x3300, "Coach Test")
        model.loaded_items["Staff"] = {staff.index: staff}
        model.selected_items["Staff"] = staff
        app = QtEditorApp(model)  # type: ignore[arg-type]
        opened: list[RecordListItem] = []

        staff_screen = app.screen_widgets["Staff"]
        edit_button = next(button for button in staff_screen.findChildren(QPushButton) if button.text() == "Edit Staff")
        with patch.object(app, "_open_editor_window", side_effect=lambda item: opened.append(item)), patch.object(
            QMessageBox,
            "warning",
        ) as warning:
            edit_button.click()

        self.assertEqual([staff], opened)
        warning.assert_not_called()

    def test_configured_combo_popup_is_bounded_dropdown(self) -> None:
        combo = configure_combo_box(QComboBox())
        combo.addItems([f"Option {index}" for index in range(50)])

        self.assertEqual(COMBO_BOX_MAX_VISIBLE_ITEMS, combo.maxVisibleItems())
        self.assertEqual(COMBO_BOX_POPUP_MAX_HEIGHT, combo.view().maximumHeight())

    def test_theme_uses_dropdown_popup_not_full_screen_combo_popup(self) -> None:
        self.assertIn("combobox-popup: 0;", editor_stylesheet())


if __name__ == "__main__":
    unittest.main()
