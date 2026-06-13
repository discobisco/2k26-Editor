from __future__ import annotations

import re
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from contracts import GeneratorInputContract

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"([A-Z]+)")


def read_sheet_rows_for_season(contract: GeneratorInputContract, sheet_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    validated = contract.validate()
    workbook_path = Path(validated.source_root) / "NBA DATA Master.xlsx"
    season = int(validated.season)
    rows: list[dict[str, Any]] = []
    for row in iter_sheet_rows(workbook_path, sheet_name):
        if row.get("season") == season:
            rows.append(row)
            if limit is not None and len(rows) >= int(limit):
                break
    return rows


def iter_sheet_rows(workbook_path: str | Path, sheet_name: str) -> Iterable[dict[str, Any]]:
    workbook_file = _workbook_cache_key(workbook_path)
    yield from _cached_workbook_rows(workbook_file)[sheet_name]


def workbook_sheet_names(workbook_path: str | Path) -> tuple[str, ...]:
    workbook_file = _workbook_cache_key(workbook_path)
    return tuple(_cached_workbook_rows(workbook_file).keys())


def _workbook_cache_key(workbook_path: str | Path) -> str:
    workbook_file = Path(workbook_path).expanduser().resolve()
    if not workbook_file.is_file():
        raise FileNotFoundError(f"workbook does not exist: {workbook_file}")
    return str(workbook_file)


@lru_cache(maxsize=None)
def _cached_sheet_rows(workbook_file: str, sheet_name: str) -> tuple[dict[str, Any], ...]:
    return _cached_workbook_rows(workbook_file)[sheet_name]


@lru_cache(maxsize=None)
def _cached_workbook_rows(workbook_file: str) -> dict[str, tuple[dict[str, Any], ...]]:
    rows_by_sheet: dict[str, tuple[dict[str, Any], ...]] = {}
    with zipfile.ZipFile(workbook_file) as workbook:
        shared_strings = _read_shared_strings(workbook)
        for sheet_name, sheet_path in _worksheet_paths_by_name(workbook).items():
            rows_by_sheet[sheet_name] = _read_sheet_rows(workbook, sheet_path, shared_strings)
    return rows_by_sheet


def _read_sheet_rows(workbook: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    header: list[str] | None = None
    with workbook.open(sheet_path) as handle:
        for event, element in ElementTree.iterparse(handle, events=("end",)):
            if _local_name(element.tag) != "row":
                continue
            values = _row_values(element, shared_strings)
            if header is None:
                header = [_normalize_header(value) for value in values]
            else:
                if not any(value is not None for value in values):
                    element.clear()
                    continue
                rows.append({name: _normalize_cell(values[index] if index < len(values) else None) for index, name in enumerate(header) if name})
            element.clear()
    return tuple(rows)



def _worksheet_paths_by_name(workbook: zipfile.ZipFile) -> dict[str, str]:
    workbook_tree = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    namespace = {"xlsx": _MAIN_NS}
    rels = _worksheet_relationship_targets(workbook)
    paths: dict[str, str] = {}
    for sheet in workbook_tree.findall(".//xlsx:sheet", namespace):
        name = str(sheet.attrib.get("name") or "").strip()
        rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id", "")
        if name and rel_id in rels:
            paths[name] = rels[rel_id]
    return paths


def _worksheet_relationship_targets(workbook: zipfile.ZipFile) -> dict[str, str]:
    rel_tree = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    targets: dict[str, str] = {}
    for relationship in rel_tree.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        rel_id = str(relationship.attrib.get("Id") or "")
        target = str(relationship.attrib.get("Target") or "").lstrip("/")
        if not rel_id or not target:
            continue
        targets[rel_id] = target if target.startswith("xl/") else f"xl/{target}"
    return targets


def _worksheet_path_for_name(workbook: zipfile.ZipFile, sheet_name: str) -> str:
    paths = _worksheet_paths_by_name(workbook)
    if sheet_name not in paths:
        raise KeyError(f"workbook sheet not found: {sheet_name}")
    return paths[sheet_name]


def _read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    strings: list[str] = []
    with workbook.open("xl/sharedStrings.xml") as handle:
        for event, element in ElementTree.iterparse(handle, events=("end",)):
            if _local_name(element.tag) != "si":
                continue
            text_parts = [node.text or "" for node in element.iter() if _local_name(node.tag) == "t"]
            strings.append("".join(text_parts))
            element.clear()
    return strings


def _row_values(row_element: ElementTree.Element, shared_strings: list[str]) -> list[Any]:
    values: list[Any] = []
    for cell in row_element:
        if _local_name(cell.tag) != "c":
            continue
        column_index = _cell_column_index(str(cell.attrib.get("r") or ""))
        while len(values) < column_index:
            values.append(None)
        values.append(_cell_value(cell, shared_strings))
    return values


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> Any:
    cell_type = str(cell.attrib.get("t") or "")
    value_element = next((child for child in cell if _local_name(child.tag) == "v"), None)
    if cell_type == "inlineStr":
        text_parts = [node.text or "" for node in cell.iter() if _local_name(node.tag) == "t"]
        return "".join(text_parts)
    if value_element is None or value_element.text is None:
        return None
    raw = value_element.text
    if cell_type == "s":
        index = int(raw)
        if index < 0 or index >= len(shared_strings):
            raise IndexError(f"shared string index out of range: {index}")
        return shared_strings[index]
    if cell_type == "str":
        return raw
    return _coerce_number(raw)


def _coerce_number(raw: str) -> Any:
    text = str(raw).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _normalize_cell(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.upper() == "NA":
            return None
        return text
    return value


def _normalize_header(value: Any) -> str:
    normalized = _normalize_cell(value)
    return str(normalized or "").strip()


def _cell_column_index(cell_ref: str) -> int:
    match = _CELL_REF_RE.match(cell_ref)
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


__all__ = ["iter_sheet_rows", "read_sheet_rows_for_season", "workbook_sheet_names"]
