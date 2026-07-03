from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class PlayerScreenModel:
    def __init__(self) -> None:
        self.player = RecordListItem("Players", 7, 0x1700, "Alpha Guard")
        self.team_a = RecordListItem("Teams", 0, 0x2000, "Team A")
        self.team_b = RecordListItem("Teams", 1, 0x3000, "Team B")
        self.loaded_items = {
            "Players": {self.player.display_label: self.player},
            "Teams": {self.team_a.display_label: self.team_a, self.team_b.display_label: self.team_b},
            "Draft Class": {},
            "Staff": {},
            "Stadiums": {},
            "Jerseys": {},
            "Shoes": {},
            "NBA History": {},
            "NBA Records": {},
        }
        self.selected_items: dict[str, RecordListItem | None] = {domain: None for domain in self.loaded_items}
        self.slot_requests: list[list[RecordListItem]] = []
        self.editor_entry = FieldEntry("Players", "Vitals", "Identity", 1, {"normalized_name": "POSITION", "display_name": "Position"})

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[str, ...]:
        return ("All Players", self.team_a.display_label, self.team_b.display_label)

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

    def select_item_by_label(self, domain: str, selected_label: str | None):
        if selected_label is None:
            self.selected_items[domain] = None
        else:
            self.selected_items[domain] = self.loaded_items[domain][selected_label]
        return self.selected_items[domain]

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def domain_status(self, domain: str) -> str:
        return "loaded"

    def player_item_labels_for_team_filter(self, _team_filter: str | None, _search_text: str | None = None) -> list[str]:
        return list(self.loaded_items["Players"])

    def player_items_for_team_filter(self, _team_filter: str | None):
        return self.loaded_items["Players"]

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

    def field_options(self, entry: FieldEntry) -> list[str]:
        if entry is self.editor_entry:
            return ["PG", "SG", "SF"]
        return []


class QtEditorPlayersScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_selected_player_detail_values_render_in_player_detail_panel(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]

        app._select_item_label("Players", model.player.display_label, True)

        self.assertEqual("91", app.player_detail_rows["OVR"].value.text())
        self.assertEqual("Team A", app.player_detail_rows["Team"].value.text())
        self.assertEqual("PG", app.player_detail_rows["Position"].value.text())
        self.assertEqual("0x1700", app.detail_addresses["Players"].text())

    def test_single_team_roster_export_uses_selected_team_filter_not_start_range(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app.state.player_team_filter = model.team_b.display_label
        app.roster_start_input.setText("0")
        app.roster_end_input.setText("0")

        mode, items, placements = app._player_roster_export_items("Players From Single Team")

        self.assertEqual("Players From Single Team", mode)
        self.assertEqual([model.player], items)
        self.assertEqual([model.team_b], model.slot_requests[-1])
        self.assertEqual([{"team_index": 1, "team_label": "Team B", "team_slot": 1, "team_slot_field": "PLAYER1"}], list(placements or ()))

    def test_background_domain_event_populates_players_list(self) -> None:
        model = PlayerScreenModel()
        model.pop_refresh_events = lambda: [("domain", "Players"), ("done", "")]  # type: ignore[attr-defined]
        app = QtEditorApp(model)  # type: ignore[arg-type]

        app._poll_background_scan()

        self.assertEqual("Players: 1", app.count_labels["Players"].text())
        self.assertEqual([model.player.display_label], [app.domain_lists["Players"].item(index).text() for index in range(app.domain_lists["Players"].count())])

    def test_player_list_selection_emits_only_changed_row(self) -> None:
        model = PlayerScreenModel()
        for index in range(30):
            player = RecordListItem("Players", index + 100, 0x4000 + index, f"Bench {index}")
            model.loaded_items["Players"][player.display_label] = player
        detail_reads = 0

        def selected_player_detail_values() -> dict[str, str]:
            nonlocal detail_reads
            detail_reads += 1
            return {"OVR": "80", "Team": "Team A", "Position": "SG"}

        model.selected_player_detail_values = selected_player_detail_values  # type: ignore[method-assign]
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app._sync_player_list()

        app.domain_lists["Players"].setCurrentRow(0)
        qt_app().processEvents()

        self.assertEqual(1, detail_reads)

    def test_player_popout_starts_smaller_and_can_shrink(self) -> None:
        model = PlayerScreenModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        captured: dict[str, tuple[int, int]] = {}

        def capture_exec(dialog):
            captured["size"] = (dialog.width(), dialog.height())
            captured["minimum"] = (dialog.minimumWidth(), dialog.minimumHeight())
            return 0

        with patch("nba2k_editor.ui.qt_app.QDialog.exec", capture_exec):
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

        with patch("nba2k_editor.ui.qt_app.QDialog.exec", capture_exec):
            app._open_editor_window(model.player)

        self.assertEqual(["PG", "SG", "SF"], captured["options"])


if __name__ == "__main__":
    unittest.main()
