# nba2k_editor/memory

## What this folder is
The Windows process-access layer for the editor. This folder owns the low-level process open/close path, module-base resolution, typed memory reads and writes, Win32 bindings, and small scan helpers.

## Current status
- Direct Python files present now: `__init__.py`, `game_memory.py`, `scan_utils.py`, and `win32.py`.
- `game_memory.py` is the main runtime surface in this folder.
- `__init__.py` is only a package docstring in the current tree.

## Key files / structure
- `game_memory.py` - main process/memory helper.
  - Owns process discovery and handle lifecycle.
  - Resolves the loaded game module base.
  - Performs typed reads and writes for bytes, integers, pointers, ASCII, and UTF-16 strings.
  - Provides running-target detection used by entrypoint/model paths.
- `scan_utils.py` - shared UTF-16 encoding and byte-pattern scan helpers.
- `win32.py` - Win32 constants, ctypes structures, and imported API bindings used by `game_memory.py`.
- `__init__.py` - package marker/docstring only.

## Known limitations or notes
- This layer is effectively Windows-only. `GameMemory.open_process()` and module enumeration rely on Win32 APIs and do not provide live process access on non-Windows platforms.
- Supported executable targets are currently defined by the memory/offset target metadata in code; no separate config module is part of the current tree.
- `detect_running_module_name(...)` can scan for multiple configured NBA 2K executables and prefer a requested one when several supported targets are defined.
- `GameMemory` works against one selected module/process at a time after process open.
- This folder is intentionally low-level: higher-level table resolution, entity scanning, and schema-aware field handling live above it in `nba2k_editor/models/` and `nba2k_editor/core/`.


Package summary
- memory/__init__.py
  - “Memory access layer (Win32 bindings and process helpers).”

Files
- memory/game_memory.py
- memory/scan_utils.py
- memory/win32.py
- memory/__init__.py

Lane check: does each file stay in the memory-access lane?

1) memory/__init__.py
Status
- Yes

Why
- package docstring only
- no behavior

2) memory/win32.py
Status
- Yes

What it does
- defines Win32 ctypes constants
- defines MODULEENTRY32W / PROCESSENTRY32W
- binds CreateToolhelp32Snapshot / Module32FirstW / OpenProcess / ReadProcessMemory / WriteProcessMemory
- provides non-Windows null stubs

Assessment
- clean Win32 binding layer
- clearly inside memory-access lane

3) memory/game_memory.py
Status
- Yes, mostly

What it does
- process detection/open/close
- module base resolution
- pointer-size detection
- low-level reads/writes:
  - read_bytes
  - write_bytes
  - write_pointer
  - read_uint32
  - write_uint32
  - read_u64
  - read_wstring / write_wstring_fixed
  - read_ascii / write_ascii_fixed

Assessment
- this is the actual process/memory helper layer
- matches the package summary well

Minor spill
- detect_running_module_name() / find_pid() depend on HOOK_TARGETS and MODULE_NAME from config
- that is still process targeting, so acceptable for this lane

4) memory/scan_utils.py
Status
- Yes

What it does
- encode_wstring()
- find_all()

Assessment
- tiny helper file for memory scanning operations
- still in lane

Bottom line
- memory/__init__.py: in lane
- memory/win32.py: in lane
- memory/game_memory.py: in lane
- memory/scan_utils.py: in lane