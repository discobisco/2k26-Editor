# importing folder

## Responsibilities
- Excel import/export mapping and workflow implementation.
- Owns direct Python files: `__init__.py`, `excel_import.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Excel import/export mapping and workflow implementation.
This folder currently has 2 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Triggered from Excel workflows in `nba2k_editor/ui/app.py`.
- Reads/writes through `nba2k_editor/models/data_model.py`.

## Function Tree
### `__init__.py`
- No callable definitions.

### `excel_import.py`
  - [def] excel_import.py::_RecordSnapshot.record_view
- [def] excel_import.py::_build_player_snapshot
- [def] excel_import.py::_decode_string_from_record
- [def] excel_import.py::_decode_float_from_record
- [def] excel_import.py::_decode_bits_from_record
- [def] excel_import.py::_decode_field_value_from_record
  - [def] excel_import.py::ImportResult.summary_text
  - [def] excel_import.py::ExportResult.summary_text
- [def] excel_import.py::template_path_for
- [def] excel_import.py::_ensure_openpyxl
- [def] excel_import.py::_sanitize_excel_value
- [def] excel_import.py::_header_text
- [def] excel_import.py::_field_text
- [def] excel_import.py::_header_candidates
- [def] excel_import.py::_preferred_categories
- [def] excel_import.py::_build_field_lookup
- [def] excel_import.py::_resolve_version_key
- [def] excel_import.py::_augment_with_display_aliases
- [def] excel_import.py::_map_headers
- [def] excel_import.py::_find_column
- [def] excel_import.py::_resolve_row_name
- [def] excel_import.py::_build_row_key_map
- [def] excel_import.py::_row_has_values
- [def] excel_import.py::_resolve_player
- [def] excel_import.py::_resolve_named_index
- [def] excel_import.py::import_excel_workbook
- [def] excel_import.py::export_excel_workbook
- [def] excel_import.py::import_players_from_excel
- [def] excel_import.py::import_teams_from_excel
- [def] excel_import.py::import_staff_from_excel
- [def] excel_import.py::import_stadiums_from_excel
- [def] excel_import.py::export_players_to_excel
- [def] excel_import.py::export_teams_to_excel
- [def] excel_import.py::export_staff_to_excel
- [def] excel_import.py::export_stadiums_to_excel

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
