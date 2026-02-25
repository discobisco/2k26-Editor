# entrypoints folder

## Responsibilities
- GUI, RL hook, extraction command entry orchestration, and MyEras MCP service launch.
- Owns direct Python files: `__init__.py`, `editor_train_hook.py`, `extract_cba_rules.py`, `full_editor.py`, `generate_code_sync.py`, `gui.py`, `mcp_server.py`, `train_gm_agent.py`, `validate_code_sync.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
GUI, RL hook, and extraction command entry orchestration.
This folder currently has 9 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Bridges startup into `core`, `memory`, `models`, and `ui`.
- CLI flows hand off into `nba2k_editor/gm_rl` and extraction modules.

## Function Tree
### `__init__.py`
- No callable definitions.

### `editor_train_hook.py`
- [def] editor_train_hook.py::run_training_from_editor

### `extract_cba_rules.py`
- [def] extract_cba_rules.py::_default_source
- [def] extract_cba_rules.py::_default_outdir
- [def] extract_cba_rules.py::main

### `full_editor.py`
- [def] full_editor.py::_parse_indices_csv
- [def] full_editor.py::parse_editor_request
- [def] full_editor.py::_build_model
- [def] full_editor.py::_resolve_team_name
- [def] full_editor.py::_open_requested_editor
- [def] full_editor.py::_viewport_title
- [def] full_editor.py::main

### `generate_code_sync.py`
- [def] generate_code_sync.py::main

### `gui.py`
- [def] gui.py::_cleanup_enabled
- [def] gui.py::_delete_runtime_cache_dirs
- [def] gui.py::_print_offsets_status
- [def] gui.py::_launch_with_dearpygui
- [def] gui.py::main

### `mcp_server.py`
- [def] mcp_server.py::main

### `train_gm_agent.py`
- No callable definitions.

### `validate_code_sync.py`
- [def] validate_code_sync.py::main

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
