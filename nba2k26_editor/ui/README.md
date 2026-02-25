# ui folder

## Responsibilities
- Dear PyGui shell, screens, dialogs, and orchestration layer.
- Owns direct Python files: `__init__.py`, `agent_screen.py`, `ai_screen.py`, `app.py`, `base_entity_editor.py`, `batch_edit.py`, `context_menu.py`, `dialogs.py`, `entity_list_screen.py`, `excel_screen.py`, `extensions_ui.py`, `full_editor_launch.py`, `full_player_editor.py`, `full_stadium_editor.py`, `full_staff_editor.py`, `full_team_editor.py`, `home_screen.py`, `league_screen.py`, `players_screen.py`, `randomizer.py`, `right_click.py`, `stadium_screen.py`, `staff_screen.py`, `team_shuffle.py`, `teams_screen.py`, `theme.py`, `trade_players.py`, `widgets.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Dear PyGui shell, screens, dialogs, and orchestration layer.
This folder currently has 28 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Load Strategy
- `PlayerEditorApp.build_ui` eagerly builds Home only; non-home screens are lazy-built via `PlayerEditorApp._ensure_screen_built` on first navigation.
- `show_players` and `show_teams` now use shared roster-load gating so loaded roster data is reused instead of forcing full scans on each tab switch.
- Trade screen initialization no longer performs a startup roster refresh; trade data refresh runs when the Trade screen is opened.
- AI and Agent screens remain lazy and keep their existing deferred control-bridge/agent-poll behavior.

## Integration Points
- Consumes model/import/AI/RL layers and presents tool screens.
- Instantiated by GUI entrypoint as top-level application shell.

## Function Tree
Scope: direct Python files in this folder only. Child folder details are documented in their own READMEs.

### `__init__.py`
- No callable definitions.

### `agent_screen.py`
- [def] agent_screen.py::build_agent_screen

### `ai_screen.py`
- [def] ai_screen.py::build_ai_screen

### `app.py`
  - [def] app.py::BoundVar.__init__
  - [def] app.py::BoundVar.get
  - [def] app.py::BoundVar.set
  - [def] app.py::BoundDoubleVar.get
  - [def] app.py::BoundDoubleVar.set
  - [def] app.py::BoundBoolVar.get
  - [def] app.py::BoundBoolVar.set
  - [def] app.py::PlayerEditorApp.__init__
  - [def] app.py::PlayerEditorApp._queue_on_main
  - [def] app.py::PlayerEditorApp.after
  - [def] app.py::PlayerEditorApp.run_on_ui_thread
  - [def] app.py::PlayerEditorApp.enqueue_ui_update
  - [def] app.py::PlayerEditorApp.destroy
  - [def] app.py::PlayerEditorApp.build_ui
  - [def] app.py::PlayerEditorApp._build_sidebar
    - [def] app.py::PlayerEditorApp._build_sidebar.nav
  - [def] app.py::PlayerEditorApp._show_screen
  - [def] app.py::PlayerEditorApp._ensure_screen_built
  - [def] app.py::PlayerEditorApp.show_home
  - [def] app.py::PlayerEditorApp.show_players
  - [def] app.py::PlayerEditorApp.show_teams
  - [def] app.py::PlayerEditorApp.show_nba_history
  - [def] app.py::PlayerEditorApp.show_nba_records
  - [def] app.py::PlayerEditorApp.show_league
  - [def] app.py::PlayerEditorApp._ensure_control_bridge_started
  - [def] app.py::PlayerEditorApp.show_ai
  - [def] app.py::PlayerEditorApp.show_agent
  - [def] app.py::PlayerEditorApp.show_trade_players
  - [def] app.py::PlayerEditorApp.show_staff
  - [def] app.py::PlayerEditorApp.show_stadium
  - [def] app.py::PlayerEditorApp.show_excel
  - [def] app.py::PlayerEditorApp._update_status
  - [def] app.py::PlayerEditorApp._set_dynamic_scan_status
  - [def] app.py::PlayerEditorApp._set_offset_status
  - [def] app.py::PlayerEditorApp.copy_to_clipboard
  - [def] app.py::PlayerEditorApp._show_modal
    - [def] app.py::PlayerEditorApp._show_modal._close_dialog
  - [def] app.py::PlayerEditorApp.show_info
  - [def] app.py::PlayerEditorApp.show_warning
  - [def] app.py::PlayerEditorApp.show_error
  - [def] app.py::PlayerEditorApp._open_file_dialog
    - [def] app.py::PlayerEditorApp._open_file_dialog._close
    - [def] app.py::PlayerEditorApp._open_file_dialog._on_select
  - [def] app.py::PlayerEditorApp._start_control_bridge
  - [def] app.py::PlayerEditorApp._load_ai_settings_into_vars
  - [def] app.py::PlayerEditorApp._load_ai_settings
  - [def] app.py::PlayerEditorApp._merge_dict
  - [def] app.py::PlayerEditorApp._get_ai_profiles
  - [def] app.py::PlayerEditorApp._ensure_ai_profiles
  - [def] app.py::PlayerEditorApp._get_team_profiles
  - [def] app.py::PlayerEditorApp._collect_ai_settings
  - [def] app.py::PlayerEditorApp.get_ai_settings
  - [def] app.py::PlayerEditorApp._coerce_int
  - [def] app.py::PlayerEditorApp._save_ai_settings
  - [def] app.py::PlayerEditorApp.get_persona_choice_items
  - [def] app.py::PlayerEditorApp._render_player_list
  - [def] app.py::PlayerEditorApp._start_scan
  - [def] app.py::PlayerEditorApp._scan_thread
  - [def] app.py::PlayerEditorApp._start_roster_scan
  - [def] app.py::PlayerEditorApp._run_roster_scan
    - [def] app.py::PlayerEditorApp._run_roster_scan.update_ui
  - [def] app.py::PlayerEditorApp._refresh_player_list
  - [def] app.py::PlayerEditorApp._filter_player_list
  - [def] app.py::PlayerEditorApp._on_team_selected
  - [def] app.py::PlayerEditorApp._on_player_selected
  - [def] app.py::PlayerEditorApp._update_detail_fields
    - [def] app.py::PlayerEditorApp._update_detail_fields._format_detail
  - [def] app.py::PlayerEditorApp._save_player
  - [def] app.py::PlayerEditorApp._open_full_editor
  - [def] app.py::PlayerEditorApp._open_copy_dialog
    - [def] app.py::PlayerEditorApp._open_copy_dialog._close_dialog
    - [def] app.py::PlayerEditorApp._open_copy_dialog._do_copy
  - [def] app.py::PlayerEditorApp._export_selected_player
    - [def] app.py::PlayerEditorApp._export_selected_player._after_choose
      - [def] app.py::PlayerEditorApp._export_selected_player._after_choose._run_export
  - [def] app.py::PlayerEditorApp._import_selected_player
    - [def] app.py::PlayerEditorApp._import_selected_player._after_choose
  - [def] app.py::PlayerEditorApp.get_player_list_items
  - [def] app.py::PlayerEditorApp.get_selected_player_indices
  - [def] app.py::PlayerEditorApp.set_selected_player_indices
  - [def] app.py::PlayerEditorApp.clear_player_selection
  - [def] app.py::PlayerEditorApp._ensure_team_listbox
  - [def] app.py::PlayerEditorApp._start_team_scan
  - [def] app.py::PlayerEditorApp._scan_teams_thread
  - [def] app.py::PlayerEditorApp._update_team_dropdown
    - [def] app.py::PlayerEditorApp._update_team_dropdown._append_unique
  - [def] app.py::PlayerEditorApp._filter_team_list
  - [def] app.py::PlayerEditorApp._on_team_listbox_select
  - [def] app.py::PlayerEditorApp._on_team_edit_selected
  - [def] app.py::PlayerEditorApp._on_team_field_changed
  - [def] app.py::PlayerEditorApp._save_team
  - [def] app.py::PlayerEditorApp._open_full_team_editor
  - [def] app.py::PlayerEditorApp._league_state
  - [def] app.py::PlayerEditorApp._is_nba_records_category
  - [def] app.py::PlayerEditorApp._filter_league_page_categories
  - [def] app.py::PlayerEditorApp._register_league_widgets
  - [def] app.py::PlayerEditorApp._on_league_category_selected
  - [def] app.py::PlayerEditorApp._ensure_league_categories
  - [def] app.py::PlayerEditorApp._update_league_status
  - [def] app.py::PlayerEditorApp._clear_league_table
  - [def] app.py::PlayerEditorApp._render_league_table
  - [def] app.py::PlayerEditorApp._refresh_league_records
  - [def] app.py::PlayerEditorApp._current_staff_index
  - [def] app.py::PlayerEditorApp._refresh_staff_list
  - [def] app.py::PlayerEditorApp._filter_staff_list
  - [def] app.py::PlayerEditorApp._on_staff_selected
  - [def] app.py::PlayerEditorApp._open_full_staff_editor
  - [def] app.py::PlayerEditorApp.get_staff_list_items
  - [def] app.py::PlayerEditorApp.get_selected_staff_indices
  - [def] app.py::PlayerEditorApp.set_staff_selection
  - [def] app.py::PlayerEditorApp._current_stadium_index
  - [def] app.py::PlayerEditorApp._refresh_stadium_list
  - [def] app.py::PlayerEditorApp._filter_stadium_list
  - [def] app.py::PlayerEditorApp._on_stadium_selected
  - [def] app.py::PlayerEditorApp._open_full_stadium_editor
  - [def] app.py::PlayerEditorApp.get_stadium_list_items
  - [def] app.py::PlayerEditorApp.get_selected_stadium_indices
  - [def] app.py::PlayerEditorApp.set_stadium_selection
  - [def] app.py::PlayerEditorApp._open_randomizer
  - [def] app.py::PlayerEditorApp._open_team_shuffle
  - [def] app.py::PlayerEditorApp._open_batch_edit
  - [def] app.py::PlayerEditorApp._open_team_player_editor
  - [def] app.py::PlayerEditorApp._on_team_player_selected
  - [def] app.py::PlayerEditorApp._update_team_players
  - [def] app.py::PlayerEditorApp._set_excel_status
  - [def] app.py::PlayerEditorApp._reset_excel_progress
  - [def] app.py::PlayerEditorApp._apply_excel_progress
  - [def] app.py::PlayerEditorApp._excel_progress_callback
    - [def] app.py::PlayerEditorApp._excel_progress_callback._callback
  - [def] app.py::PlayerEditorApp._queue_excel_export_progress
  - [def] app.py::PlayerEditorApp._poll_excel_export
  - [def] app.py::PlayerEditorApp._finish_excel_export
  - [def] app.py::PlayerEditorApp._import_excel
    - [def] app.py::PlayerEditorApp._import_excel._after_choose
      - [def] app.py::PlayerEditorApp._import_excel._after_choose._apply_mapping
  - [def] app.py::PlayerEditorApp._export_excel
    - [def] app.py::PlayerEditorApp._export_excel._start_export
      - [def] app.py::PlayerEditorApp._export_excel._start_export._after_choose
        - [def] app.py::PlayerEditorApp._export_excel._start_export._after_choose._run_export
    - [def] app.py::PlayerEditorApp._export_excel._after_team_choice
  - [def] app.py::PlayerEditorApp._open_import_dialog
  - [def] app.py::PlayerEditorApp._open_export_dialog
  - [def] app.py::PlayerEditorApp._open_load_excel
  - [def] app.py::PlayerEditorApp._hook_label_for
  - [def] app.py::PlayerEditorApp._set_hook_target
  - [def] app.py::PlayerEditorApp._open_offset_file_dialog
    - [def] app.py::PlayerEditorApp._open_offset_file_dialog._after_choose
  - [def] app.py::PlayerEditorApp._start_dynamic_base_scan
  - [def] app.py::PlayerEditorApp._run_dynamic_base_scan
    - [def] app.py::PlayerEditorApp._run_dynamic_base_scan._extract_addr
  - [def] app.py::PlayerEditorApp._refresh_trade_data
  - [def] app.py::PlayerEditorApp._trade_refresh_team_options
  - [def] app.py::PlayerEditorApp._trade_get_roster
  - [def] app.py::PlayerEditorApp._trade_load_contracts
  - [def] app.py::PlayerEditorApp._trade_player_label
  - [def] app.py::PlayerEditorApp._trade_y1_salary
  - [def] app.py::PlayerEditorApp._trade_refresh_rosters
  - [def] app.py::PlayerEditorApp._trade_set_active_team
  - [def] app.py::PlayerEditorApp._trade_set_active_team_from_list
  - [def] app.py::PlayerEditorApp._trade_add_participant
  - [def] app.py::PlayerEditorApp._trade_select_active_player
  - [def] app.py::PlayerEditorApp._trade_open_player_modal
    - [def] app.py::PlayerEditorApp._trade_open_player_modal._confirm
  - [def] app.py::PlayerEditorApp._trade_add_transaction
  - [def] app.py::PlayerEditorApp._trade_clear
  - [def] app.py::PlayerEditorApp._trade_swap_teams
  - [def] app.py::PlayerEditorApp._trade_refresh_package_lists
  - [def] app.py::PlayerEditorApp._trade_update_status
  - [def] app.py::PlayerEditorApp._trade_select_transaction
  - [def] app.py::PlayerEditorApp._trade_remove_transaction
  - [def] app.py::PlayerEditorApp._trade_select_slot
  - [def] app.py::PlayerEditorApp._trade_clear_slot
  - [def] app.py::PlayerEditorApp._trade_propose
  - [def] app.py::PlayerEditorApp._trade_render_team_lists
  - [def] app.py::PlayerEditorApp._trade_ensure_slot_entries
  - [def] app.py::PlayerEditorApp._ensure_agent_runtime
  - [def] app.py::PlayerEditorApp._build_agent_adapter
  - [def] app.py::PlayerEditorApp._agent_refresh_snapshot
  - [def] app.py::PlayerEditorApp._agent_start_evaluate
  - [def] app.py::PlayerEditorApp._agent_start_live_assist
  - [def] app.py::PlayerEditorApp._agent_start_training
  - [def] app.py::PlayerEditorApp._agent_stop_runtime
  - [def] app.py::PlayerEditorApp._agent_pick_checkpoint
  - [def] app.py::PlayerEditorApp._agent_pick_config
  - [def] app.py::PlayerEditorApp._set_agent_checkpoint
  - [def] app.py::PlayerEditorApp._set_agent_config
  - [def] app.py::PlayerEditorApp._set_agent_status
  - [def] app.py::PlayerEditorApp._append_agent_log
  - [def] app.py::PlayerEditorApp._start_agent_polling
  - [def] app.py::PlayerEditorApp._poll_agent_events

### `batch_edit.py`
  - [def] batch_edit.py::BatchEditWindow.__init__
  - [def] batch_edit.py::BatchEditWindow._build_ui
  - [def] batch_edit.py::BatchEditWindow._on_category_selected
  - [def] batch_edit.py::BatchEditWindow._on_field_selected
  - [def] batch_edit.py::BatchEditWindow._apply_changes
  - [def] batch_edit.py::BatchEditWindow._reset_core_fields
    - [def] batch_edit.py::BatchEditWindow._reset_core_fields.collect_numeric_fields
    - [def] batch_edit.py::BatchEditWindow._reset_core_fields._queue_assignment
  - [def] batch_edit.py::BatchEditWindow._clear_value_input
  - [def] batch_edit.py::BatchEditWindow._field_def
  - [def] batch_edit.py::BatchEditWindow._team_names
  - [def] batch_edit.py::BatchEditWindow._selected_teams
- [def] batch_edit.py::open_batch_edit

### `context_menu.py`
- [def] context_menu.py::attach_player_context_menu
- [def] context_menu.py::attach_team_context_menu
- [def] context_menu.py::_select_player_and
- [def] context_menu.py::_select_team_and
- [def] context_menu.py::_ensure_player_selected
- [def] context_menu.py::_ensure_team_selected

### `dialogs.py`
- [def] dialogs.py::_rgba
  - [def] dialogs.py::ImportSummaryDialog.__init__
  - [def] dialogs.py::ImportSummaryDialog._build_ui
  - [def] dialogs.py::ImportSummaryDialog._initial_suggestion
  - [def] dialogs.py::ImportSummaryDialog._apply
  - [def] dialogs.py::CategorySelectionDialog.__init__
  - [def] dialogs.py::CategorySelectionDialog._build_ui
  - [def] dialogs.py::CategorySelectionDialog._finish
  - [def] dialogs.py::TeamSelectionDialog.__init__
  - [def] dialogs.py::TeamSelectionDialog._normalize_teams
  - [def] dialogs.py::TeamSelectionDialog._build_ui
  - [def] dialogs.py::TeamSelectionDialog._toggle_all
  - [def] dialogs.py::TeamSelectionDialog._toggle_range
  - [def] dialogs.py::TeamSelectionDialog._sync_checkbox_states
  - [def] dialogs.py::TeamSelectionDialog._finish

### `excel_screen.py`
- [def] excel_screen.py::build_excel_screen
- [def] excel_screen.py::_add_section

### `extensions_ui.py`
- [def] extensions_ui.py::_module_key
- [def] extensions_ui.py::_key_to_module_name
- [def] extensions_ui.py::_key_to_path
- [def] extensions_ui.py::_normalize_autoload_key
- [def] extensions_ui.py::extension_label_for_key
- [def] extensions_ui.py::_build_restart_command
- [def] extensions_ui.py::reload_with_selected_extensions
- [def] extensions_ui.py::_load_extensions_from_keys
- [def] extensions_ui.py::autoload_extensions_from_file
- [def] extensions_ui.py::discover_extension_files
- [def] extensions_ui.py::is_extension_loaded
- [def] extensions_ui.py::load_extension_module
- [def] extensions_ui.py::toggle_extension_module

### `full_editor_launch.py`
- [def] full_editor_launch.py::_project_root
- [def] full_editor_launch.py::_normalize_indices
- [def] full_editor_launch.py::build_launch_command
- [def] full_editor_launch.py::launch_full_editor_process

### `full_player_editor.py`
  - [def] full_player_editor.py::FullPlayerEditor.__init__
  - [def] full_player_editor.py::FullPlayerEditor._build_tabs
  - [def] full_player_editor.py::FullPlayerEditor._clone_fields_with_source
  - [def] full_player_editor.py::FullPlayerEditor._stats_id_sort_key
  - [def] full_player_editor.py::FullPlayerEditor._build_season_slot_selector_field
  - [def] full_player_editor.py::FullPlayerEditor._prepare_stats_tabs
  - [def] full_player_editor.py::FullPlayerEditor._build_category_tab
  - [def] full_player_editor.py::FullPlayerEditor._add_field_control
  - [def] full_player_editor.py::FullPlayerEditor._load_all_values_async
  - [def] full_player_editor.py::FullPlayerEditor._apply_loaded_values
  - [def] full_player_editor.py::FullPlayerEditor._save_all
  - [def] full_player_editor.py::FullPlayerEditor._get_ui_value
  - [def] full_player_editor.py::FullPlayerEditor._is_season_slot_selector_field
  - [def] full_player_editor.py::FullPlayerEditor._is_season_stats_field
  - [def] full_player_editor.py::FullPlayerEditor._selected_season_slot_index
  - [def] full_player_editor.py::FullPlayerEditor._season_stats_base_and_stride
  - [def] full_player_editor.py::FullPlayerEditor._resolve_selected_season_record_ptr
  - [def] full_player_editor.py::FullPlayerEditor._set_control_default_value
  - [def] full_player_editor.py::FullPlayerEditor._load_selected_season_stats_values
  - [def] full_player_editor.py::FullPlayerEditor._on_season_slot_changed
  - [def] full_player_editor.py::FullPlayerEditor._adjust_category
  - [def] full_player_editor.py::FullPlayerEditor._mark_unsaved
  - [def] full_player_editor.py::FullPlayerEditor._coerce_int
  - [def] full_player_editor.py::FullPlayerEditor._clamp_dpg_int
  - [def] full_player_editor.py::FullPlayerEditor._sanitize_input_int_range
  - [def] full_player_editor.py::FullPlayerEditor._color_tuple
  - [def] full_player_editor.py::FullPlayerEditor._normalize_players
  - [def] full_player_editor.py::FullPlayerEditor._on_close

### `full_stadium_editor.py`
  - [def] full_stadium_editor.py::FullStadiumEditor.__init__
  - [def] full_stadium_editor.py::FullStadiumEditor._build_tabs
  - [def] full_stadium_editor.py::FullStadiumEditor._build_category_tab
  - [def] full_stadium_editor.py::FullStadiumEditor._add_field_control
  - [def] full_stadium_editor.py::FullStadiumEditor._load_all_values_async
    - [def] full_stadium_editor.py::FullStadiumEditor._load_all_values_async._worker
      - [def] full_stadium_editor.py::FullStadiumEditor._load_all_values_async._worker._apply
  - [def] full_stadium_editor.py::FullStadiumEditor._apply_loaded_values
  - [def] full_stadium_editor.py::FullStadiumEditor._save_all
  - [def] full_stadium_editor.py::FullStadiumEditor._get_ui_value
  - [def] full_stadium_editor.py::FullStadiumEditor._mark_unsaved
  - [def] full_stadium_editor.py::FullStadiumEditor._coerce_int
  - [def] full_stadium_editor.py::FullStadiumEditor._on_close

### `full_staff_editor.py`
  - [def] full_staff_editor.py::FullStaffEditor.__init__
  - [def] full_staff_editor.py::FullStaffEditor._build_tabs
  - [def] full_staff_editor.py::FullStaffEditor._build_category_tab
  - [def] full_staff_editor.py::FullStaffEditor._add_field_control
  - [def] full_staff_editor.py::FullStaffEditor._load_all_values_async
    - [def] full_staff_editor.py::FullStaffEditor._load_all_values_async._worker
      - [def] full_staff_editor.py::FullStaffEditor._load_all_values_async._worker._apply
  - [def] full_staff_editor.py::FullStaffEditor._apply_loaded_values
  - [def] full_staff_editor.py::FullStaffEditor._save_all
  - [def] full_staff_editor.py::FullStaffEditor._get_ui_value
  - [def] full_staff_editor.py::FullStaffEditor._mark_unsaved
  - [def] full_staff_editor.py::FullStaffEditor._coerce_int
  - [def] full_staff_editor.py::FullStaffEditor._on_close

### `full_team_editor.py`
  - [def] full_team_editor.py::FullTeamEditor.__init__
  - [def] full_team_editor.py::FullTeamEditor._build_tabs
  - [def] full_team_editor.py::FullTeamEditor._build_category_tab
  - [def] full_team_editor.py::FullTeamEditor._add_field_control
  - [def] full_team_editor.py::FullTeamEditor._load_all_values_async
    - [def] full_team_editor.py::FullTeamEditor._load_all_values_async._worker
      - [def] full_team_editor.py::FullTeamEditor._load_all_values_async._worker._apply
  - [def] full_team_editor.py::FullTeamEditor._apply_loaded_values
  - [def] full_team_editor.py::FullTeamEditor._save_all
  - [def] full_team_editor.py::FullTeamEditor._get_ui_value
  - [def] full_team_editor.py::FullTeamEditor._mark_unsaved
  - [def] full_team_editor.py::FullTeamEditor._coerce_int
  - [def] full_team_editor.py::FullTeamEditor._on_close

### `home_screen.py`
- [def] home_screen.py::build_home_screen
- [def] home_screen.py::_build_home_overview_tab
  - [def] home_screen.py::_build_home_overview_tab.refresh_status
- [def] home_screen.py::_build_home_ai_settings_tab
- [def] home_screen.py::_build_extension_loader
  - [def] home_screen.py::_build_extension_loader._toggle

### `league_screen.py`
- [def] league_screen.py::build_nba_history_screen
- [def] league_screen.py::build_nba_records_screen
- [def] league_screen.py::_build_league_screen
- [def] league_screen.py::_on_category_selected

### `players_screen.py`
- [def] players_screen.py::build_players_screen
- [def] players_screen.py::_on_search_changed
- [def] players_screen.py::_build_player_detail_panel

### `randomizer.py`
  - [def] randomizer.py::RandomizerWindow.__init__
  - [def] randomizer.py::RandomizerWindow._build_ui
  - [def] randomizer.py::RandomizerWindow._build_category_tab
  - [def] randomizer.py::RandomizerWindow._randomize_selected
  - [def] randomizer.py::RandomizerWindow._default_bounds
  - [def] randomizer.py::RandomizerWindow._team_names
- [def] randomizer.py::open_randomizer

### `right_click.py`
- No callable definitions.

### `stadium_screen.py`
- [def] stadium_screen.py::build_stadium_screen
- [def] stadium_screen.py::_on_search_changed

### `staff_screen.py`
- [def] staff_screen.py::build_staff_screen
- [def] staff_screen.py::_on_search_changed

### `team_shuffle.py`
  - [def] team_shuffle.py::TeamShuffleWindow.__init__
  - [def] team_shuffle.py::TeamShuffleWindow._build_ui
  - [def] team_shuffle.py::TeamShuffleWindow._shuffle_selected
  - [def] team_shuffle.py::TeamShuffleWindow._team_names
- [def] team_shuffle.py::open_team_shuffle

### `teams_screen.py`
- [def] teams_screen.py::build_teams_screen
- [def] teams_screen.py::_on_search_changed

### `theme.py`
- [def] theme.py::apply_base_theme
- [def] theme.py::_rgb

### `trade_players.py`
- [def] trade_players.py::build_trade_players_screen

### `widgets.py`
- [def] widgets.py::add_scroll_area
- [def] widgets.py::set_scroll_y

## Child Folder Map
- `controllers/`: `controllers/README.md`
- `state/`: `state/README.md`

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
