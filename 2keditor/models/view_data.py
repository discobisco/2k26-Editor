from __future__ import annotations

from dataclasses import dataclass

from nba2k_editor.models.schema import FieldEntry, RecordListItem


@dataclass(frozen=True)
class DomainRefreshRequest:
    domains: tuple[str, ...]


@dataclass(frozen=True)
class PlayerListRequest:
    filter_key: str | int
    query: str
    primary_position: str = "All Positions"


@dataclass(frozen=True)
class TableViewRequest:
    key: tuple[object, ...]


@dataclass(frozen=True)
class EditorViewRequest:
    source: RecordListItem
    selected_stat_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TableViewRow:
    item: RecordListItem
    cells: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DomainRefreshView:
    domain: str
    items: tuple[RecordListItem, ...]
    status: str
    version: int


@dataclass(frozen=True)
class PlayerListView:
    filter_key: str | int
    query: str
    items: tuple[RecordListItem, ...]
    version: int


@dataclass(frozen=True)
class TableView:
    key: tuple[object, ...]
    rows: tuple[TableViewRow, ...]
    version: int


@dataclass(frozen=True)
class EditorFieldView:
    entry: FieldEntry
    display_value: str
    options: tuple[str, ...]
    writeable: bool


@dataclass(frozen=True)
class EditorGroupView:
    label: str
    fields: tuple[EditorFieldView, ...]


@dataclass(frozen=True)
class EditorSectionView:
    label: str
    groups: tuple[EditorGroupView, ...]


@dataclass(frozen=True)
class EditorView:
    source: RecordListItem
    sections: tuple[EditorSectionView, ...]
    season_stat_options: tuple[tuple[str, tuple[str, ...]], ...]
    version: int


__all__ = [
    "DomainRefreshRequest",
    "DomainRefreshView",
    "EditorFieldView",
    "EditorGroupView",
    "EditorSectionView",
    "EditorView",
    "EditorViewRequest",
    "PlayerListRequest",
    "PlayerListView",
    "TableView",
    "TableViewRequest",
    "TableViewRow",
]
