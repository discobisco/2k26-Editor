# core folder

This folder holds the editor's shared infrastructure: configuration, offset
loading, conversions, dynamic base scanning, logging, and extension hooks.

## Configuration (config.py)
- App identity: `APP_NAME`, `APP_VERSION`.
- Paths: `BASE_DIR`, `LOG_DIR`, `CONFIG_DIR`, `CACHE_DIR`.
- Runtime files: `AI_SETTINGS_PATH`, `AUTOLOAD_EXT_FILE`.
- Offsets bundle list: `DEFAULT_OFFSET_FILES`.
- Game targeting: `MODULE_NAME`, `HOOK_TARGETS`, `HOOK_TARGET_LABELS`,
  `ALLOWED_MODULE_NAMES`.
- COY defaults: `COY_SHEET_ID`, `COY_SHEET_TABS`, `COY_TENDENCY_AVERAGE_TAB`.
- UI palette: shared colors consumed by Tk widgets and theme helpers.

## Offsets system (offsets.py)
- Loads the merged offsets bundle from `Offsets\offsets.json`.
- Normalizes field and category names using `OFFSET_FIELD_SYNONYMS`,
  `CATEGORY_ALIASES`, and `FIELD_NAME_ALIASES`.
- Supports multiple schema shapes, merged bundles, and legacy pointer formats.
- Builds pointer chain configs with:
  - `steps` (offset + dereference flags)
  - `final_offset`/`finalOffset`
  - `absolute`/`isAbsolute`
  - `direct_table`
- Populates module-level constants (stride sizes, base pointers, name offsets,
  max counts, panel field definitions, import orders).
- `_derive_offset_candidates()` probes common filenames such as
  `2k26_offsets.json` before falling back to `DEFAULT_OFFSET_FILES`.
- `initialize_offsets(target_executable, force=True)` is invoked by the GUI
  entrypoint and after dynamic base scans. It tracks the active offset file in
  `_offset_file_path` and target in `_current_offset_target`.
- Raises `OffsetSchemaError` when required schema components are missing.

## COY import layouts (offsets.py)
- `COY_IMPORT_LAYOUTS` defines column positions for Attributes, Tendencies,
  Durability, and Potential imports.
- `COY_ATTR_COLUMN_HEADERS` limits Attributes to the HSTL column (columns B-AJ).

## Dynamic base scanning (dynamic_bases.py)
- Uses Win32 APIs (and optional `psutil`) to locate the running game process.
- Scans memory for player/team name patterns to infer base addresses.
- Supports ranged scans and optional thread pool parallelism.
- Returns candidate bases plus a report used by the UI and extensions.

## Conversions (conversions.py)
- Rating conversions between raw bitfields and 25-99 display values.
- Min/max potential conversions for 40-99 ranges.
- Height conversions between inches and raw memory format.
- Weight helpers (`read_weight`/`write_weight`) for float32 values.
- Utility parsing: `to_int()` accepts decimal or hex strings.

## Extensions (extensions.py)
- Registers player panel and full editor extension callbacks.
- Reads/writes `autoload_extensions.json` for persistent autoload lists.

## Logging (logging.py)
- `get_memory_logger()` configures `logs\memory.log` with UTC timestamps and
  avoids duplicate handlers.

## Files
- `__init__.py`: package marker.
- `config.py`: shared constants and paths.
- `conversions.py`: rating, height, and tendency conversions.
- `dynamic_bases.py`: runtime base address scanning.
- `extensions.py`: extension registration and autoload list helpers.
- `logging.py`: log setup for memory operations.
- `offsets.py`: offsets schema loading and normalization.
- `README.md`: this document.

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
