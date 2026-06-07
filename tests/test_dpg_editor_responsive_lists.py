from __future__ import annotations

from nba2k_editor.models.data_model import EDITOR_DOMAINS
from nba2k_editor.ui.dpg_editor import DpgEditorApp


class FakeDpg:
    def __init__(self, viewport_height: int) -> None:
        self.viewport_height = viewport_height
        self.configured: list[tuple[str, int]] = []

    def get_viewport_client_height(self) -> int:
        return self.viewport_height

    def does_item_exist(self, _tag: str) -> bool:
        return True

    def configure_item(self, tag: str, **kwargs: object) -> None:
        num_items = kwargs.get("num_items")
        if isinstance(num_items, int):
            self.configured.append((tag, num_items))


class FakeModel:
    pass


def test_record_list_visible_rows_expand_and_contract_with_viewport_height() -> None:
    app = DpgEditorApp(FakeModel())  # type: ignore[arg-type]
    dpg = FakeDpg(viewport_height=900)

    app._resize_record_lists(dpg)
    large = {tag: rows for tag, rows in dpg.configured}

    dpg.viewport_height = 600
    dpg.configured.clear()
    app._resize_record_lists(dpg)
    small = {tag: rows for tag, rows in dpg.configured}

    assert large[app._list_tag("Players")] == 40
    assert small[app._list_tag("Players")] == 24
    assert small[app._list_tag("Players")] < large[app._list_tag("Players")]
    assert set(large) == {app._list_tag(domain) for domain in EDITOR_DOMAINS}
    assert set(small) == {app._list_tag(domain) for domain in EDITOR_DOMAINS}
