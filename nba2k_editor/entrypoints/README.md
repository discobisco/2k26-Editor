# entrypoints folder

## Current runtime surface
Startup and utility entrypoints for the active editor runtime.

Direct Python modules currently present:
- `__init__.py`
- `bootstrap.py`
- `full_editor.py`
- `gui.py`
- `runtime_cleanup.py`

## What these modules cover
- `bootstrap.py`: shared source-launch helpers, project-root path setup, local-venv relaunch, and deferred entrypoint loading.
- `full_editor.py`: child/full-editor launcher and request parsing for focused editor windows.
- `gui.py`: primary GUI startup entrypoint for the Dear PyGui editor shell.
- `runtime_cleanup.py`: optional runtime cache cleanup helpers used by entrypoints.

## Removed stale claims
- The previous README said this folder had 9 direct Python modules; the working tree currently has 5.
- It also listed deleted utility entrypoints (`extract_cba_rules.py`, `generate_code_sync.py`, `validate_code_sync.py`) that are not present in the current runtime surface.
- It referred to historical RL / MCP-oriented entry flows; those are not represented by direct modules in this folder now.

## Notes
- Keep this README limited to direct entrypoints that actually exist in `nba2k_editor/entrypoints/`.
- Behavior coverage is exercised by `nba2k_editor/tests/test_full_editor_entrypoint.py`, `test_full_editor_launch.py`, `test_launch_editor_child_mode.py`, `test_runtime_cleanup.py`, and startup-related regression suites.
