# NBA2K26 Editor Repository Guide

This repository hosts a Python live-memory editor for NBA 2K26 with a Dear
PyGui front-end. The app attaches to the running game process, loads offsets
from bundled data files, and exposes tools for editing players, teams, staff,
and stadiums.

If the User Says do x do not do the opposite.
If the User is getting angry enter /plan mode.
If the User says to fuck off do not give a text response.
This repo deals with live memory Do Not under ANY CIRMCUMSTANCE do something that the USER did not ask for. If you want to add something that is not directly requested verify first.

## What is included
- Dear PyGui desktop UI plus Windows launcher scripts.
- Win32 memory layer with structured logging.
- Offset-driven schemas with per-version support (2K22-2K26).
- Excel import/export pipelines.
- AI Assistant panel with local/remote backends and HTTP control bridge.
- Extension hooks for custom panels and editor add-ons.
- Integrated PPO GM agent at `nba2k_editor.gm_rl`.
- MyEras FastAPI MCP server at `nba2k_editor.mcp_server`.
- CPU AI personality module for MyEras front-office decisions (trade, draft, free agency, and franchise direction).

## Quick start (development)
1. Windows is required for live memory features.
2. Install dependencies:
   - `python -m pip install -e .`
3. Run one of:
   - `run_editor.bat`
   - `python -m nba2k_editor.entrypoints.gui`
   - `python launch_editor.py`
4. Full editor windows now launch in separate child processes/viewports when opened from the main UI.
   - Child entrypoint: `python -m nba2k_editor.entrypoints.full_editor --editor player --indices 12,47`
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
- `nba2k_editor/`: main package (UI, core, memory, models, AI, RL, tests).
- `nba2k_editor/Offsets/`: offsets bundle and Excel templates.
- `nba2k_editor/NBA Player Data/`: NBA workbook used by AI and mock RL adapter.
- `build/`, `dist/`: build artifacts.

## Documentation index
- `nba2k_editor/README.md`
- `nba2k_editor/tests/CALL_GRAPH.md`
- `nba2k_editor/tests/call_graph.json`
- `nba2k_editor/ai/README.md`
- `nba2k_editor/ai/backends/README.md`
- `nba2k_editor/core/README.md`
- `nba2k_editor/entrypoints/README.md`
- `nba2k_editor/gm_rl/README.md`
- `nba2k_editor/gm_rl/adapters/README.md`
- `nba2k_editor/gm_rl/cba/README.md`
- `nba2k_editor/importing/README.md`
- `nba2k_editor/logs/README.md`
- `nba2k_editor/memory/README.md`
- `nba2k_editor/models/README.md`
- `nba2k_editor/models/services/README.md`
- `nba2k_editor/Offsets/README.md`
- `nba2k_editor/NBA Player Data/README.md`
- `nba2k_editor/tests/README.md`
- `nba2k_editor/ui/README.md`
- `nba2k_editor/ui/controllers/README.md`
- `nba2k_editor/ui/state/README.md`
- `nba2k_editor/mcp_server/README.md`

## Runtime-generated files (created on demand)
- `nba2k_editor/ai_settings.json`
- `nba2k_editor/autoload_extensions.json`
- `nba2k_editor/dual_base_mirror.json` (present only after dynamic-base workflows write it)
- `nba2k_editor/logs/memory.log`
- `nba2k_editor/logs/ai.log`

---

# GM RL Agent (Integrated)

The PPO GM agent now lives inside the editor package:
- Source: `nba2k_editor/gm_rl/`
- CBA rules extraction/artifacts: `nba2k_editor/gm_rl/cba/`

## Entry points
- Train CLI: `python -m nba2k_editor.entrypoints.train_gm_agent --adapter mock --total-steps 5000 --n-envs 2`
- Editor training hook: `python -m nba2k_editor.entrypoints.editor_train_hook --config logs/gm_rl/runs/<run_id>/config.json`
- Evaluate: `python -m nba2k_editor.gm_rl.eval --checkpoint logs/gm_rl/runs/<run_id>/checkpoints/checkpoint.pt --episodes 2`
- Extract CBA rules: `python -m nba2k_editor.entrypoints.extract_cba_rules --season 2025-26 --source <path-to-cba-docx>`
- Start MyEras MCP server: `python -m nba2k_editor.entrypoints.mcp_server`

## Tests
- `python -m pytest -q`

## Docs consistency check
- Run `python scripts/check_markdown_consistency.py` before doc-related PRs.

## Perf instrumentation
Set `NBA2K_EDITOR_PROFILE=1` to print timing summaries from instrumented hot paths.
