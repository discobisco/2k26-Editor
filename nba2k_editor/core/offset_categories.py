from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, cast

from .conversions import to_int

DropdownLoader = Callable[..., dict[str, dict[str, list[str]]]]
SelectedEntriesIter = Callable[[dict[str, object], str | None], Any]
SuperTypeNormalizer = Callable[[object], str]
LengthInferer = Callable[[object, object], int]


def _load_dropdowns_map(*, timed: Any, load_dropdowns: DropdownLoader, module_file: str) -> dict[str, dict[str, list[str]]]:
    """Load dropdown metadata once per process from Offsets/dropdowns.json when present."""
    with timed("offsets.load_dropdowns"):
        base_dir = Path(module_file).resolve().parent.parent
        search_dirs = [base_dir / "Offsets", base_dir / "offsets"]
        return load_dropdowns(search_dirs=search_dirs)



def _load_categories_bundle(
    offset_config: dict[str, object] | None,
    current_offset_target: str | None,
    module_name: str,
    *,
    load_dropdowns_map: Callable[[], dict[str, dict[str, list[str]]]],
    iter_selected_entries: SelectedEntriesIter,
    normalized_super_type_label: SuperTypeNormalizer,
    infer_length_bits: LengthInferer,
) -> tuple[dict[str, list[dict]], dict[str, str], dict[str, str]]:
    """
    Load editor categories plus their metadata from the active offsets payload.
    Returns (categories, super_types, canonical_map). If parsing fails or no
    offsets are available, empty collections are returned.
    """
    dropdowns = load_dropdowns_map()
    category_super_types: dict[str, str] = {}
    category_canonical: dict[str, str] = {}
    config_data = cast(dict[str, object], offset_config) if isinstance(offset_config, dict) else None

    def _register_category_metadata(cat_label: str, entry: dict | None = None) -> None:
        """Capture super type and canonical label for a category."""
        if not cat_label:
            return
        cat_key = str(cat_label)
        if cat_key not in category_super_types:
            entry_super = None
            if isinstance(entry, dict):
                entry_super = entry.get("super_type") or entry.get("superType")
            entry_super = normalized_super_type_label(entry_super)
            if entry_super:
                category_super_types[cat_key] = str(entry_super)
        if cat_key not in category_canonical:
            canonical = None
            if isinstance(entry, dict):
                canonical = entry.get("canonical_category")
            category_canonical[cat_key] = str(canonical) if canonical else cat_key

    def _finalize_field_metadata(
        field: dict[str, object],
        category_label: str,
        *,
        offset_val: int | None = None,
        start_bit_val: int | None = None,
        length_val: int | None = None,
        source_entry: dict | None = None,
    ) -> None:
        """Ensure each field dictionary carries core offset metadata."""
        if not isinstance(field, dict):
            return
        if category_label:
            field["category"] = category_label
        provided_hex = None
        if source_entry is not None and source_entry.get("hex"):
            provided_hex = str(source_entry.get("hex"))
        if offset_val is None:
            offset_val = to_int(field.get("address") or field.get("offset") or field.get("hex"))
        if offset_val is not None and offset_val >= 0:
            offset_int = int(offset_val)
            field["address"] = offset_int
            field.setdefault("offset", hex(offset_int))
            if provided_hex is None:
                provided_hex = f"0x{offset_int:X}"
        if provided_hex is not None:
            field["hex"] = provided_hex
        if "startBit" not in field or field.get("startBit") in (None, ""):
            start_val = start_bit_val
            if start_val is None:
                start_val = to_int(field.get("start_bit"))
            field["startBit"] = int(start_val or 0)
        if "start_bit" in field and "startBit" in field:
            field.pop("start_bit", None)
        if "length" not in field or to_int(field.get("length")) <= 0:
            length = length_val
            if length is None:
                length = to_int(field.get("length") or field.get("size"))
            if length is not None and length > 0:
                field["length"] = int(length)
        if source_entry is not None and source_entry.get("type") and not field.get("type"):
            field["type"] = source_entry.get("type")
        if source_entry is not None:
            for key_name in (
                "canonical_category",
                "normalized_name",
                "super_type",
                "type_normalized",
                "source_root_category",
                "source_table_group",
                "source_table_path",
                "source_offsets_domain",
                "source_offsets_file",
                "length_inferred",
                "start_bit_inferred",
                "parse_report_entry_id",
                "selected_version",
                "selected_version_key",
            ):
                if source_entry.get(key_name) and not field.get(key_name):
                    field[key_name] = source_entry.get(key_name)

    def _humanize_label(raw: object) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", text) if tok]
        if not tokens:
            return text
        words: list[str] = []
        for tok in tokens:
            if tok.isupper() and len(tok) <= 3:
                words.append(tok)
            else:
                words.append(tok.capitalize())
        return " ".join(words)

    def _disambiguate_category_field_names(cat_map: dict[str, list[dict]]) -> None:
        for _category, fields in cat_map.items():
            if not isinstance(fields, list) or not fields:
                continue
            name_counts: dict[str, int] = {}
            for field in fields:
                if not isinstance(field, dict):
                    continue
                base_name = str(field.get("name") or "").strip()
                if not base_name:
                    continue
                name_key = base_name.casefold()
                name_counts[name_key] = name_counts.get(name_key, 0) + 1
            if not any(count > 1 for count in name_counts.values()):
                continue
            used_names: set[str] = set()
            for field in fields:
                if not isinstance(field, dict):
                    continue
                base_name = str(field.get("name") or "").strip()
                if not base_name:
                    continue
                name_key = base_name.casefold()
                if name_counts.get(name_key, 0) <= 1:
                    used_names.add(name_key)
                    continue
                suffix_parts: list[str] = []
                source_group = str(field.get("source_table_group") or field.get("source_group") or "").strip()
                if source_group:
                    suffix_parts.append(_humanize_label(source_group))
                source_path = str(field.get("source_table_path") or "").strip()
                if not suffix_parts and source_path:
                    path_parts = [segment for segment in source_path.split("/") if segment]
                    if len(path_parts) > 1:
                        suffix_parts.append(_humanize_label(path_parts[-1]))
                version_label = str(field.get("selected_version") or "").strip()
                if version_label:
                    suffix_parts.append(version_label)
                candidate = base_name
                if suffix_parts:
                    candidate = f"{base_name} [{' / '.join(suffix_parts)}]"
                unique_name = candidate
                suffix_idx = 2
                while unique_name.casefold() in used_names:
                    unique_name = f"{candidate} ({suffix_idx})"
                    suffix_idx += 1
                field["display_name"] = base_name
                field["name"] = unique_name
                used_names.add(unique_name.casefold())

    def _record_field_state(category_name: str, field: dict[str, object]) -> None:
        if not isinstance(field, dict):
            return
        seen_fields_global.setdefault(category_name, set()).add(str(field.get("name", "")))
        offset_int = to_int(field.get("offset"))
        start_val = to_int(field.get("startBit") or field.get("start_bit"))
        length_val = to_int(field.get("length"))
        bit_cursor[(category_name, offset_int)] = max(
            bit_cursor.get((category_name, offset_int), 0),
            start_val + max(length_val, 0),
        )

    def _record_category_state(cat_map: dict[str, list[dict]]) -> None:
        for category_name, fields in cat_map.items():
            if not isinstance(fields, list):
                continue
            for field in fields:
                _record_field_state(category_name, cast(dict[str, object], field))

    base_categories: dict[str, list[dict]] = {}
    bit_cursor: dict[tuple[str, int], int] = {}
    seen_fields_global: dict[str, set[str]] = {}
    if config_data is not None:
        hierarchy_obj = config_data.get("hierarchy")
        if not isinstance(hierarchy_obj, dict):
            return {}, category_super_types, category_canonical
        categories: dict[str, list[dict]] = {}
        target_exec = current_offset_target or module_name
        combined_sections = [
            entry
            for entry in iter_selected_entries(config_data, target_exec)
            if isinstance(entry, dict)
        ]
        seen_fields: set[tuple[str, str, str, str, str]] = set()
        for entry in combined_sections:
            cat_name = str(entry.get("category", "Misc")).strip() or "Misc"
            field_name = str(entry.get("name", "")).strip()
            if not field_name:
                continue
            _register_category_metadata(cat_name, entry)
            normalized_name = str(entry.get("normalized_name") or "").strip()
            key = (
                cat_name.lower(),
                normalized_name,
                str(entry.get("source_table_group") or entry.get("source_group") or "").strip().casefold(),
                str(entry.get("source_table_path") or "").strip().casefold(),
                str(entry.get("source_offsets_file") or "").strip().casefold(),
            )
            if key in seen_fields:
                continue
            seen_fields.add(key)
            offset_val = to_int(entry.get("address") or entry.get("offset") or entry.get("hex"))
            if offset_val < 0:
                continue
            start_bit = to_int(entry.get("startBit") or entry.get("start_bit"))
            length_val = to_int(entry.get("length"))
            size_val = to_int(entry.get("size"))
            entry_type = str(entry.get("type", "")).lower()
            if length_val <= 0:
                if entry_type in ("bitfield", "bool", "boolean", "combo"):
                    length_val = size_val
                elif entry_type in ("number", "slider", "int", "uint", "pointer", "float"):
                    length_val = size_val * 8
            if length_val <= 0:
                length_val = infer_length_bits(entry.get("type"), entry.get("length"))
            if length_val <= 0:
                continue
            field: dict[str, object] = {
                "name": field_name,
                "offset": hex(offset_val),
                "startBit": int(start_bit),
                "length": int(length_val),
            }
            raw_type = entry.get("type")
            normalized_type = entry.get("type_normalized")
            if raw_type not in (None, ""):
                field["type_raw"] = raw_type
            if normalized_type not in (None, ""):
                field["type_normalized"] = normalized_type
                field["type"] = normalized_type
            elif raw_type not in (None, ""):
                field["type"] = raw_type
            if entry.get("requiresDereference"):
                field["requiresDereference"] = True
                field["dereferenceAddress"] = to_int(entry.get("dereferenceAddress"))
            if "values" in entry and isinstance(entry["values"], list):
                field["values"] = entry["values"]
            try:
                dcat = dropdowns.get(cat_name) or dropdowns.get(cat_name.title()) or {}
                if field_name in dcat and isinstance(dcat[field_name], list):
                    field.setdefault("values", list(dcat[field_name]))
                elif field_name.upper().startswith("PLAYTYPE") and isinstance(dcat.get("PLAYTYPE"), list):
                    field.setdefault("values", list(dcat["PLAYTYPE"]))
            except Exception:
                pass
            _finalize_field_metadata(
                field,
                cat_name,
                offset_val=offset_val,
                start_bit_val=start_bit,
                length_val=length_val,
                source_entry=entry,
            )
            categories.setdefault(cat_name, []).append(field)
        if categories:
            _disambiguate_category_field_names(categories)
            base_categories = {key: list(value) for key, value in categories.items()}
            _record_category_state(base_categories)
    if base_categories:
        categories = {key: list(value) for key, value in base_categories.items()}
        if categories:
            return categories, dict(category_super_types), dict(category_canonical)
    return {}, dict(category_super_types), dict(category_canonical)


