# NBA2K26 Editor Repository Guide

This repository hosts a Python live-memory editor for NBA 2K26 with a Dear
PyGui front-end. The app attaches to the running game process, loads offsets
from bundled data files, and exposes tools for editing players, teams, staff,
and stadiums.


This repo deals with live memory Do Not under ANY CIRMCUMSTANCE do something that the USER did not ask for. If you want to add something that is not directly requested verify first.

## What is included
- Dear PyGui desktop UI plus Windows launcher scripts.
- Win32 memory layer with structured logging.
- Offset-driven schemas with per-version support (2K22-2K26).
- Excel import/export pipelines.
- Extension hooks for custom panels and editor add-ons.
- Active package roots are the folders that actually exist in-tree; historical AI / GM-RL archive claims have been removed.

## Quick start (development)
1. Windows is required for live memory features.
2. Use the controlled launcher path for source launches.
   - Preferred launcher: `run_editor.bat`
   - Equivalent source launcher: `python launch_editor.py`
   - Prepared-env launcher path: `\.venv\Scripts\python.exe launch_editor.py`
3. If `.venv` is missing or does not have the GUI dependencies installed, source startup will fail.
   - This repo does **not** currently ship packaging metadata for `pip install -e .`
   - Treat `.venv` as the validated development runtime unless/until packaging is added
4. Full editor windows now launch in separate child processes/viewports when opened from the main UI.
   - Child entrypoint from the prepared env: `\.venv\Scripts\python.exe -m nba2k_editor.entrypoints.full_editor --editor player --indices 12,47`
   - Launcher-routed child mode: `python launch_editor.py --child-full-editor --editor player --indices 12,47`
   - Packaged mode: `DB2kEditor.exe --child-full-editor --editor team --index 3`
5. If the game is not running, the UI still opens, but live memory reads/writes
   are unavailable.

## Runtime Loading Behavior
- Startup builds only the Home screen eagerly; all other screens are lazy-loaded on first open.
- Opening the Trade screen no longer triggers a full roster refresh during app startup.
- Player/team roster refresh now runs on demand and is reused across navigation (for example, switching Players -> Teams -> Players does not force repeated full scans once data is already loaded).
- Table base pointers are reused across refreshes and are re-resolved when offsets are reloaded (for example after loading a new offsets file).

## Optional extras
- `psutil`: improved process discovery.
- `pandas` + `openpyxl`: Excel and NBA data workflows.
- `torch`, `gymnasium`, `tensorboard`: RL training/evaluation.

## Packaging
- Build with: `pyinstaller NBA2KEditor.spec`
- Output: `dist/DB2kEditor.exe`

## Root files
- `launch_editor.py`: launcher helper.
- `NBA2KEditor.spec`: PyInstaller spec.
- `run_editor.bat`: launcher that prefers local `.venv`.

## Repository map
- `nba2k_editor/`: main package (UI, core, memory, models, tests, plus minimal legacy compatibility stubs).
- `nba2k_editor/Offsets/`: offsets bundle and Excel templates.
- `nba2k_editor/mcp_server/data/`: bundled MCP profile assets.
- `build/`, `dist/`: build artifacts.

## Documentation index
- `nba2k_editor/README.md`
- `nba2k_editor/tests/CALL_GRAPH.md`
- `nba2k_editor/tests/call_graph.json`
- `nba2k_editor/core/README.md`
- `nba2k_editor/entrypoints/README.md`
- `nba2k_editor/importing/README.md`
- `nba2k_editor/logs/README.md`
- `nba2k_editor/memory/README.md`
- `nba2k_editor/models/README.md`
- `nba2k_editor/tests/README.md`
- `nba2k_editor/ui/README.md`
- `nba2k_editor/ui/controllers/README.md`
- `nba2k_editor/ui/state/README.md`

## Runtime-generated files (created on demand)
- `nba2k_editor/autoload_extensions.json`
- `nba2k_editor/dual_base_mirror.json` (present only after dynamic-base workflows write it)
- `nba2k_editor/logs/memory.log`

---

# Optional / legacy surfaces

This working tree is centered on the live editor runtime (`core`, `memory`, `models`, `ui`, and `entrypoints`).

Legacy boundaries that still exist:
- `nba2k_editor.gm_rl`: empty compatibility namespace only; the historical integrated GM/RL implementation is not present here.
- `nba2k_editor.mcp_server`: data-only package root for bundled MCP profile assets under `nba2k_editor/mcp_server/data/`.

## Tests
- Preferred validated path: `\.venv\Scripts\python.exe -m pytest -q`
- Running `python -m pytest -q` with the system interpreter is not a reliable gate for this repo unless that interpreter is already the prepared `.venv`.

## Docs consistency check
- Run `python scripts/check_markdown_consistency.py` before doc-related PRs.

## Perf instrumentation
Set `NBA2K_EDITOR_PROFILE=1` to print timing summaries from instrumented hot paths.
