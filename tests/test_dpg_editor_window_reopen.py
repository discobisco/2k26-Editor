from __future__ import annotations

from nba2k_editor.models.schema import RecordListItem
from nba2k_editor.ui.dpg_editor import DpgEditorApp


class ExistingWindowDpg:
    def __init__(self, existing_tag: str) -> None:
        self.existing_tag = existing_tag
        self.configured: list[tuple[str, dict[str, object]]] = []
        self.focused: list[str] = []

    def does_item_exist(self, tag: str) -> bool:
        return tag == self.existing_tag

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.configured.append((tag, kwargs))

    def focus_item(self, tag: str) -> None:
        self.focused.append(tag)


class MinimalModel:
    pass


def test_open_editor_window_reshows_existing_hidden_window_before_focus() -> None:
    app = DpgEditorApp(MinimalModel())  # type: ignore[arg-type]
    item = RecordListItem(domain="Teams", index=0, address=0x3CAD85690, label="Philadelphia 76ers")
    win_tag = "editor__Teams__0__window"
    dpg = ExistingWindowDpg(win_tag)

    app._open_editor_window(dpg, item)

    assert dpg.configured == [(win_tag, {"show": True})]
    assert dpg.focused == [win_tag]
