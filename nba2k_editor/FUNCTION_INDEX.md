# NBA2K Editor Function Index

Current AST-generated index of top-level functions and direct class methods in `nba2k_editor/`.

- Python files scanned: 16
- Files with functions/methods: 9
- Functions/methods listed: 187
- Nested function definitions found: 0
- Purpose: quick ownership map so new work can reuse existing functions instead of adding duplicate wrappers.

## Quick owner map

| Area | Owner file | What belongs there |
|---|---|---|
| CLI dispatch | `__main__.py`, `entrypoints/gui.py` | argument parsing and entrypoint handoff |
| Offset config/layout | `core/offsets.py` | selecting target offset config and editor layout data |
| Value conversion | `core/conversions.py` | 2K raw/display conversion math and bounds |
| Process memory | `memory/game_memory.py`, `memory/win32.py` | process detection/open/close and low-level reads/writes |
| Editor data model | `models/data_model.py` | domain base/stride, authored layout entries, field payload lookup, conversion-backed address/read/write/readback, item loading/selection/background refresh, UI-ready detail values |
| DPG UI | `ui/dpg_editor.py`, `ui/theme.py` | widgets, callbacks, refresh-event polling, editor windows, visual theme |

## Functions by file

### `__init__.py`

_No top-level functions or direct class methods._

### `__main__.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 10 | function | `build_parser() -> argparse.ArgumentParser` | Handles build parser behavior. |
| 18 | function | `main(argv: Sequence[str] \| None=None) -> int` | Handles main behavior. |

### `core/__init__.py`

_No top-level functions or direct class methods._

### `core/conversions.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 26 | function | `_normalize_year_key(value: str) -> str` | Handles normalize year key behavior. |
| 30 | function | `is_year_offset_field(field_name: str) -> bool` | Return True if a field name should be treated as a year offset from YEAR_BASE. |
| 50 | function | `convert_raw_to_year(raw: int, base_year: int=YEAR_BASE) -> int` | Convert a stored year offset into a calendar year. |
| 64 | function | `convert_year_to_raw(year: int, base_year: int=YEAR_BASE) -> int` | Convert a calendar year into its stored offset. |
| 89 | function | `convert_raw_to_rating(raw: int, length: int) -> int` | Convert a raw bitfield value into the 25-99 display rating scale using proportional mapping. |
| 107 | function | `convert_rating_to_raw(rating: float, length: int) -> int` | Convert a 25-99 rating back into a raw bitfield value using proportional mapping. |
| 131 | function | `convert_minmax_potential_to_raw(rating: float, length: int, minimum: float=40.0, maximum: float=99.0) -> int` | Convert Minimum/Maximum Potential display ratings into raw bitfield values. |
| 141 | function | `convert_raw_to_minmax_potential(raw: int, length: int, minimum: float=40.0, maximum: float=99.0) -> int` | Convert raw Minimum/Maximum Potential values back into the 40-99 range. |
| 153 | function | `normalize_weight_value(value: object) -> float \| None` | Parse editor input into a supported weight value in pounds. |
| 169 | function | `convert_pounds_to_kilograms(pounds: object) -> float` | Convert pounds to kilograms. |
| 177 | function | `convert_kilograms_to_pounds(kilograms: object) -> float` | Convert kilograms to pounds. |
| 185 | function | `raw_height_to_inches(raw_val: int) -> int` | Convert raw stored height (inches * 254) to inches. |
| 194 | function | `clamp_height_inches(inches: int) -> int` | Clamp a height value to the supported player-editor range. |
| 207 | function | `height_inches_to_raw(inches: int) -> int` | Convert inches to raw stored height (inches * 254). |
| 216 | function | `format_height_inches(inches: int) -> str` | Format inches as feet/inches for display. |
| 227 | function | `convert_tendency_raw_to_rating(raw: int, length: int) -> int` | Convert a raw bitfield value into a 0-100 tendency rating. |
| 240 | function | `convert_rating_to_tendency_raw(rating: float, length: int) -> int` | Convert a 0-100 tendency rating into a raw bitfield value. |
| 253 | function | `player_numeric_bounds(category_name: str, field_name: str, length_bits: int) -> tuple[int, int]` | Handles player numeric bounds behavior. |
| 266 | function | `to_int(value: Any) -> int` | Convert strings or numeric values to an integer, accepting hex strings. |

### `core/offsets.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 253 | function | `_split_version_tokens(raw_key: object) -> tuple[str, ...]` | Handles split version tokens behavior. |
| 261 | function | `_version_key_matches(raw_key: object, target_label: str \| None) -> bool` | Handles version key matches behavior. |
| 271 | function | `_select_version_entry(per_version: dict[str, object], target_label: str) -> dict[str, object]` | Handles select version entry behavior. |
| 278 | function | `_select_active_version(versions_map: dict[str, object], target_executable: str \| None, *, require_hint: bool=False) -> tuple[str, str, dict[str, object]] \| None` | Handles select active version behavior. |
| 291 | function | `_resolved_length_bits(version_payload: dict[str, object]) -> int` | Handles resolved length bits behavior. |
| 304 | function | `get_editor_layout_for_super(super_type: str) -> dict[str, object]` | Return the owning offsets file's authored structure directly. |
| 352 | function | `_load_offsets_resource(file_name: str) -> dict[str, object]` | Handles load offsets resource behavior. |
| 357 | function | `_load_league_offset_config(target_executable: str \| None=None) -> dict[str, object]` | Load the authored league offsets resource only. |
| 380 | function | `get_active_offset_config(target_executable: str \| None=None) -> dict[str, object]` | Handles get active offset config behavior. |
| 386 | function | `_derive_version_label(executable: str \| None) -> str` | Handles derive version label behavior. |
| 394 | function | `_resolve_version_context(data: dict[str, Any] \| None, target_executable: str \| None) -> tuple[str, dict[str, Any], dict[str, Any]]` | Handles resolve version context behavior. |
| 411 | function | `_normalize_chain_steps(chain_data: list[dict[str, object]]) -> list[dict[str, object]]` | Handles normalize chain steps behavior. |
| 421 | function | `_parse_pointer_chain_config(base_cfg: dict[str, object]) -> list[dict[str, object]]` | Handles parse pointer chain config behavior. |
| 436 | function | `_apply_offset_config(data: dict \| None, target_executable: str \| None=None) -> None` | Update module-level constants using the loaded offset data. |
| 496 | function | `has_active_config() -> bool` | Handles has active config behavior. |
| 500 | function | `get_current_target() -> str` | Handles get current target behavior. |
| 504 | function | `initialize_offsets(target_executable: str \| None=None, force: bool=False) -> None` | Ensure embedded offset data for the requested executable is loaded. |

### `entrypoints/__init__.py`

_No top-level functions or direct class methods._

### `entrypoints/gui.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 11 | function | `build_parser() -> argparse.ArgumentParser` | Handles build parser behavior. |
| 22 | function | `main(argv: Sequence[str] \| None=None) -> int` | Handles main behavior. |

### `entrypoints/runtime_cleanup.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 12 | function | `delete_runtime_cache_dirs(root: Path \| None=None) -> tuple[int, int]` | Handles delete runtime cache dirs behavior. |

### `memory/__init__.py`

_No top-level functions or direct class methods._

### `memory/game_memory.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 35 | method | `GameMemory.__init__(self, module_name: str=MODULE_NAME)` | Handles init behavior. |
| 42 | method | `GameMemory._detect_pointer_size(self, handle: wintypes.HANDLE \| None) -> int` | Handles detect pointer size behavior. |
| 86 | method | `GameMemory.detect_running_module_name(preferred_module: str \| None=None) -> str \| None` | Handles detect running module name behavior. |
| 110 | method | `GameMemory.find_pid(self) -> int \| None` | Handles find pid behavior. |
| 123 | method | `GameMemory.open_process(self) -> bool` | Open the game process and resolve its base address. |
| 150 | method | `GameMemory.close(self) -> None` | Close any open process handle and reset state. |
| 162 | method | `GameMemory._get_module_base(self, pid: int, module_name: str) -> int \| None` | Handles get module base behavior. |
| 186 | method | `GameMemory._check_open(self, op: str \| None=None, addr: int \| None=None, length: int \| None=None) -> None` | Handles check open behavior. |
| 190 | method | `GameMemory.read_bytes(self, addr: int, length: int) -> bytes` | Read length bytes from absolute address addr. |
| 203 | method | `GameMemory.write_bytes(self, addr: int, data: bytes) -> None` | Write data to absolute address addr. |
| 216 | method | `GameMemory.write_pointer(self, addr: int, value: int) -> None` | Write a pointer-sized value to absolute address addr. |
| 225 | method | `GameMemory.read_uint32(self, addr: int) -> int` | Handles read uint32 behavior. |
| 229 | method | `GameMemory.write_uint32(self, addr: int, value: int) -> None` | Handles write uint32 behavior. |
| 233 | method | `GameMemory.read_u64(self, addr: int) -> int` | Handles read u64 behavior. |
| 237 | method | `GameMemory.read_wstring(self, addr: int, max_chars: int) -> str` | Read a UTF-16LE string of at most max_chars characters from addr. |
| 249 | method | `GameMemory.write_wstring_fixed(self, addr: int, value: str, max_chars: int) -> None` | Write a fixed length null-terminated UTF-16LE string at addr. |
| 257 | method | `GameMemory.read_ascii(self, addr: int, max_chars: int) -> str` | Read an ASCII string of up to max_chars bytes from addr. |
| 269 | method | `GameMemory.write_ascii_fixed(self, addr: int, value: str, max_chars: int) -> None` | Write a fixed length null-terminated ASCII string at addr. |

### `memory/win32.py`

_No top-level functions or direct class methods._

### `models/__init__.py`

_No top-level functions or direct class methods._

### `models/data_model.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 83 | function | `target_display_label(executable: str \| None) -> str` | Handles target display label behavior. |
| 100 | method | `FieldEntry.normalized_name(self) -> str` | Handles normalized name behavior. |
| 104 | method | `FieldEntry.display_name(self) -> str` | Handles display name behavior. |
| 116 | method | `RecordListItem.display_label(self) -> str` | Handles display label behavior. |
| 120 | function | `_iter_layout_fields(domain: str, layout: dict[str, Any]) -> Iterable[FieldEntry]` | Handles iter layout fields behavior. |
| 140 | function | `record_address(*, base: int, index: int, stride: int) -> int` | Return the absolute record address for a zero-based record number. |
| 149 | function | `_field_offset(payload: dict[str, Any]) -> int` | Handles field offset behavior. |
| 155 | function | `_type_key(payload: dict[str, Any]) -> str` | Handles type key behavior. |
| 159 | function | `_implemented_payload(payload: dict[str, Any]) -> bool` | Handles implemented payload behavior. |
| 186 | function | `_numeric_width(payload: dict[str, Any]) -> int` | Handles numeric width behavior. |
| 196 | function | `_bit_window(payload: dict[str, Any]) -> tuple[int, int, int]` | Handles bit window behavior. |
| 205 | function | `_read_bitfield(memory: Any, address: int, payload: dict[str, Any]) -> int` | Handles read bitfield behavior. |
| 212 | function | `_write_bitfield(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | Handles write bitfield behavior. |
| 220 | function | `_field_identity(value: object) -> str` | Handles field identity behavior. |
| 224 | function | `_field_display_or_name(field: dict[str, Any]) -> str` | Handles field display or name behavior. |
| 228 | function | `_uses_bitfield_io(payload: dict[str, Any]) -> bool` | Handles uses bitfield io behavior. |
| 236 | function | `_list_mapping_value(raw_value: Any, options: object) -> Any \| None` | Handles list mapping value behavior. |
| 248 | function | `_reverse_list_mapping(value: Any, options: object) -> int \| None` | Handles reverse list mapping behavior. |
| 258 | function | `_mapped_display_value(payload: dict[str, Any], raw_value: Any) -> Any \| None` | Handles mapped display value behavior. |
| 277 | function | `_mapped_raw_value(payload: dict[str, Any], value: Any) -> Any \| None` | Handles mapped raw value behavior. |
| 293 | function | `_raw_to_display_value(section: str, field: dict[str, Any], payload: dict[str, Any], raw_value: Any) -> Any` | Handles raw to display value behavior. |
| 319 | function | `_display_to_raw_value(section: str, field: dict[str, Any], payload: dict[str, Any], value: Any) -> Any` | Handles display to raw value behavior. |
| 350 | function | `_string_length(payload: dict[str, Any]) -> int` | Handles string length behavior. |
| 357 | function | `_read_string(memory: Any, address: int, payload: dict[str, Any]) -> str` | Handles read string behavior. |
| 367 | function | `_write_string(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | Handles write string behavior. |
| 380 | function | `_read_authored_value(memory: Any, address: int, payload: dict[str, Any]) -> Any` | Handles read authored value behavior. |
| 416 | function | `_write_authored_value(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None` | Handles write authored value behavior. |
| 459 | method | `EditorDataModel.__init__(self, *, memory: GameMemory \| Any \| None=None, offsets_api: Any=offsets_mod, target_executable: str \| None=None) -> None` | Handles init behavior. |
| 485 | method | `EditorDataModel._active_config(self) -> dict[str, Any]` | Handles active config behavior. |
| 489 | method | `EditorDataModel._domain_base_key(self, domain: str) -> str` | Handles domain base key behavior. |
| 494 | method | `EditorDataModel._domain_stride_key(self, domain: str) -> str` | Handles domain stride key behavior. |
| 501 | method | `EditorDataModel.editor_layout(self, domain: str) -> dict[str, Any]` | Handles editor layout behavior. |
| 507 | method | `EditorDataModel._layout_entries(self, domain: str) -> tuple[FieldEntry, ...]` | Handles layout entries behavior. |
| 512 | method | `EditorDataModel._field_lookup(self, domain: str) -> dict[str, FieldEntry]` | Handles field lookup behavior. |
| 525 | method | `EditorDataModel._field_context_map(self, domain: str) -> dict[int, tuple[str, str]]` | Handles field context map behavior. |
| 530 | method | `EditorDataModel._field_context(self, domain: str, field: dict[str, Any]) -> tuple[str, str]` | Handles field context behavior. |
| 543 | method | `EditorDataModel._field_by_display_or_normalized_name(self, domain: str, name: object) -> FieldEntry \| None` | Handles field by display or normalized name behavior. |
| 546 | method | `EditorDataModel._field_address(self, domain: str, record_addr: int, field: dict[str, Any], payload: dict[str, Any]) -> int` | Handles field address behavior. |
| 567 | method | `EditorDataModel.attach(self) -> bool` | Handles attach behavior. |
| 577 | method | `EditorDataModel.runtime_status_text(self) -> str` | Handles runtime status text behavior. |
| 583 | method | `EditorDataModel.select_target_executable(self, executable: str) -> None` | Handles select target executable behavior. |
| 598 | method | `EditorDataModel.domain_status(self, domain: str) -> str` | Handles domain status behavior. |
| 601 | method | `EditorDataModel.domain_item_labels(self, domain: str) -> list[str]` | Handles domain item labels behavior. |
| 604 | method | `EditorDataModel.domain_item_count(self, domain: str) -> int` | Handles domain item count behavior. |
| 607 | method | `EditorDataModel.selected_item(self, domain: str) -> RecordListItem \| None` | Handles selected item behavior. |
| 610 | method | `EditorDataModel.select_item_by_label(self, domain: str, selected_label: str \| None) -> RecordListItem \| None` | Handles select item by label behavior. |
| 615 | method | `EditorDataModel.refresh_domain_items(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | Handles refresh domain items behavior. |
| 636 | method | `EditorDataModel.start_background_refresh(self, domains: tuple[str, ...]) -> bool` | Handles start background refresh behavior. |
| 643 | method | `EditorDataModel._background_refresh_worker(self, domains: tuple[str, ...]) -> None` | Handles background refresh worker behavior. |
| 657 | method | `EditorDataModel.pop_refresh_events(self) -> list[tuple[str, str]]` | Handles pop refresh events behavior. |
| 665 | method | `EditorDataModel.player_detail_labels(self) -> tuple[str, ...]` | Handles player detail labels behavior. |
| 668 | method | `EditorDataModel.team_summary_labels(self) -> tuple[str, ...]` | Handles team summary labels behavior. |
| 671 | method | `EditorDataModel._read_named_value(self, domain: str, item: RecordListItem \| None, candidates: tuple[str, ...]) -> str` | Handles read named value behavior. |
| 685 | method | `EditorDataModel.selected_player_detail_values(self) -> dict[str, str]` | Handles selected player detail values behavior. |
| 689 | method | `EditorDataModel.selected_team_summary_values(self) -> dict[str, str]` | Handles selected team summary values behavior. |
| 693 | method | `EditorDataModel.save_selected_team_summary(self, values: dict[str, str]) -> tuple[int, int]` | Handles save selected team summary behavior. |
| 715 | method | `EditorDataModel.selected_detail_title(self, domain: str, label: str) -> str` | Handles selected detail title behavior. |
| 719 | method | `EditorDataModel.selected_record_address_text(self, domain: str) -> str` | Handles selected record address text behavior. |
| 723 | method | `EditorDataModel.grouped_fields(self, domain: str) -> OrderedDict[str, OrderedDict[str, list[FieldEntry]]]` | Handles grouped fields behavior. |
| 733 | method | `EditorDataModel._field_by_normalized_name(self, domain: str, name: str) -> FieldEntry \| None` | Handles field by normalized name behavior. |
| 736 | method | `EditorDataModel._label_entries(self, domain: str) -> list[FieldEntry]` | Handles label entries behavior. |
| 746 | method | `EditorDataModel._read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]` | Handles read field at record address behavior. |
| 761 | method | `EditorDataModel._label_for_record_address(self, domain: str, index: int, record_addr: int, label_entries: list[FieldEntry]) -> str` | Handles label for record address behavior. |
| 770 | method | `EditorDataModel._label_for_index(self, domain: str, index: int) -> str` | Handles label for index behavior. |
| 773 | method | `EditorDataModel.scan_records(self, domain: str, *, limit: int \| None=None) -> list[RecordListItem]` | Handles scan records behavior. |
| 794 | method | `EditorDataModel.read_entry_value(self, entry: FieldEntry, *, index: int) -> dict[str, Any]` | Handles read entry value behavior. |
| 797 | method | `EditorDataModel.write_entry_value(self, entry: FieldEntry, *, index: int, value: Any) -> dict[str, Any]` | Handles write entry value behavior. |
| 800 | method | `EditorDataModel.section_fields(self, domain: str, section: str, group: str) -> list[dict[str, Any]]` | Handles section fields behavior. |
| 815 | method | `EditorDataModel.domain_base(self, domain: str) -> int` | Handles domain base behavior. |
| 839 | method | `EditorDataModel.domain_stride(self, domain: str) -> int` | Handles domain stride behavior. |
| 850 | method | `EditorDataModel.record_address(self, domain: str, index: int) -> int` | Handles record address behavior. |
| 853 | method | `EditorDataModel._field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]` | Handles field version payload behavior. |
| 865 | method | `EditorDataModel._field_offset(self, field: dict[str, Any]) -> int` | Handles field offset behavior. |
| 868 | method | `EditorDataModel.read_value(self, domain: str, *, index: int, field: dict[str, Any]) -> dict[str, Any]` | Handles read value behavior. |
| 883 | method | `EditorDataModel.write_value(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> None` | Handles write value behavior. |
| 892 | method | `EditorDataModel.write_and_readback(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> dict[str, Any]` | Handles write and readback behavior. |
| 897 | function | `verify_edits(*, target_executable: str \| None=None) -> dict[str, Any]` | Handles verify edits behavior. |

### `ui/__init__.py`

_No top-level functions or direct class methods._

### `ui/dpg_editor.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 35 | function | `_tag(*parts: object) -> str` | Handles tag behavior. |
| 39 | function | `_target_executable(label: str) -> str` | Handles target executable behavior. |
| 45 | method | `DpgEditorApp.__init__(self, model: EditorDataModel) -> None` | Handles init behavior. |
| 53 | method | `DpgEditorApp._screen_tag(self, domain: str) -> str` | Handles screen tag behavior. |
| 56 | method | `DpgEditorApp._app_screen_tag(self, screen: str) -> str` | Handles app screen tag behavior. |
| 59 | method | `DpgEditorApp._home_status_tag(self) -> str` | Handles home status tag behavior. |
| 62 | method | `DpgEditorApp._home_target_status_tag(self) -> str` | Handles home target status tag behavior. |
| 65 | method | `DpgEditorApp._status_tag(self, domain: str) -> str` | Handles status tag behavior. |
| 68 | method | `DpgEditorApp._count_tag(self, domain: str) -> str` | Handles count tag behavior. |
| 71 | method | `DpgEditorApp._list_tag(self, domain: str) -> str` | Handles list tag behavior. |
| 74 | method | `DpgEditorApp._record_list_rows_for_height(self, viewport_height: int) -> int` | Handles record list rows for height behavior. |
| 77 | method | `DpgEditorApp._resize_record_lists(self, dpg: Any) -> None` | Handles resize record lists behavior. |
| 85 | method | `DpgEditorApp._detail_tag(self, domain: str, name: str) -> str` | Handles detail tag behavior. |
| 88 | method | `DpgEditorApp._team_input_tag(self, label: str) -> str` | Handles team input tag behavior. |
| 91 | method | `DpgEditorApp._nav_tag(self, screen: str) -> str` | Handles nav tag behavior. |
| 94 | method | `DpgEditorApp._display_label(self, domain: str) -> str` | Handles display label behavior. |
| 97 | method | `DpgEditorApp._game_status_text(self) -> str` | Handles game status text behavior. |
| 100 | method | `DpgEditorApp._safe_set(self, dpg: Any, tag: str, value: object) -> None` | Handles safe set behavior. |
| 104 | method | `DpgEditorApp._safe_configure(self, dpg: Any, tag: str, **kwargs: object) -> None` | Handles safe configure behavior. |
| 108 | method | `DpgEditorApp._bind_item_theme(self, dpg: Any, item: str, theme: str) -> None` | Handles bind item theme behavior. |
| 112 | method | `DpgEditorApp._refresh_nav_state(self, dpg: Any) -> None` | Handles refresh nav state behavior. |
| 117 | method | `DpgEditorApp._show_screen(self, dpg: Any, domain: str) -> None` | Handles show screen behavior. |
| 125 | method | `DpgEditorApp._set_target(self, dpg: Any, selected: str) -> None` | Handles set target behavior. |
| 131 | method | `DpgEditorApp._refresh_status_labels(self, dpg: Any) -> None` | Handles refresh status labels behavior. |
| 139 | method | `DpgEditorApp._attach(self, dpg: Any) -> None` | Handles attach behavior. |
| 143 | method | `DpgEditorApp._attach_and_scan(self, dpg: Any, domain: str) -> None` | Handles attach and scan behavior. |
| 146 | method | `DpgEditorApp._attach_and_load_all(self, dpg: Any) -> None` | Handles attach and load all behavior. |
| 149 | method | `DpgEditorApp._start_background_scan(self, dpg: Any, domains: tuple[str, ...]) -> None` | Handles start background scan behavior. |
| 157 | method | `DpgEditorApp._poll_background_scan(self, dpg: Any) -> None` | Handles poll background scan behavior. |
| 172 | method | `DpgEditorApp._sync_domain_list(self, dpg: Any, domain: str) -> None` | Handles sync domain list behavior. |
| 182 | method | `DpgEditorApp._select_current(self, dpg: Any, domain: str, selected_label: str \| None=None) -> None` | Handles select current behavior. |
| 187 | method | `DpgEditorApp._open_selected(self, dpg: Any, domain: str) -> None` | Handles open selected behavior. |
| 194 | method | `DpgEditorApp._update_detail_panel(self, dpg: Any, domain: str) -> None` | Handles update detail panel behavior. |
| 208 | method | `DpgEditorApp._save_team_summary(self, dpg: Any) -> None` | Handles save team summary behavior. |
| 217 | method | `DpgEditorApp._row_current_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | Handles row current tag behavior. |
| 220 | method | `DpgEditorApp._row_new_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | Handles row new tag behavior. |
| 223 | method | `DpgEditorApp._row_status_tag(self, item: RecordListItem, entry: FieldEntry) -> str` | Handles row status tag behavior. |
| 226 | method | `DpgEditorApp._editor_status_tag(self, item: RecordListItem) -> str` | Handles editor status tag behavior. |
| 229 | method | `DpgEditorApp._load_item_editor(self, dpg: Any, item: RecordListItem) -> None` | Handles load item editor behavior. |
| 250 | method | `DpgEditorApp._save_item_editor(self, dpg: Any, item: RecordListItem) -> None` | Handles save item editor behavior. |
| 273 | method | `DpgEditorApp._open_editor_window(self, dpg: Any, item: RecordListItem) -> None` | Handles open editor window behavior. |
| 319 | method | `DpgEditorApp._add_nav_button(self, dpg: Any, screen: str, label: str) -> None` | Handles add nav button behavior. |
| 325 | method | `DpgEditorApp._add_detail_row(self, dpg: Any, label: str, value_tag: str, *, accent: bool=False) -> None` | Handles add detail row behavior. |
| 333 | method | `DpgEditorApp._build_home_screen(self, dpg: Any, *, show: bool=True) -> None` | Handles build home screen behavior. |
| 351 | method | `DpgEditorApp._build_players_screen(self, dpg: Any, *, show: bool=False) -> None` | Handles build players screen behavior. |
| 377 | method | `DpgEditorApp._build_teams_screen(self, dpg: Any, *, show: bool=False) -> None` | Handles build teams screen behavior. |
| 407 | method | `DpgEditorApp._build_domain_screen(self, dpg: Any, domain: str, *, show: bool=False) -> None` | Handles build domain screen behavior. |
| 436 | method | `DpgEditorApp.run(self, *, close_after_frames: int \| None=None, load_on_start: bool=True) -> None` | Handles run behavior. |

### `ui/theme.py`

| Line | Kind | Function | What it does |
|---:|---|---|---|
| 30 | function | `to_rgba(hex_color: str, alpha: int=255) -> tuple[int, int, int, int]` | Convert exact '#RRGGBB' hex to an RGBA tuple. |
| 40 | function | `apply_base_theme() -> str` | Create and bind the base Dear PyGui theme. |
| 127 | function | `ensure_editor_themes() -> dict[str, str]` | Create reusable item themes for the compact editor shell. |
