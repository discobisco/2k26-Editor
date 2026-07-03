from __future__ import annotations

import os
import unittest
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _TextBox:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _Status:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: object) -> None:
        self.text = str(value)


class _Row:
    def __init__(self, current: str, new: str) -> None:
        self.current = _TextBox(current)
        self.new_value = _TextBox(new)
        self.status = _Status()

    def value_text(self) -> str:
        return self.new_value.text()

class FakeModel:

    def __init__(self) -> None:
        self.items = (
            RecordListItem(domain="Players", index=0, address=0x1000, label="Alpha"),
            RecordListItem(domain="Players", index=1, address=0x1100, label="Beta"),
        )
        self.team_items = (
            RecordListItem(domain="Teams", index=0, address=0x2000, label="Team A"),
            RecordListItem(domain="Teams", index=1, address=0x3000, label="Team B"),
        )
        self.loaded_items = {
            "Players": {item.display_label: item for item in self.items},
            "Teams": {item.display_label: item for item in self.team_items},
            "Draft Class": {},
            "Staff": {},
            "Stadiums": {},
            "Jerseys": {},
            "Shoes": {},
            "NBA History": {},
            "NBA Records": {},
        }
        self.selected_items: dict[str, RecordListItem | None] = {"Players": self.items[0], "Teams": self.team_items[0]}
        self.writes: list[tuple[int, str]] = []
        self.resets: list[tuple[int, str | None]] = []

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[str, ...]:
        return ("All Players",)

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR", "Team", "Position")

    def selected_player_detail_values(self) -> dict[str, str]:
        return {}

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name", "City Name", "City Abbrev")

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def domain_status(self, domain: str) -> str:
        return f"loaded {len(self.loaded_items[domain])} {domain.lower()} records"

    def selected_item(self, domain: str) -> RecordListItem | None:
        return self.selected_items.get(domain)

    def selected_detail_title(self, _domain: str, _label: str) -> str:
        return ""

    def selected_record_address_text(self, _domain: str) -> str:
        return "0x1000"

    def selected_team_summary_values(self) -> dict[str, str]:
        return {}

    def player_item_labels_for_team_filter(self, _team_filter: str | None, _search_text: str | None = None) -> list[str]:
        return self.domain_item_labels("Players")

    def player_items_for_team_filter(self, _team_filter: str | None) -> dict[str, RecordListItem]:
        return self.loaded_items["Players"]

    def select_item_by_label(self, domain: str, selected_label: str | None) -> RecordListItem | None:
        if selected_label is None:
            self.selected_items[domain] = None
            return None
        self.selected_items[domain] = self.loaded_items[domain].get(selected_label)
        return self.selected_items[domain]

    def grouped_fields(self, _domain: str) -> dict[str, dict[str, list[FieldEntry]]]:
        return {}

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: str | None = None) -> dict[str, object]:
        return {"raw_value": 80 if index == 0 else 70, "display_value": "80" if index == 0 else "70", "address": 0x2000 + index}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: str, stat_selector: str | None = None) -> None:
        self.writes.append((index, value))

    def reset_player_editor_values(self, *, index: int, stat_selector: str | None = None) -> dict[str, int]:
        self.resets.append((index, stat_selector))
        return {"attempted": 8, "succeeded": 8, "failed": 0}

    def editor_field_save_key(self, entry: FieldEntry) -> str:
        return f"{entry.domain}\x1f{entry.section}\x1f{entry.group}\x1f{entry.ordinal}"

    def _entry_for_save_key(self, save_key: str) -> FieldEntry:
        domain, section, group, ordinal = save_key.split("\x1f")
        return FieldEntry(domain, section, group, int(ordinal), {"display_name": "Field", "normalized_name": "FIELD"})

    def editor_row_key(self, item: RecordListItem, save_key: str) -> str:
        return f"{item.domain}:{item.index}:{save_key}"

    def selected_editor_items(self, source: RecordListItem, selected_labels=None, *, player_team_filter: str | None = None):
        labels = set(selected_labels or ()) or {source.display_label}
        if source.domain == "Players":
            items = self.player_items_for_team_filter(player_team_filter)
        else:
            items = self.loaded_items[source.domain]
        return [item for label, item in items.items() if label in labels] or [source]

    def editor_window_label(self, source: RecordListItem, selected_labels=None, *, player_team_filter: str | None = None) -> str:
        items = self.selected_editor_items(source, selected_labels, player_team_filter=player_team_filter)
        return f"{source.domain} [{len(items)} selected]" if len(items) > 1 else f"{source.domain} [{source.index}] {source.label}"

    def save_editor_values(self, source: RecordListItem, changes, *, selected_labels=None, player_team_filter: str | None = None, stat_selectors=None):
        targets = self.selected_editor_items(source, selected_labels, player_team_filter=player_team_filter)
        results = {}
        for change in changes:
            for item in targets:
                self.writes.append((item.index, change["value"]))
            results[change["save_key"]] = len(targets)
        return results


class QtEditorBatchSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_dirty_batch_field_applies_even_when_value_matches_source_current(self) -> None:
        model = FakeModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        source = model.items[0]
        entry = FieldEntry("Players", "Vitals", "Ratings", 7, {"display_name": "OVR", "normalized_name": "OVR"})
        save_key = model.editor_field_save_key(entry)
        row_key = model.editor_row_key(source, save_key)
        app.state.open_rows[row_key] = entry
        app.state.selected_item_labels["Players"] = {item.display_label for item in model.items}
        app._mark_row_dirty(row_key)

        row = _Row("80", "80")
        app._save_item_editor(source, {row_key: row})  # type: ignore[arg-type]

        self.assertEqual([(0, "80"), (1, "80")], model.writes)
        self.assertNotIn(row_key, app.state.dirty_rows)
        self.assertEqual("saved 2 records", row.status.text)

    def test_batch_editor_window_label_uses_player_count_not_player_name(self) -> None:
        model = FakeModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        source = model.items[0]
        app.state.selected_item_labels["Players"] = {item.display_label for item in model.items}

        label = app._editor_window_label(source)

        self.assertEqual("Players [2 selected]", label)
        self.assertNotIn(source.label, label)

    def test_single_editor_window_label_keeps_player_name(self) -> None:
        model = FakeModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        source = model.items[0]
        app.state.selected_item_labels["Players"] = {source.display_label}

        self.assertEqual("Players [0] Alpha", app._editor_window_label(source))

    def test_batch_save_applies_to_same_non_player_domain(self) -> None:
        model = FakeModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        source = model.team_items[0]
        entry = FieldEntry("Teams", "Vitals", "Names", 7, {"display_name": "City", "normalized_name": "CITYNAME"})
        save_key = model.editor_field_save_key(entry)
        row_key = model.editor_row_key(source, save_key)
        app.state.open_rows[row_key] = entry
        app.state.selected_item_labels["Teams"] = {item.display_label for item in model.team_items}

        row = _Row("Old City", "New City")
        app._save_item_editor(source, {row_key: row})  # type: ignore[arg-type]

        self.assertEqual([(0, "New City"), (1, "New City")], model.writes)
        self.assertEqual("saved 2 records", row.status.text)


if __name__ == "__main__":
    unittest.main()
