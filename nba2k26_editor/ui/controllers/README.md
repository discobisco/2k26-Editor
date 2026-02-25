# ui/controllers folder

## Responsibilities
- Shared controller helpers for app workflows.
- Owns direct Python files: `__init__.py`, `entity_edit.py`, `import_export.py`, `navigation.py`, `trade.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Shared controller helpers for app workflows.
This folder currently has 5 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/ui/controllers` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
### `__init__.py`
- No callable definitions.

### `entity_edit.py`
- [def] entity_edit.py::coerce_int

### `import_export.py`
- [def] import_export.py::normalize_entity_key
- [def] import_export.py::entity_title

### `navigation.py`
- [def] navigation.py::show_screen

### `trade.py`
- [def] trade.py::format_trade_summary

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
