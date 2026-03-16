# memory folder

## Responsibilities
- Win32 process access, typed memory IO, and scan utilities.
- Owns direct Python files: `__init__.py`, `game_memory.py`, `scan_utils.py`, `win32.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Win32 process access, typed memory IO, and scan utilities.
This folder currently has 4 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Called by `nba2k_editor/models/data_model.py` for live reads/writes.
- Scanner helpers are used for shared UTF-16 pattern scanning utilities.

## Function Tree
### `__init__.py`
- No callable definitions.

### `game_memory.py`
  - [def] game_memory.py::GameMemory.__init__
  - [def] game_memory.py::GameMemory._detect_pointer_size
  - [def] game_memory.py::GameMemory._log_event
  - [def] game_memory.py::GameMemory.find_pid
  - [def] game_memory.py::GameMemory.open_process
  - [def] game_memory.py::GameMemory.close
  - [def] game_memory.py::GameMemory._get_module_base
  - [def] game_memory.py::GameMemory._check_open
  - [def] game_memory.py::GameMemory.read_bytes
  - [def] game_memory.py::GameMemory.write_bytes
  - [def] game_memory.py::GameMemory.write_pointer
  - [def] game_memory.py::GameMemory.read_uint32
  - [def] game_memory.py::GameMemory.write_uint32
  - [def] game_memory.py::GameMemory.read_uint64
  - [def] game_memory.py::GameMemory.read_wstring
  - [def] game_memory.py::GameMemory.write_wstring_fixed
  - [def] game_memory.py::GameMemory.read_ascii
  - [def] game_memory.py::GameMemory.write_ascii_fixed

### `scan_utils.py`
- [def] scan_utils.py::encode_wstring
- [def] scan_utils.py::find_all

### `win32.py`
- No callable definitions.

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits; run them from the parent repo root (or set `PYTHONPATH` so `nba2k_editor` imports resolve).
