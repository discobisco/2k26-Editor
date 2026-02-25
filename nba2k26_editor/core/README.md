# core folder

## Responsibilities
- Offsets, config, perf, and extension infrastructure.
- Owns direct Python files: `__init__.py`, `config.py`, `conversions.py`, `extensions.py`, `import_map.py`, `offset_cache.py`, `offset_loader.py`, `offset_resolver.py`, `offsets.py`, `perf.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Offsets, config, perf, and extension infrastructure.
This folder currently has 10 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Startup path in `nba2k_editor/entrypoints/gui.py` depends on this folder.
- `nba2k_editor/models/data_model.py` consumes resolved offsets metadata.

## Function Tree
### `__init__.py`
- No callable definitions.

### `config.py`
- No callable definitions.

### `conversions.py`
- [def] conversions.py::_normalize_year_key
- [def] conversions.py::is_year_offset_field
- [def] conversions.py::convert_raw_to_year
- [def] conversions.py::convert_year_to_raw
- [def] conversions.py::convert_raw_to_rating
- [def] conversions.py::convert_rating_to_raw
- [def] conversions.py::convert_minmax_potential_to_raw
- [def] conversions.py::convert_raw_to_minmax_potential
- [def] conversions.py::read_weight
- [def] conversions.py::write_weight
- [def] conversions.py::raw_height_to_inches
- [def] conversions.py::height_inches_to_raw
- [def] conversions.py::format_height_inches
- [def] conversions.py::convert_tendency_raw_to_rating
- [def] conversions.py::convert_rating_to_tendency_raw
- [def] conversions.py::to_int

### `extensions.py`
- [def] extensions.py::register_player_panel_extension
- [def] extensions.py::register_full_editor_extension
- [def] extensions.py::load_autoload_extensions
- [def] extensions.py::save_autoload_extensions

### `import_map.py`
- [def] import_map.py::_read_text
- [def] import_map.py::_module_name_for
- [def] import_map.py::build_import_map
- [def] import_map.py::write_import_report

### `offset_cache.py`
  - [def] offset_cache.py::OffsetCache.__init__
  - [def] offset_cache.py::OffsetCache.get_target
  - [def] offset_cache.py::OffsetCache.set_target
  - [def] offset_cache.py::OffsetCache.get_json
  - [def] offset_cache.py::OffsetCache.set_json
  - [def] offset_cache.py::OffsetCache.get_dropdowns
  - [def] offset_cache.py::OffsetCache.set_dropdowns
  - [def] offset_cache.py::OffsetCache.invalidate_target
  - [def] offset_cache.py::OffsetCache.clear

### `offset_loader.py`
  - [def] offset_loader.py::OffsetRepository.__init__
  - [def] offset_loader.py::OffsetRepository.load_offsets
  - [def] offset_loader.py::OffsetRepository.load_dropdowns
  - [def] offset_loader.py::OffsetRepository._load_raw_json
  - [def] offset_loader.py::OffsetRepository._parse_dropdowns

### `offset_resolver.py`
  - [def] offset_resolver.py::OffsetResolver.__init__
  - [def] offset_resolver.py::OffsetResolver.resolve
  - [def] offset_resolver.py::OffsetResolver.require_dict

### `offsets.py`
- [def] offsets.py::_derive_offset_candidates
- [def] offsets.py::_split_version_tokens
- [def] offsets.py::_version_key_matches
- [def] offsets.py::_select_version_entry
- [def] offsets.py::_infer_length_bits
- [def] offsets.py::_normalize_offset_type
- [def] offsets.py::_read_json_cached
- [def] offsets.py::_build_dropdown_values_index
- [def] offsets.py::_resolve_split_category
- [def] offsets.py::_collect_split_leaf_nodes
- [def] offsets.py::_append_split_domain_entries
- [def] offsets.py::_build_split_offsets_payload
- [def] offsets.py::_select_merged_offset_entry
- [def] offsets.py::_build_player_stats_relations
  - [def] offsets.py::_build_player_stats_relations._entry_sort_key
  - [def] offsets.py::_build_player_stats_relations._id_sort_key
- [def] offsets.py::_extract_player_stats_relations
- [def] offsets.py::_sync_player_stats_relations
- [def] offsets.py::_convert_merged_offsets_schema
  - [def] offsets.py::_convert_merged_offsets_schema._record_skip
- [def] offsets.py::_load_offset_config_file
- [def] offsets.py::_build_offset_index
- [def] offsets.py::_find_offset_entry
- [def] offsets.py::_find_offset_entry_by_normalized
- [def] offsets.py::_load_dropdowns_map
- [def] offsets.py::_derive_version_label
- [def] offsets.py::_resolve_version_context
- [def] offsets.py::_load_categories
  - [def] offsets.py::_load_categories._emit_super_type_warnings
  - [def] offsets.py::_load_categories._register_category_metadata
  - [def] offsets.py::_load_categories._finalize_field_metadata
  - [def] offsets.py::_load_categories._entry_to_field
  - [def] offsets.py::_load_categories._humanize_label
  - [def] offsets.py::_load_categories._template_entry_to_field
  - [def] offsets.py::_load_categories._compose_field_prefix
  - [def] offsets.py::_load_categories._convert_template_payload
  - [def] offsets.py::_load_categories._merge_extra_template_files
  - [def] offsets.py::_load_categories._extend
  - [def] offsets.py::_load_categories._append_field
  - [def] offsets.py::_load_categories._walk_field_map
- [def] offsets.py::_normalize_chain_steps
- [def] offsets.py::_parse_pointer_chain_config
- [def] offsets.py::_extend_pointer_candidates
- [def] offsets.py::_apply_offset_config
  - [def] offsets.py::_apply_offset_config._pointer_address
  - [def] offsets.py::_apply_offset_config._require_field
- [def] offsets.py::initialize_offsets

### `perf.py`
- [def] perf.py::is_enabled
- [def] perf.py::record_duration
- [def] perf.py::timed
- [def] perf.py::time_call
- [def] perf.py::clear
- [def] perf.py::snapshot
- [def] perf.py::summarize

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
