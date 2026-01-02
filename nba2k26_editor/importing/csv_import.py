"""CSV import/export helpers lifted from the monolithic editor."""
from __future__ import annotations

import csv
from typing import Any, Iterable, Sequence, cast

from ..core.conversions import (
    NON_NUMERIC_RE,
    convert_minmax_potential_to_raw,
    convert_rating_to_raw,
    convert_rating_to_tendency_raw,
    height_inches_to_raw,
    write_weight,
    to_int,
)
from ..core.offsets import (
    ATTR_IMPORT_ORDER,
    COY_IMPORT_LAYOUTS,
    DUR_IMPORT_ORDER,
    FIRST_NAME_ENCODING,
    LAST_NAME_ENCODING,
    NAME_MAX_CHARS,
    OFF_FIRST_NAME,
    OFF_LAST_NAME,
    POTENTIAL_IMPORT_ORDER,
    PLAYER_STRIDE,
    TEND_IMPORT_ORDER,
)
from ..models.player import Player
from ..models.schema import FieldWriteSpec, PreparedImportRows


def prepare_import_rows(model, category_name: str, rows: Sequence[Sequence[str]], *, context: str = "default") -> PreparedImportRows | None:
    """Normalize a CSV/TSV sheet into a PreparedImportRows payload."""
    if not rows:
        return None
    context_key = (context or "").strip().lower()
    if context_key == "excel_template":
        header = [str(cell) for cell in rows[0]]
        if not header:
            return None
        data_rows = []
        for row in rows[1:]:
            normalized_row = [str(cell) for cell in row]
            if any(str(cell).strip() for cell in normalized_row):
                data_rows.append(normalized_row)
        if not data_rows:
            return None
        return cast(
            PreparedImportRows,
            {
                "header": header,
                "data_rows": data_rows,
                "name_col": -1,
                "value_columns": list(range(len(header))),
                "fixed_mapping": True,
                "allow_missing_names": True,
            },
        )
    layout_raw = COY_IMPORT_LAYOUTS.get(category_name) if context_key == "coy" else None
    layout: dict[str, object] | None = layout_raw if isinstance(layout_raw, dict) else None
    if layout:
        normalize_header = model._normalize_coy_header_name
        value_columns_raw = layout.get("value_columns")
        value_columns = [int(col) for col in cast(Iterable[int | str], value_columns_raw)] if value_columns_raw else []
        column_headers_raw = layout.get("column_headers")
        column_headers = [str(header) for header in cast(Iterable[Any], column_headers_raw)] if column_headers_raw else []
        skip_names_raw = layout.get("skip_names")
        skip_names = {str(s).strip().lower() for s in cast(Iterable[Any], skip_names_raw)} if skip_names_raw else set()
        name_columns_raw = layout.get("name_columns")
        if name_columns_raw:
            name_columns = [int(col) for col in cast(Iterable[int | str], name_columns_raw)]
        else:
            name_col_fallback = layout.get("name_col")
            name_columns = [int(cast(int | str, name_col_fallback))] if name_col_fallback is not None else [0]
        if column_headers and not value_columns:
            value_columns = list(range(1, 1 + len(column_headers)))
        header_lookup: dict[str, int] = {}
        header_row: list[str] | None = None
        if column_headers:
            for row in rows:
                normalized_row = [str(cell) for cell in row]
                if any(
                    normalized_row[col].strip().lower() in skip_names
                    for col in name_columns
                    if col < len(normalized_row)
                ):
                    header_row = normalized_row
                    break
            if header_row is None:
                header_row = [str(cell) for cell in rows[0]]
            for idx, cell in enumerate(header_row):
                norm_cell = normalize_header(cell)
                if norm_cell and norm_cell not in header_lookup:
                    header_lookup[norm_cell] = idx
        resolved_value_indices: list[int] = []
        if column_headers:
            for hdr in column_headers:
                norm_hdr = normalize_header(hdr)
                if norm_hdr and norm_hdr in header_lookup:
                    resolved_value_indices.append(header_lookup[norm_hdr])
            if resolved_value_indices and len(resolved_value_indices) < max(4, len(column_headers) // 2):
                resolved_value_indices = []

        def _is_valid_name(cell: str) -> bool:
            normalized = cell.strip()
            if not normalized:
                return False
            if normalized.lower() in skip_names:
                return False
            return any(ch.isalpha() for ch in normalized)

        def _row_has_numeric(row: Sequence[str]) -> bool:
            target_columns = resolved_value_indices or value_columns
            if not target_columns and column_headers:
                target_columns = [i for i in range(len(row)) if i not in name_columns]
            for idx in target_columns:
                if idx >= len(row):
                    continue
                cell = row[idx].strip()
                if cell and any(ch.isdigit() for ch in cell) and not any(ch.isalpha() for ch in cell):
                    return True
            return False

        data_rows: list[list[str]] = []
        for row in rows:
            normalized_row = [str(cell) for cell in row]
            name_value: str | None = None
            used_name_col: int | None = None
            for col in name_columns:
                if col >= len(normalized_row):
                    continue
                candidate = normalized_row[col].strip()
                if _is_valid_name(candidate):
                    name_value = candidate
                    used_name_col = col
                    break
            if not name_value:
                continue
            if not _row_has_numeric(normalized_row):
                continue
            if column_headers:
                values: list[str] = []
                matched_count = 0
                for hdr in column_headers:
                    norm_hdr = normalize_header(hdr)
                    col_idx = header_lookup.get(norm_hdr)
                    if col_idx is None or col_idx >= len(normalized_row):
                        values.append("")
                    else:
                        matched_count += 1
                        values.append(normalized_row[col_idx])
                if matched_count < max(4, len(column_headers) // 2):
                    fallback_cols = resolved_value_indices or value_columns
                    if not fallback_cols:
                        fallback_cols = [idx for idx in range(len(normalized_row)) if idx != used_name_col]
                    fallback_cols = fallback_cols[: len(column_headers)]
                    values = [
                        normalized_row[idx] if idx < len(normalized_row) else ""
                        for idx in fallback_cols
                    ]
            else:
                values = [normalized_row[idx] if idx < len(normalized_row) else "" for idx in value_columns]
            data_rows.append([name_value, *values])
        if not data_rows:
            return None
        if category_name == "Attributes":
            order_headers = ["Player Name", *ATTR_IMPORT_ORDER]
        elif category_name == "Tendencies":
            order_headers = ["Player Name", *TEND_IMPORT_ORDER]
        elif category_name == "Durability":
            order_headers = ["Player Name", *DUR_IMPORT_ORDER]
        elif category_name == "Potential":
            order_headers = ["Player Name", *POTENTIAL_IMPORT_ORDER]
        else:
            order_headers = []
        return cast(
            PreparedImportRows,
            {
                "header": order_headers,
                "data_rows": data_rows,
                "name_col": 0,
                "value_columns": list(range(1, len(order_headers))),
            },
        )
    if context_key == "excel":
        header = [str(cell) for cell in rows[0]]
        if not header:
            return None
        name_col = 0
        skip_value_cols = {name_col}
        value_columns = [idx for idx in range(len(header)) if idx not in skip_value_cols]
        data_rows = [
            [str(cell) for cell in row]
            for row in rows[1:]
            if any(str(cell).strip() for cell in row)
        ]
        if not value_columns or not data_rows:
            return None
        return cast(
            PreparedImportRows,
            {
                "header": header,
                "data_rows": data_rows,
                "name_col": name_col,
                "value_columns": value_columns,
            },
        )
    header = [str(cell) for cell in rows[0]]
    if not header:
        return None
    name_col = 0

    def _simple_norm(token: str) -> str:
        return "".join(ch for ch in str(token).upper() if ch.isalnum())

    first_name_markers = {"FIRSTNAME", "FIRST", "FNAME", "PLAYERFIRST", "PLAYERFIRSTNAME", "GIVENNAME"}
    last_name_markers = {"LASTNAME", "LAST", "LNAME", "PLAYERLAST", "PLAYERLASTNAME", "SURNAME", "FAMILYNAME"}
    normalized_headers = [_simple_norm(cell) for cell in header]
    first_name_col = None
    last_name_col = None
    for idx, norm in enumerate(normalized_headers):
        if not norm:
            continue
        if first_name_col is None and norm in first_name_markers:
            first_name_col = idx
            continue
        if last_name_col is None and norm in last_name_markers:
            last_name_col = idx
            continue
        if name_col == 0 and norm not in first_name_markers and norm not in last_name_markers:
            name_col = idx
    skip_value_cols = {name_col}
    if first_name_col is not None:
        skip_value_cols.add(first_name_col)
    if last_name_col is not None:
        skip_value_cols.add(last_name_col)
    value_columns = [idx for idx in range(len(header)) if idx not in skip_value_cols]
    data_rows = [[str(cell) for cell in row] for row in rows[1:] if any(str(cell).strip() for cell in row)]
    if not value_columns or not data_rows:
        return None
    return cast(
        PreparedImportRows,
        {
            "header": header,
            "data_rows": data_rows,
            "name_col": name_col,
            "value_columns": value_columns,
            "first_name_col": first_name_col,
            "last_name_col": last_name_col,
        },
    )


def compose_import_row_name(info: PreparedImportRows, row: Sequence[object]) -> str:
    """Return the best full-name string for a prepared import row."""
    if not row or not info:
        return ""

    def _idx(value: object) -> int | None:
        if isinstance(value, int):
            return value if value >= 0 else None
        try:
            idx_val = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return idx_val if idx_val >= 0 else None

    first_idx = _idx(info.get("first_name_col"))
    last_idx = _idx(info.get("last_name_col"))
    name_idx = _idx(info.get("name_col"))

    def _piece(idx: int | None) -> str:
        if idx is None or idx < 0 or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    parts: list[str] = []
    first_part = _piece(first_idx)
    last_part = _piece(last_idx)
    if first_part:
        parts.append(first_part)
    if last_part:
        parts.append(last_part)
    if parts:
        return " ".join(parts).strip()
    fallback = _piece(name_idx)
    return fallback.strip() if fallback else ""


def import_table(
    model,
    category_name: str,
    filepath: str,
    *,
    context: str = "default",
    match_by_name: bool = True,
) -> int:
    """
    Import player data from a tab- or comma-delimited file for a single category.
    Mirrors the monolithic PlayerDataModel.import_table logic.
    """
    if category_name not in getattr(model, "categories", {}):
        return 0
    context_key = (context or "").strip().lower()
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.readline()
            delim = "\t" if "\t" in sample else "," if "," in sample else ";"
            f.seek(0)
            reader = csv.reader(f, delimiter=delim)
            rows = list(reader)
    except Exception:
        return 0
    if not rows:
        return 0
    info = prepare_import_rows(model, category_name, rows, context=context)
    if not info:
        return 0
    header = info["header"]
    data_rows = info["data_rows"]
    name_col = info["name_col"]
    value_columns = info["value_columns"]
    allow_missing_names = bool(info.get("allow_missing_names"))

    def _resolve_optional_index(value: Any) -> int | None:
        if isinstance(value, int):
            return value if value >= 0 else None
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return None
        return idx if idx >= 0 else None

    field_defs = model._get_import_fields(category_name, context=context_key) or model.categories.get(category_name, [])
    if not field_defs:
        return 0
    first_name_col: int | None = _resolve_optional_index(info.get("first_name_col"))
    last_name_col: int | None = _resolve_optional_index(info.get("last_name_col"))
    if header and (first_name_col is None or last_name_col is None) and context_key not in {"excel", "excel_template"}:
        normalize_header = model._normalize_coy_header_name if context_key == "coy" else model._normalize_header_name
        first_name_markers = {"FIRSTNAME", "FIRST", "PLAYERFIRST", "PLAYERFIRSTNAME", "FNAME", "GIVENNAME"}
        last_name_markers = {"LASTNAME", "LAST", "PLAYERLAST", "PLAYERLASTNAME", "LNAME", "SURNAME", "FAMILYNAME"}

        def _looks_like_first(norm: str) -> bool:
            return any(
                (
                    norm in first_name_markers,
                    "FIRSTNAME" in norm,
                    "GIVENNAME" in norm,
                    norm.endswith("FNAME"),
                    norm.startswith("FNAME"),
                )
            )

        def _looks_like_last(norm: str) -> bool:
            return any(
                (
                    norm in last_name_markers,
                    "LASTNAME" in norm,
                    "SURNAME" in norm,
                    "FAMILYNAME" in norm,
                    norm.endswith("LNAME"),
                    norm.startswith("LNAME"),
                )
            )

        for idx, column_name in enumerate(header):
            if first_name_col is not None and last_name_col is not None and idx not in (first_name_col, last_name_col):
                continue
            normalized_name = normalize_header(column_name)
            if not normalized_name:
                continue
            if first_name_col is None and _looks_like_first(normalized_name):
                first_name_col = idx
                continue
            if last_name_col is None and _looks_like_last(normalized_name):
                last_name_col = idx
    normalize_header = model._normalize_coy_header_name if context_key == "coy" else model._normalize_header_name
    fixed_mapping = bool(info.get("fixed_mapping"))
    header = info.get("header") or []
    selected_columns: list[int] = []
    mappings: list[dict] = []
    skip_match_cols = {name_col}
    if first_name_col is not None:
        skip_match_cols.add(first_name_col)
    if last_name_col is not None:
        skip_match_cols.add(last_name_col)
    if header and not fixed_mapping:
        remaining_fields = list(field_defs)
        if context_key == "excel":
            header_tokens = [
                str(h).strip() if idx not in skip_match_cols else ""
                for idx, h in enumerate(header)
            ]
            for idx, token in enumerate(header_tokens):
                if idx == name_col or not token:
                    continue
                match_idx = -1
                for j, fdef in enumerate(remaining_fields):
                    if not isinstance(fdef, dict):
                        continue
                    candidates: list[str] = []
                    for key in ("name", "label", "displayName", "display_name"):
                        val = fdef.get(key)
                        if isinstance(val, str):
                            val = val.strip()
                            if val:
                                candidates.append(val)
                    variants = fdef.get("variants") or fdef.get("variant_names") or fdef.get("aliases")
                    if isinstance(variants, (list, tuple, set)):
                        for val in variants:
                            if isinstance(val, str):
                                val = val.strip()
                                if val:
                                    candidates.append(val)
                    if token in candidates:
                        match_idx = j
                        break
                if match_idx >= 0:
                    mappings.append(remaining_fields.pop(match_idx))
                    selected_columns.append(idx)
        else:
            normalized_headers = [
                normalize_header(h) if idx not in skip_match_cols else ""
                for idx, h in enumerate(header)
            ]
            for idx, norm_hdr in enumerate(normalized_headers):
                if idx == name_col or not norm_hdr:
                    continue
                match_idx = -1
                for j, fdef in enumerate(remaining_fields):
                    norm_field = model._normalize_field_name(fdef.get("name", ""))
                    if norm_hdr == norm_field or norm_hdr in norm_field or norm_field in norm_hdr:
                        match_idx = j
                        break
                if match_idx >= 0:
                    mappings.append(remaining_fields.pop(match_idx))
                    selected_columns.append(idx)
    else:
        selected_columns = value_columns[: len(field_defs)]
        mappings = list(field_defs[: len(selected_columns)])
    if not data_rows or not selected_columns:
        return 0
    field_specs: list[dict[str, object] | None] = []
    for meta in mappings:
        if not isinstance(meta, dict):
            field_specs.append(None)
            continue
        length = to_int(meta.get("length"))
        if length <= 0:
            field_specs.append(None)
            continue
        raw_values = meta.get("values")
        if isinstance(raw_values, (list, tuple)) and raw_values:
            field_specs.append(None)
            continue
        offset = to_int(meta.get("offset"))
        start_bit = to_int(meta.get("startBit", meta.get("start_bit", 0)))
        requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
        deref_offset = to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
        max_raw = (1 << length) - 1
        field_specs.append(
            {
                "name": str(meta.get("name", "")),
                "offset": offset,
                "start_bit": start_bit,
                "length": length,
                "requires_deref": requires_deref,
                "deref_offset": deref_offset,
                "max_raw": max_raw,
                "field_type": str(meta.get("type", "")).lower() if meta.get("type") else "",
            }
        )
    if not any(spec is not None for spec in field_specs):
        return 0
    if PLAYER_STRIDE <= 0:
        return 0
    if not model.mem.open_process():
        return 0
    player_base = model._resolve_player_table_base()
    if player_base is None:
        return 0
    if category_name in ("Attributes", "Durability", "Potential"):
        def encode_value(num: float, length: int, max_raw: int) -> int:
            return convert_rating_to_raw(num, length)
    elif category_name == "Tendencies":
        def encode_value(num: float, length: int, max_raw: int) -> int:
            return convert_rating_to_tendency_raw(num, length)
    else:
        def encode_value(num: float, length: int, max_raw: int) -> int:
            if max_raw <= 0:
                return 0
            pct = min(max(num, 0.0), 100.0) / 100.0
            return int(round(pct * max_raw))
    numeric_clean = NON_NUMERIC_RE.sub
    column_specs = list(zip(selected_columns, field_specs))
    players_updated = 0
    name_match_mode = bool(match_by_name)
    template_names: list[str] | None = None
    if name_match_mode and context_key == "excel_template":
        raw_names = getattr(model, "_excel_template_row_names", None)
        if isinstance(raw_names, list):
            template_names = [str(name) for name in raw_names]
    player_sequence: list[int] = []
    seq_index = 0
    if not name_match_mode:
        if not model.players:
            model.refresh_players()
        cached_players = list(model.players or [])
        if not cached_players:
            return 0

        def _player_order_key(p: Player) -> tuple[int, int, int]:
            team_id = getattr(p, "team_id", None)
            if isinstance(team_id, int) and team_id is not None and team_id >= 0:
                return (0, team_id, p.index)
            return (1, 1_000_000 + p.index, p.index)

        sorted_players = sorted(cached_players, key=_player_order_key)
        player_sequence = [p.index for p in sorted_players]

    def _get_cell(row: Sequence[str], idx: int | None) -> str:
        if idx is None or idx < 0 or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    def _coerce_position_value(raw: object) -> int | None:
        """Translate free text position codes (PG/SG/SF/PF/C) into slot indices."""
        if raw is None:
            return None
        try:
            num = float(str(raw))
        except Exception:
            token = str(raw).strip().upper()
            mapping = {
                "PG": 0,
                "POINT": 0,
                "POINTGUARD": 0,
                "SG": 1,
                "SHOOTING": 1,
                "SHOOTINGGUARD": 1,
                "SF": 2,
                "SMALL": 2,
                "SMALLFORWARD": 2,
                "PF": 3,
                "POWER": 3,
                "POWERFORWARD": 3,
                "C": 4,
                "CENTER": 4,
            }
            return mapping.get(token)
        else:
            try:
                return int(round(num))
            except Exception:
                return None

    partial_matches: dict[str, list[dict[str, object]]] = {}
    for row_index, row in enumerate(data_rows):
        if not row:
            continue
        row_len = len(row)
        has_name_col = 0 <= name_col < row_len
        has_first = first_name_col is not None and 0 <= first_name_col < row_len
        has_last = last_name_col is not None and 0 <= last_name_col < row_len
        if not (has_name_col or has_first or has_last):
            if not allow_missing_names:
                continue
        first_piece = _get_cell(row, first_name_col)
        last_piece = _get_cell(row, last_name_col)
        raw_name_parts = [part for part in (first_piece, last_piece) if part]
        raw_name = " ".join(raw_name_parts).strip()
        if not raw_name and has_name_col:
            raw_name = str(row[name_col]).strip()
        if not raw_name and template_names is not None and row_index < len(template_names):
            raw_name = str(template_names[row_index]).strip()
        row_first_name = ""
        row_last_name = ""
        if not name_match_mode and context_key != "coy":
            row_first_name = first_piece
            row_last_name = last_piece
        if name_match_mode:
            if not raw_name:
                continue
            idxs = model._match_player_indices(raw_name)
            if not idxs:
                candidates = model._partial_name_candidates(raw_name)
                if candidates:
                    bucket = partial_matches.setdefault(raw_name, [])
                    existing = {str(entry.get("name")).strip().lower() for entry in bucket if isinstance(entry, dict)}
                    for cand in candidates:
                        if not isinstance(cand, dict):
                            continue
                        cand_name = str(cand.get("name", "")).strip()
                        if not cand_name:
                            continue
                        key = cand_name.lower()
                        if key in existing:
                            continue
                        existing.add(key)
                        bucket.append({"name": cand_name, "score": cand.get("score")})
                continue
        else:
            if not (row_first_name or row_last_name):
                if not allow_missing_names:
                    break
            if seq_index >= len(player_sequence):
                break
            idxs = [player_sequence[seq_index]]
            seq_index += 1
        for idx in idxs:
            assignments: list[FieldWriteSpec] = []
            post_writes: list[tuple[str, int, float]] = []
            string_writes: list[tuple[str, int, str]] = []
            has_first_override = False
            has_last_override = False
            for col_idx, spec in column_specs:
                if spec is None or col_idx >= len(row):
                    continue
                val = row[col_idx]
                field_name = str(spec.get("name", "")).lower()
                field_type = str(spec.get("field_type", "")).lower()
                spec_offset = cast(int, spec["offset"])
                if field_type in ("string", "text") or "name" in field_name:
                    text_value = str(val).strip()
                    if not text_value:
                        continue
                    if field_name in ("first name", "firstname"):
                        string_writes.append(("first", spec_offset, text_value))
                        has_first_override = True
                    elif field_name in ("last name", "lastname"):
                        string_writes.append(("last", spec_offset, text_value))
                        has_last_override = True
                    else:
                        string_writes.append(("generic", spec_offset, text_value))
                    continue
                    # end string handling
                if field_name in ("position", "position 2", "position2", "secondary position"):
                    coerced = _coerce_position_value(val)
                    if coerced is None:
                        continue
                    cleaned = str(coerced)
                else:
                    cleaned = numeric_clean("", str(val))
                if not cleaned:
                    continue
                try:
                    num = float(cleaned)
                except Exception:
                    continue
                spec_start = cast(int, spec["start_bit"])
                spec_length = cast(int, spec["length"])
                if field_name in ("position", "position 2", "position2"):
                    max_raw = int(cast(int, spec["max_raw"]))
                    raw_value = max(0, min(int(round(num)), max_raw))
                elif category_name == "Potential" and ("min" in field_name or "max" in field_name):
                    raw_value = convert_minmax_potential_to_raw(num, spec_length)
                elif field_name in ("height", "wingspan"):
                    try:
                        inches_val = int(round(float(num)))
                    except Exception:
                        continue
                    raw_value = height_inches_to_raw(inches_val)
                elif field_name in ("weight", "body weight"):
                    try:
                        weight_val = float(num)
                    except Exception:
                        continue
                    post_writes.append(("weight", spec_offset, weight_val))
                    continue
                else:
                    raw_value = encode_value(num, spec_length, cast(int, spec["max_raw"]))
                assignments.append(
                    (
                        spec_offset,
                        spec_start,
                        spec_length,
                        raw_value,
                        bool(spec.get("requires_deref")),
                        cast(int, spec.get("deref_offset") or 0),
                    )
                )
            record_ptr = None
            try:
                record_ptr = model._player_record_address(idx)
            except Exception:
                record_ptr = None
            if record_ptr is None:
                continue
            if assignments:
                applied = model._apply_field_assignments(record_ptr, assignments)
                if applied > 0:
                    players_updated += 1
            if string_writes:
                if model.mem.hproc and model.mem.base_addr is not None:
                    for kind, offset, text_value in string_writes:
                        if kind == "first":
                            model._write_string(record_ptr + offset, text_value, NAME_MAX_CHARS, FIRST_NAME_ENCODING)
                        elif kind == "last":
                            model._write_string(record_ptr + offset, text_value, NAME_MAX_CHARS, LAST_NAME_ENCODING)
                        else:
                            model._write_string(record_ptr + offset, text_value, NAME_MAX_CHARS, LAST_NAME_ENCODING)
                    if not has_first_override and first_piece:
                        model._write_string(record_ptr + OFF_FIRST_NAME, first_piece, NAME_MAX_CHARS, FIRST_NAME_ENCODING)
                    if not has_last_override and last_piece:
                        model._write_string(record_ptr + OFF_LAST_NAME, last_piece, NAME_MAX_CHARS, LAST_NAME_ENCODING)
            if post_writes:
                for action, offset, val in post_writes:
                    if action != "weight":
                        continue
                    try:
                        write_weight(model.mem, record_ptr + offset, val)
                        players_updated += 1
                    except Exception:
                        continue
    if partial_matches:
        model.import_partial_matches[category_name] = partial_matches
    return players_updated


__all__ = ["prepare_import_rows", "compose_import_row_name", "import_table"]
