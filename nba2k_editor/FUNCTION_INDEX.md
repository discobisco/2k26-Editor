# NBA2K Editor Function Index

AST-generated index of every Python callable definition inside `nba2k_editor/` only.

- Python files scanned: 19
- Files with named function definitions: 12
- Named functions/methods listed: 293
- Lambda expressions listed: 26
- Total callable definitions listed: 319
- Direct methods listed: 190
- Nested named functions listed: 2
- Scope: all `*.py` files below `nba2k_editor/`, including nested functions and lambda expressions; excludes only cache folders.
- Out of scope: every file outside `nba2k_editor/`.
- Purpose: ownership map so new work checks existing behavior before adding another function under a different name.

## Package owner map from `__init__.py`

| Package | Declared owner lane | Source |
|---|---|---|
| `nba2k_editor` | NBA 2K26 editor package scaffold. This package will host the modularized code currently in ``2k26Editor.py``. | `nba2k_editor/__init__.py` |
| `nba2k_editor.core` | Core utilities: configuration, logging, conversions, offsets, and extensions. | `core/__init__.py` |
| `nba2k_editor.entrypoints` | Executable entrypoints for the modular editor. | `entrypoints/__init__.py` |
| `nba2k_editor.memory` | Memory access layer (Win32 bindings and process helpers). | `memory/__init__.py` |
| `nba2k_editor.models` | Data models for players, schemas, and roster metadata. | `models/__init__.py` |
| `nba2k_editor.ui` | UI layer for the Dear PyGui-based editor. | `ui/__init__.py` |

## Cleanup baseline after current pass

- AST-normalized exact duplicate function bodies: 0
- Definition-only private functions by textual reference scan: 0
- Removed stale definition-only functions, unused imports, UI fallback wrappers, and memory capability probes after live-code reference checks.

## Functions by file

### `__init__.py`

_No callable definitions._

### `__main__.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 10 | 15 | function | `build_parser` | `build_parser() -> argparse.ArgumentParser` | — | No docstring; handles build parser behavior. |
| 18 | 24 | function | `main` | `main(argv: Sequence[str] \| None=None) -> int` | — | No docstring; handles main behavior. |

### `core/__init__.py`

_No callable definitions._

### `core/addressing.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 8 | 14 | function | `record_address` | `record_address(*, base: int, index: int, stride: int) -> int` | — | Return the absolute record address for a zero-based record number. |
| 17 | 44 | function | `resolve_base_pointer_entry` | `resolve_base_pointer_entry(memory: Any, base_entry: dict[str, Any], *, label: str, apply_final_offset_without_module_base: bool=True, follow_chain: bool=True) -> int` | — | No docstring; handles resolve base pointer entry behavior. |

### `core/conversions.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 25 | 26 | function | `_normalize_year_key` | `_normalize_year_key(value: str) -> str` | — | No docstring; handles normalize year key behavior. |
| 29 | 31 | function | `parse_id_prefixed_option` | `parse_id_prefixed_option(value: Any) -> int \| None` | — | No docstring; handles parse id prefixed option behavior. |
| 34 | 51 | function | `is_year_offset_field` | `is_year_offset_field(field_name: str) -> bool` | — | Return True if a field name should be treated as a year offset from YEAR_BASE. |
| 54 | 65 | function | `convert_raw_to_year` | `convert_raw_to_year(raw: int, base_year: int=YEAR_BASE) -> int` | — | Convert a stored year offset into a calendar year. |
| 68 | 80 | function | `convert_year_to_raw` | `convert_year_to_raw(year: int, base_year: int=YEAR_BASE) -> int` | — | Convert a calendar year into its stored offset. |
| 93 | 108 | function | `convert_raw_to_rating` | `convert_raw_to_rating(raw: int, length: int) -> int` | — | Convert a raw bitfield value into the 25-99 display rating scale using proportional mapping. |
| 111 | 132 | function | `convert_rating_to_raw` | `convert_rating_to_raw(rating: float, length: int) -> int` | — | Convert a 25-99 rating back into a raw bitfield value using proportional mapping. |
| 135 | 141 | function | `convert_potential_to_raw` | `convert_potential_to_raw(rating: float, length: int \| None=None, minimum: float=40.0, maximum: float=99.0) -> int` | — | Convert Potential display ratings into raw values, bounded to the 40-99 display scale. |
| 144 | 153 | function | `convert_raw_to_potential` | `convert_raw_to_potential(raw: int, length: int \| None=None, minimum: float=40.0, maximum: float=99.0) -> int` | — | Convert raw Potential values through the rating curve, bounded to 40-99. |
| 156 | 158 | function | `convert_minmax_potential_to_raw` | `convert_minmax_potential_to_raw(rating: float, length: int, minimum: float=0.0, maximum: float=100.0) -> int` | — | Convert Min/Max/Average potential-like display values on the 0-100 scale into raw values. |
| 161 | 163 | function | `convert_raw_to_minmax_potential` | `convert_raw_to_minmax_potential(raw: int, length: int, minimum: float=0.0, maximum: float=100.0) -> int` | — | Convert Min/Max/Average potential-like raw values into the 0-100 display scale. |
| 166 | 172 | function | `convert_raw_to_body_scale_display` | `convert_raw_to_body_scale_display(raw: object, length: int=0) -> int` | — | Convert body scale raw float storage into the 0-100 editor display scale. |
| 175 | 177 | function | `convert_body_scale_display_to_raw` | `convert_body_scale_display_to_raw(display_value: object, length: int=0) -> float` | — | Convert body scale 0-100 display values into raw float storage. |
| 180 | 186 | function | `convert_raw_to_injury_duration_days` | `convert_raw_to_injury_duration_days(raw: int, maximum_days: int=450) -> int` | — | Convert player injury duration storage into displayed days, ignoring high status flag bits. |
| 189 | 196 | function | `convert_injury_duration_days_to_raw` | `convert_injury_duration_days_to_raw(days: float, maximum_days: int=450) -> int` | — | Convert displayed injury duration days into low duration ticks, clamped to the editor range. |
| 199 | 212 | function | `normalize_weight_value` | `normalize_weight_value(value: object) -> float \| None` | — | Parse editor input into a supported weight value in pounds. |
| 215 | 220 | function | `convert_pounds_to_kilograms` | `convert_pounds_to_kilograms(pounds: object) -> float` | — | Convert pounds to kilograms. |
| 223 | 228 | function | `convert_kilograms_to_pounds` | `convert_kilograms_to_pounds(kilograms: object) -> float` | — | Convert kilograms to pounds. |
| 231 | 237 | function | `raw_height_to_inches` | `raw_height_to_inches(raw_val: int) -> int` | — | Convert raw stored height (inches * 254) to inches. |
| 240 | 250 | function | `clamp_height_inches` | `clamp_height_inches(inches: int) -> int` | — | Clamp a height value to the supported player-editor range. |
| 253 | 259 | function | `height_inches_to_raw` | `height_inches_to_raw(inches: int) -> int` | — | Convert inches to raw stored height (inches * 254). |
| 262 | 270 | function | `format_height_inches` | `format_height_inches(inches: int) -> str` | — | Format inches as feet/inches for display. |
| 273 | 283 | function | `convert_tendency_raw_to_rating` | `convert_tendency_raw_to_rating(raw: int, length: int) -> int` | — | Convert a raw bitfield value into a 0-100 tendency rating. |
| 286 | 296 | function | `convert_rating_to_tendency_raw` | `convert_rating_to_tendency_raw(rating: float, length: int) -> int` | — | Convert a 0-100 tendency rating into a raw bitfield value. |
| 299 | 309 | function | `player_numeric_bounds` | `player_numeric_bounds(category_name: str, field_name: str, length_bits: int) -> tuple[int, int]` | — | No docstring; handles player numeric bounds behavior. |
| 312 | 326 | function | `to_int` | `to_int(value: Any) -> int` | — | Convert strings or numeric values to an integer, accepting hex strings. |

### `core/field_io.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 76 | 79 | function | `_field_offset` | `_field_offset(payload: dict[str, Any]) -> int` | — | No docstring; handles field offset behavior. |
| 82 | 83 | function | `_type_key` | `_type_key(payload: dict[str, Any]) -> str` | — | No docstring; handles type key behavior. |
| 86 | 115 | function | `_implemented_payload` | `_implemented_payload(payload: dict[str, Any]) -> bool` | — | No docstring; handles implemented payload behavior. |
| 118 | 121 | function | `_readable_payload` | `_readable_payload(payload: dict[str, Any]) -> bool` | — | No docstring; handles readable payload behavior. |
| 124 | 125 | function | `_bits_to_bytes` | `_bits_to_bytes(bits: int) -> int` | — | No docstring; handles bits to bytes behavior. |
| 128 | 147 | function | `_numeric_width` | `_numeric_width(payload: dict[str, Any]) -> int` | — | No docstring; handles numeric width behavior. |
| 150 | 156 | function | `_bit_window` | `_bit_window(payload: dict[str, Any]) -> tuple[int, int, int]` | — | No docstring; handles bit window behavior. |
| 159 | 165 | function | `_read_pointer_value` | `_read_pointer_value(memory: Any, address: int) -> int` | — | No docstring; handles read pointer value behavior. |
| 168 | 182 | function | `_field_address` | `_field_address(memory: Any, record_addr: int, payload: dict[str, Any], *, parent_payload: dict[str, Any] \| None=None) -> int` | — | No docstring; handles field address behavior. |
| 185 | 189 | function | `_read_bitfield` | `_read_bitfield(memory: Any, address: int, payload: dict[str, Any]) -> int` | — | No docstring; handles read bitfield behavior. |
| 192 | 197 | function | `_write_bitfield` | `_write_bitfield(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write bitfield behavior. |
| 200 | 205 | function | `_uses_bitfield_io` | `_uses_bitfield_io(payload: dict[str, Any]) -> bool` | — | No docstring; handles uses bitfield io behavior. |
| 208 | 217 | function | `_list_mapping_value` | `_list_mapping_value(raw_value: Any, options: object) -> Any \| None` | — | No docstring; handles list mapping value behavior. |
| 220 | 227 | function | `_reverse_list_mapping` | `_reverse_list_mapping(value: Any, options: object) -> int \| None` | — | No docstring; handles reverse list mapping behavior. |
| 230 | 246 | function | `_mapped_display_value` | `_mapped_display_value(payload: dict[str, Any], raw_value: Any) -> Any \| None` | — | No docstring; handles mapped display value behavior. |
| 249 | 262 | function | `_mapped_raw_value` | `_mapped_raw_value(payload: dict[str, Any], value: Any) -> Any \| None` | — | No docstring; handles mapped raw value behavior. |
| 265 | 267 | function | `_id_prefixed_option` | `_id_prefixed_option(raw_id: int, label: str) -> str` | — | No docstring; handles id prefixed option behavior. |
| 270 | 309 | function | `_raw_to_display_value` | `_raw_to_display_value(section: str, field: dict[str, Any], payload: dict[str, Any], raw_value: Any) -> Any` | — | No docstring; handles raw to display value behavior. |
| 312 | 354 | function | `_display_to_raw_value` | `_display_to_raw_value(section: str, field: dict[str, Any], payload: dict[str, Any], value: Any) -> Any` | — | No docstring; handles display to raw value behavior. |
| 357 | 361 | function | `_string_length` | `_string_length(payload: dict[str, Any]) -> int` | — | No docstring; handles string length behavior. |
| 364 | 368 | function | `_read_string` | `_read_string(memory: Any, address: int, payload: dict[str, Any]) -> str` | — | No docstring; handles read string behavior. |
| 371 | 379 | function | `_write_string` | `_write_string(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write string behavior. |
| 382 | 388 | function | `_read_ptr_string` | `_read_ptr_string(memory: Any, address: int, payload: dict[str, Any]) -> str` | — | No docstring; handles read ptr string behavior. |
| 391 | 397 | function | `_result_score_addresses` | `_result_score_addresses(address: int, payload: dict[str, Any]) -> tuple[int, int]` | — | No docstring; handles result score addresses behavior. |
| 400 | 402 | function | `_coerce_result_component` | `_coerce_result_component(value: float) -> int \| float` | — | No docstring; handles coerce result component behavior. |
| 405 | 409 | function | `_read_result_score` | `_read_result_score(memory: Any, address: int, payload: dict[str, Any]) -> tuple[int \| float, int \| float]` | — | No docstring; handles read result score behavior. |
| 412 | 420 | function | `_parse_result_score` | `_parse_result_score(value: Any) -> tuple[float, float]` | — | No docstring; handles parse result score behavior. |
| 423 | 426 | function | `_format_result_component` | `_format_result_component(value: int \| float) -> str` | — | No docstring; handles format result component behavior. |
| 429 | 430 | function | `_format_result_score` | `_format_result_score(value: tuple[int \| float, int \| float]) -> str` | — | No docstring; handles format result score behavior. |
| 433 | 434 | function | `_color_hex` | `_color_hex(raw_value: bytes) -> str` | — | No docstring; handles color hex behavior. |
| 437 | 448 | function | `_parse_color_value` | `_parse_color_value(value: Any, width: int) -> bytes` | — | No docstring; handles parse color value behavior. |
| 451 | 491 | function | `_read_authored_value` | `_read_authored_value(memory: Any, address: int, payload: dict[str, Any]) -> Any` | — | No docstring; handles read authored value behavior. |
| 494 | 539 | function | `_write_authored_value` | `_write_authored_value(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | — | No docstring; handles write authored value behavior. |

### `core/offsets.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 254 | 259 | function | `_split_version_tokens` | `_split_version_tokens(raw_key: object) -> tuple[str, ...]` | — | No docstring; handles split version tokens behavior. |
| 262 | 269 | function | `_version_key_matches` | `_version_key_matches(raw_key: object, target_label: str \| None) -> bool` | — | No docstring; handles version key matches behavior. |
| 272 | 282 | function | `_select_active_version` | `_select_active_version(versions_map: dict[str, object], target_executable: str \| None, *, require_hint: bool=False) -> tuple[str, str, dict[str, object]] \| None` | — | No docstring; handles select active version behavior. |
| 285 | 295 | function | `_resolved_length_bits` | `_resolved_length_bits(version_payload: dict[str, object]) -> int` | — | No docstring; handles resolved length bits behavior. |
| 298 | 343 | function | `get_editor_layout_for_super` | `get_editor_layout_for_super(super_type: str) -> dict[str, object]` | — | Return the owning offsets file's authored structure directly. |
| 346 | 348 | function | `_load_offsets_resource` | `_load_offsets_resource(file_name: str) -> dict[str, object]` | — | No docstring; handles load offsets resource behavior. |
| 351 | 371 | function | `_load_league_offset_config` | `_load_league_offset_config(target_executable: str \| None=None) -> dict[str, object]` | — | Load the authored league offsets resource only. |
| 374 | 377 | function | `get_active_offset_config` | `get_active_offset_config(target_executable: str \| None=None) -> dict[str, object]` | — | No docstring; handles get active offset config behavior. |
| 380 | 385 | function | `_derive_version_label` | `_derive_version_label(executable: str \| None) -> str` | — | No docstring; handles derive version label behavior. |
| 388 | 401 | function | `_resolve_version_context` | `_resolve_version_context(data: dict[str, Any] \| None, target_executable: str \| None) -> tuple[str, dict[str, Any], dict[str, Any]]` | — | No docstring; handles resolve version context behavior. |
| 405 | 412 | function | `_normalize_chain_steps` | `_normalize_chain_steps(chain_data: list[dict[str, object]]) -> list[dict[str, object]]` | — | No docstring; handles normalize chain steps behavior. |
| 415 | 427 | function | `_parse_pointer_chain_config` | `_parse_pointer_chain_config(base_cfg: dict[str, object]) -> list[dict[str, object]]` | — | No docstring; handles parse pointer chain config behavior. |
| 430 | 487 | function | `_apply_offset_config` | `_apply_offset_config(data: dict \| None, target_executable: str \| None=None) -> None` | — | Update module-level constants using the loaded offset data. |
| 490 | 491 | function | `has_active_config` | `has_active_config() -> bool` | — | No docstring; handles has active config behavior. |
| 494 | 495 | function | `get_current_target` | `get_current_target() -> str` | — | No docstring; handles get current target behavior. |
| 498 | 511 | function | `initialize_offsets` | `initialize_offsets(target_executable: str \| None=None, force: bool=False) -> None` | — | Ensure embedded offset data for the requested executable is loaded. |

### `entrypoints/__init__.py`

_No callable definitions._

### `entrypoints/gui.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 11 | 18 | function | `build_parser` | `build_parser() -> argparse.ArgumentParser` | — | No docstring; handles build parser behavior. |
| 21 | 27 | function | `main` | `main(argv: Sequence[str] \| None=None) -> int` | — | No docstring; handles main behavior. |

### `entrypoints/runtime_cleanup.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 12 | 28 | function | `delete_runtime_cache_dirs` | `delete_runtime_cache_dirs(root: Path \| None=None) -> tuple[int, int]` | — | No docstring; handles delete runtime cache dirs behavior. |

### `memory/__init__.py`

_No callable definitions._

### `memory/game_memory.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 35 | 40 | method | `GameMemory.__init__` | `__init__(self, module_name: str=MODULE_NAME)` | — | No docstring; handles init behavior. |
| 42 | 80 | method | `GameMemory._detect_pointer_size` | `_detect_pointer_size(self, handle: wintypes.HANDLE \| None) -> int` | — | No docstring; handles detect pointer size behavior. |
| 86 | 108 | method | `GameMemory.detect_running_module_name` | `detect_running_module_name(preferred_module: str \| None=None) -> str \| None` | staticmethod | No docstring; handles detect running module name behavior. |
| 110 | 121 | method | `GameMemory.find_pid` | `find_pid(self) -> int \| None` | — | No docstring; handles find pid behavior. |
| 123 | 148 | method | `GameMemory.open_process` | `open_process(self) -> bool` | — | Open the game process and resolve its base address. |
| 150 | 160 | method | `GameMemory.close` | `close(self) -> None` | — | Close any open process handle and reset state. |
| 162 | 181 | method | `GameMemory._get_module_base` | `_get_module_base(self, pid: int, module_name: str) -> int \| None` | — | No docstring; handles get module base behavior. |
| 186 | 188 | method | `GameMemory._check_open` | `_check_open(self) -> None` | — | No docstring; handles check open behavior. |
| 190 | 201 | method | `GameMemory.read_bytes` | `read_bytes(self, addr: int, length: int) -> bytes` | — | Read length bytes from absolute address addr. |
| 203 | 214 | method | `GameMemory.write_bytes` | `write_bytes(self, addr: int, data: bytes) -> None` | — | Write data to absolute address addr. |
| 216 | 218 | method | `GameMemory.read_uint32` | `read_uint32(self, addr: int) -> int` | — | No docstring; handles read uint32 behavior. |
| 220 | 222 | method | `GameMemory.write_uint32` | `write_uint32(self, addr: int, value: int) -> None` | — | No docstring; handles write uint32 behavior. |
| 224 | 226 | method | `GameMemory.read_u64` | `read_u64(self, addr: int) -> int` | — | No docstring; handles read u64 behavior. |
| 228 | 238 | method | `GameMemory.read_wstring` | `read_wstring(self, addr: int, max_chars: int) -> str` | — | Read a UTF-16LE string of at most max_chars characters from addr. |
| 240 | 245 | method | `GameMemory.write_wstring_fixed` | `write_wstring_fixed(self, addr: int, value: str, max_chars: int) -> None` | — | Write a fixed length null-terminated UTF-16LE string at addr. |
| 248 | 258 | method | `GameMemory.read_ascii` | `read_ascii(self, addr: int, max_chars: int) -> str` | — | Read an ASCII string of up to max_chars bytes from addr. |
| 260 | 265 | method | `GameMemory.write_ascii_fixed` | `write_ascii_fixed(self, addr: int, value: str, max_chars: int) -> None` | — | Write a fixed length null-terminated ASCII string at addr. |

### `memory/win32.py`

_No callable definitions._

### `models/__init__.py`

_No callable definitions._

### `models/data_model.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 72 | 76 | function | `_plausible_record_name_part` | `_plausible_record_name_part(value: object) -> bool` | — | No docstring; handles plausible record name part behavior. |
| 79 | 89 | function | `_valid_nba_record_label_values` | `_valid_nba_record_label_values(values: list[Any]) -> bool` | — | No docstring; handles valid nba record label values behavior. |
| 92 | 93 | function | `_has_alpha_text` | `_has_alpha_text(value: object) -> bool` | — | No docstring; handles has alpha text behavior. |
| 139 | 144 | function | `target_display_label` | `target_display_label(executable: str \| None) -> str` | — | No docstring; handles target display label behavior. |
| 152 | 179 | method | `EditorDataModel.__init__` | `__init__(self, *, memory: GameMemory \| Any \| None=None, offsets_api: Any=offsets_mod, target_executable: str \| None=None) -> None` | — | No docstring; handles init behavior. |
| 181 | 183 | method | `EditorDataModel._active_config` | `_active_config(self) -> dict[str, Any]` | — | No docstring; handles active config behavior. |
| 185 | 188 | method | `EditorDataModel._domain_base_key` | `_domain_base_key(self, domain: str) -> str` | — | No docstring; handles domain base key behavior. |
| 190 | 195 | method | `EditorDataModel._domain_stride_key` | `_domain_stride_key(self, domain: str) -> str` | — | No docstring; handles domain stride key behavior. |
| 197 | 201 | method | `EditorDataModel.editor_layout` | `editor_layout(self, domain: str) -> dict[str, Any]` | — | No docstring; handles editor layout behavior. |
| 203 | 206 | method | `EditorDataModel._layout_entries` | `_layout_entries(self, domain: str) -> tuple[FieldEntry, ...]` | — | No docstring; handles layout entries behavior. |
| 208 | 219 | method | `EditorDataModel._field_lookup` | `_field_lookup(self, domain: str) -> dict[str, FieldEntry]` | — | No docstring; handles field lookup behavior. |
| 221 | 224 | method | `EditorDataModel._field_context_map` | `_field_context_map(self, domain: str) -> dict[int, tuple[str, str]]` | — | No docstring; handles field context map behavior. |
| 226 | 237 | method | `EditorDataModel._field_context` | `_field_context(self, domain: str, field: dict[str, Any]) -> tuple[str, str]` | — | No docstring; handles field context behavior. |
| 239 | 246 | method | `EditorDataModel._parent_payload` | `_parent_payload(self, domain: str, payload: dict[str, Any]) -> dict[str, Any] \| None` | — | No docstring; handles parent payload behavior. |
| 248 | 256 | method | `EditorDataModel.attach` | `attach(self) -> bool` | — | No docstring; handles attach behavior. |
| 258 | 262 | method | `EditorDataModel.runtime_status_text` | `runtime_status_text(self) -> str` | — | No docstring; handles runtime status text behavior. |
| 264 | 277 | method | `EditorDataModel.select_target_executable` | `select_target_executable(self, executable: str) -> None` | — | No docstring; handles select target executable behavior. |
| 279 | 280 | method | `EditorDataModel.domain_status` | `domain_status(self, domain: str) -> str` | — | No docstring; handles domain status behavior. |
| 282 | 283 | method | `EditorDataModel.domain_item_labels` | `domain_item_labels(self, domain: str) -> list[str]` | — | No docstring; handles domain item labels behavior. |
| 285 | 286 | method | `EditorDataModel.domain_item_count` | `domain_item_count(self, domain: str) -> int` | — | No docstring; handles domain item count behavior. |
| 288 | 289 | method | `EditorDataModel.player_team_filter_options` | `player_team_filter_options(self) -> tuple[str, ...]` | — | No docstring; handles player team filter options behavior. |
| 291 | 298 | method | `EditorDataModel._read_player_current_team_pointer` | `_read_player_current_team_pointer(self, item: RecordListItem) -> int \| None` | — | No docstring; handles read player current team pointer behavior. |
| 300 | 303 | method | `EditorDataModel._player_current_team_pointer` | `_player_current_team_pointer(self, item: RecordListItem) -> int \| None` | — | No docstring; handles player current team pointer behavior. |
| 305 | 306 | method | `EditorDataModel._cache_player_team_pointers` | `_cache_player_team_pointers(self, items: list[RecordListItem]) -> None` | — | No docstring; handles cache player team pointers behavior. |
| 308 | 324 | method | `EditorDataModel.player_item_labels_for_team_filter` | `player_item_labels_for_team_filter(self, selected_team_label: str \| None, search_text: str \| None=None) -> list[str]` | — | No docstring; handles player item labels for team filter behavior. |
| 326 | 327 | method | `EditorDataModel.is_player_season_id_selector_entry` | `is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool` | — | No docstring; handles is player season id selector entry behavior. |
| 329 | 330 | method | `EditorDataModel.is_player_selected_stat_detail_entry` | `is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool` | — | No docstring; handles is player selected stat detail entry behavior. |
| 332 | 346 | method | `EditorDataModel.player_season_stat_id_options` | `player_season_stat_id_options(self, player_index: int) -> list[str]` | — | No docstring; handles player season stat id options behavior. |
| 348 | 354 | method | `EditorDataModel._player_season_id_selector_entries` | `_player_season_id_selector_entries(self, selector_role: object) -> list[FieldEntry]` | — | No docstring; handles player season id selector entries behavior. |
| 356 | 366 | method | `EditorDataModel._player_season_id_selector_entry_for_option` | `_player_season_id_selector_entry_for_option(self, selected: object, *, selector_role: object=_STAT_ROLE_SELECTOR) -> FieldEntry` | — | No docstring; handles player season id selector entry for option behavior. |
| 368 | 372 | method | `EditorDataModel._selected_record_source_for_entry` | `_selected_record_source_for_entry(self, entry: FieldEntry) -> dict[str, Any]` | — | No docstring; handles selected record source for entry behavior. |
| 374 | 388 | method | `EditorDataModel._player_season_stat_detail_base_address` | `_player_season_stat_detail_base_address(self, entry: FieldEntry, player_index: int, selected: object) -> int` | — | No docstring; handles player season stat detail base address behavior. |
| 390 | 398 | method | `EditorDataModel._base_pointer_entry` | `_base_pointer_entry(self, key: str) -> dict[str, Any]` | — | No docstring; handles base pointer entry behavior. |
| 400 | 408 | method | `EditorDataModel._stride_value` | `_stride_value(self, key: str) -> int` | — | No docstring; handles stride value behavior. |
| 410 | 418 | method | `EditorDataModel._record_id_value` | `_record_id_value(self, domain: str, item: RecordListItem, id_field_name: str) -> int \| None` | — | No docstring; handles record id value behavior. |
| 420 | 426 | method | `EditorDataModel._shoe_option_map` | `_shoe_option_map(self) -> dict[int, str]` | — | No docstring; handles shoe option map behavior. |
| 428 | 433 | method | `EditorDataModel.field_options` | `field_options(self, entry: FieldEntry) -> list[str]` | — | No docstring; handles field options behavior. |
| 435 | 436 | method | `EditorDataModel.selected_item` | `selected_item(self, domain: str) -> RecordListItem \| None` | — | No docstring; handles selected item behavior. |
| 438 | 441 | method | `EditorDataModel.select_item_by_label` | `select_item_by_label(self, domain: str, selected_label: str \| None) -> RecordListItem \| None` | — | No docstring; handles select item by label behavior. |
| 443 | 466 | method | `EditorDataModel.refresh_domain_items` | `refresh_domain_items(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | — | No docstring; handles refresh domain items behavior. |
| 468 | 473 | method | `EditorDataModel.start_background_refresh` | `start_background_refresh(self, domains: tuple[str, ...]) -> bool` | — | No docstring; handles start background refresh behavior. |
| 475 | 487 | method | `EditorDataModel._background_refresh_worker` | `_background_refresh_worker(self, domains: tuple[str, ...]) -> None` | — | No docstring; handles background refresh worker behavior. |
| 489 | 495 | method | `EditorDataModel.pop_refresh_events` | `pop_refresh_events(self) -> list[tuple[str, str]]` | — | No docstring; handles pop refresh events behavior. |
| 497 | 498 | method | `EditorDataModel.player_detail_labels` | `player_detail_labels(self) -> tuple[str, ...]` | — | No docstring; handles player detail labels behavior. |
| 500 | 501 | method | `EditorDataModel.team_summary_labels` | `team_summary_labels(self) -> tuple[str, ...]` | — | No docstring; handles team summary labels behavior. |
| 503 | 509 | method | `EditorDataModel._selected_item_rank_text` | `_selected_item_rank_text(self, domain: str, item: RecordListItem \| None) -> str` | — | No docstring; handles selected item rank text behavior. |
| 511 | 516 | method | `EditorDataModel._record_summary_specs` | `_record_summary_specs(self, domain: str) -> tuple[tuple[str, tuple[str, ...]], ...]` | — | No docstring; handles record summary specs behavior. |
| 518 | 525 | method | `EditorDataModel._record_summary_values_for_item` | `_record_summary_values_for_item(self, domain: str, item: RecordListItem \| None, rank: int \| None=None) -> dict[str, str]` | — | No docstring; handles record summary values for item behavior. |
| 527 | 537 | method | `EditorDataModel._read_named_value_at_record_address` | `_read_named_value_at_record_address(self, domain: str, record_addr: int, candidates: tuple[str, ...]) -> str` | — | No docstring; handles read named value at record address behavior. |
| 539 | 546 | method | `EditorDataModel._record_summary_values_for_address` | `_record_summary_values_for_address(self, domain: str, record_addr: int, rank: int) -> dict[str, str]` | — | No docstring; handles record summary values for address behavior. |
| 548 | 566 | method | `EditorDataModel._packed_record_summary_stride` | `_packed_record_summary_stride(self, domain: str) -> int` | — | No docstring; handles packed record summary stride behavior. |
| 568 | 569 | method | `EditorDataModel.selected_record_summary_values` | `selected_record_summary_values(self, domain: str) -> dict[str, str]` | — | No docstring; handles selected record summary values behavior. |
| 571 | 604 | method | `EditorDataModel.record_summary_rows` | `record_summary_rows(self, domain: str, *, limit: int \| None, history_type: int \| None=None, record_row_start: int \| None=None, record_row_count: int \| None=None, record_row_stride: int \| None=None) -> list[dict[str, str]]` | — | No docstring; handles record summary rows behavior. |
| 597 | 597 | lambda | `EditorDataModel.record_summary_rows.<lambda>@597` | `lambda item` | — | Lambda callback/expression. |
| 606 | 607 | method | `EditorDataModel.clear_history_screen_rows` | `clear_history_screen_rows(self) -> None` | — | No docstring; handles clear history screen rows behavior. |
| 609 | 610 | method | `EditorDataModel.clear_record_screen_rows` | `clear_record_screen_rows(self) -> None` | — | No docstring; handles clear record screen rows behavior. |
| 612 | 615 | method | `EditorDataModel.refresh_history_screen_rows` | `refresh_history_screen_rows(self, section: str, tab: str, history_type: int \| None) -> list[dict[str, str]]` | — | No docstring; handles refresh history screen rows behavior. |
| 617 | 621 | method | `EditorDataModel.history_screen_rows` | `history_screen_rows(self, section: str, tab: str, history_type: int \| None) -> list[dict[str, str]]` | — | No docstring; handles history screen rows behavior. |
| 623 | 638 | method | `EditorDataModel.refresh_record_screen_rows` | `refresh_record_screen_rows(self, section: str, stat: str, *, record_row_start: int, record_row_count: int) -> list[dict[str, str]]` | — | No docstring; handles refresh record screen rows behavior. |
| 640 | 656 | method | `EditorDataModel.record_screen_rows` | `record_screen_rows(self, section: str, stat: str, *, record_row_start: int, record_row_count: int) -> list[dict[str, str]]` | — | No docstring; handles record screen rows behavior. |
| 658 | 667 | method | `EditorDataModel._read_named_raw_int` | `_read_named_raw_int(self, domain: str, item: RecordListItem \| None, name: str) -> int \| None` | — | No docstring; handles read named raw int behavior. |
| 669 | 681 | method | `EditorDataModel._read_named_value` | `_read_named_value(self, domain: str, item: RecordListItem \| None, candidates: tuple[str, ...]) -> str` | — | No docstring; handles read named value behavior. |
| 683 | 685 | method | `EditorDataModel.selected_player_detail_values` | `selected_player_detail_values(self) -> dict[str, str]` | — | No docstring; handles selected player detail values behavior. |
| 687 | 689 | method | `EditorDataModel.selected_team_summary_values` | `selected_team_summary_values(self) -> dict[str, str]` | — | No docstring; handles selected team summary values behavior. |
| 691 | 711 | method | `EditorDataModel.save_selected_team_summary` | `save_selected_team_summary(self, values: dict[str, str]) -> tuple[int, int]` | — | No docstring; handles save selected team summary behavior. |
| 713 | 715 | method | `EditorDataModel.selected_detail_title` | `selected_detail_title(self, domain: str, label: str) -> str` | — | No docstring; handles selected detail title behavior. |
| 717 | 719 | method | `EditorDataModel.selected_record_address_text` | `selected_record_address_text(self, domain: str) -> str` | — | No docstring; handles selected record address text behavior. |
| 721 | 731 | method | `EditorDataModel.grouped_fields` | `grouped_fields(self, domain: str) -> OrderedDict[str, OrderedDict[str, list[FieldEntry]]]` | — | No docstring; handles grouped fields behavior. |
| 733 | 734 | method | `EditorDataModel._field_by_normalized_name` | `_field_by_normalized_name(self, domain: str, name: str) -> FieldEntry \| None` | — | No docstring; handles field by normalized name behavior. |
| 736 | 744 | method | `EditorDataModel._label_entries` | `_label_entries(self, domain: str) -> list[FieldEntry]` | — | No docstring; handles label entries behavior. |
| 746 | 747 | method | `EditorDataModel._team_pointer_display` | `_team_pointer_display(self, raw_value: Any) -> str \| None` | — | No docstring; handles team pointer display behavior. |
| 749 | 775 | method | `EditorDataModel._record_pointer_display` | `_record_pointer_display(self, raw_value: Any, target_domain: str) -> str \| None` | — | No docstring; handles record pointer display behavior. |
| 777 | 788 | method | `EditorDataModel._pointer_display_for_payload` | `_pointer_display_for_payload(self, payload: dict[str, Any], raw_value: Any) -> str \| None` | — | No docstring; handles pointer display for payload behavior. |
| 790 | 805 | method | `EditorDataModel._read_field_at_record_address` | `_read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles read field at record address behavior. |
| 807 | 817 | method | `EditorDataModel._write_field_at_record_address` | `_write_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any], value: Any) -> Any` | — | No docstring; handles write field at record address behavior. |
| 819 | 830 | method | `EditorDataModel._label_for_record_address` | `_label_for_record_address(self, domain: str, index: int, record_addr: int, label_entries: list[FieldEntry]) -> str` | — | No docstring; handles label for record address behavior. |
| 832 | 846 | method | `EditorDataModel._valid_label_values` | `_valid_label_values(self, domain: str, record_addr: int, values: list[Any], labels: list[str]) -> bool` | — | No docstring; handles valid label values behavior. |
| 848 | 878 | method | `EditorDataModel.scan_records` | `scan_records(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | — | No docstring; handles scan records behavior. |
| 880 | 887 | method | `EditorDataModel.read_entry_value` | `read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object \| None=None) -> dict[str, Any]` | — | No docstring; handles read entry value behavior. |
| 889 | 894 | method | `EditorDataModel.write_entry_value` | `write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object \| None=None) -> dict[str, Any]` | — | No docstring; handles write entry value behavior. |
| 896 | 904 | method | `EditorDataModel.domain_base` | `domain_base(self, domain: str) -> int` | — | No docstring; handles domain base behavior. |
| 906 | 915 | method | `EditorDataModel.domain_stride` | `domain_stride(self, domain: str) -> int` | — | No docstring; handles domain stride behavior. |
| 917 | 918 | method | `EditorDataModel.record_address` | `record_address(self, domain: str, index: int) -> int` | — | No docstring; handles record address behavior. |
| 920 | 930 | method | `EditorDataModel._field_version_payload` | `_field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles field version payload behavior. |
| 932 | 933 | method | `EditorDataModel.read_value` | `read_value(self, domain: str, *, index: int, field: dict[str, Any]) -> dict[str, Any]` | — | No docstring; handles read value behavior. |
| 935 | 941 | method | `EditorDataModel.write_value` | `write_value(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> None` | — | No docstring; handles write value behavior. |
| 943 | 945 | method | `EditorDataModel.write_and_readback` | `write_and_readback(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> dict[str, Any]` | — | No docstring; handles write and readback behavior. |
| 948 | 982 | function | `verify_edits` | `verify_edits(*, target_executable: str \| None=None) -> dict[str, Any]` | — | No docstring; handles verify edits behavior. |

### `models/schema.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 17 | 18 | method | `FieldEntry.normalized_name` | `normalized_name(self) -> str` | property | No docstring; handles normalized name behavior. |
| 21 | 22 | method | `FieldEntry.display_name` | `display_name(self) -> str` | property | No docstring; handles display name behavior. |
| 33 | 34 | method | `RecordListItem.display_label` | `display_label(self) -> str` | property | No docstring; handles display label behavior. |
| 37 | 38 | function | `_field_identity` | `_field_identity(value: object) -> str` | — | No docstring; handles field identity behavior. |
| 41 | 42 | function | `_field_display_or_name` | `_field_display_or_name(field: dict[str, Any]) -> str` | — | No docstring; handles field display or name behavior. |
| 45 | 57 | function | `_iter_layout_fields` | `_iter_layout_fields(domain: str, layout: dict[str, Any]) -> Iterable[FieldEntry]` | — | No docstring; handles iter layout fields behavior. |
| 64 | 65 | function | `_stat_role` | `_stat_role(field: dict[str, Any]) -> str` | — | No docstring; handles stat role behavior. |
| 68 | 70 | function | `_selected_record_source` | `_selected_record_source(field: dict[str, Any]) -> dict[str, Any] \| None` | — | No docstring; handles selected record source behavior. |
| 73 | 74 | function | `_is_player_season_id_selector_entry` | `_is_player_season_id_selector_entry(entry: FieldEntry) -> bool` | — | No docstring; handles is player season id selector entry behavior. |
| 77 | 78 | function | `_is_player_selected_stat_detail_entry` | `_is_player_selected_stat_detail_entry(entry: FieldEntry) -> bool` | — | No docstring; handles is player selected stat detail entry behavior. |
| 81 | 82 | function | `_player_season_id_option_label` | `_player_season_id_option_label(entry: FieldEntry) -> str` | — | No docstring; handles player season id option label behavior. |
| 85 | 90 | function | `_player_season_id_identity_from_option` | `_player_season_id_identity_from_option(option: object) -> str` | — | No docstring; handles player season id identity from option behavior. |

### `ui/__init__.py`

_No callable definitions._

### `ui/dpg_editor.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 146 | 147 | function | `_tag` | `_tag(*parts: object) -> str` | — | No docstring; handles tag behavior. |
| 150 | 152 | function | `_target_executable` | `_target_executable(label: str) -> str` | — | No docstring; handles target executable behavior. |
| 157 | 172 | method | `DpgEditorApp.__init__` | `__init__(self, model: EditorDataModel) -> None` | — | No docstring; handles init behavior. |
| 174 | 175 | method | `DpgEditorApp._screen_tag` | `_screen_tag(self, domain: str) -> str` | — | No docstring; handles screen tag behavior. |
| 177 | 178 | method | `DpgEditorApp._app_screen_tag` | `_app_screen_tag(self, screen: str) -> str` | — | No docstring; handles app screen tag behavior. |
| 180 | 181 | method | `DpgEditorApp._home_status_tag` | `_home_status_tag(self) -> str` | — | No docstring; handles home status tag behavior. |
| 183 | 184 | method | `DpgEditorApp._home_target_status_tag` | `_home_target_status_tag(self) -> str` | — | No docstring; handles home target status tag behavior. |
| 186 | 187 | method | `DpgEditorApp._status_tag` | `_status_tag(self, domain: str) -> str` | — | No docstring; handles status tag behavior. |
| 189 | 190 | method | `DpgEditorApp._count_tag` | `_count_tag(self, domain: str) -> str` | — | No docstring; handles count tag behavior. |
| 192 | 193 | method | `DpgEditorApp._list_tag` | `_list_tag(self, domain: str) -> str` | — | No docstring; handles list tag behavior. |
| 195 | 196 | method | `DpgEditorApp._player_team_filter_tag` | `_player_team_filter_tag(self) -> str` | — | No docstring; handles player team filter tag behavior. |
| 198 | 199 | method | `DpgEditorApp._player_search_tag` | `_player_search_tag(self) -> str` | — | No docstring; handles player search tag behavior. |
| 201 | 202 | method | `DpgEditorApp._record_list_rows_for_height` | `_record_list_rows_for_height(self, viewport_height: int) -> int` | — | No docstring; handles record list rows for height behavior. |
| 204 | 210 | method | `DpgEditorApp._resize_record_lists` | `_resize_record_lists(self, dpg: Any) -> None` | — | No docstring; handles resize record lists behavior. |
| 212 | 213 | method | `DpgEditorApp._detail_tag` | `_detail_tag(self, domain: str, name: str) -> str` | — | No docstring; handles detail tag behavior. |
| 215 | 216 | method | `DpgEditorApp._preview_tag` | `_preview_tag(self, domain: str, row: int, label: str) -> str` | — | No docstring; handles preview tag behavior. |
| 218 | 219 | method | `DpgEditorApp._record_card_tag` | `_record_card_tag(self, row: int) -> str` | — | No docstring; handles record card tag behavior. |
| 221 | 222 | method | `DpgEditorApp._record_cards_container_tag` | `_record_cards_container_tag(self) -> str` | — | No docstring; handles record cards container tag behavior. |
| 224 | 225 | method | `DpgEditorApp._record_career_table_tag` | `_record_career_table_tag(self) -> str` | — | No docstring; handles record career table tag behavior. |
| 227 | 228 | method | `DpgEditorApp._record_career_cell_tag` | `_record_career_cell_tag(self, row: int, label: str) -> str` | — | No docstring; handles record career cell tag behavior. |
| 230 | 231 | method | `DpgEditorApp._record_stat_group_tag` | `_record_stat_group_tag(self, section: str) -> str` | — | No docstring; handles record stat group tag behavior. |
| 233 | 234 | method | `DpgEditorApp._history_tab_group_tag` | `_history_tab_group_tag(self, section: str) -> str` | — | No docstring; handles history tab group tag behavior. |
| 236 | 237 | method | `DpgEditorApp._history_table_group_tag` | `_history_table_group_tag(self, section: str) -> str` | — | No docstring; handles history table group tag behavior. |
| 239 | 240 | method | `DpgEditorApp._history_table_content_tag` | `_history_table_content_tag(self, section: str) -> str` | — | No docstring; handles history table content tag behavior. |
| 242 | 243 | method | `DpgEditorApp._history_preview_tag` | `_history_preview_tag(self, section: str, row: int, label: str) -> str` | — | No docstring; handles history preview tag behavior. |
| 245 | 246 | method | `DpgEditorApp._record_card_title_tag` | `_record_card_title_tag(self, row: int) -> str` | — | No docstring; handles record card title tag behavior. |
| 248 | 249 | method | `DpgEditorApp._heading_tag` | `_heading_tag(self, domain: str) -> str` | — | No docstring; handles heading tag behavior. |
| 251 | 252 | method | `DpgEditorApp._team_input_tag` | `_team_input_tag(self, label: str) -> str` | — | No docstring; handles team input tag behavior. |
| 254 | 255 | method | `DpgEditorApp._nav_tag` | `_nav_tag(self, screen: str) -> str` | — | No docstring; handles nav tag behavior. |
| 257 | 258 | method | `DpgEditorApp._display_label` | `_display_label(self, domain: str) -> str` | — | No docstring; handles display label behavior. |
| 260 | 261 | method | `DpgEditorApp._game_status_text` | `_game_status_text(self) -> str` | — | No docstring; handles game status text behavior. |
| 263 | 265 | method | `DpgEditorApp._safe_set` | `_safe_set(self, dpg: Any, tag: str, value: object) -> None` | — | No docstring; handles safe set behavior. |
| 267 | 269 | method | `DpgEditorApp._safe_configure` | `_safe_configure(self, dpg: Any, tag: str, **kwargs: object) -> None` | — | No docstring; handles safe configure behavior. |
| 271 | 273 | method | `DpgEditorApp._safe_delete_children` | `_safe_delete_children(self, dpg: Any, tag: str) -> None` | — | No docstring; handles safe delete children behavior. |
| 275 | 277 | method | `DpgEditorApp._bind_item_theme` | `_bind_item_theme(self, dpg: Any, item: str, theme: str) -> None` | — | No docstring; handles bind item theme behavior. |
| 279 | 282 | method | `DpgEditorApp._refresh_nav_state` | `_refresh_nav_state(self, dpg: Any) -> None` | — | No docstring; handles refresh nav state behavior. |
| 284 | 290 | method | `DpgEditorApp._show_screen` | `_show_screen(self, dpg: Any, domain: str) -> None` | — | No docstring; handles show screen behavior. |
| 292 | 296 | method | `DpgEditorApp._set_target` | `_set_target(self, dpg: Any, selected: str) -> None` | — | No docstring; handles set target behavior. |
| 298 | 304 | method | `DpgEditorApp._refresh_status_labels` | `_refresh_status_labels(self, dpg: Any) -> None` | — | No docstring; handles refresh status labels behavior. |
| 306 | 308 | method | `DpgEditorApp._attach` | `_attach(self, dpg: Any) -> None` | — | No docstring; handles attach behavior. |
| 310 | 311 | method | `DpgEditorApp._attach_and_scan` | `_attach_and_scan(self, dpg: Any, domain: str) -> None` | — | No docstring; handles attach and scan behavior. |
| 313 | 314 | method | `DpgEditorApp._attach_and_load_all` | `_attach_and_load_all(self, dpg: Any) -> None` | — | No docstring; handles attach and load all behavior. |
| 316 | 322 | method | `DpgEditorApp._start_background_scan` | `_start_background_scan(self, dpg: Any, domains: tuple[str, ...]) -> None` | — | No docstring; handles start background scan behavior. |
| 324 | 337 | method | `DpgEditorApp._poll_background_scan` | `_poll_background_scan(self, dpg: Any) -> None` | — | No docstring; handles poll background scan behavior. |
| 339 | 355 | method | `DpgEditorApp._sync_domain_list` | `_sync_domain_list(self, dpg: Any, domain: str) -> None` | — | No docstring; handles sync domain list behavior. |
| 357 | 362 | method | `DpgEditorApp._sync_player_team_filter` | `_sync_player_team_filter(self, dpg: Any) -> None` | — | No docstring; handles sync player team filter behavior. |
| 364 | 384 | method | `DpgEditorApp._sync_player_list` | `_sync_player_list(self, dpg: Any) -> None` | — | No docstring; handles sync player list behavior. |
| 386 | 388 | method | `DpgEditorApp._set_player_team_filter` | `_set_player_team_filter(self, dpg: Any, selected: str \| None) -> None` | — | No docstring; handles set player team filter behavior. |
| 390 | 392 | method | `DpgEditorApp._set_player_search_text` | `_set_player_search_text(self, dpg: Any, search_text: str \| None) -> None` | — | No docstring; handles set player search text behavior. |
| 394 | 411 | method | `DpgEditorApp._sync_record_screen_rows` | `_sync_record_screen_rows(self, dpg: Any, domain: str) -> None` | — | No docstring; handles sync record screen rows behavior. |
| 413 | 440 | method | `DpgEditorApp._show_record_screen_rows` | `_show_record_screen_rows(self, dpg: Any) -> None` | — | No docstring; handles show record screen rows behavior. |
| 442 | 449 | method | `DpgEditorApp._show_history_screen_rows` | `_show_history_screen_rows(self, dpg: Any) -> None` | — | No docstring; handles show history screen rows behavior. |
| 451 | 461 | method | `DpgEditorApp._render_history_table` | `_render_history_table(self, dpg: Any, section: str, labels: tuple[str, ...], rows: list[dict[str, str]]) -> None` | — | No docstring; handles render history table behavior. |
| 463 | 468 | method | `DpgEditorApp._history_cell_value` | `_history_cell_value(self, row_values: dict[str, str], label: str) -> str` | — | No docstring; handles history cell value behavior. |
| 470 | 474 | method | `DpgEditorApp._history_type_for_tab` | `_history_type_for_tab(self, section: str, tab: str) -> int \| None` | — | No docstring; handles history type for tab behavior. |
| 476 | 478 | method | `DpgEditorApp._active_history_type` | `_active_history_type(self) -> int \| None` | — | No docstring; handles active history type behavior. |
| 480 | 484 | method | `DpgEditorApp._record_row_group` | `_record_row_group(self, section: str, stat: str) -> tuple[int, int]` | — | No docstring; handles record row group behavior. |
| 486 | 487 | method | `DpgEditorApp._active_record_row_group` | `_active_record_row_group(self) -> tuple[int, int]` | — | No docstring; handles active record row group behavior. |
| 489 | 492 | method | `DpgEditorApp._set_history_section` | `_set_history_section(self, dpg: Any, label: str) -> None` | — | No docstring; handles set history section behavior. |
| 494 | 498 | method | `DpgEditorApp._set_history_tab` | `_set_history_tab(self, dpg: Any, label: str) -> None` | — | No docstring; handles set history tab behavior. |
| 500 | 506 | method | `DpgEditorApp._set_record_section` | `_set_record_section(self, dpg: Any, label: str) -> None` | — | No docstring; handles set record section behavior. |
| 508 | 511 | method | `DpgEditorApp._set_record_stat` | `_set_record_stat(self, dpg: Any, label: str) -> None` | — | No docstring; handles set record stat behavior. |
| 513 | 516 | method | `DpgEditorApp._select_current` | `_select_current(self, dpg: Any, domain: str, selected_label: str \| None=None) -> None` | — | No docstring; handles select current behavior. |
| 518 | 523 | method | `DpgEditorApp._open_selected` | `_open_selected(self, dpg: Any, domain: str) -> None` | — | No docstring; handles open selected behavior. |
| 525 | 542 | method | `DpgEditorApp._update_detail_panel` | `_update_detail_panel(self, dpg: Any, domain: str) -> None` | — | No docstring; handles update detail panel behavior. |
| 544 | 551 | method | `DpgEditorApp._save_team_summary` | `_save_team_summary(self, dpg: Any) -> None` | — | No docstring; handles save team summary behavior. |
| 553 | 554 | method | `DpgEditorApp._row_current_tag` | `_row_current_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row current tag behavior. |
| 556 | 557 | method | `DpgEditorApp._row_new_tag` | `_row_new_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row new tag behavior. |
| 559 | 560 | method | `DpgEditorApp._row_status_tag` | `_row_status_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | — | No docstring; handles row status tag behavior. |
| 562 | 563 | method | `DpgEditorApp._editor_status_tag` | `_editor_status_tag(self, item: RecordListItem) -> str` | — | No docstring; handles editor status tag behavior. |
| 565 | 566 | method | `DpgEditorApp._season_stat_selector_key` | `_season_stat_selector_key(self, item: RecordListItem) -> tuple[int, str]` | — | No docstring; handles season stat selector key behavior. |
| 568 | 569 | method | `DpgEditorApp._season_stat_selector_tag` | `_season_stat_selector_tag(self, item: RecordListItem) -> str` | — | No docstring; handles season stat selector tag behavior. |
| 571 | 577 | method | `DpgEditorApp._selected_season_stat_selector` | `_selected_season_stat_selector(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> str \| None` | — | No docstring; handles selected season stat selector behavior. |
| 579 | 583 | method | `DpgEditorApp._set_player_season_stat_id` | `_set_player_season_stat_id(self, dpg: Any, item: RecordListItem, selected: str \| None) -> None` | — | No docstring; handles set player season stat id behavior. |
| 585 | 586 | method | `DpgEditorApp._read_editor_entry_value` | `_read_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry) -> dict[str, Any]` | — | No docstring; handles read editor entry value behavior. |
| 588 | 589 | method | `DpgEditorApp._write_editor_entry_value` | `_write_editor_entry_value(self, dpg: Any, item: RecordListItem, entry: FieldEntry, value: str) -> dict[str, Any]` | — | No docstring; handles write editor entry value behavior. |
| 591 | 611 | method | `DpgEditorApp._load_item_editor` | `_load_item_editor(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles load item editor behavior. |
| 613 | 635 | method | `DpgEditorApp._save_item_editor` | `_save_item_editor(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles save item editor behavior. |
| 637 | 700 | method | `DpgEditorApp._open_editor_window` | `_open_editor_window(self, dpg: Any, item: RecordListItem) -> None` | — | No docstring; handles open editor window behavior. |
| 643 | 644 | method | `DpgEditorApp._open_editor_window.options_for` | `options_for(entry: FieldEntry) -> list[str]` | — | No docstring; handles options for behavior. |
| 646 | 663 | method | `DpgEditorApp._open_editor_window.render_table` | `render_table(render_entries: list[FieldEntry]) -> None` | — | No docstring; handles render table behavior. |
| 667 | 667 | lambda | `DpgEditorApp._open_editor_window.<lambda>@667` | `lambda *_args, i=item` | — | Lambda callback/expression. |
| 668 | 668 | lambda | `DpgEditorApp._open_editor_window.<lambda>@668` | `lambda *_args, i=item` | — | Lambda callback/expression. |
| 691 | 691 | lambda | `DpgEditorApp._open_editor_window.<lambda>@691` | `lambda _s, app_data, _u=None, *args, i=item` | — | Lambda callback/expression. |
| 702 | 706 | method | `DpgEditorApp._add_nav_button` | `_add_nav_button(self, dpg: Any, screen: str, label: str) -> None` | — | No docstring; handles add nav button behavior. |
| 705 | 705 | lambda | `DpgEditorApp._add_nav_button.<lambda>@705` | `lambda *_args, s=screen` | — | Lambda callback/expression. |
| 708 | 714 | method | `DpgEditorApp._add_detail_row` | `_add_detail_row(self, dpg: Any, label: str, value_tag: str, *, accent: bool=False) -> None` | — | No docstring; handles add detail row behavior. |
| 716 | 732 | method | `DpgEditorApp._build_home_screen` | `_build_home_screen(self, dpg: Any, *, show: bool=True) -> None` | — | No docstring; handles build home screen behavior. |
| 721 | 721 | lambda | `DpgEditorApp._build_home_screen.<lambda>@721` | `lambda _s, app_data, _u` | — | Lambda callback/expression. |
| 725 | 725 | lambda | `DpgEditorApp._build_home_screen.<lambda>@725` | `lambda *_args` | — | Lambda callback/expression. |
| 734 | 770 | method | `DpgEditorApp._build_players_screen` | `_build_players_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build players screen behavior. |
| 738 | 738 | lambda | `DpgEditorApp._build_players_screen.<lambda>@738` | `lambda *_args` | — | Lambda callback/expression. |
| 749 | 749 | lambda | `DpgEditorApp._build_players_screen.<lambda>@749` | `lambda _s, app_data, _u=None, *args` | — | Lambda callback/expression. |
| 757 | 757 | lambda | `DpgEditorApp._build_players_screen.<lambda>@757` | `lambda _s, app_data, _u=None, *args` | — | Lambda callback/expression. |
| 762 | 762 | lambda | `DpgEditorApp._build_players_screen.<lambda>@762` | `lambda _s, app_data, _u=None, *_, d=domain` | — | Lambda callback/expression. |
| 770 | 770 | lambda | `DpgEditorApp._build_players_screen.<lambda>@770` | `lambda *_args` | — | Lambda callback/expression. |
| 772 | 798 | method | `DpgEditorApp._build_teams_screen` | `_build_teams_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build teams screen behavior. |
| 776 | 776 | lambda | `DpgEditorApp._build_teams_screen.<lambda>@776` | `lambda *_args` | — | Lambda callback/expression. |
| 784 | 784 | lambda | `DpgEditorApp._build_teams_screen.<lambda>@784` | `lambda _s, app_data, _u=None, *_, d=domain` | — | Lambda callback/expression. |
| 797 | 797 | lambda | `DpgEditorApp._build_teams_screen.<lambda>@797` | `lambda *_args` | — | Lambda callback/expression. |
| 798 | 798 | lambda | `DpgEditorApp._build_teams_screen.<lambda>@798` | `lambda *_args` | — | Lambda callback/expression. |
| 800 | 805 | method | `DpgEditorApp._add_button_strip` | `_add_button_strip(self, dpg: Any, labels: tuple[str, ...], *, per_row: int, callback: Any \| None=None) -> None` | — | No docstring; handles add button strip behavior. |
| 804 | 804 | lambda | `DpgEditorApp._add_button_strip.<lambda>@804` | `lambda *_args, selected=label` | — | Lambda callback/expression. |
| 807 | 831 | method | `DpgEditorApp._build_history_screen` | `_build_history_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build history screen behavior. |
| 812 | 812 | lambda | `DpgEditorApp._build_history_screen.<lambda>@812` | `lambda *_args` | — | Lambda callback/expression. |
| 815 | 815 | lambda | `DpgEditorApp._build_history_screen.<lambda>@815` | `lambda *_args, selected=label` | — | Lambda callback/expression. |
| 822 | 822 | lambda | `DpgEditorApp._build_history_screen.<lambda>@822` | `lambda selected` | — | Lambda callback/expression. |
| 833 | 875 | method | `DpgEditorApp._build_records_screen` | `_build_records_screen(self, dpg: Any, *, show: bool=False) -> None` | — | No docstring; handles build records screen behavior. |
| 838 | 838 | lambda | `DpgEditorApp._build_records_screen.<lambda>@838` | `lambda *_args` | — | Lambda callback/expression. |
| 841 | 841 | lambda | `DpgEditorApp._build_records_screen.<lambda>@841` | `lambda *_args, selected=label` | — | Lambda callback/expression. |
| 848 | 848 | lambda | `DpgEditorApp._build_records_screen.<lambda>@848` | `lambda selected` | — | Lambda callback/expression. |
| 877 | 881 | method | `DpgEditorApp._build_history_or_records_screen` | `_build_history_or_records_screen(self, dpg: Any, domain: str, *, show: bool=False) -> None` | — | No docstring; handles build history or records screen behavior. |
| 883 | 911 | method | `DpgEditorApp._build_domain_screen` | `_build_domain_screen(self, dpg: Any, domain: str, *, show: bool=False) -> None` | — | No docstring; handles build domain screen behavior. |
| 896 | 896 | lambda | `DpgEditorApp._build_domain_screen.<lambda>@896` | `lambda *_args, d=domain` | — | Lambda callback/expression. |
| 904 | 904 | lambda | `DpgEditorApp._build_domain_screen.<lambda>@904` | `lambda _s, app_data, _u=None, *_, d=domain` | — | Lambda callback/expression. |
| 911 | 911 | lambda | `DpgEditorApp._build_domain_screen.<lambda>@911` | `lambda *_args, d=domain` | — | Lambda callback/expression. |
| 913 | 957 | method | `DpgEditorApp.run` | `run(self, *, load_on_start: bool=True) -> None` | — | No docstring; handles run behavior. |

### `ui/theme.py`

| Line | End | Kind | Qualname | Signature | Decorators | What it does |
|---:|---:|---|---|---|---|---|
| 30 | 37 | function | `to_rgba` | `to_rgba(hex_color: str, alpha: int=255) -> tuple[int, int, int, int]` | — | Convert exact '#RRGGBB' hex to an RGBA tuple. |
| 40 | 124 | function | `apply_base_theme` | `apply_base_theme() -> str` | — | Create and bind the base Dear PyGui theme. |
| 127 | 159 | function | `ensure_editor_themes` | `ensure_editor_themes() -> dict[str, str]` | — | Create reusable item themes for the compact editor shell. |

