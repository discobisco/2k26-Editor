from __future__ import annotations

from typing import Any


def build_offset_index(
    offsets: list[dict[str, Any]],
    *,
    offset_index: dict[tuple[str, str], dict[str, Any]],
    offset_normalized_index: dict[tuple[str, str], dict[str, Any]],
    offset_hierarchy_index: dict[tuple[str, str, str, str], dict[str, Any]],
) -> None:
    """Populate facade-owned lookup indexes for the provided offsets entries."""
    offset_index.clear()
    offset_normalized_index.clear()
    offset_hierarchy_index.clear()
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category_raw = str(entry.get("category", "")).strip()
        name_raw = str(entry.get("name", "")).strip()
        if not name_raw:
            continue
        offset_index[(category_raw, name_raw)] = entry

        canonical = str(entry.get("canonical_category", "")).strip()
        normalized = str(entry.get("normalized_name", "")).strip()
        if canonical and normalized:
            offset_normalized_index[(canonical, normalized)] = entry

        source_super_type = str(
            entry.get("source_super_type")
            or entry.get("super_type")
            or entry.get("superType")
            or ""
        ).strip()
        source_category = str(entry.get("source_category") or "").strip()
        source_group = str(entry.get("source_group") or "").strip()
        if source_super_type and source_category and normalized:
            offset_hierarchy_index[(source_super_type, source_category, source_group, normalized)] = entry


def find_offset_entry(
    name: str,
    category: str | None = None,
    *,
    offset_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the offset entry matching the provided exact name/category."""
    exact_name = name.strip()
    if category:
        return offset_index.get((category.strip(), exact_name))
    for (entry_category, entry_name), entry in offset_index.items():
        if entry_name == exact_name and (category is None or entry_category == category.strip()):
            return entry
    return None


def find_offset_entry_by_normalized(
    canonical_category: str,
    normalized_name: str,
    *,
    offset_normalized_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return an offsets entry by exact canonical_category + normalized_name."""
    return offset_normalized_index.get((canonical_category, normalized_name))


def find_offset_entry_by_hierarchy(
    source_super_type: str,
    source_category: str,
    source_group: str,
    normalized_name: str,
    *,
    offset_hierarchy_index: dict[tuple[str, str, str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return an offsets entry by exact hierarchy + normalized name."""
    key = (
        str(source_super_type or "").strip(),
        str(source_category or "").strip(),
        str(source_group or "").strip(),
        str(normalized_name or "").strip(),
    )
    return offset_hierarchy_index.get(key)
