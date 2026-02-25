# ai folder

## Responsibilities
- Assistant orchestration, personas, settings, and control bridge runtime.
- Owns direct Python files: `__init__.py`, `assistant.py`, `backend_helpers.py`, `cba_context.py`, `detection.py`, `nba_data.py`, `personas.py`, `settings.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Assistant orchestration, personas, settings, and control bridge runtime.
This folder currently has 8 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Consumed by `nba2k_editor/ui/app.py` and `nba2k_editor/ui/ai_screen.py`.
- Loads workbook context from `nba2k_editor/NBA Player Data`.

## Function Tree
Scope: direct Python files in this folder only. Child folder details are documented in their own READMEs.

### `__init__.py`
- No callable definitions.

### `assistant.py`
  - [def] assistant.py::PlayerEditorApp.run_on_ui_thread
  - [def] assistant.py::PlayerEditorApp.enqueue_ui_update
  - [def] assistant.py::PlayerEditorApp._refresh_player_list
  - [def] assistant.py::PlayerEditorApp._filter_player_list
  - [def] assistant.py::PlayerEditorApp._refresh_staff_list
  - [def] assistant.py::PlayerEditorApp._refresh_stadium_list
  - [def] assistant.py::PlayerEditorApp._save_player
  - [def] assistant.py::PlayerEditorApp._save_team
  - [def] assistant.py::PlayerEditorApp._on_team_edit_selected
  - [def] assistant.py::PlayerEditorApp.show_home
  - [def] assistant.py::PlayerEditorApp.show_players
  - [def] assistant.py::PlayerEditorApp.show_teams
  - [def] assistant.py::PlayerEditorApp.show_staff
  - [def] assistant.py::PlayerEditorApp.show_stadium
  - [def] assistant.py::PlayerEditorApp.show_excel
  - [def] assistant.py::PlayerEditorApp.show_ai
  - [def] assistant.py::PlayerEditorApp.get_ai_settings
  - [def] assistant.py::PlayerEditorApp._open_full_editor
  - [def] assistant.py::PlayerEditorApp._open_full_staff_editor
  - [def] assistant.py::PlayerEditorApp._open_full_stadium_editor
  - [def] assistant.py::PlayerEditorApp._open_copy_dialog
  - [def] assistant.py::PlayerEditorApp._open_randomizer
  - [def] assistant.py::PlayerEditorApp._open_team_shuffle
  - [def] assistant.py::PlayerEditorApp._open_batch_edit
  - [def] assistant.py::PlayerEditorApp._open_import_dialog
  - [def] assistant.py::PlayerEditorApp._open_export_dialog
  - [def] assistant.py::PlayerEditorApp._open_load_excel
  - [def] assistant.py::PlayerEditorApp._open_team_player_editor
  - [def] assistant.py::PlayerEditorApp.get_persona_choice_items
  - [def] assistant.py::PlayerEditorApp.copy_to_clipboard
  - [def] assistant.py::PlayerEditorApp.get_player_list_items
  - [def] assistant.py::PlayerEditorApp.get_selected_player_indices
  - [def] assistant.py::PlayerEditorApp.set_selected_player_indices
  - [def] assistant.py::PlayerEditorApp.clear_player_selection
  - [def] assistant.py::PlayerEditorApp.get_staff_list_items
  - [def] assistant.py::PlayerEditorApp.get_selected_staff_indices
  - [def] assistant.py::PlayerEditorApp.set_staff_selection
  - [def] assistant.py::PlayerEditorApp.get_stadium_list_items
  - [def] assistant.py::PlayerEditorApp.get_selected_stadium_indices
  - [def] assistant.py::PlayerEditorApp.set_stadium_selection
  - [def] assistant.py::LLMControlBridge.__init__
  - [def] assistant.py::LLMControlBridge.app
  - [def] assistant.py::LLMControlBridge._start_server
    - [def] assistant.py::LLMControlBridge._start_server.handler_factory
        - [def] assistant.py::LLMControlBridge._start_server.handler_factory.ControlHandler._send_json
        - [def] assistant.py::LLMControlBridge._start_server.handler_factory.ControlHandler.do_OPTIONS
        - [def] assistant.py::LLMControlBridge._start_server.handler_factory.ControlHandler.do_GET
        - [def] assistant.py::LLMControlBridge._start_server.handler_factory.ControlHandler.do_POST
        - [def] assistant.py::LLMControlBridge._start_server.handler_factory.ControlHandler.log_message
  - [def] assistant.py::LLMControlBridge.describe_state
    - [def] assistant.py::LLMControlBridge.describe_state.gather
  - [def] assistant.py::LLMControlBridge.list_players
    - [def] assistant.py::LLMControlBridge.list_players.gather
  - [def] assistant.py::LLMControlBridge.handle_command
  - [def] assistant.py::LLMControlBridge.feature_actions
  - [def] assistant.py::LLMControlBridge.available_actions
  - [def] assistant.py::LLMControlBridge._cmd_select_player
  - [def] assistant.py::LLMControlBridge._cmd_select_staff
  - [def] assistant.py::LLMControlBridge._cmd_select_stadium
  - [def] assistant.py::LLMControlBridge._select_player_index
  - [def] assistant.py::LLMControlBridge._select_staff_index
  - [def] assistant.py::LLMControlBridge._select_stadium_index
  - [def] assistant.py::LLMControlBridge._select_player_name
  - [def] assistant.py::LLMControlBridge._cmd_set_name_fields
    - [def] assistant.py::LLMControlBridge._cmd_set_name_fields.apply
  - [def] assistant.py::LLMControlBridge._cmd_save_player
  - [def] assistant.py::LLMControlBridge._cmd_select_team
    - [def] assistant.py::LLMControlBridge._cmd_select_team.apply
  - [def] assistant.py::LLMControlBridge._cmd_set_search_filter
    - [def] assistant.py::LLMControlBridge._cmd_set_search_filter.apply
  - [def] assistant.py::LLMControlBridge._cmd_get_team_state
    - [def] assistant.py::LLMControlBridge._cmd_get_team_state.gather
  - [def] assistant.py::LLMControlBridge._cmd_set_team_field
    - [def] assistant.py::LLMControlBridge._cmd_set_team_field.apply
  - [def] assistant.py::LLMControlBridge._cmd_set_team_fields
    - [def] assistant.py::LLMControlBridge._cmd_set_team_fields.apply
  - [def] assistant.py::LLMControlBridge._cmd_save_team
    - [def] assistant.py::LLMControlBridge._cmd_save_team.save
  - [def] assistant.py::LLMControlBridge._cmd_refresh_players
  - [def] assistant.py::LLMControlBridge._cmd_show_screen
    - [def] assistant.py::LLMControlBridge._cmd_show_screen.apply
  - [def] assistant.py::LLMControlBridge._cmd_invoke_feature
  - [def] assistant.py::LLMControlBridge._cmd_open_full_editor
    - [def] assistant.py::LLMControlBridge._cmd_open_full_editor.open_it
  - [def] assistant.py::LLMControlBridge._cmd_open_full_staff_editor
    - [def] assistant.py::LLMControlBridge._cmd_open_full_staff_editor.open_it
  - [def] assistant.py::LLMControlBridge._cmd_open_full_stadium_editor
    - [def] assistant.py::LLMControlBridge._cmd_open_full_stadium_editor.open_it
  - [def] assistant.py::LLMControlBridge._invoke_app_method
  - [def] assistant.py::LLMControlBridge._cmd_set_detail_field
    - [def] assistant.py::LLMControlBridge._cmd_set_detail_field.apply
  - [def] assistant.py::LLMControlBridge.list_teams
  - [def] assistant.py::LLMControlBridge.list_staff
  - [def] assistant.py::LLMControlBridge.list_stadiums
  - [def] assistant.py::LLMControlBridge._save_player_and_refresh
  - [def] assistant.py::LLMControlBridge._gather_selection_summary
  - [def] assistant.py::LLMControlBridge._find_open_full_editor
  - [def] assistant.py::LLMControlBridge._find_open_staff_editor
  - [def] assistant.py::LLMControlBridge._find_open_stadium_editor
  - [def] assistant.py::LLMControlBridge._coerce_int
  - [def] assistant.py::LLMControlBridge._get_control_value
  - [def] assistant.py::LLMControlBridge._set_control_value
  - [def] assistant.py::LLMControlBridge._cmd_list_full_fields
    - [def] assistant.py::LLMControlBridge._cmd_list_full_fields.list_fields
  - [def] assistant.py::LLMControlBridge._cmd_set_full_field
    - [def] assistant.py::LLMControlBridge._cmd_set_full_field.set_field
  - [def] assistant.py::LLMControlBridge._set_full_field_on_ui
  - [def] assistant.py::LLMControlBridge._cmd_save_full_editor
    - [def] assistant.py::LLMControlBridge._cmd_save_full_editor.save
  - [def] assistant.py::LLMControlBridge._cmd_set_full_fields
    - [def] assistant.py::LLMControlBridge._cmd_set_full_fields.set_many
  - [def] assistant.py::LLMControlBridge._cmd_get_full_editor_state
    - [def] assistant.py::LLMControlBridge._cmd_get_full_editor_state.state
  - [def] assistant.py::LLMControlBridge._cmd_list_staff_fields
    - [def] assistant.py::LLMControlBridge._cmd_list_staff_fields.list_fields
  - [def] assistant.py::LLMControlBridge._cmd_set_staff_field
    - [def] assistant.py::LLMControlBridge._cmd_set_staff_field.set_field
  - [def] assistant.py::LLMControlBridge._set_staff_field_on_ui
  - [def] assistant.py::LLMControlBridge._cmd_set_staff_fields
    - [def] assistant.py::LLMControlBridge._cmd_set_staff_fields.set_many
  - [def] assistant.py::LLMControlBridge._cmd_save_staff_editor
    - [def] assistant.py::LLMControlBridge._cmd_save_staff_editor.save
  - [def] assistant.py::LLMControlBridge._cmd_get_staff_editor_state
    - [def] assistant.py::LLMControlBridge._cmd_get_staff_editor_state.state
  - [def] assistant.py::LLMControlBridge._cmd_list_stadium_fields
    - [def] assistant.py::LLMControlBridge._cmd_list_stadium_fields.list_fields
  - [def] assistant.py::LLMControlBridge._cmd_set_stadium_field
    - [def] assistant.py::LLMControlBridge._cmd_set_stadium_field.set_field
  - [def] assistant.py::LLMControlBridge._set_stadium_field_on_ui
  - [def] assistant.py::LLMControlBridge._cmd_set_stadium_fields
    - [def] assistant.py::LLMControlBridge._cmd_set_stadium_fields.set_many
  - [def] assistant.py::LLMControlBridge._cmd_save_stadium_editor
    - [def] assistant.py::LLMControlBridge._cmd_save_stadium_editor.save
  - [def] assistant.py::LLMControlBridge._cmd_get_stadium_editor_state
    - [def] assistant.py::LLMControlBridge._cmd_get_stadium_editor_state.state
  - [def] assistant.py::LLMControlBridge._run_on_ui_thread
    - [def] assistant.py::LLMControlBridge._run_on_ui_thread.wrapper
  - [def] assistant.py::LLMControlBridge.server_address
  - [def] assistant.py::LLMControlBridge._detect_screen
- [def] assistant.py::ensure_control_bridge
  - [def] assistant.py::PlayerAIAssistant.__init__
  - [def] assistant.py::PlayerAIAssistant._build_panel
  - [def] assistant.py::PlayerAIAssistant._refresh_persona_dropdown
  - [def] assistant.py::PlayerAIAssistant._on_persona_select
  - [def] assistant.py::PlayerAIAssistant._set_status
  - [def] assistant.py::PlayerAIAssistant._set_output
  - [def] assistant.py::PlayerAIAssistant._append_output
  - [def] assistant.py::PlayerAIAssistant._start_progress
  - [def] assistant.py::PlayerAIAssistant._stop_progress
  - [def] assistant.py::PlayerAIAssistant._copy_response
  - [def] assistant.py::PlayerAIAssistant._get_settings_for_request
  - [def] assistant.py::PlayerAIAssistant._on_request
  - [def] assistant.py::PlayerAIAssistant._run_ai
    - [def] assistant.py::PlayerAIAssistant._run_ai._on_update
  - [def] assistant.py::PlayerAIAssistant._finalize_request
  - [def] assistant.py::PlayerAIAssistant._build_prompt
- [def] assistant.py::build_local_command
- [def] assistant.py::call_local_process
- [def] assistant.py::call_python_backend
- [def] assistant.py::call_remote_api
- [def] assistant.py::invoke_ai_backend

### `backend_helpers.py`
- [def] backend_helpers.py::load_python_instance
- [def] backend_helpers.py::generate_text_sync
- [def] backend_helpers.py::generate_text_async

### `cba_context.py`
- [def] cba_context.py::_format_with_citations
- [def] cba_context.py::build_cba_guidance

### `detection.py`
- [def] detection.py::_maybe_path
- [def] detection.py::_local_ai_candidates
- [def] detection.py::_local_model_roots
- [def] detection.py::_iter_model_files
- [def] detection.py::detect_local_ai_installations

### `nba_data.py`
- [def] nba_data.py::_normalize_name
- [def] nba_data.py::_clean_text
- [def] nba_data.py::_to_int
- [def] nba_data.py::_to_float
- [def] nba_data.py::warm_cache_async
- [def] nba_data.py::ensure_loaded
- [def] nba_data.py::_load_data
- [def] nba_data.py::get_player_summary
- [def] nba_data.py::_fmt_num
- [def] nba_data.py::_fmt_pct
- [def] nba_data.py::_format_summary
- [def] nba_data.py::last_error

### `personas.py`
- [def] personas.py::ensure_default_profiles
- [def] personas.py::get_persona_text
- [def] personas.py::export_profiles
- [def] personas.py::import_profiles

### `settings.py`
- [def] settings.py::load_settings
- [def] settings.py::save_settings

## Child Folder Map
- `backends/`: `backends/README.md`

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
