# memory folder

This folder provides the low-level process and memory access layer for the
editor, implemented with Win32 ctypes bindings.

## Architecture
- `win32.py` exposes Win32 constants and ctypes wrappers for Toolhelp and
  process APIs.
- `game_memory.py` wraps process discovery, module base resolution, and
  read/write operations with structured logging.

## GameMemory workflow
- `find_pid()`:
  - Uses `psutil` when available, otherwise Toolhelp snapshots.
  - Prefers the configured module name but falls back to any
    `ALLOWED_MODULE_NAMES` executable.
- `open_process()`:
  - Opens the process with `PROCESS_ALL_ACCESS` and resolves the module base.
  - Caches the handle, PID, and base address for later reads/writes.
- `read_bytes()`/`write_bytes()`:
  - Enforce full-length reads/writes and log results to `logs\memory.log`.
  - Raise errors when the process is not open.
- Typed helpers:
  - `read_uint32`, `read_uint64`, `read_wstring`, `read_ascii`.
  - `write_uint32`, `write_uint64`, `write_wstring_fixed`, `write_ascii_fixed`.

## Logging
- All memory operations flow through `_log_event()` which writes structured
  entries including address, length, PID, and RVA when available.

## Files
- `__init__.py`: package marker.
- `win32.py`: Win32 API bindings and ctypes structures.
- `game_memory.py`: high-level memory helper.
- `README.md`: this document.

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
