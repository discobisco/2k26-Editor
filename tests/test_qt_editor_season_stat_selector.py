from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.qt_app import QtEditorApp


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


class SeasonSelectorModel:
    def __init__(self) -> None:
        self.player_a = RecordListItem("Players", 0, 0x1000, "Alpha Guard")
        self.player_b = RecordListItem("Players", 1, 0x1100, "Beta Guard")
        self.loaded_items = {
            "Players": {self.player_a.display_label: self.player_a, self.player_b.display_label: self.player_b},
            "Teams": {},
            "Staff": {},
            "Stadiums": {},
            "Jerseys": {},
            "Shoes": {},
            "NBA History": {},
            "NBA Records": {},
        }
        self.selected_items = {domain: None for domain in self.loaded_items}
        self.selector_entry = FieldEntry("Players", "Stats", "Season IDs", 1, {"normalized_name": "STATSID1", "display_name": "STATS ID#1", "stat_role": "season_id_selector"})
        self.points_entry = FieldEntry("Players", "Stats", "Season IDs", 2, {"normalized_name": "POINTS", "display_name": "Points", "stat_role": "season_id_detail", "selected_record_source": {"base_pointer": "PlayerSeasonStats", "stride": "playerSeasonStatsSize"}})
        self.read_calls: list[tuple[str, int, object | None]] = []
        self.write_calls: list[tuple[str, int, object, object | None]] = []

    def runtime_status_text(self) -> str:
        return "not attached"

    def player_team_filter_options(self) -> tuple[str, ...]:
        return ("All Players",)

    def team_summary_labels(self) -> tuple[str, ...]:
        return ("Team Name", "City Name", "City Abbrev")

    def player_detail_labels(self) -> tuple[str, ...]:
        return ("OVR", "Team", "Position")

    def selected_player_detail_values(self) -> dict[str, str]:
        return {}

    def selected_team_summary_values(self) -> dict[str, str]:
        return {}

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

    def selected_item(self, domain: str):
        return self.selected_items.get(domain)

    def select_item_by_label(self, domain: str, selected_label: str | None):
        self.selected_items[domain] = self.loaded_items[domain].get(str(selected_label or ""))
        return self.selected_items[domain]

    def selected_detail_title(self, domain: str, label: str) -> str:
        item = self.selected_items.get(domain)
        return "" if item is None else item.display_label

    def selected_record_address_text(self, domain: str) -> str:
        item = self.selected_items.get(domain)
        return "--" if item is None else f"0x{item.address:X}"

    def grouped_fields(self, domain: str):
        if domain == "Players":
            return {"Stats": {"Season IDs": [self.selector_entry, self.points_entry]}}
        return {}

    def player_season_stat_id_options(self, player_index: int) -> list[str]:
        self.read_calls.append(("options", player_index, None))
        return ["[42] STATS ID#1", "[99] STATS ID#2"]

    def is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool:
        return entry is self.selector_entry

    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return entry is self.points_entry

    def season_stat_id_options(self, domain: str, index: int) -> list[str]:
        return self.player_season_stat_id_options(index)

    def is_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return self.is_player_selected_stat_detail_entry(entry)

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None):
        self.read_calls.append((entry.normalized_name, index, stat_selector))
        if entry is self.selector_entry:
            return {"raw_value": 42, "display_value": "42"}
        suffix = "99" if stat_selector == "[99] STATS ID#2" else "42"
        return {"raw_value": int(suffix), "display_value": f"PTS-{suffix}"}

    def read_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, stat_selector: object | None = None):
        return self.read_entry_value(entry, index=item.index, stat_selector=stat_selector)

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: object, stat_selector: object | None = None) -> None:
        self.write_calls.append((entry.normalized_name, index, value, stat_selector))

    def write_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, value: object, stat_selector: object | None = None) -> None:
        self.write_entry_value(entry, index=item.index, value=value, stat_selector=stat_selector)

    def apply_player_roster_snapshot(self, snapshot, *, target_items=None, stat_selector=None, **_kwargs):
        attempted = 0
        for item, row in zip(tuple(target_items or ()), snapshot.get("records", [])):
            for key, payload in row.get("fields", {}).items():
                normalized = str(key).split("/")[-1]
                entry = self.points_entry if normalized == self.points_entry.normalized_name else self.selector_entry
                value = payload.get("display_value") if isinstance(payload, dict) else payload
                self.write_entry_value(entry, index=item.index, value=value, stat_selector=stat_selector)
                attempted += 1
        return {"attempted": attempted, "succeeded": attempted, "failed": 0, "skipped": 0}

    def editor_field_save_key(self, entry: FieldEntry) -> str:
        return f"{entry.domain}\x1f{entry.section}\x1f{entry.group}\x1f{entry.ordinal}"

    def _entry_for_save_key(self, save_key: str) -> FieldEntry:
        ordinal = int(save_key.split("\x1f")[-1])
        return self.selector_entry if ordinal == self.selector_entry.ordinal else self.points_entry

    def editor_row_key(self, item: RecordListItem, save_key: str) -> str:
        return f"{item.domain}:{item.index}:{save_key}"

    def selected_editor_items(self, source: RecordListItem, selected_labels=None, *, player_team_filter: str | None = None):
        labels = set(selected_labels or ()) or {source.display_label}
        return [item for label, item in self.loaded_items[source.domain].items() if label in labels] or [source]

    def editor_window_label(self, source: RecordListItem, selected_labels=None, *, player_team_filter: str | None = None) -> str:
        items = self.selected_editor_items(source, selected_labels, player_team_filter=player_team_filter)
        return f"{source.domain} [{len(items)} selected]" if len(items) > 1 else f"{source.domain} [{source.index}] {source.label}"

    def editor_group_stat_selector(self, domain: str, index: int, group: str, entries, selected=None):
        detail_entries = [entry for entry in entries if self.is_selected_stat_detail_entry(entry)]
        if not detail_entries:
            return None
        options = self.season_stat_id_options(domain, index)
        return {"group": group, "label": "Active Season Stat ID", "options": options, "selected": selected if selected in options else options[0]}

    def editor_sections(self, source: RecordListItem, *, stat_selectors=None):
        stat_selectors = stat_selectors or {}
        sections = []
        for section, groups in self.grouped_fields(source.domain).items():
            section_rows = {"label": section, "groups": []}
            for group, entries in groups.items():
                selector = self.editor_group_stat_selector(source.domain, source.index, group, entries, stat_selectors.get(group))
                selected = selector["selected"] if selector else None
                fields = []
                for entry in entries:
                    save_key = self.editor_field_save_key(entry)
                    value = self.read_entry_value(entry, index=source.index, stat_selector=selected)
                    fields.append({"row_key": self.editor_row_key(source, save_key), "save_key": save_key, "label": entry.display_name, "value": value["display_value"]})
                section_rows["groups"].append({"label": group, "stat_selector": selector, "fields": fields})
            sections.append(section_rows)
        return sections

    def editor_field_value(self, save_key: str, *, index: int, stat_selector: object | None = None):
        return self.read_entry_value(self._entry_for_save_key(save_key), index=index, stat_selector=stat_selector)

    def save_editor_values(self, source: RecordListItem, changes, *, selected_labels=None, player_team_filter: str | None = None, stat_selectors=None):
        results = {}
        targets = self.selected_editor_items(source, selected_labels, player_team_filter=player_team_filter)
        stat_selectors = stat_selectors or {}
        for change in changes:
            save_key = change["save_key"]
            entry = self._entry_for_save_key(save_key)
            for item in targets:
                self.write_entry_value(entry, index=item.index, value=change["value"], stat_selector=stat_selectors.get(entry.group))
            results[save_key] = len(targets)
        return results


class QtEditorSeasonStatSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        qt_app()

    def test_editor_adds_active_season_stat_selector_and_reads_detail_with_selected_option(self) -> None:
        model = SeasonSelectorModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]

        with patch("nba2k_editor.ui.qt_app.QDialog.exec", return_value=0):
            app._open_editor_window(model.player_a)

        key = ("Players", model.player_a.index, "Season IDs")
        self.assertIn(key, app.editor_stat_selectors)
        self.assertEqual("[42] STATS ID#1", app.editor_stat_selectors[key].currentText())
        self.assertIn(("POINTS", 0, "[42] STATS ID#1"), model.read_calls)
        self.assertNotIn(model.selector_entry, app.state.open_rows.values())
        self.assertNotIn(("STATSID1", 0, "[42] STATS ID#1"), model.read_calls)

    def test_changing_active_season_stat_selector_refreshes_stat_detail_rows(self) -> None:
        model = SeasonSelectorModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        with patch("nba2k_editor.ui.qt_app.QDialog.exec", return_value=0):
            app._open_editor_window(model.player_a)

        key = ("Players", model.player_a.index, "Season IDs")
        app.editor_stat_selectors[key].setCurrentText("[99] STATS ID#2")

        self.assertEqual("[99] STATS ID#2", app.state.player_season_stat_id_selection[("Players", model.player_a.index, "Season IDs")])
        self.assertIn(("POINTS", 0, "[99] STATS ID#2"), model.read_calls)

    def test_batch_save_reuses_source_active_season_stat_selector_for_other_selected_players(self) -> None:
        model = SeasonSelectorModel()
        app = QtEditorApp(model)  # type: ignore[arg-type]
        app.state.selected_item_labels["Players"] = {model.player_a.display_label, model.player_b.display_label}
        row_key = app._row_key(model.player_a, model.points_entry)
        app.state.open_rows[row_key] = model.points_entry
        app.state.dirty_rows.add(row_key)
        app.state.player_season_stat_id_selection[("Players", model.player_a.index, "Season IDs")] = "[99] STATS ID#2"

        from nba2k_editor.ui.qt_widgets import EditableFieldRow

        row = EditableFieldRow("Points", "PTS-99", app._mark_row_dirty, row_key)
        row.new_value.setText("77")
        app._save_item_editor(model.player_a, {row_key: row})

        self.assertEqual(
            [("POINTS", 0, "77", "[99] STATS ID#2"), ("POINTS", 1, "77", "[99] STATS ID#2")],
            model.write_calls,
        )


if __name__ == "__main__":
    unittest.main()
