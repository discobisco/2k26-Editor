"""Typed definitions and schema metadata placeholders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, NotRequired, Sequence


class PreparedImportRows(TypedDict):
    header: list[str]
    data_rows: list[list[str]]
    name_col: int
    value_columns: list[int]
    first_name_col: NotRequired[int | None]
    last_name_col: NotRequired[int | None]


class CoyImportLayout(TypedDict, total=False):
    name_columns: Sequence[int]
    name_col: int
    value_columns: Sequence[int]
    column_headers: Sequence[str]
    skip_names: Sequence[str]


@dataclass
class FieldMetadata:
    offset: int
    start_bit: int
    length: int
    requires_deref: bool = False
    deref_offset: int = 0
    widget: object | None = None
    values: tuple[str, ...] | None = None
    data_type: str | None = None
    byte_length: int = 0


FieldWriteSpec = tuple[int, int, int, int, bool, int]

class ExportFieldSpec(TypedDict):
    category: str
    name: str
    offset: int
    hex: str
    length: int
    start_bit: int
    requires_deref: bool
    deref_offset: int
    type: str | None
    meta: dict[str, object]


__all__ = ["PreparedImportRows", "CoyImportLayout", "FieldMetadata", "FieldWriteSpec", "ExportFieldSpec"]
