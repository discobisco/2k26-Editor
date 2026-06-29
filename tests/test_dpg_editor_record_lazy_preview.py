from __future__ import annotations

import inspect
import unittest
from typing import Any

from nba2k_editor.ui.dpg_editor import DpgEditorApp


class FakeDpg:
    def does_item_exist(self, _tag: str) -> bool:
        return False

    def set_value(self, _tag: str, _value: object) -> None:
        pass

    def configure_item(self, _tag: str, **_kwargs: object) -> None:
        pass

    def delete_item(self, _tag: str, *, children_only: bool = False) -> None:
        pass


class LazyRecordModel:
    def __init__(self) -> None:
        self.refresh_history_calls = 0
        self.refresh_record_calls = 0
        self.clear_history_calls = 0
        self.clear_record_calls = 0
        self.loaded_items = {"NBA History": {}, "NBA Records": {}, "Teams": {}, "Players": {}}

    def domain_item_labels(self, domain: str) -> list[str]:
        return []

    def domain_item_count(self, domain: str) -> int:
        return 0

    def selected_item(self, domain: str) -> Any:
        return None

    def select_item_by_label(self, domain: str, selected_label: str | None) -> Any:
        return None

    def domain_status(self, domain: str) -> str:
        return "loaded"

    def selected_detail_title(self, domain: str, label: str) -> str:
        return ""

    def selected_record_summary_values(self, domain: str) -> dict[str, str]:
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


class DpgEditorRecordLazyPreviewTests(unittest.TestCase):
    def test_history_and_records_list_sync_does_not_eagerly_build_preview_rows(self) -> None:
        model = LazyRecordModel()
        app = DpgEditorApp(model)  # type: ignore[arg-type]
        dpg = FakeDpg()

        app._sync_domain_list(dpg, "NBA History")
        app._sync_domain_list(dpg, "NBA Records")

        self.assertEqual(0, model.clear_history_calls)
        self.assertEqual(0, model.clear_record_calls)
        self.assertEqual(0, model.refresh_history_calls)
        self.assertEqual(0, model.refresh_record_calls)

    def test_history_and_records_screens_keep_existing_layout_buttons_only(self) -> None:
        history_source = inspect.getsource(DpgEditorApp._build_history_screen)
        records_source = inspect.getsource(DpgEditorApp._build_records_screen)
        history_table_source = inspect.getsource(DpgEditorApp._render_history_table)

        self.assertNotIn('self._list_content_tag(domain)', history_source)
        self.assertNotIn('dpg.add_table_column(label="Edit")', history_table_source)
        self.assertNotIn('dpg.add_button(label="Edit"', history_table_source)
        self.assertIn("_attach_and_scan(dpg, domain)", history_source)
        self.assertNotIn('self._list_content_tag(domain)', records_source)
        self.assertNotIn('label="Edit Selected Record"', records_source)
        self.assertNotIn('dpg.add_table_column(label="Edit")', records_source)
        self.assertIn("_attach_and_scan(dpg, domain)", records_source)


if __name__ == "__main__":
    unittest.main()
