from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.models.view_data import (
    DomainRefreshRequest,
    DomainRefreshView,
    EditorFieldView,
    EditorGroupView,
    EditorSectionView,
    EditorView,
    EditorViewRequest,
    PlayerListRequest,
    PlayerListView,
    TableView,
    TableViewRequest,
    TableViewRow,
)


def _item(index: int = 7) -> RecordListItem:
    return RecordListItem("Players", index, 0x1000 + index * 0x20, f"Player {index}")


def _entry() -> FieldEntry:
    return FieldEntry("Players", "Attributes", "Offense", 3, {"normalized_name": "MIDRANGE", "display_name": "Mid Range"})


def test_requests_are_frozen_value_objects() -> None:
    item = _item()
    requests = (
        DomainRefreshRequest(("Players", "Teams")),
        PlayerListRequest(4, "guard"),
        TableViewRequest(("NBA History", "Season Awards", "MVP")),
        EditorViewRequest(item, (("Season Stats", "[42] Active"),)),
    )

    for request in requests:
        with pytest.raises(FrozenInstanceError):
            request.__setattr__(next(iter(request.__dataclass_fields__)), None)


def test_views_preserve_stable_record_index_and_address() -> None:
    item = _item()
    row = TableViewRow(item, (("Player", item.display_label), ("Value", "96")))
    domain = DomainRefreshView("Players", (item,), "loaded 1 players records", 5)
    players = PlayerListView(4, "player", (item,), 5)
    table = TableView(("NBA Records", "Career", "Points"), (row,), 5)

    for resolved in (domain.items[0], players.items[0], table.rows[0].item):
        assert resolved.index == item.index
        assert resolved.address == item.address
        assert resolved is item


def test_editor_view_contains_only_tuple_owned_children() -> None:
    item = _item()
    field = EditorFieldView(_entry(), "84", ("80", "84", "88"), True)
    view = EditorView(
        source=item,
        sections=(EditorSectionView("Attributes", (EditorGroupView("Offense", (field,)),)),),
        season_stat_options=(("Season Stats", ("[42] Active",)),),
        version=9,
    )

    assert view.source.index == 7
    assert view.sections[0].groups[0].fields == (field,)
    assert view.season_stat_options == (("Season Stats", ("[42] Active",)),)
    with pytest.raises(FrozenInstanceError):
        view.version = 10  # type: ignore[misc]
