# NBA2K Editor Function Index

AST-generated index of every Python function definition inside `nba2k_editor/` only.

- Python files scanned: 16
- Files with function definitions: 9
- Named functions/methods listed: 295
- Lambda expressions listed: 26
- Total callable definitions listed: 321
- Direct methods listed: 192
- Nested named functions listed: 2
- Scope: all `*.py` files below `nba2k_editor/`, including nested functions and lambda expressions; excludes only cache folders.
- Out of scope: every file outside `nba2k_editor/`.
- Purpose: quick ownership map so new work can reuse existing editor functions instead of adding duplicate wrappers.

## Quick owner map

| Area | Owner file | What belongs there |
|---|---|---|
| CLI dispatch | `__main__.py`, `entrypoints/gui.py` | argument parsing and entrypoint handoff |
| Offset config/layout | `core/offsets.py` | selecting target offset config and editor layout data |
| Value conversion | `core/conversions.py` | 2K raw/display conversion math and bounds |
| Process memory | `memory/game_memory.py`, `memory/win32.py` | process detection/open/close and low-level reads/writes |
| Editor data model | `models/data_model.py` | domain base/stride, authored layout entries, field payload lookup, conversion-backed address/read/write/readback, item loading/selection/background refresh, stat-ID season detail routing, UI-ready detail values |
| DPG UI | `ui/dpg_editor.py`, `ui/theme.py` | widgets, callbacks, refresh-event polling, editor windows, visual theme |

## Functions by file

### `__init__.py`

_No function definitions._

### `__main__.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 10 | 15 | function | `build_parser` | `build_parser() -> argparse.ArgumentParser` | — | No docstring; handles build parser behavior. |
| 18 | 24 | function | `main` | `main(argv: Sequence[str] \| None=None) -> int` | — | No docstring; handles main behavior. |

### `core/__init__.py`

_No function definitions._

### `core/conversions.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 26 | 27 | function | `_normalize_year_key` | `_normalize_year_key(value: str) -> str` | — | No docstring; handles normalize year key behavior. |
| 30 | 47 | function | `is_year_offset_field` | `is_year_offset_field(field_name: str) -> bool` | — | Return True if a field name should be treated as a year offset from YEAR_BASE. |
| 50 | 61 | function | `convert_raw_to_year` | `convert_raw_to_year(raw: int, base_year: int=YEAR_BASE) -> int` | — | Convert a stored year offset into a calendar year. |
| 64 | 76 | function | `convert_year_to_raw` | `convert_year_to_raw(year: int, base_year: int=YEAR_BASE) -> int` | — | Convert a calendar year into its stored offset. |
| 89 | 104 | function | `convert_raw_to_rating` | `convert_raw_to_rating(raw: int, length: int) -> int` | — | Convert a raw bitfield value into the 25-99 display rating scale using proportional mapping. |
| 107 | 128 | function | `convert_rating_to_raw` | `convert_rating_to_raw(rating: float, length: int) -> int` | — | Convert a 25-99 rating back into a raw bitfield value using proportional mapping. |
| 131 | 137 | function | `convert_potential_to_raw` | `convert_potential_to_raw(rating: float, length: int \| None=None, minimum: float=40.0, maximum: float=99.0) -> int` | — | Convert Potential display ratings into raw values, bounded to the 40-99 display scale. |
| 140 | 149 | function | `convert_raw_to_potential` | `convert_raw_to_potential(raw: int, length: int \| None=None, minimum: float=40.0, maximum: float=99.0) -> int` | — | Convert raw Potential values through the rating curve, bounded to 40-99. |
| 152 | 154 | function | `convert_minmax_potential_to_raw` | `convert_minmax_potential_to_raw(rating: float, length: int, minimum: float=0.0, maximum: float=100.0) -> int` | — | Convert Min/Max/Average potential-like display values on the 0-100 scale into raw values. |
| 157 | 159 | function | `convert_raw_to_minmax_potential` | `convert_raw_to_minmax_potential(raw: int, length: int, minimum: float=0.0, maximum: float=100.0) -> int` | — | Convert Min/Max/Average potential-like raw values into the 0-100 display scale. |
| 162 | 168 | function | `convert_raw_to_body_scale_display` | `convert_raw_to_body_scale_display(raw: object, length: int=0) -> int` | — | Convert body scale raw float storage into the 0-100 editor display scale. |
| 171 | 173 | function | `convert_body_scale_display_to_raw` | `convert_body_scale_display_to_raw(display_value: object, length: int=0) -> float` | — | Convert body scale 0-100 display values into raw float storage. |
| 176 | 182 | function | `convert_raw_to_injury_duration_days` | `convert_raw_to_injury_duration_days(raw: int, maximum_days: int=450) -> int` | — | Convert player injury duration storage into displayed days, ignoring high status flag bits. |
| 185 | 192 | function | `convert_injury_duration_days_to_raw` | `convert_injury_duration_days_to_raw(days: float, maximum_days: int=450) -> int` | — | Convert displayed injury duration days into low duration ticks, clamped to the editor range. |
| 195 | 208 | function | `normalize_weight_value` | `normalize_weight_value(value: object) -> float \| None` | — | Parse editor input into a supported weight value in pounds. |
| 211 | 216 | function | `convert_pounds_to_kilograms` | `convert_pounds_to_kilograms(pounds: object) -> float` | — | Convert pounds to kilograms. |
| 219 | 224 | function | `convert_kilograms_to_pounds` | `convert_kilograms_to_pounds(kilograms: object) -> float` | — | Convert kilograms to pounds. |
| 227 | 233 | function | `raw_height_to_inches` | `raw_height_to_inches(raw_val: int) -> int` | — | Convert raw stored height (inches * 254) to inches. |
| 236 | 246 | function | `clamp_height_inches` | `clamp_height_inches(inches: int) -> int` | — | Clamp a height value to the supported player-editor range. |
| 249 | 255 | function | `height_inches_to_raw` | `height_inches_to_raw(inches: int) -> int` | — | Convert inches to raw stored height (inches * 254). |
| 258 | 266 | function | `format_height_inches` | `format_height_inches(inches: int) -> str` | — | Format inches as feet/inches for display. |
| 269 | 279 | function | `convert_tendency_raw_to_rating` | `convert_tendency_raw_to_rating(raw: int, length: int) -> int` | — | Convert a raw bitfield value into a 0-100 tendency rating. |
| 282 | 292 | function | `convert_rating_to_tendency_raw` | `convert_rating_to_tendency_raw(rating: float, length: int) -> int` | — | Convert a 0-100 tendency rating into a raw bitfield value. |
| 295 | 305 | function | `player_numeric_bounds` | `player_numeric_bounds(category_name: str, field_name: str, length_bits: int) -> tuple[int, int]` | — | No docstring; handles player numeric bounds behavior. |
| 308 | 322 | function | `to_int` | `to_int(value: Any) -> int` | — | Convert strings or numeric values to an integer, accepting hex strings. |

### `core/offsets.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 254 | 259 | function | `_split_version_tokens` | `_split_version_tokens(raw_key: object) -> tuple[str, ...]` | — | No docstring; handles split version tokens behavior. |
| 262 | 269 | function | `_version_key_matches` | `_version_key_matches(raw_key: object, target_label: str \| None) -> bool` | — | No docstring; handles version key matches behavior. |
| 272 | 276 | function | `_select_version_entry` | `_select_version_entry(per_version: dict[str, object], target_label: str) -> dict[str, object]` | — | No docstring; handles select version entry behavior. |
| 279 | 289 | function | `_select_active_version` | `_select_active_version(versions_map: dict[str, object], target_executable: str \| None, *, require_hint: bool=False) -> tuple[str, str, dict[str, object]] \| None` | — | No docstring; handles select active version behavior. |
| 292 | 302 | function | `_resolved_length_bits` | `_resolved_length_bits(version_payload: dict[str, object]) -> int` | — | No docstring; handles resolved length bits behavior. |
| 305 | 350 | function | `get_editor_layout_for_super` | `get_editor_layout_for_super(super_type: str) -> dict[str, object]` | — | Return the owning offsets file's authored structure directly. |
| 353 | 355 | function | `_load_offsets_resource` | `_load_offsets_resource(file_name: str) -> dict[str, object]` | — | No docstring; handles load offsets resource behavior. |
| 358 | 378 | function | `_load_league_offset_config` | `_load_league_offset_config(target_executable: str \| None=None) -> dict[str, object]` | — | Load the authored league offsets resource only. |
| 381 | 384 | function | `get_active_offset_config` | `get_active_offset_config(target_executable: str \| None=None) -> dict[str, object]` | — | No docstring; handles get active offset config behavior. |
| 387 | 392 | function | `_derive_version_label` | `_derive_version_label(executable: str \| None) -> str` | — | No docstring; handles derive version label behavior. |
| 395 | 408 | function | `_resolve_version_context` | `_resolve_version_context(data: dict[str, Any] \| None, target_executable: str \| None) -> tuple[str, dict[str, Any], dict[str, Any]]` | — | No docstring; handles resolve version context behavior. |
| 412 | 419 | function | `_normalize_chain_steps` | `_normalize_chain_steps(chain_data: list[dict[str, object]]) -> list[dict[str, object]]` | — | No docstring; handles normalize chain steps behavior. |
| 422 | 434 | function | `_parse_pointer_chain_config` | `_parse_pointer_chain_config(base_cfg: dict[str, object]) -> list[dict[str, object]]` | — | No docstring; handles parse pointer chain config behavior. |
| 437 | 494 | function | `_apply_offset_config` | `_apply_offset_config(data: dict \| None, target_executable: str \| None=None) -> None` | — | Update module-level constants using the loaded offset data. |
| 497 | 498 | function | `has_active_config` | `has_active_config() -> bool` | — | No docstring; handles has active config behavior. |
| 501 | 502 | function | `get_current_target` | `get_current_target() -> str` | — | No docstring; handles get current target behavior. |
| 505 | 518 | function | `initialize_offsets` | `initialize_offsets(target_executable: str \| None=None, force: bool=False) -> None` | — | Ensure embedded offset data for the requested executable is loaded. |

### `entrypoints/__init__.py`

_No function definitions._

### `entrypoints/gui.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 11 | 19 | function | `build_parser` | `build_parser() -> argparse.ArgumentParser` | — | No docstring; handles build parser behavior. |
| 22 | 31 | function | `main` | `main(argv: Sequence[str] \| None=None) -> int` | — | No docstring; handles main behavior. |

### `entrypoints/runtime_cleanup.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 12 | 28 | function | `delete_runtime_cache_dirs` | `delete_runtime_cache_dirs(root: Path \| None=None) -> tuple[int, int]` | — | No docstring; handles delete runtime cache dirs behavior. |

### `memory/__init__.py`

_No function definitions._

### `memory/game_memory.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 35 | 40 | method | `GameMemory.__init__` | `__init__(self, module_name: str=MODULE_NAME)` | — | No docstring; handles init behavior. |
| 42 | 80 | method | `GameMemory._detect_pointer_size` | `_detect_pointer_size(self, handle: wintypes.HANDLE \| None) -> int` | — | No docstring; handles detect pointer size behavior. |
| 86 | 108 | method | `GameMemory.detect_running_module_name` | `detect_running_module_name(preferred_module: str \| None=None) -> str \| None` | @staticmethod | No docstring; handles detect running module name behavior. |
| 110 | 121 | method | `GameMemory.find_pid` | `find_pid(self) -> int \| None` | — | No docstring; handles find pid behavior. |
| 123 | 148 | method | `GameMemory.open_process` | `open_process(self) -> bool` | — | Open the game process and resolve its base address. |
| 150 | 160 | method | `GameMemory.close` | `close(self) -> None` | — | Close any open process handle and reset state. |
| 162 | 181 | method | `GameMemory._get_module_base` | `_get_module_base(self, pid: int, module_name: str) -> int \| None` | — | No docstring; handles get module base behavior. |
| 186 | 188 | method | `GameMemory._check_open` | `_check_open(self, op: str \| None=None, addr: int \| None=None, length: int \| None=None) -> None` | — | No docstring; handles check open behavior. |
| 190 | 201 | method | `GameMemory.read_bytes` | `read_bytes(self, addr: int, length: int) -> bytes` | — | Read length bytes from absolute address addr. |
| 203 | 214 | method | `GameMemory.write_bytes` | `write_bytes(self, addr: int, data: bytes) -> None` | — | Write data to absolute address addr. |
| 216 | 223 | method | `GameMemory.write_pointer` | `write_pointer(self, addr: int, value: int) -> None` | — | Write a pointer-sized value to absolute address addr. |
| 225 | 227 | method | `GameMemory.read_uint32` | `read_uint32(self, addr: int) -> int` | — | No docstring; handles read uint32 behavior. |
| 229 | 231 | method | `GameMemory.write_uint32` | `write_uint32(self, addr: int, value: int) -> None` | — | No docstring; handles write uint32 behavior. |
| 233 | 235 | method | `GameMemory.read_u64` | `read_u64(self, addr: int) -> int` | — | No docstring; handles read u64 behavior. |
| 237 | 247 | method | `GameMemory.read_wstring` | `read_wstring(self, addr: int, max_chars: int) -> str` | — | Read a UTF-16LE string of at most max_chars characters from addr. |
| 249 | 254 | method | `GameMemory.write_wstring_fixed` | `write_wstring_fixed(self, addr: int, value: str, max_chars: int) -> None` | — | Write a fixed length null-terminated UTF-16LE string at addr. |
| 257 | 267 | method | `GameMemory.read_ascii` | `read_ascii(self, addr: int, max_chars: int) -> str` | — | Read an ASCII string of up to max_chars bytes from addr. |
| 269 | 274 | method | `GameMemory.write_ascii_fixed` | `write_ascii_fixed(self, addr: int, value: str, max_chars: int) -> None` | — | Write a fixed length null-terminated ASCII string at addr. |

### `memory/win32.py`

_No function definitions._

### `models/__init__.py`

_No function definitions._

### `models/data_model.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 66 | 70 | function | `_plausible_record_name_part` | `_plausible_record_name_part(value: object) -> bool` | — | No docstring; handles plausible record name part behavior. |
| 73 | 83 | function | `_valid_nba_record_label_values` | `_valid_nba_record_label_values(values: list[Any]) -> bool` | — | No docstring; handles valid nba record label values behavior. |
| 86 | 87 | function | `_has_alpha_text` | `_has_alpha_text(value: object) -> bool` | — | No docstring; handles has alpha text behavior. |
| 133 | 138 | function | `target_display_label` | `target_display_label(executable: str \| None) -> str` | — | No docstring; handles target display label behavior. |
| 150 | 151 | method | `FieldEntry.normalized_name` | `normalized_name(self) -> str` | @property | No docstring; handles normalized name behavior. |
| 154 | 155 | method | `FieldEntry.display_name` | `display_name(self) -> str` | @property | No docstring; handles display name behavior. |
| 166 | 167 | method | `RecordListItem.display_label` | `display_label(self) -> str` | @property | No docstring; handles display label behavior. |
| 170 | 182 | function | `_iter_layout_fields` | `_iter_layout_fields(domain: str, layout: dict[str, Any]) -> Iterable[FieldEntry]` | — | No docstring; handles iter layout fields behavior. |
| 200 | 201 | function | `_stat_role` | `_stat_role(field: dict[str, Any]) -> str` | — | No docstring; handles stat role behavior. |
| 204 | 206 | function | `_selected_record_source` | `_selected_record_source(field: dict[str, Any]) -> dict[str, Any] \| None` | — | No docstring; handles selected record source behavior. |
| 209 | 210 | function | `_is_player_season_id_selector_entry` | `_is_player_season_id_selector_entry(entry: FieldEntry) -> bool` | — | No docstring; handles is player season id selector entry behavior. |
| 213 | 214 | function | `_is_player_selected_stat_detail_entry` | `_is_player_selected_stat_detail_entry(entry: FieldEntry) -> bool` | — | No docstring; handles is player selected stat detail entry behavior. |
| 217 | 218 | function | `_player_season_id_option_label` | `_player_season_id_option_label(entry: FieldEntry) -> str` | — | No docstring; handles player season id option label behavior. |
| 221 | 226 | function | `_player_season_id_identity_from_option` | `_player_season_id_identity_from_option(option: object) -> str` | — | No docstring; handles player season id identity from option behavior. |
| 229 | 235 | function | `record_address` | `record_address(*, base: int, index: int, stride: int) -> int` | — | Return the absolute record address for a zero-based record number. |
| 238 | 241 | function | `_field_offset` | `_field_offset(payload: dict[str, Any]) -> int` | — | No docstring; handles field offset behavior. |
| 244 | 245 | function | `_type_key` | `_type_key(payload: dict[str, Any]) -> str` | — | No docstring; handles type key behavior. |
| 248 | 277 | function | `_implemented_payload` | `_implemented_payload(payload: dict[str, Any]) -> bool` | — | No docstring; handles implemented payload behavior. |
| 280 | 283 | function | `_readable_payload` | `_readable_payload(payload: dict[str, Any]) -> bool` | — | No docstring; handles readable payload behavior. |
| 301 | 302 | function | `_bits_to_bytes` | `_bits_to_bytes(bits: int) -> int` | — | No docstring; handles bits to bytes behavior. |
| 305 | 324 | function | `_numeric_width` | `_numeric_width(payload: dict[str, Any]) -> int` | — | No docstring; handles numeric width behavior. |
| 327 | 333 | function | `_bit_window` | `_bit_window(payload: dict[str, Any]) -> tuple[int, int, int]` | — | No docstring; handles bit window behavior. |
| 339 | 345 | function | `_read_pointer_value` | `_read_pointer_value(memory: Any, address: int) -> int` | — | No docstring; handles read pointer value behavior. |
| 348 | 352 | function | `_read_bitfield` | `_read_bitfield(memory: Any, address: int, payload: dict[str, Any]) -> int` | — | No docstring; handles read bitfield behavior. |
| 355 | 360 | function | `_write_bitfield` | `_write_bitfield(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write bitfield behavior. |
| 363 | 364 | function | `_field_identity` | `_field_identity(value: object) -> str` | — | No docstring; handles field identity behavior. |
| 367 | 368 | function | `_field_display_or_name` | `_field_display_or_name(field: dict[str, Any]) -> str` | — | No docstring; handles field display or name behavior. |
| 371 | 376 | function | `_uses_bitfield_io` | `_uses_bitfield_io(payload: dict[str, Any]) -> bool` | — | No docstring; handles uses bitfield io behavior. |
| 379 | 388 | function | `_list_mapping_value` | `_list_mapping_value(raw_value: Any, options: object) -> Any \| None` | — | No docstring; handles list mapping value behavior. |
| 391 | 398 | function | `_reverse_list_mapping` | `_reverse_list_mapping(value: Any, options: object) -> int \| None` | — | No docstring; handles reverse list mapping behavior. |
| 401 | 417 | function | `_mapped_display_value` | `_mapped_display_value(payload: dict[str, Any], raw_value: Any) -> Any \| None` | — | No docstring; handles mapped display value behavior. |
| 420 | 433 | function | `_mapped_raw_value` | `_mapped_raw_value(payload: dict[str, Any], value: Any) -> Any \| None` | — | No docstring; handles mapped raw value behavior. |
| 436 | 438 | function | `_id_prefixed_option` | `_id_prefixed_option(raw_id: int, label: str) -> str` | — | No docstring; handles id prefixed option behavior. |
| 441 | 443 | function | `_parse_id_prefixed_option` | `_parse_id_prefixed_option(value: Any) -> int \| None` | — | No docstring; handles parse id prefixed option behavior. |
| 463 | 502 | function | `_raw_to_display_value` | `_raw_to_display_value(section: str, field: dict[str, Any], payload: dict[str, Any], raw_value: Any) -> Any` | — | No docstring; handles raw to display value behavior. |
| 505 | 547 | function | `_display_to_raw_value` | `_display_to_raw_value(section: str, field: dict[str, Any], payload: dict[str, Any], value: Any) -> Any` | — | No docstring; handles display to raw value behavior. |
| 551 | 555 | function | `_string_length` | `_string_length(payload: dict[str, Any]) -> int` | — | No docstring; handles string length behavior. |
| 558 | 565 | function | `_read_string` | `_read_string(memory: Any, address: int, payload: dict[str, Any]) -> str` | — | No docstring; handles read string behavior. |
| 568 | 578 | function | `_write_string` | `_write_string(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write string behavior. |
| 581 | 587 | function | `_read_ptr_string` | `_read_ptr_string(memory: Any, address: int, payload: dict[str, Any]) -> str` | — | No docstring; handles read ptr string behavior. |
| 590 | 596 | function | `_result_score_addresses` | `_result_score_addresses(address: int, payload: dict[str, Any]) -> tuple[int, int]` | — | No docstring; handles result score addresses behavior. |
| 599 | 601 | function | `_coerce_result_component` | `_coerce_result_component(value: float) -> int \| float` | — | No docstring; handles coerce result component behavior. |
| 604 | 608 | function | `_read_result_score` | `_read_result_score(memory: Any, address: int, payload: dict[str, Any]) -> tuple[int \| float, int \| float]` | — | No docstring; handles read result score behavior. |
| 611 | 619 | function | `_parse_result_score` | `_parse_result_score(value: Any) -> tuple[float, float]` | — | No docstring; handles parse result score behavior. |
| 622 | 625 | function | `_format_result_component` | `_format_result_component(value: int \| float) -> str` | — | No docstring; handles format result component behavior. |
| 628 | 629 | function | `_format_result_score` | `_format_result_score(value: tuple[int \| float, int \| float]) -> str` | — | No docstring; handles format result score behavior. |
| 632 | 633 | function | `_color_hex` | `_color_hex(raw_value: bytes) -> str` | — | No docstring; handles color hex behavior. |
| 636 | 647 | function | `_parse_color_value` | `_parse_color_value(value: Any, width: int) -> bytes` | — | No docstring; handles parse color value behavior. |
| 650 | 690 | function | `_read_authored_value` | `_read_authored_value(memory: Any, address: int, payload: dict[str, Any]) -> Any` | — | No docstring; handles read authored value behavior. |
| 693 | 738 | function | `_write_authored_value` | `_write_authored_value(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write authored value behavior. |
| 744 | 769 | method | `EditorDataModel.__init__` | `__init__(self, *, memory: GameMemory \| Any \| None=None, offsets_api: Any=offsets_mod, target_executable: str \| None=None) -> None` | — | No docstring; handles init behavior. |
| 771 | 773 | method | `EditorDataModel._active_config` | `_active_config(self) -> dict[str, Any]` | — | No docstring; handles active config behavior. |
| 775 | 778 | method | `EditorDataModel._domain_base_key` | `_domain_base_key(self, domain: str) -> str` | — | No docstring; handles domain base key behavior. |
| 780 | 785 | method | `EditorDataModel._domain_stride_key` | `_domain_stride_key(self, domain: str) -> str` | — | No docstring; handles domain stride key behavior. |
| 787 | 791 | method | `EditorDataModel.editor_layout` | `editor_layout(self, domain: str) -> dict[str, Any]` | — | No docstring; handles editor layout behavior. |
| 793 | 796 | method | `EditorDataModel._layout_entries` | `_layout_entries(self, domain: str) -> tuple[FieldEntry, ...]` | — | No docstring; handles layout entries behavior. |
| 798 | 809 | method | `EditorDataModel._field_lookup` | `_field_lookup(self, domain: str) -> dict[str, FieldEntry]` | — | No docstring; handles field lookup behavior. |
| 811 | 814 | method | `EditorDataModel._field_context_map` | `_field_context_map(self, domain: str) -> dict[int, tuple[str, str]]` | — | No docstring; handles field context map behavior. |
| 816 | 827 | method | `EditorDataModel._field_context` | `_field_context(self, domain: str, field: dict[str, Any]) -> tuple[str, str]` | — | No docstring; handles field context behavior. |
| 829 | 830 | method | `EditorDataModel._field_by_display_or_normalized_name` | `_field_by_display_or_normalized_name(self, domain: str, name: object) -> FieldEntry \| None` | — | No docstring; handles field by display or normalized name behavior. |
| 832 | 857 | method | `EditorDataModel._field_address` | `_field_address(self, domain: str, record_addr: int, field: dict[str, Any], payload: dict[str, Any]) -> int` | — | No docstring; handles field address behavior. |
| 859 | 867 | method | `EditorDataModel.attach` | `attach(self) -> bool` | — | No docstring; handles attach behavior. |
| 869 | 873 | method | `EditorDataModel.runtime_status_text` | `runtime_status_text(self) -> str` | — | No docstring; handles runtime status text behavior. |
| 875 | 889 | method | `EditorDataModel.select_target_executable` | `select_target_executable(self, executable: str) -> None` | — | No docstring; handles select target executable behavior. |
| 891 | 892 | method | `EditorDataModel.domain_status` | `domain_status(self, domain: str) -> str` | — | No docstring; handles domain status behavior. |
| 894 | 895 | method | `EditorDataModel.domain_item_labels` | `domain_item_labels(self, domain: str) -> list[str]` | — | No docstring; handles domain item labels behavior. |
| 897 | 898 | method | `EditorDataModel.domain_item_count` | `domain_item_count(self, domain: str) -> int` | — | No docstring; handles domain item count behavior. |
| 900 | 901 | method | `EditorDataModel.player_team_filter_options` | `player_team_filter_options(self) -> tuple[str, ...]` | — | No docstring; handles player team filter options behavior. |
| 903 | 910 | method | `EditorDataModel._read_player_current_team_pointer` | `_read_player_current_team_pointer(self, item: RecordListItem) -> int \| None` | — | No docstring; handles read player current team pointer behavior. |
| 912 | 915 | method | `EditorDataModel._player_current_team_pointer` | `_player_current_team_pointer(self, item: RecordListItem) -> int \| None` | — | No docstring; handles player current team pointer behavior. |
| 917 | 918 | method | `EditorDataModel._cache_player_team_pointers` | `_cache_player_team_pointers(self, items: list[RecordListItem]) -> None` | — | No docstring; handles cache player team pointers behavior. |
| 920 | 936 | method | `EditorDataModel.player_item_labels_for_team_filter` | `player_item_labels_for_team_filter(self, selected_team_label: str \| None, search_text: str \| None=None) -> list[str]` | — | No docstring; handles player item labels for team filter behavior. |
| 938 | 939 | method | `EditorDataModel.player_item_count_for_team_filter` | `player_item_count_for_team_filter(self, selected_team_label: str \| None, search_text: str \| None=None) -> int` | — | No docstring; handles player item count for team filter behavior. |
| 941 | 942 | method | `EditorDataModel.is_player_season_id_selector_entry` | `is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool` | — | No docstring; handles is player season id selector entry behavior. |
| 944 | 945 | method | `EditorDataModel.is_player_selected_stat_detail_entry` | `is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool` | — | No docstring; handles is player selected stat detail entry behavior. |
| 947 | 961 | method | `EditorDataModel.player_season_stat_id_options` | `player_season_stat_id_options(self, player_index: int) -> list[str]` | — | No docstring; handles player season stat id options behavior. |
| 963 | 969 | method | `EditorDataModel._player_season_id_selector_entries` | `_player_season_id_selector_entries(self, selector_role: object) -> list[FieldEntry]` | — | No docstring; handles player season id selector entries behavior. |
| 971 | 981 | method | `EditorDataModel._player_season_id_selector_entry_for_option` | `_player_season_id_selector_entry_for_option(self, selected: object, *, selector_role: object=_STAT_ROLE_SELECTOR) -> FieldEntry` | — | No docstring; handles player season id selector entry for option behavior. |
| 983 | 987 | method | `EditorDataModel._selected_record_source_for_entry` | `_selected_record_source_for_entry(self, entry: FieldEntry) -> dict[str, Any]` | — | No docstring; handles selected record source for entry behavior. |
| 989 | 1003 | method | `EditorDataModel._player_season_stat_detail_base_address` | `_player_season_stat_detail_base_address(self, entry: FieldEntry, player_index: int, selected: object) -> int` | — | No docstring; handles player season stat detail base address behavior. |
| 1005 | 1026 | method | `EditorDataModel._resolve_base_pointer_entry` | `_resolve_base_pointer_entry(self, base_entry: dict[str, Any], *, label: str) -> int` | — | No docstring; handles resolve base pointer entry behavior. |
| 1028 | 1034 | method | `EditorDataModel._read_pointer_value` | `_read_pointer_value(self, address: int, pointer_size: int \| None=None) -> int` | — | No docstring; handles read pointer value behavior. |
| 1036 | 1044 | method | `EditorDataModel._base_pointer_entry` | `_base_pointer_entry(self, key: str) -> dict[str, Any]` | — | No docstring; handles base pointer entry behavior. |
| 1046 | 1047 | method | `EditorDataModel._resolve_base_pointer_by_key` | `_resolve_base_pointer_by_key(self, key: str) -> int` | — | No docstring; handles resolve base pointer by key behavior. |
| 1049 | 1057 | method | `EditorDataModel._stride_value` | `_stride_value(self, key: str) -> int` | — | No docstring; handles stride value behavior. |
| 1059 | 1067 | method | `EditorDataModel._record_id_value` | `_record_id_value(self, domain: str, item: RecordListItem, id_field_name: str) -> int \| None` | — | No docstring; handles record id value behavior. |
| 1069 | 1075 | method | `EditorDataModel._shoe_option_map` | `_shoe_option_map(self) -> dict[int, str]` | — | No docstring; handles shoe option map behavior. |
| 1077 | 1082 | method | `EditorDataModel.field_options` | `field_options(self, entry: FieldEntry) -> list[str]` | — | No docstring; handles field options behavior. |
| 1084 | 1085 | method | `EditorDataModel.selected_item` | `selected_item(self, domain: str) -> RecordListItem \| None` | — | No docstring; handles selected item behavior. |
| 1087 | 1090 | method | `EditorDataModel.select_item_by_label` | `select_item_by_label(self, domain: str, selected_label: str \| None) -> RecordListItem \| None` | — | No docstring; handles select item by label behavior. |
| 1092 | 1115 | method | `EditorDataModel.refresh_domain_items` | `refresh_domain_items(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | — | No docstring; handles refresh domain items behavior. |
| 1117 | 1122 | method | `EditorDataModel.start_background_refresh` | `start_background_refresh(self, domains: tuple[str, ...]) -> bool` | — | No docstring; handles start background refresh behavior. |
| 1124 | 1136 | method | `EditorDataModel._background_refresh_worker` | `_background_refresh_worker(self, domains: tuple[str, ...]) -> None` | — | No docstring; handles background refresh worker behavior. |
| 1138 | 1144 | method | `EditorDataModel.pop_refresh_events` | `pop_refresh_events(self) -> list[tuple[str, str]]` | — | No docstring; handles pop refresh events behavior. |
| 1146 | 1147 | method | `EditorDataModel.player_detail_labels` | `player_detail_labels(self) -> tuple[str, ...]` | — | No docstring; handles player detail labels behavior. |
| 1149 | 1150 | method | `EditorDataModel.team_summary_labels` | `team_summary_labels(self) -> tuple[str, ...]` | — | No docstring; handles team summary labels behavior. |
| 1152 | 1157 | method | `EditorDataModel.record_summary_labels` | `record_summary_labels(self, domain: str) -> tuple[str, ...]` | — | No docstring; handles record summary labels behavior. |
| 1159 | 1165 | method | `EditorDataModel._selected_item_rank_text` | `_selected_item_rank_text(self, domain: str, item: RecordListItem \| None) -> str` | — | No docstring; handles selected item rank text behavior. |
| 1167 | 1172 | method | `EditorDataModel._record_summary_specs` | `_record_summary_specs(self, domain: str) -> tuple[tuple[str, tuple[str, ...]], ...]` | — | No docstring; handles record summary specs behavior. |
| 1174 | 1181 | method | `EditorDataModel._record_summary_values_for_item` | `_record_summary_values_for_item(self, domain: str, item: RecordListItem \| None, rank: int \| None=None) -> dict[str, str]` | — | No docstring; handles record summary values for item behavior. |
| 1183 | 1193 | method | `EditorDataModel._read_named_value_at_record_address` | `_read_named_value_at_record_address(self, domain: str, record_addr: int, candidates: tuple[str, ...]) -> str` | — | No docstring; handles read named value at record address behavior. |
| 1195 | 1202 | method | `EditorDataModel._record_summary_values_for_address` | `_record_summary_values_for_address(self, domain: str, record_addr: int, rank: int) -> dict[str, str]` | — | No docstring; handles record summary values for address behavior. |
| 1204 | 1222 | method | `EditorDataModel._packed_record_summary_stride` | `_packed_record_summary_stride(self, domain: str) -> int` | — | No docstring; handles packed record summary stride behavior. |
| 1224 | 1225 | method | `EditorDataModel.selected_record_summary_values` | `selected_record_summary_values(self, domain: str) -> dict[str, str]` | — | No docstring; handles selected record summary values behavior. |
| 1227 | 1260 | method | `EditorDataModel.record_summary_rows` | `record_summary_rows(self, domain: str, *, limit: int \| None, history_type: int \| None=None, record_row_start: int \| None=None, record_row_count: int \| None=None, record_row_stride: int \| None=None) -> list[dict[str, str]]` | — | No docstring; handles record summary rows behavior. |
| 1253 | 1253 | lambda | `EditorDataModel.record_summary_rows.<lambda#1>` | `<lambda#1>(item)` | — | Lambda expression. |
| 1262 | 1271 | method | `EditorDataModel._read_named_raw_int` | `_read_named_raw_int(self, domain: str, item: RecordListItem \| None, name: str) -> int \| None` | — | No docstring; handles read named raw int behavior. |
| 1273 | 1285 | method | `EditorDataModel._read_named_value` | `_read_named_value(self, domain: str, item: RecordListItem \| None, candidates: tuple[str, ...]) -> str` | — | No docstring; handles read named value behavior. |
| 1287 | 1289 | method | `EditorDataModel.selected_player_detail_values` | `selected_player_detail_values(self) -> dict[str, str]` | — | No docstring; handles selected player detail values behavior. |
| 1291 | 1293 | method | `EditorDataModel.selected_team_summary_values` | `selected_team_summary_values(self) -> dict[str, str]` | — | No docstring; handles selected team summary values behavior. |
| 1295 | 1315 | method | `EditorDataModel.save_selected_team_summary` | `save_selected_team_summary(self, values: dict[str, str]) -> tuple[int, int]` | — | No docstring; handles save selected team summary behavior. |
| 1317 | 1319 | method | `EditorDataModel.selected_detail_title` | `selected_detail_title(self, domain: str, label: str) -> str` | — | No docstring; handles selected detail title behavior. |
| 1321 | 1323 | method | `EditorDataModel.selected_record_address_text` | `selected_record_address_text(self, domain: str) -> str` | — | No docstring; handles selected record address text behavior. |
| 1325 | 1335 | method | `EditorDataModel.grouped_fields` | `grouped_fields(self, domain: str) -> OrderedDict[str, OrderedDict[str, list[FieldEntry]]]` | — | No docstring; handles grouped fields behavior. |
| 1337 | 1338 | method | `EditorDataModel._field_by_normalized_name` | `_field_by_normalized_name(self, domain: str, name: str) -> FieldEntry \| None` | — | No docstring; handles field by normalized name behavior. |
| 1340 | 1348 | method | `EditorDataModel._label_entries` | `_label_entries(self, domain: str) -> list[FieldEntry]` | — | No docstring; handles label entries behavior. |
| 1350 | 1351 | method | `EditorDataModel._team_pointer_display` | `_team_pointer_display(self, raw_value: Any) -> str \| None` | — | No docstring; handles team pointer display behavior. |
| 1353 | 1379 | method | `EditorDataModel._record_pointer_display` | `_record_pointer_display(self, raw_value: Any, target_domain: str) -> str \| None` | — | No docstring; handles record pointer display behavior. |
| 1381 | 1392 | method | `EditorDataModel._pointer_display_for_payload` | `_pointer_display_for_payload(self, payload: dict[str, Any], raw_value: Any) -> str \| None` | — | No docstring; handles pointer display for payload behavior. |
| 1394 | 1409 | method | `EditorDataModel._read_field_at_record_address` | `_read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles read field at record address behavior. |
| 1411 | 1420 | method | `EditorDataModel._write_field_at_record_address` | `_write_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any], value: Any) -> None` | — | No docstring; handles write field at record address behavior. |
| 1422 | 1433 | method | `EditorDataModel._label_for_record_address` | `_label_for_record_address(self, domain: str, index: int, record_addr: int, label_entries: list[FieldEntry]) -> str` | — | No docstring; handles label for record address behavior. |
| 1435 | 1449 | method | `EditorDataModel._valid_label_values` | `_valid_label_values(self, domain: str, record_addr: int, values: list[Any], labels: list[str]) -> bool` | — | No docstring; handles valid label values behavior. |
| 1451 | 1452 | method | `EditorDataModel._label_for_index` | `_label_for_index(self, domain: str, index: int) -> str` | — | No docstring; handles label for index behavior. |
| 1454 | 1484 | method | `EditorDataModel.scan_records` | `scan_records(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | — | No docstring; handles scan records behavior. |
| 1486 | 1493 | method | `EditorDataModel.read_entry_value` | `read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object \| None=None) -> dict[str, Any]` | — | No docstring; handles read entry value behavior. |
| 1495 | 1500 | method | `EditorDataModel.write_entry_value` | `write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object \| None=None) -> dict[str, Any]` | — | No docstring; handles write entry value behavior. |
| 1502 | 1515 | method | `EditorDataModel.section_fields` | `section_fields(self, domain: str, section: str, group: str) -> list[dict[str, Any]]` | — | No docstring; handles section fields behavior. |
| 1517 | 1540 | method | `EditorDataModel.domain_base` | `domain_base(self, domain: str) -> int` | — | No docstring; handles domain base behavior. |
| 1542 | 1551 | method | `EditorDataModel.domain_stride` | `domain_stride(self, domain: str) -> int` | — | No docstring; handles domain stride behavior. |
| 1553 | 1554 | method | `EditorDataModel.record_address` | `record_address(self, domain: str, index: int) -> int` | — | No docstring; handles record address behavior. |
| 1556 | 1566 | method | `EditorDataModel._field_version_payload` | `_field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles field version payload behavior. |
| 1568 | 1569 | method | `EditorDataModel._field_offset` | `_field_offset(self, field: dict[str, Any]) -> int` | — | No docstring; handles field offset behavior. |
| 1571 | 1586 | method | `EditorDataModel.read_value` | `read_value(self, domain: str, *, index: int, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles read value behavior. |
| 1588 | 1602 | method | `EditorDataModel.write_value` | `write_value(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> None` | — | No docstring; handles write value behavior. |
| 1604 | 1606 | method | `EditorDataModel.write_and_readback` | `write_and_readback(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> dict[str, Any]` | — | No docstring; handles write and readback behavior. |
| 1609 | 1643 | function | `verify_edits` | `verify_edits(*, target_executable: str \| None=None) -> dict[str, Any]` | — | No docstring; handles verify edits behavior. |

### `ui/__init__.py`

_No function definitions._

### `ui/dpg_editor.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 146 | 147 | function | `_tag` | `_tag(*parts: object) -> str` | — | No docstring; handles tag behavior. |
| 150 | 152 | function | `_target_executable` | `_target_executable(label: str) -> str` | — | No docstring; handles target executable behavior. |
| 155 | 157 | function | `_parse_id_prefixed_option` | `_parse_id_prefixed_option(value: object) -> int \| None` | — | No docstring; handles parse id prefixed option behavior. |
| 161 | 176 | method | `DpgEditorApp.__init__` | `__init__(self, model: EditorDataModel) -> None` | — | No docstring; handles init behavior. |
| 178 | 179 | method | `DpgEditorApp._screen_tag` | `_screen_tag(self, domain: str) -> str` | — | No docstring; handles screen tag behavior. |
| 181 | 182 | method | `DpgEditorApp._app_screen_tag` | `_app_screen_tag(self, screen: str) -> str` | — | No docstring; handles app screen tag behavior. |
| 184 | 185 | method | `DpgEditorApp._home_status_tag` | `_home_status_tag(self) -> str` | — | No docstring; handles home status tag behavior. |
| 187 | 188 | method | `DpgEditorApp._home_target_status_tag` | `_home_target_status_tag(self) -> str` | — | No docstring; handles home target status tag behavior. |
| 190 | 191 | method | `DpgEditorApp._status_tag` | `_status_tag(self, domain: str) -> str` | — | No docstring; handles status tag behavior. |
| 193 | 194 | method | `DpgEditorApp._count_tag` | `_count_tag(self, domain: str) -> str` | — | No docstring; handles count tag behavior. |
| 196 | 197 | method | `DpgEditorApp._list_tag` | `_list_tag(self, domain: str) -> str` | — | No docstring; handles list tag behavior. |
| 199 | 200 | method | `DpgEditorApp._player_team_filter_tag` | `_player_team_filter_tag(self) -> str` | — | No docstring; handles player team filter tag behavior. |
| 202 | 203 | method | `DpgEditorApp._player_search_tag` | `_player_search_tag(self) -> str` | — | No docstring; handles player search tag behavior. |
| 205 | 206 | method | `DpgEditorApp._record_list_rows_for_height` | `_record_list_rows_for_height(self, viewport_height: int) -> int` | — | No docstring; handles record list rows for height behavior. |
| 208 | 214 | method | `DpgEditorApp._resize_record_lists` | `_resize_record_lists(self, dpg: Any) -> None` | — | No docstring; handles resize record lists behavior. |
| 216 | 217 | method | `DpgEditorApp._detail_tag` | `_detail_tag(self, domain: str, name: str) -> str` | — | No docstring; handles detail tag behavior. |
| 219 | 220 | method | `DpgEditorApp._preview_tag` | `_preview_tag(self, domain: str, row: int, label: str) -> str` | — | No docstring; handles preview tag behavior. |
| 222 | 223 | method | `DpgEditorApp._record_card_tag` | `_record_card_tag(self, row: int) -> str` | — | No docstring; handles record card tag behavior. |
| 225 | 226 | method | `DpgEditorApp._record_cards_container_tag` | `_record_cards_container_tag(self) -> str` | — | No docstring; handles record cards container tag behavior. |
| 228 | 229 | method | `DpgEditorApp._record_career_table_tag` | `_record_career_table_tag(self) -> str` | — | No docstring; handles record career table tag behavior. |
| 231 | 232 | method | `DpgEditorApp._record_career_cell_tag` | `_record_career_cell_tag(self, row: int, label: str) -> str` | — | No docstring; handles record career cell tag behavior. |
| 234 | 235 | method | `DpgEditorApp._record_stat_group_tag` | `_record_stat_group_tag(self, section: str) -> str` | — | No docstring; handles record stat group tag behavior. |
| 237 | 238 | method | `DpgEditorApp._history_tab_group_tag` | `_history_tab_group_tag(self, section: str) -> str` | — | No docstring; handles history tab group tag behavior. |
| 240 | 241 | method | `DpgEditorApp._history_table_group_tag` | `_history_table_group_tag(self, section: str) -> str` | — | No docstring; handles history table group tag behavior. |
| 243 | 244 | method | `DpgEditorApp._history_table_content_tag` | `_history_table_content_tag(self, section: str) -> str` | — | No docstring; handles history table content tag behavior. |
| 246 | 247 | method | `DpgEditorApp._history_preview_tag` | `_history_preview_tag(self, section: str, row: int, label: str) -> str` | — | No docstring; handles history preview tag behavior. |
| 249 | 250 | method | `DpgEditorApp._record_card_title_tag` | `_record_card_title_tag(self, row: int) -> str` | — | No docstring; handles record card title tag behavior. |
| 252 | 253 | method | `DpgEditorApp._heading_tag` | `_heading_tag(self, domain: str) -> str` | — | No docstring; handles heading tag behavior. |
| 255 | 256 | method | `DpgEditorApp._team_input_tag` | `_team_input_tag(self, label: str) -> str` | — | No docstring; handles team input tag behavior. |
| 258 | 259 | method | `DpgEditorApp._nav_tag` | `_nav_tag(self, screen: str) -> str` | — | No docstring; handles nav tag behavior. |
| 261 | 262 | method | `DpgEditorApp._display_label` | `_display_label(self, domain: str) -> str` | — | No docstring; handles display label behavior. |
| 264 | 265 | method | `DpgEditorApp._game_status_text` | `_game_status_text(self) -> str` | — | No docstring; handles game status text behavior. |
| 267 | 269 | method | `DpgEditorApp._safe_set` | `_safe_set(self, dpg: Any, tag: str, value: object) -> None` | — | No docstring; handles safe set behavior. |
| 271 | 273 | method | `DpgEditorApp._safe_configure` | `_safe_configure(self, dpg: Any, tag: str, **kwargs: object) -> None` | — | No docstring; handles safe configure behavior. |
| 275 | 277 | method | `DpgEditorApp._safe_delete_children` | `_safe_delete_children(self, dpg: Any, tag: str) -> None` | — | No docstring; handles safe delete children behavior. |
| 279 | 281 | method | `DpgEditorApp._bind_item_theme` | `_bind_item_theme(self, dpg: Any, item: str, theme: str) -> None` | — | No docstring; handles bind item theme behavior. |
| 283 | 286 | method | `DpgEditorApp._refresh_nav_state` | `_refresh_nav_state(self, dpg: Any) -> None` | — | No docstring; handles refresh nav state behavior. |
| 288 | 294 | method | `DpgEditorApp._show_screen` | `_show_screen(self, dpg: Any, domain: str) -> None` | — | No docstring; handles show screen behavior. |
| 296 | 300 | method | `DpgEditorApp._set_target` | `_set_target(self, dpg: Any, selected: str) -> None` | — | No docstring; handles set target behavior. |
| 302 | 308 | method | `DpgEditorApp._refresh_status_labels` | `_refresh_status_labels(self, dpg: Any) -> None` | — | No docstring; handles refresh status labels behavior. |
| 310 | 312 | method | `DpgEditorApp._attach` | `_attach(self, dpg: Any) -> None` | — | No docstring; handles attach behavior. |
| 314 | 315 | method | `DpgEditorApp._attach_and_scan` | `_attach_and_scan(self, dpg: Any, domain: str) -> None` | — | No docstring; handles attach and scan behavior. |
| 317 | 318 | method | `DpgEditorApp._attach_and_load_all` | `_attach_and_load_all(self, dpg: Any) -> None` | — | No docstring; handles attach and load all behavior. |
| 320 | 326 | method | `DpgEditorApp._start_background_scan` | `_start_background_scan(self, dpg: Any, domains: tuple[str, ...]) -> None` | — | No docstring; handles start background scan behavior. |
| 328 | 341 | method | `DpgEditorApp._poll_background_scan` | `_poll_background_scan(self, dpg: Any) -> None` | — | No docstring; handles poll background scan behavior. |
| 343 | 359 | method | `DpgEditorApp._sync_domain_list` | `_sync_domain_list(self, dpg: Any, domain: str) -> None` | — | No docstring; handles sync domain list behavior. |
| 361 | 366 | method | `DpgEditorApp._sync_player_team_filter` | `_sync_player_team_filter(self, dpg: Any) -> None` | — | No docstring; handles sync player team filter behavior. |
| 368 | 388 | method | `DpgEditorApp._sync_player_list` | `_sync_player_list(self, dpg: Any) -> None` | — | No docstring; handles sync player list behavior. |
| 390 | 392 | method | `DpgEditorApp._set_player_team_filter` | `_set_player_team_filter(self, dpg: Any, selected: str \| None) -> None` | — | No docstring; handles set player team filter behavior. |
| 394 | 396 | method | `DpgEditorApp._set_player_search_text` | `_set_player_search_text(self, dpg: Any, search_text: str \| None) -> None` | — | No docstring; handles set player search text behavior. |
| 398 | 438 | method | `DpgEditorApp._sync_record_preview` | `_sync_record_preview(self, dpg: Any, domain: str) -> None` | — | No docstring; handles sync record preview behavior. |
| 440 | 450 | method | `DpgEditorApp._render_history_table` | `_render_history_table(self, dpg: Any, section: str, labels: tuple[str, ...], rows: list[dict[str, str]]) -> None` | — | No docstring; handles render history table behavior. |
| 452 | 457 | method | `DpgEditorApp._history_cell_value` | `_history_cell_value(self, row_values: dict[str, str], label: str) -> str` | — | No docstring; handles history cell value behavior. |
| 459 | 464 | method | `DpgEditorApp._active_history_type` | `_active_history_type(self) -> int \| None` | — | No docstring; handles active history type behavior. |
| 466 | 470 | method | `DpgEditorApp._active_record_row_group` | `_active_record_row_group(self) -> tuple[int, int]` | — | No docstring; handles active record row group behavior. |
| 472 | 475 | method | `DpgEditorApp._set_history_section` | `_set_history_section(self, dpg: Any, label: str) -> None` | — | No docstring; handles set history section behavior. |
| 477 | 481 | method | `DpgEditorApp._set_history_tab` | `_set_history_tab(self, dpg: Any, label: str) -> None` | — | No docstring; handles set history tab behavior. |
| 483 | 485 | method | `DpgEditorApp._set_history_award` | `_set_history_award(self, dpg: Any, label: str) -> None` | — | No docstring; handles set history award behavior. |
| 487 | 493 | method | `DpgEditorApp._set_record_section` | `_set_record_section(self, dpg: Any, label: str) -> None` | — | No docstring; handles set record section behavior. |
| 495 | 498 | method | `DpgEditorApp._set_record_stat` | `_set_record_stat(self, dpg: Any, label: str) -> None` | — | No docstring; handles set record stat behavior. |
| 500 | 503 | method | `DpgEditorApp._select_current` | `_select_current(self, dpg: Any, domain: str, selected_label: str \| None=None) -> None` | — | No docstring; handles select current behavior. |
| 505 | 510 | method | `DpgEditorApp._open_selected` | `_open_selected(self, dpg: Any, domain: str) -> None` | — | No docstring; handles open selected behavior. |
| 512 | 529 | method | `DpgEditorApp._update_detail_panel` | `_update_detail_panel(self, dpg: Any, domain: str) -> None` | — | No docstring; handles update detail panel behavior. |
| 531 | 538 | method | `DpgEditorApp._save_team_summary` | `_save_team_summary(self, dpg: Any) -> None` | — | No docstring; handles save team summary behavior. |
| 540 | 541 | method | `DpgEditorApp._row_current_tag` | `_row_current_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row current tag behavior. |
| 543 | 544 | method | `DpgEditorApp._row_new_tag` | `_row_new_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row new tag behavior. |
| 546 | 547 | method | `DpgEditorApp._row_status_tag` | `_row_status_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row status tag behavior. |
| 549 | 550 | method | `DpgEditorApp._editor_status_tag` | `_editor_status_tag(self, item: RecordListItem) -> str` | — | No docstring; handles editor status tag behavior. |
| 552 | 553 | method | `DpgEditorApp._season_stat_selector_key` | `_season_stat_selector_key(self, item: RecordListItem) -> tuple[int, str]` | — | No docstring; handles season stat selector key behavior. |
| 555 | 556 | method | `DpgEditorApp._season_stat_selector_tag` | `_season_stat_selector_tag(self, item: RecordListItem) -> str` | — | No docstring; handles season stat selector tag behavior. |
| 558 | 564 | method | `DpgEditorApp._selected_season_stat_selector` | `_selected_season_stat_selector(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> str \| None` | — | No docstring; handles selected season stat selector behavior. |
| 566 | 570 | method | `DpgEditorApp._set_player_season_stat_id` | `_set_player_season_stat_id(self, dpg: Any, item: RecordListItem, selected: str \| None) -> None` | — | No docstring; handles set player season stat id behavior. |
| 572 | 573 | method | `DpgEditorApp._read_editor_entry_value` | `_read_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> dict[str, Any]` | — | No docstring; handles read editor entry value behavior. |
| 575 | 576 | method | `DpgEditorApp._write_editor_entry_value` | `_write_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry, value: str) -> dict[str, Any]` | — | No docstring; handles write editor entry value behavior. |
| 578 | 598 | method | `DpgEditorApp._load_item_editor` | `_load_item_editor(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles load item editor behavior. |
| 600 | 622 | method | `DpgEditorApp._save_item_editor` | `_save_item_editor(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles save item editor behavior. |
| 624 | 687 | method | `DpgEditorApp._open_editor_window` | `_open_editor_window(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles open editor window behavior. |
| 630 | 631 | nested function | `DpgEditorApp._open_editor_window.options_for` | `options_for(entry: FieldEntry) -> list[str]` | — | No docstring; handles options for behavior. |
| 633 | 650 | nested function | `DpgEditorApp._open_editor_window.render_table` | `render_table(render_entries: list[FieldEntry]) -> None` | — | No docstring; handles render table behavior. |
| 654 | 654 | lambda | `DpgEditorApp._open_editor_window.<lambda#1>` | `<lambda#1>(*_args, i=item)` | — | Lambda expression. |
| 655 | 655 | lambda | `DpgEditorApp._open_editor_window.<lambda#2>` | `<lambda#2>(*_args, i=item)` | — | Lambda expression. |
| 678 | 678 | lambda | `DpgEditorApp._open_editor_window.<lambda#3>` | `<lambda#3>(_s, app_data, _u=None, *args, i=item)` | — | Lambda expression. |
| 689 | 693 | method | `DpgEditorApp._add_nav_button` | `_add_nav_button(self, dpg: Any, screen: str, label: str) -> None` | — | No docstring; handles add nav button behavior. |
| 692 | 692 | lambda | `DpgEditorApp._add_nav_button.<lambda#4>` | `<lambda#4>(*_args, s=screen)` | — | Lambda expression. |
| 695 | 701 | method | `DpgEditorApp._add_detail_row` | `_add_detail_row(self, dpg: Any, label: str, value_tag: str, *, accent: bool=False) -> None` | — | No docstring; handles add detail row behavior. |
| 703 | 719 | method | `DpgEditorApp._build_home_screen` | `_build_home_screen(self, dpg: Any, *, show: bool=True) -> None` | — | No docstring; handles build home screen behavior. |
| 708 | 708 | lambda | `DpgEditorApp._build_home_screen.<lambda#5>` | `<lambda#5>(_s, app_data, _u)` | — | Lambda expression. |
| 712 | 712 | lambda | `DpgEditorApp._build_home_screen.<lambda#6>` | `<lambda#6>(*_args)` | — | Lambda expression. |
| 721 | 757 | method | `DpgEditorApp._build_players_screen` | `_build_players_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build players screen behavior. |
| 725 | 725 | lambda | `DpgEditorApp._build_players_screen.<lambda#7>` | `<lambda#7>(*_args)` | — | Lambda expression. |
| 736 | 736 | lambda | `DpgEditorApp._build_players_screen.<lambda#8>` | `<lambda#8>(_s, app_data, _u=None, *args)` | — | Lambda expression. |
| 744 | 744 | lambda | `DpgEditorApp._build_players_screen.<lambda#9>` | `<lambda#9>(_s, app_data, _u=None, *args)` | — | Lambda expression. |
| 749 | 749 | lambda | `DpgEditorApp._build_players_screen.<lambda#10>` | `<lambda#10>(_s, app_data, _u=None, *_, d=domain)` | — | Lambda expression. |
| 757 | 757 | lambda | `DpgEditorApp._build_players_screen.<lambda#11>` | `<lambda#11>(*_args)` | — | Lambda expression. |
| 759 | 785 | method | `DpgEditorApp._build_teams_screen` | `_build_teams_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build teams screen behavior. |
| 763 | 763 | lambda | `DpgEditorApp._build_teams_screen.<lambda#12>` | `<lambda#12>(*_args)` | — | Lambda expression. |
| 771 | 771 | lambda | `DpgEditorApp._build_teams_screen.<lambda#13>` | `<lambda#13>(_s, app_data, _u=None, *_, d=domain)` | — | Lambda expression. |
| 784 | 784 | lambda | `DpgEditorApp._build_teams_screen.<lambda#14>` | `<lambda#14>(*_args)` | — | Lambda expression. |
| 785 | 785 | lambda | `DpgEditorApp._build_teams_screen.<lambda#15>` | `<lambda#15>(*_args)` | — | Lambda expression. |
| 787 | 792 | method | `DpgEditorApp._record_screen_heading` | `_record_screen_heading(self, domain: str) -> str` | — | No docstring; handles record screen heading behavior. |
| 794 | 799 | method | `DpgEditorApp._add_button_strip` | `_add_button_strip(self, dpg: Any, labels: tuple[str, ...], *, per_row: int, callback: Any \| None=None) -> None` | — | No docstring; handles add button strip behavior. |
| 798 | 798 | lambda | `DpgEditorApp._add_button_strip.<lambda#16>` | `<lambda#16>(*_args, selected=label)` | — | Lambda expression. |
| 801 | 825 | method | `DpgEditorApp._build_history_screen` | `_build_history_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build history screen behavior. |
| 806 | 806 | lambda | `DpgEditorApp._build_history_screen.<lambda#17>` | `<lambda#17>(*_args)` | — | Lambda expression. |
| 809 | 809 | lambda | `DpgEditorApp._build_history_screen.<lambda#18>` | `<lambda#18>(*_args, selected=label)` | — | Lambda expression. |
| 816 | 816 | lambda | `DpgEditorApp._build_history_screen.<lambda#19>` | `<lambda#19>(selected)` | — | Lambda expression. |
| 827 | 869 | method | `DpgEditorApp._build_records_screen` | `_build_records_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build records screen behavior. |
| 832 | 832 | lambda | `DpgEditorApp._build_records_screen.<lambda#20>` | `<lambda#20>(*_args)` | — | Lambda expression. |
| 835 | 835 | lambda | `DpgEditorApp._build_records_screen.<lambda#21>` | `<lambda#21>(*_args, selected=label)` | — | Lambda expression. |
| 842 | 842 | lambda | `DpgEditorApp._build_records_screen.<lambda#22>` | `<lambda#22>(selected)` | — | Lambda expression. |
| 871 | 875 | method | `DpgEditorApp._build_history_or_records_screen` | `_build_history_or_records_screen(self, dpg: Any, domain: str, *, show: bool=False) -> None` | — | No docstring; handles build history or records screen behavior. |
| 877 | 905 | method | `DpgEditorApp._build_domain_screen` | `_build_domain_screen(self, dpg: Any, domain: str, *, show: bool=False) -> None` | — | No docstring; handles build domain screen behavior. |
| 890 | 890 | lambda | `DpgEditorApp._build_domain_screen.<lambda#23>` | `<lambda#23>(*_args, d=domain)` | — | Lambda expression. |
| 898 | 898 | lambda | `DpgEditorApp._build_domain_screen.<lambda#24>` | `<lambda#24>(_s, app_data, _u=None, *_, d=domain)` | — | Lambda expression. |
| 905 | 905 | lambda | `DpgEditorApp._build_domain_screen.<lambda#25>` | `<lambda#25>(*_args, d=domain)` | — | Lambda expression. |
| 907 | 955 | method | `DpgEditorApp.run` | `run(self, *, close_after_frames: int \| None=None, load_on_start: bool=True) -> None` | — | No docstring; handles run behavior. |

### `ui/theme.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 30 | 37 | function | `to_rgba` | `to_rgba(hex_color: str, alpha: int=255) -> tuple[int, int, int, int]` | — | Convert exact '#RRGGBB' hex to an RGBA tuple. |
| 40 | 124 | function | `apply_base_theme` | `apply_base_theme() -> str` | — | Create and bind the base Dear PyGui theme. |
| 127 | 159 | function | `ensure_editor_themes` | `ensure_editor_themes() -> dict[str, str]` | — | Create reusable item themes for the compact editor shell. |
