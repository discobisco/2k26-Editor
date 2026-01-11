# Offsets folder

This folder is the data backbone for the editor. It stores the merged offsets
bundle plus the Excel reference workbooks and import templates used by the
import/export pipelines.

## How the editor uses this folder
- `core.offsets.initialize_offsets()` loads `Offsets\offsets.json` and populates
  module-level constants (stride sizes, base pointers, name offsets, category
  lists).
- `models.data_model` consumes those constants for live memory reads/writes and
  for building the UI category definitions.
- `importing.excel_import` validates Excel sheets against the bundled templates
  stored in this folder.
- `NBA2K26Editor.spec` bundles this folder into the packaged application.

## offsets.json (merged offsets bundle)
Top-level keys:
- `source_files`: maps version labels to original offsets filenames.
- `category_normalization` and `super_type_map`: normalize categories and map
  them into UI super-types (Players, Teams, Staff, Stadiums).
- `versions`: per-version metadata with `game_info` and `base_pointers`.
- `offsets`: list of normalized field definitions used by the editor.

Base pointer entries (under `versions.*.base_pointers`) include:
- `address`: base pointer address (absolute).
- `chain`: pointer chain steps (empty list for direct pointers).
- Optional flags handled by the loader: `absolute`, `direct_table`,
  `finalOffset`/`final_offset`.

Each `offsets` entry contains:
- `canonical_category`, `super_type`, `normalized_name`, `display_name`,
  `variant_names`.
- `versions`: per-version field specs with keys like `category`, `name`,
  `address`/`hex`, `length`, `type`, and `startBit`.
- Optional dereference metadata: `requiresDereference`, `dereferenceAddress`.

Field spec notes:
- `address` is the byte offset relative to the record base (player/team/etc).
- `length` is typically a bit length for bitfields or byte length for strings.
- `startBit` applies to bitfield entries.
- `type` values include `Integer`, `Float`, `String`, `WString`, `Pointer`,
  `combo`, `slider`, and `number`.

## Import/export templates
These spreadsheets match the exact column names used by import/export flows:
- `ImportPlayers.xlsx`
- `ImportTeams.xlsx`
- `ImportStaff.xlsx`
- `ImportStadiums.xlsx`

## Custom offsets workflow
- Use the Home screen "Load Offsets" action to load a custom offsets JSON.
- `_derive_offset_candidates()` probes per-version names such as
  `2k26_offsets.json` before falling back to `DEFAULT_OFFSET_FILES`.
- After loading, UI categories and field metadata are rebuilt on the fly.
