from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from nba2k_editor.ui.qt_widgets import RecordListWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_large_player_list_filter_preserves_all_qt_items() -> None:
    app = _app()
    widget = RecordListWidget()
    records = [(index, f"Player {index:04d}") for index in range(5430)]
    widget.set_all_records(records)
    sampled_item_ids = {index: id(widget.item(index)) for index in (0, 1, 2715, 5429)}

    visible = set(range(300, 315))
    widget.set_visible_indexes(visible)

    assert widget.count() == 5430
    assert sum(not widget.item(row).isHidden() for row in range(widget.count())) == 15
    assert sampled_item_ids == {index: id(widget.item(index)) for index in sampled_item_ids}

    widget.set_visible_records([(0, "Draft Prospect")])

    assert widget.count() == 5430
    assert widget.item(0).text() == "Draft Prospect"
    assert id(widget.item(0)) == sampled_item_ids[0]

    widget.set_visible_records(records)

    assert widget.count() == 5430
    assert widget.item(0).text() == "Player 0000"
    assert all(not widget.item(row).isHidden() for row in range(widget.count()))
    assert sampled_item_ids == {index: id(widget.item(index)) for index in sampled_item_ids}
