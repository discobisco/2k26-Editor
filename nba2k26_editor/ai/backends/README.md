# ai/backends folder

## Responsibilities
- Backend adapters for in-process and HTTP generation paths.
- Owns direct Python files: `__init__.py`, `base.py`, `http_backend.py`, `python_backend.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Backend adapters for in-process and HTTP generation paths.
This folder currently has 4 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/ai/backends` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
### `__init__.py`
- No callable definitions.

### `base.py`
- No callable definitions.

### `http_backend.py`
- [def] http_backend.py::call_chat_completions

### `python_backend.py`
- [def] python_backend.py::_instance_key
- [def] python_backend.py::load_instance
- [def] python_backend.py::generate_sync
- [def] python_backend.py::generate_async
  - [def] python_backend.py::generate_async._worker
    - [def] python_backend.py::generate_async._worker._cb
    - [def] python_backend.py::generate_async._worker._gen
- [def] python_backend.py::_emit_chunked

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
