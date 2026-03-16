from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, cast

from .conversions import to_int

JsonReader = Callable[[Path], tuple[dict[str, Any] | None, str | None]]
VersionLabelDeriver = Callable[[str | None], str | None]


def _split_version_tokens(raw_key: object) -> tuple[str, ...]:
    text = str(raw_key or "").strip()
    if not text:
        return ()
    tokens = [chunk.strip().upper() for chunk in text.split(",") if chunk and chunk.strip()]
    return tuple(dict.fromkeys(tokens))



def _version_key_matches(raw_key: object, target_label: str | None) -> bool:
    target = str(target_label or "").strip().upper()
    if not target:
        return False
    tokens = _split_version_tokens(raw_key)
    if tokens:
        return target in tokens
    return str(raw_key or "").strip().upper() == target



def _select_version_entry(per_version: dict[str, object], target_label: str) -> dict[str, object] | None:
    for raw_key, payload in per_version.items():
        if not isinstance(payload, dict):
            continue
        if _version_key_matches(raw_key, target_label):
            return payload
    return None



def _select_active_version(
    versions_map: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
    derive_version_label: VersionLabelDeriver,
) -> tuple[str, str, dict[str, object]] | None:
    version_hint = derive_version_label(target_executable)
    if require_hint and not version_hint:
        return None
    selected_key: str | None = None
    selected_label = version_hint or ""
    if version_hint:
        for key in versions_map.keys():
            if _version_key_matches(key, version_hint):
                selected_key = str(key)
                break
        if selected_key is None:
            return None
    else:
        selected_key = str(next(iter(versions_map.keys()), ""))
        selected_label = selected_key
    selected_info = versions_map.get(selected_key) if selected_key else None
    if not isinstance(selected_info, dict) or not selected_key:
        return None
    return selected_label, selected_key, cast(dict[str, object], selected_info)



def _read_json_cached(path: Path, *, read_json_with_error: JsonReader) -> dict[str, Any] | None:
    parsed, _error = read_json_with_error(path)
    return parsed



def _read_json_with_error(path: Path, *, offset_cache: Any) -> tuple[dict[str, Any] | None, str | None]:
    cached = offset_cache.get_json(path)
    if cached is not None:
        return cached, None
    try:
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
    except json.JSONDecodeError as exc:
        return None, (
            f"{path}: invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        )
    except OSError as exc:
        return None, f"{path}: unable to read file: {exc}"
    except Exception as exc:
        return None, f"{path}: unable to parse JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, f"{path}: top-level JSON value must be an object."
    offset_cache.set_json(path, parsed)
    return parsed, None



def _build_dropdown_values_index(raw_dropdowns: object) -> dict[tuple[str, str, str], list[str]]:
    index: dict[tuple[str, str, str], list[str]] = {}
    if not isinstance(raw_dropdowns, dict):
        return index
    dropdown_entries = raw_dropdowns.get("dropdowns")
    if not isinstance(dropdown_entries, list):
        return index
    for entry in dropdown_entries:
        if not isinstance(entry, dict):
            continue
        canonical_category = str(entry.get("canonical_category") or "").strip()
        normalized_name = str(entry.get("normalized_name") or "").strip()
        versions = entry.get("versions")
        if not canonical_category or not normalized_name or not isinstance(versions, dict):
            continue
        category_key = canonical_category.lower()
        normalized_key = normalized_name.upper()
        for version_key, value in versions.items():
            if not isinstance(value, dict):
                continue
            values = value.get("values")
            if not isinstance(values, list):
                values = value.get("dropdown")
            if not isinstance(values, list):
                continue
            cleaned_values = [str(item) for item in values]
            if not cleaned_values:
                continue
            for token in _split_version_tokens(version_key):
                index[(category_key, normalized_key, token)] = cleaned_values
    return index



def _resolve_split_category(
    root_category: str,
    table_segments: tuple[str, ...],
    *,
    player_stats_table_category_map: dict[str, str],
) -> str:
    root = str(root_category or "").strip() or "Misc"
    if root.lower() != "stats":
        return root
    if not table_segments:
        return "Stats - Misc"
    table_key = str(table_segments[0] or "").strip().lower()
    mapped = player_stats_table_category_map.get(table_key)
    if mapped:
        return mapped
    table_label = str(table_segments[0]).strip()
    return f"Stats - {table_label}" if table_label else "Stats - Misc"



def _iter_hierarchy_leaf_nodes(node: object, path_segments: tuple[str, ...]):
    if isinstance(node, list):
        for item in node:
            yield from _iter_hierarchy_leaf_nodes(item, path_segments)
        return
    if not isinstance(node, dict):
        return

    versions_raw = node.get("versions")
    normalized_raw = (
        node.get("normalized_name")
        or node.get("canonical_name")
        or node.get("name")
        or node.get("display_name")
    )
    if isinstance(versions_raw, dict) and normalized_raw:
        yield cast(dict[str, object], node), path_segments
        return

    for key, child in node.items():
        if not isinstance(child, (dict, list)):
            continue
        child_path = path_segments + (str(key),)
        yield from _iter_hierarchy_leaf_nodes(child, child_path)



def _resolve_hierarchy_context(
    path_segments: tuple[str, ...],
    *,
    source_file: str,
    leaf_node: dict[str, object],
    version_payload: dict[str, object],
    split_schema_file_map: dict[str, dict[str, tuple[str, str]]],
    normalized_super_type_label: Callable[[object], str],
    looks_like_super_type: Callable[[object], bool],
    resolve_split_category: Callable[[str, tuple[str, ...]], str],
) -> dict[str, object]:
    segments = tuple(str(seg).strip() for seg in path_segments if str(seg).strip())
    version_super = normalized_super_type_label(
        version_payload.get("super_type")
        or version_payload.get("superType")
        or leaf_node.get("super_type")
        or leaf_node.get("superType")
    )
    file_category_map = split_schema_file_map.get(str(source_file or "").strip().casefold(), {})
    source_category = "Misc"
    source_group = ""
    table_segments: tuple[str, ...] = ()
    source_super_type = version_super
    split_resolved = file_category_map.get(str(segments[0] if segments else "").strip().lower())
    if split_resolved is not None:
        source_category, split_super_type = split_resolved
        source_super_type = split_super_type or source_super_type
        source_group = str(segments[1] if len(segments) > 1 else "")
        table_segments = tuple(segments[1:])
    elif segments and looks_like_super_type(segments[0]):
        source_super_type = str(segments[0]).strip() or source_super_type
        source_category = str(segments[1] if len(segments) > 1 else "Misc")
        source_group = str(segments[2] if len(segments) > 2 else "")
        table_segments = tuple(segments[2:])
    else:
        source_category = str(segments[0] if segments else "Misc")
        source_group = str(segments[1] if len(segments) > 1 else "")
        table_segments = tuple(segments[1:])
    emitted_category = resolve_split_category(source_category, table_segments)
    source_table_path = "/".join(segments) if segments else source_category
    return {
        "source_super_type": source_super_type,
        "source_category": source_category,
        "source_group": source_group,
        "source_table_segments": table_segments,
        "source_table_path": source_table_path,
        "emitted_category": emitted_category,
    }



def _iter_hierarchy_sections(hierarchy: object):
    if not isinstance(hierarchy, dict):
        return
    for source_file, raw_domain in hierarchy.items():
        if not isinstance(raw_domain, dict):
            continue
        for domain_key, categories in raw_domain.items():
            if isinstance(categories, dict):
                for category_name, payload in categories.items():
                    yield str(source_file), str(domain_key), str(category_name).strip() or "Misc", payload
                continue
            if not isinstance(categories, list):
                continue
            for section in categories:
                if not isinstance(section, dict):
                    continue
                for category_name, payload in section.items():
                    yield str(source_file), str(domain_key), str(category_name).strip() or "Misc", payload



def _collect_selected_entries(
    data: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
    select_active_version: Callable[..., tuple[str, str, dict[str, object]] | None],
    build_split_schema_file_category_map: Callable[[object], dict[str, dict[str, tuple[str, str]]]],
    resolve_hierarchy_context: Callable[..., dict[str, object]],
    normalize_offset_type: Callable[[object], str],
    infer_length_bits: Callable[[object, object], int],
) -> tuple[list[dict[str, object]], dict[str, object], str | None, str | None, dict[str, object] | None]:
    hierarchy = data.get("hierarchy")
    versions_map = data.get("versions")
    if not isinstance(hierarchy, dict) or not isinstance(versions_map, dict) or not versions_map:
        return [], {}, None, None, None
    version_ctx = select_active_version(versions_map, target_executable, require_hint=require_hint)
    if version_ctx is None:
        return [], {}, None, None, None
    version_label, version_key, version_info = version_ctx
    split_schema_file_map = build_split_schema_file_category_map(data.get("split_schema"))
    dropdown_values_raw = data.get("_dropdown_values_index")
    dropdown_values = dropdown_values_raw if isinstance(dropdown_values_raw, dict) else {}

    entries: list[dict[str, object]] = []
    skipped_entries: list[dict[str, object]] = []
    skips_by_reason: dict[str, int] = {}
    discovered_leaf_fields = 0

    def _record_skip(leaf_obj: dict[str, object], reason: str, **extra: object) -> None:
        skips_by_reason[reason] = skips_by_reason.get(reason, 0) + 1
        context = extra.pop("context", None)
        source_category = ""
        source_group = ""
        source_path = ""
        source_super_type = ""
        emitted_category = ""
        if isinstance(context, dict):
            source_category = str(context.get("source_category") or "")
            source_group = str(context.get("source_group") or "")
            source_path = str(context.get("source_table_path") or "")
            source_super_type = str(context.get("source_super_type") or "")
            emitted_category = str(context.get("emitted_category") or "")
        record: dict[str, object] = {
            "reason": reason,
            "category": emitted_category,
            "canonical_category": str(leaf_obj.get("canonical_category") or ""),
            "normalized_name": str(leaf_obj.get("normalized_name") or ""),
            "source_super_type": source_super_type,
            "source_category": source_category,
            "source_group": source_group,
            "source_root_category": source_category,
            "source_table_group": source_group,
            "source_table_path": source_path,
            "source_offsets_file": str(extra.pop("source_offsets_file", "")),
            "source_offsets_domain": str(extra.pop("source_offsets_domain", "")),
            "parse_report_entry_id": to_int(extra.pop("parse_report_entry_id", 0)),
        }
        for key_name, value in extra.items():
            record[str(key_name)] = value
        skipped_entries.append(record)

    entry_counter = 0
    for source_file, source_domain, category_name, payload in _iter_hierarchy_sections(hierarchy):
        for leaf_node, path_segments in _iter_hierarchy_leaf_nodes(payload, (category_name,)):
            discovered_leaf_fields += 1
            versions_raw = leaf_node.get("versions")
            normalized_raw = (
                leaf_node.get("normalized_name")
                or leaf_node.get("canonical_name")
                or leaf_node.get("name")
                or leaf_node.get("display_name")
            )
            if not isinstance(versions_raw, dict):
                _record_skip(leaf_node, "missing_versions", source_offsets_file=source_file, source_offsets_domain=source_domain)
                continue
            version_payload = _select_version_entry(versions_raw, version_label)
            if not isinstance(version_payload, dict):
                _record_skip(
                    leaf_node,
                    "missing_target_version",
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                    available_versions=[str(key) for key in versions_raw.keys()],
                )
                continue
            if not normalized_raw:
                _record_skip(leaf_node, "missing_normalized_name", source_offsets_file=source_file, source_offsets_domain=source_domain)
                continue
            context = resolve_hierarchy_context(
                path_segments,
                source_file=source_file,
                leaf_node=leaf_node,
                version_payload=cast(dict[str, object], version_payload),
                split_schema_file_map=split_schema_file_map,
            )
            normalized_name = str(normalized_raw).strip()
            canonical_category = str(leaf_node.get("canonical_category") or context.get("emitted_category") or "Misc").strip() or str(context.get("emitted_category") or "Misc")
            emitted_category = str(context.get("emitted_category") or "Misc").strip() or "Misc"
            display_name = str(leaf_node.get("display_name") or leaf_node.get("name") or normalized_name).strip() or normalized_name

            normalized_payload: dict[str, object] = dict(version_payload)
            if not isinstance(normalized_payload.get("values"), list) and isinstance(dropdown_values, dict):
                dropdown_categories = (
                    canonical_category,
                    str(leaf_node.get("canonical_category") or ""),
                    emitted_category,
                    str(context.get("source_category") or ""),
                    str(context.get("source_group") or ""),
                )
                version_tokens = tuple(dict.fromkeys([*_split_version_tokens(version_key), *_split_version_tokens(version_label)]))
                for token in version_tokens:
                    for dropdown_category in dropdown_categories:
                        if not dropdown_category:
                            continue
                        values = dropdown_values.get((dropdown_category.lower(), normalized_name.upper(), token))
                        if isinstance(values, list) and values:
                            normalized_payload["values"] = list(values)
                            break
                    if isinstance(normalized_payload.get("values"), list):
                        break

            address_raw = normalized_payload.get("address")
            if address_raw in (None, ""):
                address_raw = normalized_payload.get("offset")
            if address_raw in (None, ""):
                address_raw = normalized_payload.get("hex")
            if address_raw in (None, ""):
                _record_skip(leaf_node, "missing_address", context=context, source_offsets_file=source_file, source_offsets_domain=source_domain)
                continue
            address = to_int(address_raw)
            if address < 0:
                _record_skip(leaf_node, "invalid_address", context=context, source_offsets_file=source_file, source_offsets_domain=source_domain, address=address_raw)
                continue
            field_type_raw = normalized_payload.get("type") or leaf_node.get("type")
            field_type_normalized = normalize_offset_type(field_type_raw)
            explicit_length = to_int(normalized_payload.get("length"))
            length_bits = explicit_length
            if length_bits <= 0:
                if field_type_normalized in {"wstring", "string"}:
                    _record_skip(leaf_node, "missing_required_string_length", context=context, source_offsets_file=source_file, source_offsets_domain=source_domain)
                    continue
                length_bits = infer_length_bits(field_type_raw, normalized_payload.get("length"))
                if length_bits <= 0:
                    _record_skip(leaf_node, "missing_length", context=context, source_offsets_file=source_file, source_offsets_domain=source_domain)
                    continue

            source_super_type = str(context.get("source_super_type") or leaf_node.get("super_type") or leaf_node.get("superType") or "").strip()
            if emitted_category.startswith("Stats - "):
                canonical_category = emitted_category

            entry_counter += 1
            version_metadata: dict[str, object] = dict(normalized_payload)
            source_path = str(context.get("source_table_path") or "").strip()
            if source_path and not isinstance(version_metadata.get("path"), str):
                version_metadata["path"] = source_path
            for metadata_key in (
                "source_super_type",
                "source_category",
                "source_group",
                "source_root_category",
                "source_table_group",
                "source_table_path",
                "source_offsets_domain",
                "source_offsets_file",
                "parse_report_entry_id",
            ):
                if metadata_key in version_metadata:
                    continue
                if metadata_key == "source_super_type":
                    version_metadata[metadata_key] = source_super_type
                elif metadata_key in {"source_category", "source_root_category"}:
                    version_metadata[metadata_key] = str(context.get("source_category") or "")
                elif metadata_key in {"source_group", "source_table_group"}:
                    version_metadata[metadata_key] = str(context.get("source_group") or "")
                elif metadata_key == "source_table_path":
                    version_metadata[metadata_key] = source_path
                elif metadata_key == "source_offsets_domain":
                    version_metadata[metadata_key] = source_domain
                elif metadata_key == "source_offsets_file":
                    version_metadata[metadata_key] = source_file
                elif metadata_key == "parse_report_entry_id":
                    version_metadata[metadata_key] = int(entry_counter)
            entry: dict[str, object] = dict(normalized_payload)
            entry.update({
                "category": emitted_category,
                "name": display_name,
                "display_name": display_name,
                "canonical_category": canonical_category,
                "normalized_name": normalized_name,
                "super_type": source_super_type,
                "selected_version": version_label,
                "selected_version_key": version_key,
                "version_metadata": version_metadata,
                "source_super_type": source_super_type,
                "source_category": str(context.get("source_category") or ""),
                "source_group": str(context.get("source_group") or ""),
                "source_root_category": str(context.get("source_category") or ""),
                "source_table_group": str(context.get("source_group") or ""),
                "source_table_path": str(context.get("source_table_path") or ""),
                "source_offsets_domain": source_domain,
                "source_offsets_file": source_file,
                "parse_report_entry_id": int(entry_counter),
            })
            if "address" not in entry and "offset" not in entry and "hex" not in entry:
                entry["address"] = int(address)
            field_type_text = str(field_type_raw or "").strip()
            if field_type_text and "type" not in entry:
                entry["type"] = field_type_text
            if normalized_payload.get("requiresDereference") is True or normalized_payload.get("requires_deref") is True:
                entry["requiresDereference"] = True
            deref = normalized_payload.get("dereferenceAddress")
            if deref in (None, ""):
                deref = normalized_payload.get("deref_offset")
            if deref in (None, ""):
                deref = normalized_payload.get("dereference_address")
            if deref not in (None, ""):
                entry["dereferenceAddress"] = to_int(deref)
            values = normalized_payload.get("values")
            if isinstance(values, list):
                entry["values"] = list(values)
            if isinstance(leaf_node.get("variant_names"), list):
                entry["variant_names"] = list(leaf_node.get("variant_names") or [])
            if leaf_node.get("canonical_name"):
                entry["canonical_name"] = str(leaf_node.get("canonical_name"))
            entries.append(entry)

    skipped_fields = len(skipped_entries)
    emitted_fields = len(entries)
    accounted_fields = emitted_fields + skipped_fields
    report: dict[str, object] = {
        "target_version": version_label,
        "selected_version_key": version_key,
        "discovered_leaf_fields": discovered_leaf_fields,
        "emitted_fields": emitted_fields,
        "skipped_fields": skipped_fields,
        "accounted_fields": accounted_fields,
        "untracked_loss": max(0, discovered_leaf_fields - accounted_fields),
        "skips_by_reason": dict(sorted(skips_by_reason.items())),
        "skipped": skipped_entries,
    }
    return entries, report, version_label, version_key, version_info



def _iter_selected_entries(data: dict[str, object], target_executable: str | None, *, collect_selected_entries: Callable[..., Any]):
    entries, _report, _version_label, _version_key, _version_info = collect_selected_entries(data, target_executable)
    for entry in entries:
        yield entry



def _build_split_offsets_payload(
    offsets_dir: Path,
    *,
    parse_errors: list[str] | None = None,
    split_offsets_league_file: str,
    split_offsets_domain_files: tuple[str, ...],
    split_offsets_optional_files: tuple[str, ...],
    read_json_with_error: JsonReader,
    read_json_cached: Callable[[Path], dict[str, Any] | None],
    derive_super_type_map_from_split_schema: Callable[[object], dict[str, str]],
) -> tuple[Path, dict[str, Any]] | None:
    league_path = offsets_dir / split_offsets_league_file
    if not league_path.is_file():
        return None
    missing_domains = [name for name in split_offsets_domain_files if not (offsets_dir / name).is_file()]
    if missing_domains:
        return None

    league_raw, league_error = read_json_with_error(league_path)
    if league_error and parse_errors is not None:
        parse_errors.append(league_error)
    if not isinstance(league_raw, dict):
        return None
    versions = league_raw.get("versions")
    if not isinstance(versions, dict) or not versions:
        return None
    dropdown_values: dict[tuple[str, str, str], list[str]] = {}
    dropdown_path = offsets_dir / split_offsets_optional_files[0]
    if dropdown_path.is_file():
        dropdown_values = _build_dropdown_values_index(read_json_cached(dropdown_path))

    hierarchy_payload: dict[str, dict[str, object]] = {}
    discovered_leaf_fields = 0
    for file_name in split_offsets_domain_files:
        file_path = offsets_dir / file_name
        raw_domain, domain_error = read_json_with_error(file_path)
        if domain_error and parse_errors is not None:
            parse_errors.append(domain_error)
        if not isinstance(raw_domain, dict):
            return None
        hierarchy_payload[file_name] = raw_domain
        for _source_file, _source_domain, category_name, payload in _iter_hierarchy_sections({file_name: raw_domain}):
            for _leaf_node, _path_segments in _iter_hierarchy_leaf_nodes(payload, (category_name,)):
                discovered_leaf_fields += 1
    if not hierarchy_payload:
        return None

    merged_payload: dict[str, Any] = {
        "hierarchy": hierarchy_payload,
        "versions": dict(versions),
        "_dropdown_values_index": dropdown_values,
        "_split_manifest": {
            "required_files": [split_offsets_league_file, *split_offsets_domain_files],
            "optional_files": list(split_offsets_optional_files),
            "discovered_leaf_fields": discovered_leaf_fields,
        },
    }
    split_schema_raw = league_raw.get("split_schema")
    if isinstance(split_schema_raw, dict):
        merged_payload["split_schema"] = dict(split_schema_raw)
        merged_payload["super_type_map"] = derive_super_type_map_from_split_schema(split_schema_raw)
    league_category_pointer_map = league_raw.get("league_category_pointer_map")
    if isinstance(league_category_pointer_map, dict):
        merged_payload["league_category_pointer_map"] = dict(league_category_pointer_map)
    return league_path, merged_payload



def _build_player_stats_relations(
    offsets: list[dict[str, object]],
    *,
    player_stats_ids_category: str,
    player_stats_season_category: str,
) -> dict[str, object]:
    id_entries: list[dict[str, object]] = []
    season_entries: list[dict[str, object]] = []
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("canonical_category") or entry.get("category") or "").strip()
        if category == player_stats_ids_category:
            id_entries.append(entry)
        elif category == player_stats_season_category:
            season_entries.append(entry)

    def _entry_sort_key(item: dict[str, object]) -> tuple[int, int, str]:
        return (
            to_int(item.get("address") or item.get("offset") or item.get("hex")),
            to_int(item.get("startBit") or item.get("start_bit")),
            str(item.get("normalized_name") or ""),
        )

    def _id_sort_key(item: dict[str, object]) -> tuple[int, int, int, str]:
        normalized = str(item.get("normalized_name") or "").strip().upper()
        if normalized.startswith("STATSID"):
            suffix = normalized.replace("STATSID", "", 1)
            return (0, int(suffix or 0) if suffix.isdigit() else 0, 0, normalized)
        if normalized == "CURRENTYEARSTATID":
            return (1, 0, 0, normalized)
        addr, bit, name = _entry_sort_key(item)
        return (2, addr, bit, name)

    ordered_ids = [
        str(item.get("normalized_name") or "").strip()
        for item in sorted(id_entries, key=_id_sort_key)
        if str(item.get("normalized_name") or "").strip()
    ]
    ordered_season = [
        str(item.get("normalized_name") or "").strip()
        for item in sorted(season_entries, key=_entry_sort_key)
        if str(item.get("normalized_name") or "").strip()
    ]
    return {
        "source_category": player_stats_ids_category,
        "target_category": player_stats_season_category,
        "relation_type": "season_only",
        "id_fields": ordered_ids,
        "target_fields": ordered_season,
    }



def _extract_player_stats_relations(config_data: dict | None) -> dict[str, Any]:
    if not isinstance(config_data, dict):
        return {}
    relations = config_data.get("relations")
    if not isinstance(relations, dict):
        return {}
    relation = relations.get("player_stats")
    if not isinstance(relation, dict):
        return {}
    return dict(relation)



def _resolve_split_offsets_config(
    raw: object,
    target_exe: str | None,
    *,
    collect_selected_entries: Callable[..., Any],
    build_player_stats_relations: Callable[[list[dict[str, object]]], dict[str, object]],
    derive_super_type_map_from_split_schema: Callable[[object], dict[str, str]],
) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("hierarchy"), dict):
        return None
    if not isinstance(raw.get("versions"), dict):
        return None

    selected_entries, parse_report, _version_label, version_key, version_info = collect_selected_entries(
        cast(dict[str, object], raw),
        target_exe,
        require_hint=True,
    )
    if not selected_entries or not version_key or not isinstance(version_info, dict):
        return None

    player_stats_relations = build_player_stats_relations(selected_entries)
    converted: dict[str, object] = {
        "hierarchy": dict(cast(dict[str, object], raw.get("hierarchy") or {})),
        "relations": {"player_stats": player_stats_relations},
        "_parse_report": parse_report,
        "versions": {version_key: dict(version_info)},
    }
    if isinstance(raw.get("_split_manifest"), dict):
        converted["_split_manifest"] = dict(cast(dict[str, object], raw.get("_split_manifest") or {}))
    if isinstance(raw.get("_dropdown_values_index"), dict):
        converted["_dropdown_values_index"] = dict(cast(dict[str, object], raw.get("_dropdown_values_index") or {}))
    if isinstance(raw.get("league_category_pointer_map"), dict):
        converted["league_category_pointer_map"] = raw["league_category_pointer_map"]
    split_schema = raw.get("split_schema")
    if isinstance(split_schema, dict):
        converted["split_schema"] = split_schema
        converted["super_type_map"] = dict(cast(dict[str, str], raw.get("super_type_map") or derive_super_type_map_from_split_schema(split_schema)))

    base_ptrs = version_info.get("base_pointers") if isinstance(version_info.get("base_pointers"), dict) else None
    if base_ptrs:
        converted["base_pointers"] = dict(base_ptrs)
    game_info = version_info.get("game_info") if isinstance(version_info.get("game_info"), dict) else None
    if game_info:
        converted["game_info"] = dict(game_info)
    return converted



def _load_offset_bundle_from_dir(
    offsets_dir: Path,
    target_executable: str | None,
    *,
    parse_errors: list[str] | None = None,
    build_split_offsets_payload: Callable[..., tuple[Path, dict[str, Any]] | None],
    resolve_split_offsets_config: Callable[[object, str | None], dict | None],
) -> tuple[Path, dict[str, Any]] | None:
    split_payload = build_split_offsets_payload(offsets_dir, parse_errors=parse_errors)
    if split_payload is None:
        return None
    path, raw_payload = split_payload
    resolved = resolve_split_offsets_config(raw_payload, target_executable)
    if not isinstance(resolved, dict):
        return None
    return path, dict(resolved)



def _load_offset_config_file(
    target_executable: str | None = None,
    *,
    timed_ctx: Any,
    offset_cache: Any,
    offset_schema_error: type[Exception],
    load_offset_bundle_from_dir: Callable[..., tuple[Path, dict[str, Any]] | None],
    search_dirs: list[Path],
) -> tuple[Path | None, dict | None]:
    with timed_ctx("offsets.load_offset_config_file"):
        target_key = (target_executable or "").lower()
        if target_key:
            cached = offset_cache.get_target(target_key)
            if cached is not None:
                return cached.path, dict(cached.data)
        parse_errors: list[str] = []
        for folder in search_dirs:
            resolved_payload = load_offset_bundle_from_dir(folder, target_executable, parse_errors=parse_errors)
            if resolved_payload is None:
                continue
            path, payload = resolved_payload
            if target_key:
                from .offset_cache import CachedOffsetPayload

                offset_cache.set_target(CachedOffsetPayload(path=path, target_key=target_key, data=payload))
            return path, payload
        if parse_errors:
            unique_errors: list[str] = []
            seen_error_keys: set[str] = set()
            for message in parse_errors:
                key = message.casefold()
                if key in seen_error_keys:
                    continue
                seen_error_keys.add(key)
                unique_errors.append(message)
            details = " ; ".join(unique_errors)
            raise offset_schema_error(
                "Offsets files were found, but one or more required files could not be parsed. "
                f"{details}"
            )
        return None, None
