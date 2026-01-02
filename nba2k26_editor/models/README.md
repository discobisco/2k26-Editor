# models folder

This folder contains the editor's data model and schema definitions for
players, teams, staff, and stadiums. It is the core engine that turns offsets
and memory access into UI-ready data and import/export flows.

## Key types
- `Player`: lightweight dataclass with identity and roster metadata.
- `FieldMetadata`: offsets/bitfield metadata used to build editors.
- `FieldWriteSpec`: tuple signature used for batch writes.
- `PreparedImportRows`: normalized import rows for CSV/Excel data.
- `ExportFieldSpec`: row metadata for long-form exports.

## PlayerDataModel (data_model.py)
The main model encapsulates live memory access and editor logic:

- Initialization:
  - Accepts a `GameMemory` instance and `max_players`.
  - Loads optional Cheat Engine team name mappings
    (`2K26 Team Data (10.18.24).txt`, `2K26 Team Data.txt`).
  - Calls `initialize_offsets()` and builds category definitions from offsets.
  - Loads categories even when the game is not running so the UI can render.
- Name normalization and search:
  - Normalizes diacritics, suffixes, punctuation, and aliases.
  - Builds multiple name variants for fuzzy matching and partial search.
- Live scanning:
  - Scans player, team, staff, stadium, and draft-class tables using offsets.
  - Validates pointer chains and name offsets to confirm bases.
  - Provides fallback roster scans when full-table scans fail.
- Field access:
  - Handles ASCII/UTF-16 fixed strings, floats, and bitfield math.
  - Converts ratings and tendencies to display scales and back.
  - Exposes typed accessors for players/teams/staff/stadiums.
- Import flows:
  - CSV import via `importing.csv_import.import_table`.
  - Excel import via `importing.excel_import.import_excel_workbook`.
  - Template XLSX support with optional match-by-name (Vitals sheet required).
  - COY (2KCOY) imports sanitize Attributes/Tendencies/Potential/Durability
    and can auto-download sheets via Google Sheet CSV URLs.
  - Tracks partial name matches in `import_partial_matches` for UI review.
- Export flows:
  - Per-category CSV export and multi-category directory export.
  - Raw player record dumps to `player_records\`.
  - Excel template export preserving bundled template structure.
  - Long-form offsets export with raw and display values.
- Team utilities:
  - Builds team display lists and supports edits via `TEAM_FIELD_DEFS`.
  - Scans team rosters and maps player pointers back to indices.
- Safety:
  - Tracks `external_loaded` to guard writes when using offline rosters.

## Files
- `__init__.py`: package marker.
- `player.py`: `Player` dataclass and helpers.
- `schema.py`: typed schema helpers and metadata containers.
- `data_model.py`: live memory model and import/export logic.
- `README.md`: this document.

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
