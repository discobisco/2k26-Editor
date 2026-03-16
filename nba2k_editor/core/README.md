# core folder

## Responsibilities
- Owns shared editor infrastructure: config, conversions, perf helpers, extension loading, import-map/code-sync utilities, and the offsets runtime/facade.
- Houses the split-offsets loading pipeline and the compatibility surface that the rest of the repo still imports as `nba2k_editor.core.offsets`.
- Provides low-level services consumed by entrypoints, models, importing, and UI.

## Current module layout
Direct Python modules in this folder:
- `__init__.py`
- `code_sync.py`
- `config.py`
- `conversions.py`
- `extensions.py`
- `import_map.py`
- `offset_bundle.py`
- `offset_cache.py`
- `offset_categories.py`
- `offset_index_queries.py`
- `offset_loader.py`
- `offset_resolver.py`
- `offset_runtime_apply.py`
- `offset_runtime_support.py`
- `offsets.py`
- `perf.py`

## Offsets architecture
The current offsets system is split internally, but still exposed through one public facade.

### Internal split
- `offset_bundle.py`
  - Reads and normalizes the split bundle rooted at `Offsets/offsets_league.json` plus `offsets_*.json` domain files.
  - Selects the active version payload for the requested executable.
  - Produces the merged runtime payload used by the rest of the editor.
- `offset_categories.py`
  - Builds UI/model category bundles from the active offsets payload.
  - Derives category metadata, canonical names, dropdown-backed fields, and field descriptors.
- `offset_runtime_support.py`
  - Provides version-label derivation, version-context lookup, and pointer-chain parsing helpers.
- `offset_runtime_apply.py`
  - Validates the active offsets payload and computes the runtime scalar/chain/mapping updates that get installed into the facade globals.
- `offset_index_queries.py`
  - Builds and queries the exact-match / normalized / hierarchy indexes over selected offset entries.
- `offset_loader.py`
  - Handles file discovery, JSON parsing, and dropdown loading.
- `offset_cache.py`
  - Caches loaded JSON/dropdowns by target and path.
- `offset_resolver.py`
  - Small schema-resolution seam used by tests/services when normalizing raw offset payloads.

### Public facade
- `offsets.py`
  - Remains the compatibility boundary for the rest of the repo.
  - Imports the helper modules above, owns the mutable process-wide runtime state, and re-exports the functions/constants most callers still use.
  - Key public entry points include:
    - `initialize_offsets(...)`
    - `has_active_config()`
    - `get_current_target()`
    - `get_offset_file_path()`
    - `get_offset_category_metadata()`
    - `load_category_bundle()`
    - `get_version_context(...)`
    - `parse_pointer_chain_config(...)`
    - `get_league_category_pointer_map()`
    - `get_league_pointer_meta(...)`
    - `find_offset_entry(...)`

## Runtime/data flow
1. Startup/UI/model code calls into `core.offsets`.
2. `offsets.py` loads the split bundle through `offset_loader.py` + `offset_bundle.py`.
3. The selected payload is validated/applied through `offset_runtime_apply.py` and installed into facade-owned globals.
4. Category/index helpers build derived views used by UI and model consumers.
5. Downstream code continues to read the public facade surface, even though most parsing/build logic now lives in helper modules.

## Key boundaries
- `config.py`: app constants, paths, hook target defaults.
- `conversions.py`: raw-value <-> UI-value conversions and coercion helpers.
- `perf.py`: lightweight timing and profiling helpers used across startup/model/import flows.
- `extensions.py`: registration/autoload persistence for extension hooks.
- `code_sync.py`: stores and validates runtime-module fingerprints inside `Offsets/offsets_league.json`.
- `import_map.py`: import graph/report helper for repo hygiene work.

## Integration points
- Entry points in `nba2k_editor/entrypoints/` initialize offsets through `core.offsets`.
- `nba2k_editor/models/data_model.py` consumes the facade constants plus category/pointer helpers.
- UI modules and import flows still import runtime constants directly from `core.offsets`.
- Tests exercise both the extracted helpers and the facade compatibility surface.

## Notes for future cleanup
- The major extraction already happened: bundle parsing, category assembly, runtime apply, pointer support, and index lookups are no longer all implemented inline in `offsets.py`.
- The remaining architectural debt is mostly that `offsets.py` is still the mutable global runtime registry and compatibility facade for the repo.
- If core cleanup continues, the leverage-positive move is shrinking direct consumer dependence on facade globals rather than splitting more helper files.
