# NBA2K26 Editor Repository Guide

This repository hosts a Python/Tkinter live-memory editor for NBA 2K26. The app
attaches to the running game process, loads offsets from bundled data files, and
exposes tools for editing players, teams, staff, and stadiums.

## What is included
- GUI launcher + Windows batch launcher.
- Win32 memory layer with structured logging.
- Offset-driven schemas with per-version support (2K22-2K26).
- Import/export for CSV and Excel templates, including 2KCOY flows.
- AI Assistant panel with optional local/remote backends and HTTP control bridge.
- Extension hooks for custom panels and full editor add-ons.

## Quick start (development)
1. Windows is required (the memory layer uses Win32 APIs).
2. Run one of:
   - `run_editor.bat`
   - `python -m nba2k26_editor.entrypoints.gui`
   - `python launch_editor.py`
3. If the game is not running, the UI still opens but live memory reads/writes
   will be unavailable.

## Optional dependencies
- `psutil`: more reliable process discovery.
- `pandas` + `openpyxl`: Excel import/export and NBA data lookups in the AI panel.

## Packaging
- Build a standalone executable with:
  - `pyinstaller NBA2K26Editor.spec`
- Output lands in `nba2k26_editor\dist\NBA2K26Editor.exe`.
- The spec bundles `nba2k26_editor\Offsets` and `nba2k26_editor\NBA Player Data`
  as data resources.

## Root files
- `launch_editor.py`: PyInstaller-friendly launcher.
- `NBA2K26Editor.spec`: PyInstaller build spec.
- `run_editor.bat`: Windows launcher that prefers a local `.venv`.
- `README.md`: this guide.

## Repository map
- `nba2k26_editor\`: main package (see `nba2k26_editor\README.md`).
- `nba2k26_editor\Offsets\`: offsets bundle and reference spreadsheets.
- `nba2k26_editor\NBA Player Data\`: NBA reference workbook for the AI panel.
- `nba2k26_editor\importing\`: CSV/Excel import logic and templates.
- `nba2k26_editor\logs\`: runtime logs.
- `nba2k26_editor\build\`, `nba2k26_editor\dist\`: PyInstaller artifacts.

## Documentation index
- `nba2k26_editor\README.md`: package architecture and data flow.
- `nba2k26_editor\ai\README.md`: AI assistant and control bridge.
- `nba2k26_editor\core\README.md`: config, offsets, dynamic base scanning.
- `nba2k26_editor\entrypoints\README.md`: launch entrypoints.
- `nba2k26_editor\memory\README.md`: Win32 memory access layer.
- `nba2k26_editor\models\README.md`: data models and import/export logic.
- `nba2k26_editor\ui\README.md`: Tkinter UI screens and tools.
- `nba2k26_editor\Offsets\README.md`: offsets data format and templates.
- `nba2k26_editor\NBA Player Data\README.md`: NBA workbook schema.
- `nba2k26_editor\logs\README.md`: log format and retention notes.
- `nba2k26_editor\build\README.md`: PyInstaller build cache.
- `nba2k26_editor\dist\README.md`: packaged output.

## Runtime-generated files
- `nba2k26_editor\ai_settings.json`: AI backend config.
- `nba2k26_editor\autoload_extensions.json`: extension autoload list.
- `nba2k26_editor\dual_base_mirror.json`: dual-base mirror settings.
- `nba2k26_editor\logs\memory.log`: memory read/write audit log.
