# models folder

## Responsibilities
- Primary data model and typed entity/schema abstractions.
- Owns direct Python files: `__init__.py`, `data_model.py`, `player.py`, `schema.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Primary data model and typed entity/schema abstractions.
This folder currently has 4 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Refresh and Cache Behavior
- `PlayerDataModel.refresh_players` reuses resolved table bases for the current process and avoids forced base re-resolution on every refresh.
- Base caches are explicitly invalidated when offsets change (for example, after offsets reload).
- Team-derived lookups (`team id -> display`, `display -> team id`, ordered team names) are cached and invalidated when `team_list` changes to reduce repeated recomputation in UI-heavy paths.
- Dirty flags remain the primary signal for when UI should request a fresh model scan.

## Integration Points
- Primary consumer is `nba2k_editor/ui` plus importing and live adapters.
- Depends on offsets metadata and memory layer services.

## Function Tree
Scope: direct Python files in this folder only. Child folder details are documented in their own READMEs.

### `__init__.py`
- No callable definitions.

### `data_model.py`
  - [def] data_model.py::PlayerDataModel.__init__
  - [def] data_model.py::PlayerDataModel.mark_dirty
  - [def] data_model.py::PlayerDataModel.clear_dirty
  - [def] data_model.py::PlayerDataModel.is_dirty
  - [def] data_model.py::PlayerDataModel._make_name_key
  - [def] data_model.py::PlayerDataModel._sync_offset_constants
  - [def] data_model.py::PlayerDataModel._resolve_name_fields
    - [def] data_model.py::PlayerDataModel._resolve_name_fields._string_enc_for_type
    - [def] data_model.py::PlayerDataModel._resolve_name_fields._build_field
    - [def] data_model.py::PlayerDataModel._resolve_name_fields._find_normalized_field
    - [def] data_model.py::PlayerDataModel._resolve_name_fields._log_field
  - [def] data_model.py::PlayerDataModel.invalidate_base_cache
  - [def] data_model.py::PlayerDataModel.prime_bases
  - [def] data_model.py::PlayerDataModel._strip_suffix_string
  - [def] data_model.py::PlayerDataModel._generate_name_keys
  - [def] data_model.py::PlayerDataModel._strip_diacritics
  - [def] data_model.py::PlayerDataModel._sanitize_name_token
  - [def] data_model.py::PlayerDataModel._strip_suffix_words
  - [def] data_model.py::PlayerDataModel._normalize_family_token
  - [def] data_model.py::PlayerDataModel._build_name_index_map
  - [def] data_model.py::PlayerDataModel._build_name_index_map_from_players
  - [def] data_model.py::PlayerDataModel._build_name_index_map_async
    - [def] data_model.py::PlayerDataModel._build_name_index_map_async._worker
  - [def] data_model.py::PlayerDataModel._match_name_tokens
  - [def] data_model.py::PlayerDataModel._candidate_name_pairs
    - [def] data_model.py::PlayerDataModel._candidate_name_pairs.add_pair
  - [def] data_model.py::PlayerDataModel.get_categories_for_super
  - [def] data_model.py::PlayerDataModel.get_league_categories
  - [def] data_model.py::PlayerDataModel._league_context
  - [def] data_model.py::PlayerDataModel._league_stride
  - [def] data_model.py::PlayerDataModel._league_pointer_meta
  - [def] data_model.py::PlayerDataModel._league_pointer_for_category
  - [def] data_model.py::PlayerDataModel._resolve_league_base
  - [def] data_model.py::PlayerDataModel.get_league_records
    - [def] data_model.py::PlayerDataModel.get_league_records._validator
  - [def] data_model.py::PlayerDataModel._expand_first_name_variants
    - [def] data_model.py::PlayerDataModel._expand_first_name_variants.add
  - [def] data_model.py::PlayerDataModel._expand_last_name_variants
    - [def] data_model.py::PlayerDataModel._expand_last_name_variants.add
  - [def] data_model.py::PlayerDataModel._name_variants
  - [def] data_model.py::PlayerDataModel._match_player_indices
  - [def] data_model.py::PlayerDataModel._token_similarity
  - [def] data_model.py::PlayerDataModel._rank_roster_candidates
  - [def] data_model.py::PlayerDataModel._partial_name_candidates
  - [def] data_model.py::PlayerDataModel.find_player_indices_by_name
  - [def] data_model.py::PlayerDataModel._normalize_field_name
  - [def] data_model.py::PlayerDataModel._normalize_header_name
  - [def] data_model.py::PlayerDataModel._reorder_categories
    - [def] data_model.py::PlayerDataModel._reorder_categories._normalize_field_name_local
    - [def] data_model.py::PlayerDataModel._reorder_categories._reorder_category
  - [def] data_model.py::PlayerDataModel.parse_team_comments
  - [def] data_model.py::PlayerDataModel._player_record_address
  - [def] data_model.py::PlayerDataModel._team_record_address
  - [def] data_model.py::PlayerDataModel._staff_record_address
  - [def] data_model.py::PlayerDataModel._stadium_record_address
  - [def] data_model.py::PlayerDataModel._resolve_pointer_from_chain
  - [def] data_model.py::PlayerDataModel._resolve_player_base_ptr
    - [def] data_model.py::PlayerDataModel._resolve_player_base_ptr._validate_player_table
  - [def] data_model.py::PlayerDataModel._resolve_player_table_base
  - [def] data_model.py::PlayerDataModel._resolve_team_base_ptr
    - [def] data_model.py::PlayerDataModel._resolve_team_base_ptr._is_valid_team_base
  - [def] data_model.py::PlayerDataModel._resolve_staff_base_ptr
    - [def] data_model.py::PlayerDataModel._resolve_staff_base_ptr._log
    - [def] data_model.py::PlayerDataModel._resolve_staff_base_ptr._is_valid_staff_base
  - [def] data_model.py::PlayerDataModel._direct_base_from_chain
  - [def] data_model.py::PlayerDataModel._resolve_stadium_base_ptr
    - [def] data_model.py::PlayerDataModel._resolve_stadium_base_ptr._is_valid_stadium_base
    - [def] data_model.py::PlayerDataModel._resolve_stadium_base_ptr._is_valid_stadium_base
  - [def] data_model.py::PlayerDataModel._scan_team_names
  - [def] data_model.py::PlayerDataModel.get_team_fields
  - [def] data_model.py::PlayerDataModel.set_team_fields
  - [def] data_model.py::PlayerDataModel._scan_all_players
    - [def] data_model.py::PlayerDataModel._scan_all_players._decode_string
    - [def] data_model.py::PlayerDataModel._scan_all_players._read_uint64
    - [def] data_model.py::PlayerDataModel._scan_all_players._read_uint32
    - [def] data_model.py::PlayerDataModel._scan_all_players._is_ascii_printable
  - [def] data_model.py::PlayerDataModel.scan_team_players
  - [def] data_model.py::PlayerDataModel._team_display_map
  - [def] data_model.py::PlayerDataModel._team_index_for_display_name
  - [def] data_model.py::PlayerDataModel._get_team_display_name
  - [def] data_model.py::PlayerDataModel.get_teams
    - [def] data_model.py::PlayerDataModel.get_teams._classify
  - [def] data_model.py::PlayerDataModel.refresh_staff
    - [def] data_model.py::PlayerDataModel.refresh_staff._read_field
  - [def] data_model.py::PlayerDataModel.get_staff
  - [def] data_model.py::PlayerDataModel.refresh_stadiums
    - [def] data_model.py::PlayerDataModel.refresh_stadiums._read_field
  - [def] data_model.py::PlayerDataModel.get_stadiums
  - [def] data_model.py::PlayerDataModel._build_team_display_list
  - [def] data_model.py::PlayerDataModel._ensure_team_entry
  - [def] data_model.py::PlayerDataModel._build_team_list_from_players
  - [def] data_model.py::PlayerDataModel._apply_team_display_to_players
  - [def] data_model.py::PlayerDataModel._read_panel_entry
  - [def] data_model.py::PlayerDataModel.get_player_panel_snapshot
  - [def] data_model.py::PlayerDataModel._collect_assigned_player_indexes
  - [def] data_model.py::PlayerDataModel.refresh_players
    - [def] data_model.py::PlayerDataModel.refresh_players._team_sort_key_pair
  - [def] data_model.py::PlayerDataModel.get_players_by_team
  - [def] data_model.py::PlayerDataModel.update_player
  - [def] data_model.py::PlayerDataModel.copy_player_data
  - [def] data_model.py::PlayerDataModel._normalize_encoding_tag
  - [def] data_model.py::PlayerDataModel._read_string
  - [def] data_model.py::PlayerDataModel._write_string
  - [def] data_model.py::PlayerDataModel._effective_byte_length
  - [def] data_model.py::PlayerDataModel._normalize_field_type
  - [def] data_model.py::PlayerDataModel._is_string_type
  - [def] data_model.py::PlayerDataModel._string_encoding_for_type
  - [def] data_model.py::PlayerDataModel._is_float_type
  - [def] data_model.py::PlayerDataModel._is_pointer_type
  - [def] data_model.py::PlayerDataModel._is_color_type
  - [def] data_model.py::PlayerDataModel._extract_field_parts
  - [def] data_model.py::PlayerDataModel._resolve_entity_address
  - [def] data_model.py::PlayerDataModel._resolve_field_address
  - [def] data_model.py::PlayerDataModel._read_entity_field_typed
  - [def] data_model.py::PlayerDataModel._write_entity_field_typed
  - [def] data_model.py::PlayerDataModel._parse_int_value
  - [def] data_model.py::PlayerDataModel._parse_float_value
  - [def] data_model.py::PlayerDataModel._parse_hex_value
  - [def] data_model.py::PlayerDataModel._clamp_enum_index
  - [def] data_model.py::PlayerDataModel._format_hex_value
  - [def] data_model.py::PlayerDataModel._is_team_pointer_field
  - [def] data_model.py::PlayerDataModel._team_pointer_to_display_name
  - [def] data_model.py::PlayerDataModel._team_display_name_to_pointer
  - [def] data_model.py::PlayerDataModel._coerce_field_value
  - [def] data_model.py::PlayerDataModel.coerce_field_value
  - [def] data_model.py::PlayerDataModel.decode_field_value
  - [def] data_model.py::PlayerDataModel.decode_field_value_from_buffer
  - [def] data_model.py::PlayerDataModel.encode_field_value
  - [def] data_model.py::PlayerDataModel._load_external_roster
  - [def] data_model.py::PlayerDataModel.get_field_value
  - [def] data_model.py::PlayerDataModel.get_field_value_typed
  - [def] data_model.py::PlayerDataModel.get_team_field_value
  - [def] data_model.py::PlayerDataModel._write_field_bits
  - [def] data_model.py::PlayerDataModel._apply_field_assignments
  - [def] data_model.py::PlayerDataModel.set_field_value
  - [def] data_model.py::PlayerDataModel.set_field_value_typed
  - [def] data_model.py::PlayerDataModel.set_team_field_value
  - [def] data_model.py::PlayerDataModel.get_team_field_value_typed
  - [def] data_model.py::PlayerDataModel.set_team_field_value_typed
  - [def] data_model.py::PlayerDataModel.get_staff_field_value
  - [def] data_model.py::PlayerDataModel.get_staff_field_value_typed
  - [def] data_model.py::PlayerDataModel.set_staff_field_value
  - [def] data_model.py::PlayerDataModel.set_staff_field_value_typed
  - [def] data_model.py::PlayerDataModel.get_stadium_field_value
  - [def] data_model.py::PlayerDataModel.get_stadium_field_value_typed
  - [def] data_model.py::PlayerDataModel.set_stadium_field_value
  - [def] data_model.py::PlayerDataModel.set_stadium_field_value_typed
  - [def] data_model.py::PlayerDataModel._player_flag_entry
  - [def] data_model.py::PlayerDataModel._read_player_flag
  - [def] data_model.py::PlayerDataModel.is_player_draft_prospect
  - [def] data_model.py::PlayerDataModel.is_player_hidden
  - [def] data_model.py::PlayerDataModel.get_draft_prospects
  - [def] data_model.py::PlayerDataModel.is_player_free_agent_group
  - [def] data_model.py::PlayerDataModel.get_free_agents_by_flags
  - [def] data_model.py::PlayerDataModel._get_free_agents

### `player.py`
  - [def] player.py::Player.full_name
  - [def] player.py::Player.__repr__

### `schema.py`
- No callable definitions.

## Child Folder Map
- `services/`: `services/README.md`

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
