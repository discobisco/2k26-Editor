from __future__ import annotations

import unittest
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.dpg_editor import DpgEditorApp


class FakeDpg:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def get_value(self, tag: str) -> str:
        return str(self.values.get(tag, ""))

    def set_value(self, tag: str, value: object) -> None:
        self.values[tag] = value

    def does_item_exist(self, tag: str) -> bool:
        return True


class FakePopupDpg(FakeDpg):
    def __init__(self) -> None:
        super().__init__()
        self.items: set[str] = set()
        self.configs: dict[str, dict[str, object]] = {}
        self.frames = 0
        self.focused: list[str] = []

    def does_item_exist(self, tag: str) -> bool:
        return tag in self.items

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.items.add(tag)
        self.configs.setdefault(tag, {}).update(kwargs)

    def window(self, **kwargs: object) -> "FakePopupDpg":
        tag = str(kwargs.get("tag") or f"window_{len(self.items)}")
        self.items.add(tag)
        self.configs.setdefault(tag, {}).update(kwargs)
        return self

    def __enter__(self) -> "FakePopupDpg":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def add_text(self, default_value: object = "", *, tag: str | None = None, **_kwargs: object) -> str:
        tag = tag or f"text_{len(self.items)}"
        self.items.add(tag)
        self.values[tag] = default_value
        return tag

    def add_spacer(self, **_kwargs: object) -> None:
        return None

    def add_progress_bar(self, *, tag: str, default_value: float = 0.0, overlay: str = "", **kwargs: object) -> str:
        self.items.add(tag)
        self.values[tag] = default_value
        self.configs[tag] = {"overlay": overlay, **kwargs}
        return tag

    def add_button(self, *, tag: str | None = None, **kwargs: object) -> str:
        tag = tag or f"button_{len(self.items)}"
        self.items.add(tag)
        self.configs[tag] = dict(kwargs)
        return tag

    def render_dearpygui_frame(self) -> None:
        self.frames += 1

    def focus_item(self, tag: str) -> None:
        self.focused.append(tag)


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
        }
        self.writes: list[tuple[int, str]] = []
        self.resets: list[tuple[int, str | None]] = []

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def player_item_labels_for_team_filter(self, _team_filter: str | None, _search_text: str | None) -> list[str]:
        return self.domain_item_labels("Players")

    def player_items_for_team_filter(self, _team_filter: str | None) -> dict[str, RecordListItem]:
        return self.loaded_items["Players"]

    def select_item_by_label(self, domain: str, selected_label: str | None) -> RecordListItem | None:
        if selected_label is None:
            return None
        return self.loaded_items[domain].get(selected_label)

    def selected_detail_title(self, _domain: str, _label: str) -> str:
        return ""

    def selected_player_detail_values(self) -> dict[str, object]:
        return {}

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: str | None = None) -> dict[str, object]:
        return {"raw_value": 80 if index == 0 else 70, "display_value": "80" if index == 0 else "70", "address": 0x2000 + index}

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: str, stat_selector: str | None = None) -> None:
        self.writes.append((index, value))

    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return False

    def reset_player_editor_values(self, *, index: int, stat_selector: str | None = None) -> dict[str, int]:
        self.resets.append((index, stat_selector))
        return {"attempted": 8, "succeeded": 8, "failed": 0}


class DpgEditorBatchSelectionTests(unittest.TestCase):
    def test_dirty_batch_field_applies_even_when_value_matches_source_current(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()
        source = model.items[0]
        entry = FieldEntry("Players", "Vitals", "Ratings", 7, {"display_name": "OVR", "normalized_name": "OVR"})
        row_key = f"Players:{source.index}:{entry.ordinal}"
        app.open_rows[row_key] = entry
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}

        dpg.set_value(app._row_current_tag(source, entry), "80")
        dpg.set_value(app._row_new_tag(source, entry), "80")
        app._mark_row_dirty(row_key)

        app._save_item_editor(dpg, source)

        self.assertEqual([(0, "80"), (1, "80")], model.writes)
        self.assertNotIn(row_key, app.dirty_rows)
        self.assertEqual("saved 2 records", dpg.get_value(app._row_status_tag(source, entry)))

    def test_batch_editor_window_label_uses_player_count_not_player_name(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        source = model.items[0]
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}

        label = app._editor_window_label(source)

        self.assertEqual("Players [2 selected]", label)
        self.assertNotIn(source.label, label)

    def test_single_editor_window_label_keeps_player_name(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        source = model.items[0]
        app.selected_item_labels["Players"] = {source.display_label}

        self.assertEqual("Players [0] Alpha", app._editor_window_label(source))

    def test_batch_save_applies_to_same_non_player_domain(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()
        source = model.team_items[0]
        entry = FieldEntry("Teams", "Vitals", "Names", 7, {"display_name": "City", "normalized_name": "CITYNAME"})
        row_key = f"Teams:{source.index}:{entry.ordinal}"
        app.open_rows[row_key] = entry
        app.selected_item_labels["Teams"] = {item.display_label for item in model.team_items}
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}

        dpg.set_value(app._row_current_tag(source, entry), "Old City")
        dpg.set_value(app._row_new_tag(source, entry), "New City")
        app._save_item_editor(dpg, source)

        self.assertEqual([(0, "New City"), (1, "New City")], model.writes)
        self.assertEqual("saved 2 records", dpg.get_value(app._row_status_tag(source, entry)))

    def test_batch_save_shows_operation_popup_for_multi_selected_players(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        source = model.items[0]
        entry = FieldEntry("Players", "Vitals", "Ratings", 7, {"display_name": "OVR", "normalized_name": "OVR"})
        row_key = f"Players:{source.index}:{entry.ordinal}"
        app.open_rows[row_key] = entry
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}

        dpg.set_value(app._row_current_tag(source, entry), "80")
        dpg.set_value(app._row_new_tag(source, entry), "82")
        app._save_item_editor(dpg, source)

        self.assertEqual([(0, "82"), (1, "82")], model.writes)
        self.assertEqual(1.0, dpg.values[app._operation_progress_tag()])
        self.assertEqual("complete", dpg.configs[app._operation_progress_tag()]["overlay"])
        self.assertIn("saved 2 field writes", str(dpg.values[app._operation_message_tag()]))
        self.assertTrue(dpg.configs[app._operation_popup_tag()]["show"])
        self.assertEqual(560, dpg.configs[app._operation_popup_tag()]["width"])
        self.assertEqual(220, dpg.configs[app._operation_popup_tag()]["height"])
        self.assertTrue(dpg.configs[app._operation_popup_tag()]["no_scrollbar"])
        self.assertEqual(app._operation_popup_tag(), dpg.focused[-1])
        self.assertEqual(0, dpg.frames)

    def test_generator_import_failure_stays_in_status_without_escaping(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        app.generator_display_state = SimpleNamespace(source_loaded=True, player_rows=(object(),), status="ready")
        dpg.items.add(app._player_generator_tag("status"))

        class FakeGeneratorModule:
            def empty_generator_display_state(self, status: str) -> object:
                return SimpleNamespace(status=status, seasons=(), source_team_filters=(), player_rows=())

            def import_generator_to_game_display_state(self, *_args, **_kwargs):
                raise RuntimeError("missing source data")

        app._generator_display_module = lambda: FakeGeneratorModule()  # type: ignore[method-assign]
        app._import_generator_to_game_display(dpg)

        self.assertIn("Import failed: missing source data", str(dpg.values[app._player_generator_tag("status")]))
        app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        dpg.items.add(app._player_generator_tag("status"))

        class FakeGeneratorModule:
            def empty_generator_display_state(self, status: str) -> object:
                return SimpleNamespace(status=status, seasons=(), source_team_filters=(), player_rows=())

            def load_generator_display_state(self):
                raise RuntimeError("missing source data")

        app._generator_display_module = lambda: FakeGeneratorModule()  # type: ignore[method-assign]
        app._load_player_generator_source(dpg)

        self.assertIn("Load failed: missing source data", str(dpg.values[app._player_generator_tag("status")]))

    def test_generator_preview_failure_stays_in_status_without_escaping(self) -> None:
        app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        dpg.items.add(app._player_generator_tag("status"))

        class FakeGeneratorModule:
            def empty_generator_display_state(self, status: str) -> object:
                return SimpleNamespace(status=status, seasons=(), source_team_filters=(), player_rows=())

            def load_generator_display_state(self):
                return SimpleNamespace(source_loaded=True, status="loaded", seasons=("2025",), source_team_filters=("All source teams",), player_rows=())

            def generate_generator_preview_display_state(self, _state):
                raise RuntimeError("missing source row")

        app._generator_display_module = lambda: FakeGeneratorModule()  # type: ignore[method-assign]
        app._display_generator_preview(dpg)

        self.assertIn("Preview failed: missing source row", str(dpg.values[app._player_generator_tag("status")]))

    def test_generator_import_failure_stays_in_popup_without_escaping(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        app.generator_display_state = SimpleNamespace(source_loaded=True, player_rows=(object(),), status="ready")
        dpg.items.add(app._player_generator_tag("status"))

        class FakeGeneratorModule:
            def import_generator_to_game_display_state(self, *_args, **_kwargs):
                raise RuntimeError("missing source data")

        app._generator_display_module = lambda: FakeGeneratorModule()  # type: ignore[method-assign]
        app._import_generator_to_game_display(dpg)

        self.assertEqual("failed", dpg.configs[app._operation_progress_tag()]["overlay"])
        self.assertIn("Import failed: missing source data", str(dpg.values[app._operation_message_tag()]))
        self.assertIn("Import failed: missing source data", str(dpg.values[app._player_generator_tag("status")]))

    def test_untouched_equal_source_field_does_not_batch_write(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()
        source = model.items[0]
        entry = FieldEntry("Players", "Vitals", "Ratings", 7, {"display_name": "OVR", "normalized_name": "OVR"})
        row_key = f"Players:{source.index}:{entry.ordinal}"
        app.open_rows[row_key] = entry
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}

        dpg.set_value(app._row_current_tag(source, entry), "80")
        dpg.set_value(app._row_new_tag(source, entry), "80")

        app._save_item_editor(dpg, source)

        self.assertEqual([], model.writes)
    def test_plain_click_forces_visible_rows_to_single_selection(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()
        first, second = model.items
        first_label = first.display_label
        second_label = second.display_label
        app.selected_item_labels["Players"] = {second_label}
        dpg.set_value(app._list_row_tag("Players", first_label), True)
        dpg.set_value(app._list_row_tag("Players", second_label), True)

        app._select_item_label(dpg, "Players", second_label)

        self.assertEqual({second_label}, app.selected_item_labels["Players"])
        self.assertIs(False, dpg.values[app._list_row_tag("Players", first_label)])
        self.assertIs(True, dpg.values[app._list_row_tag("Players", second_label)])

    def test_reset_player_applies_to_selected_batch_players(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()
        source = model.items[0]
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}
        app.player_season_stat_id_selection[app._season_stat_selector_key(source)] = "[65535] Active"

        app._reset_item_editor(dpg, source)

        self.assertEqual([(0, "[65535] Active"), (1, "[65535] Active")], model.resets)
        self.assertEqual(
            "reset 16 fields across 2 records, 0 failed",
            dpg.get_value(app._editor_status_tag(source)),
        )

    def test_batch_reset_shows_operation_popup_for_multi_selected_players(self) -> None:
        model = FakeModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakePopupDpg()
        source = model.items[0]
        app.selected_item_labels["Players"] = {item.display_label for item in model.items}
        app.player_season_stat_id_selection[app._season_stat_selector_key(source)] = "[65535] Active"

        app._reset_item_editor(dpg, source)

        self.assertEqual([(0, "[65535] Active"), (1, "[65535] Active")], model.resets)
        self.assertEqual(1.0, dpg.values[app._operation_progress_tag()])
        self.assertEqual("complete", dpg.configs[app._operation_progress_tag()]["overlay"])
        self.assertIn("reset 16 fields across 2 records", str(dpg.values[app._operation_message_tag()]))
        self.assertTrue(dpg.configs[app._operation_popup_tag()]["show"])
        self.assertEqual(560, dpg.configs[app._operation_popup_tag()]["width"])
        self.assertEqual(220, dpg.configs[app._operation_popup_tag()]["height"])
        self.assertTrue(dpg.configs[app._operation_popup_tag()]["no_scrollbar"])
        self.assertEqual(app._operation_popup_tag(), dpg.focused[-1])


if __name__ == "__main__":
    unittest.main()



