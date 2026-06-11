# NBA2K Editor Redundant Function Candidates

Evidence-backed redundancy report built from `FUNCTION_INDEX.md` plus AST/source checks inside `nba2k_editor/` only.

This file is a review map, not a deletion patch. Anything marked `candidate` needs a targeted test or live check before removal.

## Scope checked

- Source root: `nba2k_editor/`
- Python files scanned by `FUNCTION_INDEX.md`: 16
- Callable rows in `FUNCTION_INDEX.md`: 321
- Named functions/methods in source AST: 295
- Lambda expressions in source AST: 26
- Out of scope: tests, `.hermes/probes`, root `launch_editor.py`, and any other file outside `nba2k_editor/`

## Highest-confidence duplicates

### 1. Duplicate ID-prefixed option parser

| Status | Function | Location | Evidence |
|---|---|---:|---|
| duplicate body | `_parse_id_prefixed_option(value: Any) -> int \| None` | `models/data_model.py:441-443` | Exact AST-normalized body match |
| duplicate body | `_parse_id_prefixed_option(value: object) -> int \| None` | `ui/dpg_editor.py:155-157` | Exact AST-normalized body match |

Same implementation:

```py
match = re.match(r"^\s*\[(\d+)\]", str(value or ""))
return int(match.group(1)) if match else None
```

Current internal uses:

- `models/data_model.py:1417`
- `models/data_model.py:1594`
- `ui/dpg_editor.py:669`

Likely consolidation target:

- Keep one implementation and have the other caller import/use it.
- Do not add a new helper file unless explicitly approved.

---

### 2. Duplicate field lookup methods

| Status | Function | Location | Evidence |
|---|---|---:|---|
| duplicate body | `EditorDataModel._field_by_display_or_normalized_name(self, domain, name)` | `models/data_model.py:829-830` | Exact AST-normalized body match |
| duplicate body | `EditorDataModel._field_by_normalized_name(self, domain, name)` | `models/data_model.py:1337-1338` | Exact AST-normalized body match |

Same effective implementation:

```py
return self._field_lookup(domain).get(_field_identity(name))
```

Current internal uses:

- `_field_by_display_or_normalized_name`: `models/data_model.py:836`
- `_field_by_normalized_name`: `models/data_model.py:904`, `1060`, `1186`, `1208`, `1266`, `1278`, `1304`, `1343`, `1439`

Why this is redundant:

- `_field_lookup()` already stores both `normalized_name` and `display_name` keys.
- The two method names imply different behavior, but the bodies are identical.

Likely consolidation target:

- Keep one method name that accurately reflects lookup behavior.
- Replace the single `_field_by_display_or_normalized_name` call or rename `_field_by_normalized_name` if clarity is preferred.

## Strong redundancy candidates

### 3. Pointer-read helper duplicated as module function and model method

| Status | Function | Location | Evidence |
|---|---|---:|---|
| candidate | `_read_pointer_value(memory, address)` | `models/data_model.py:339-345` | Same read-width logic |
| candidate | `EditorDataModel._read_pointer_value(self, address, pointer_size=None)` | `models/data_model.py:1028-1034` | Same read-width logic |

Shared behavior:

- Choose 8-byte `read_u64` when pointer size is 8.
- Choose 4-byte `read_uint32` when pointer size is 4.
- Fall back to `read_bytes(..., pointer_size)` and `int.from_bytes(..., "little")`.

Current internal uses:

- Module helper: `models/data_model.py:582`, `842`
- Method helper: `models/data_model.py:1017`, `1025`

Likely consolidation target:

- Prefer one pointer-read implementation.
- If the method is kept for readability, it can delegate to the module helper instead of duplicating the read logic.

---

### 4. Indexed read path duplicates record-address read path

| Status | Function | Location | Evidence |
|---|---|---:|---|
| candidate | `EditorDataModel._read_field_at_record_address(...)` | `models/data_model.py:1394-1409` | Same read/display/result dict pipeline |
| candidate | `EditorDataModel.read_value(...)` | `models/data_model.py:1571-1586` | Same read/display/result dict pipeline |

Shared pipeline:

1. Resolve active field payload.
2. Compute field address.
3. Read authored raw value.
4. Resolve section/group context.
5. Convert pointer display or raw display.
6. Return the same dict keys: `field`, `address`, `raw_value`, `display_value`, `writeable`, `value_behavior`.

Only meaningful difference:

- `_read_field_at_record_address` receives `record_addr`.
- `read_value` computes `record_addr` from `domain + index`.

Likely consolidation target:

- Make `read_value()` compute `record_addr` and delegate to `_read_field_at_record_address()`.

---

### 5. Indexed write path duplicates record-address write path

| Status | Function | Location | Evidence |
|---|---|---:|---|
| candidate | `EditorDataModel._write_field_at_record_address(...)` | `models/data_model.py:1411-1420` | Same readonly/address/display-to-raw/write pipeline |
| candidate | `EditorDataModel.write_value(...)` | `models/data_model.py:1588-1602` | Same readonly/address/display-to-raw/write pipeline plus cache update |

Shared pipeline:

1. Resolve active field payload.
2. Reject readonly payload.
3. Compute field address.
4. Convert shoe dropdown ID-prefixed value or display value to raw.
5. Write authored value.

Important difference:

- `write_value()` also updates `_player_team_pointer_cache` for `Players/CURRENTTEAM`.

Likely consolidation target:

- Extract the shared write pipeline or have `write_value()` delegate to `_write_field_at_record_address()` and keep the player-team cache update outside the shared write.

---

### 6. Base-pointer resolution split across overlapping helpers

| Status | Function | Location | Evidence |
|---|---|---:|---|
| candidate | `EditorDataModel._resolve_base_pointer_entry(...)` | `models/data_model.py:1005-1026` | Generic base-entry resolver |
| candidate | `EditorDataModel._resolve_base_pointer_by_key(...)` | `models/data_model.py:1046-1047` | Thin key wrapper around generic resolver |
| candidate | `EditorDataModel.domain_base(...)` | `models/data_model.py:1517-1540` | Separately resolves domain base pointer from config |

Overlap:

- All paths resolve authored base-pointer config into an absolute base address.
- `domain_base()` manually repeats pointer-size/deref/final-offset behavior that exists in `_resolve_base_pointer_entry()`.

Current internal uses:

- `_resolve_base_pointer_by_key`: `models/data_model.py:1003`
- `domain_base`: `models/data_model.py:1239`, `1365`, `1458`, `1554`

Likely consolidation target:

- If domain base entries follow the same authored base-pointer contract, route `domain_base()` through `_resolve_base_pointer_entry()` / `_resolve_base_pointer_by_key()`.
- Verify against direct-table and final-offset cases before changing.

## Thin wrappers / likely removable if no external dependency

### 7. Private field-offset method wrapper

| Status | Function | Location | Evidence |
|---|---|---:|---|
| likely redundant | `EditorDataModel._field_offset(self, field)` | `models/data_model.py:1568-1569` | One-line wrapper around module `_field_offset(...)` |

Implementation:

```py
return _field_offset(self._field_version_payload(field))
```

Internal references found:

- Definition only.
- No `self._field_offset(...)` calls found inside `nba2k_editor/`.

Likely action:

- Remove if no external/private test dependency exists.

---

### 8. Private label-for-index wrapper appears unused

| Status | Function | Location | Evidence |
|---|---|---:|---|
| likely redundant / unused | `EditorDataModel._label_for_index(self, domain, index)` | `models/data_model.py:1451-1452` | Definition only in internal search |

Implementation:

```py
return self._label_for_record_address(domain, index, self.record_address(domain, index), self._label_entries(domain))
```

Internal references found:

- Definition only.

Likely action:

- Remove if no external/private test dependency exists.

---

### 9. Record-address method wrapper duplicates top-level address function

| Status | Function | Location | Evidence |
|---|---|---:|---|
| wrapper | `record_address(base, index, stride)` | `models/data_model.py:229-235` | Authoritative address math |
| wrapper | `EditorDataModel.record_address(self, domain, index)` | `models/data_model.py:1553-1554` | One-line domain-aware wrapper |

Implementation of method wrapper:

```py
return record_address(base=self.domain_base(domain), index=index, stride=self.domain_stride(domain))
```

Current internal uses:

- Method wrapper: `models/data_model.py:1452`, `1573`, `1592`
- Top-level helper: `models/data_model.py:1466`

This is not necessarily wrong; it may be an intentional domain-aware API. It is listed because it is a pure wrapper around the top-level helper.

## Repetitive UI tag helpers

These are not proven wrong, but they are function-count bloat: many one-line methods only call `_tag(...)` with a fixed suffix.

Representative cluster:

| Function | Location | Pattern |
|---|---:|---|
| `DpgEditorApp._row_current_tag(...)` | `ui/dpg_editor.py:540-541` | `_tag(domain, index, ordinal, "editor", ...)` |
| `DpgEditorApp._row_new_tag(...)` | `ui/dpg_editor.py:543-544` | `_tag(domain, index, ordinal, "editor", ...)` |
| `DpgEditorApp._row_status_tag(...)` | `ui/dpg_editor.py:546-547` | `_tag(domain, index, ordinal, "editor", ...)` |
| `DpgEditorApp._editor_status_tag(...)` | `ui/dpg_editor.py:549-550` | `_tag(domain, index, "editor", ...)` |
| `DpgEditorApp._season_stat_selector_tag(...)` | `ui/dpg_editor.py:555-556` | `_tag(domain, index, "editor", ...)` |

Likely action:

- Leave unless the goal is specifically reducing wrapper count.
- If reducing wrappers, replace with one parameterized tag helper and preserve exact tag strings with tests.

## Repeated named-value readers

These helpers share lookup/read/exception-swallowing structure but differ by address-vs-item and raw-vs-display return.

| Status | Function | Location | Difference |
|---|---|---:|---|
| candidate | `EditorDataModel._read_named_raw_int(...)` | `models/data_model.py:1262-1271` | item + single name + raw int |
| candidate | `EditorDataModel._read_named_value(...)` | `models/data_model.py:1273-1285` | item + candidate names + display string |
| candidate | `EditorDataModel._read_named_value_at_record_address(...)` | `models/data_model.py:1183-1193` | record address + candidate names + display string |

Likely consolidation target:

- A shared internal lookup/read primitive could reduce repetition.
- Do not merge until callers are checked, because return types and default values differ.

## Do not treat these as redundant only because names are similar

These pairs are inverse operations or intentionally different directions:

- `convert_pounds_to_kilograms` vs `convert_kilograms_to_pounds`
- `raw_height_to_inches` vs `height_inches_to_raw`
- `convert_raw_to_rating` vs `convert_rating_to_raw`
- `convert_tendency_raw_to_rating` vs `convert_rating_to_tendency_raw`
- `_read_bitfield` vs `_write_bitfield`
- `GameMemory.read_bytes` vs `GameMemory.write_bytes`

They are similar by token scan but not redundant.

## Suggested cleanup order

1. Remove or merge exact duplicates first:
   - `_parse_id_prefixed_option`
   - `_field_by_display_or_normalized_name` / `_field_by_normalized_name`
2. Remove unused private wrappers if tests confirm no references:
   - `EditorDataModel._field_offset`
   - `EditorDataModel._label_for_index`
3. Consolidate read/write pipelines only with regression tests around:
   - normal indexed field read/write
   - selected season stat detail read/write
   - `Players/CURRENTTEAM` cache behavior
4. Treat UI tag wrapper reduction as optional and low priority.
