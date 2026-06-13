from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from nba2k_editor.ui.dpg_editor import DpgEditorApp
from nba2k_editor.ui.multi_select_list import MultiSelectListState, copy_multi_select_to_clipboard, render_multi_select_list


class FakeDpg:
    def __init__(self, existing_tags: set[str] | None = None) -> None:
        self.existing_tags = set(existing_tags or set())
        self.children_deleted: list[str] = []
        self.selectables: list[dict[str, Any]] = []
        self.values: dict[str, str] = {}
        self.clipboard = ""

    def does_item_exist(self, tag: str) -> bool:
        return tag in self.existing_tags

    def delete_item(self, tag: str, *, children_only: bool = False) -> None:
        assert children_only is True
        self.children_deleted.append(tag)
        self.selectables = [selectable for selectable in self.selectables if selectable.get("parent") != tag]

    def add_button(self, **kwargs: Any) -> None:
        tag = str(kwargs["tag"])
        self.existing_tags.add(tag)
        self.selectables.append(dict(kwargs))

    def configure_item(self, tag: str, **kwargs: Any) -> None:
        for selectable in self.selectables:
            if selectable.get("tag") == tag:
                selectable.update(kwargs)
                return

    def set_value(self, tag: str, value: object) -> None:
        self.values[tag] = str(value)

    def get_value(self, tag: str) -> str:
        return self.values.get(tag, "")

    def set_clipboard_text(self, value: str) -> None:
        self.clipboard = value


class MinimalModel:
    def __init__(self) -> None:
        self.selected: tuple[str, str | None] | None = None

    def select_item_by_label(self, domain: str, selected: str | None):
        self.selected = (domain, selected)
        return None


def test_multi_select_state_preserves_visible_order_for_copy() -> None:
    state = MultiSelectListState()
    state.toggle("Chicago Bulls")
    state.toggle("Philadelphia 76ers")

    assert state.selected_items(["Philadelphia 76ers", "Boston Celtics", "Chicago Bulls"]) == [
        "Philadelphia 76ers",
        "Chicago Bulls",
    ]
    assert state.copy_text(["Philadelphia 76ers", "Boston Celtics", "Chicago Bulls"]) == "Philadelphia 76ers\nChicago Bulls"

    state.prune(["Boston Celtics"])
    assert state.selected_items(["Boston Celtics"]) == []

    state.toggle("Boston Celtics")
    dpg = FakeDpg()
    assert copy_multi_select_to_clipboard(dpg, state, ["Philadelphia 76ers", "Boston Celtics"]) == 1
    assert dpg.clipboard == "Boston Celtics"


def test_render_multi_select_list_builds_left_click_toggle_rows() -> None:
    dpg = FakeDpg(existing_tags={"teams_list"})
    state = MultiSelectListState()
    clicked: list[str] = []

    render_multi_select_list(
        dpg,
        container_tag="teams_list",
        row_tag=lambda index, _label: f"teams_row_{index}",
        items=["Philadelphia 76ers", "Boston Celtics"],
        state=state,
        on_select=clicked.append,
    )

    assert dpg.children_deleted == ["teams_list"]
    assert [selectable["label"] for selectable in dpg.selectables] == ["  Philadelphia 76ers", "  Boston Celtics"]

    callback: Callable[..., None] = dpg.selectables[0]["callback"]
    callback("sender", None, None)
    assert clicked == ["Philadelphia 76ers"]


def test_dpg_editor_multi_select_copies_multiple_items_from_same_list() -> None:
    app = DpgEditorApp(MinimalModel())  # type: ignore[arg-type]
    app._update_detail_panel = lambda _dpg, _domain: None  # type: ignore[method-assign]
    domain = "Teams"
    dpg = FakeDpg(existing_tags={app._list_tag(domain), app._list_selected_count_tag(domain), app._status_tag(domain)})

    labels = ["Philadelphia 76ers", "Boston Celtics", "Chicago Bulls"]
    app._sync_selectable_list(dpg, domain, labels)

    dpg.selectables[0]["callback"]("sender", None, None)
    dpg.selectables[2]["callback"]("sender", None, None)
    app._copy_selected_list_items(dpg, domain)

    assert app.multi_select_lists[domain].selected_items(labels) == ["Philadelphia 76ers", "Chicago Bulls"]
    assert dpg.selectables[0]["label"] == "✓ Philadelphia 76ers"
    assert dpg.selectables[2]["label"] == "✓ Chicago Bulls"
    assert dpg.clipboard == "Philadelphia 76ers\nChicago Bulls"
    assert dpg.values[app._list_selected_count_tag(domain)] == "2 selected"
    assert dpg.values[app._status_tag(domain)] == "copied 2 selected teams item(s)"
    assert cast(MinimalModel, app.model).selected == (domain, "Chicago Bulls")

    app._clear_selected_list_items(dpg, domain)

    assert app.multi_select_lists[domain].selected_items(labels) == []
    assert dpg.values[app._list_selected_count_tag(domain)] == "0 selected"
