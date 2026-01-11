# nba2k26_editor package

This package contains the full NBA 2K26 editor runtime: entrypoints, memory
access, offsets, data models, import/export logic, and the Tkinter UI.

## Runtime flow (high level)
1. `entrypoints.gui.main` opens the NBA 2K process (if running) and loads
   offsets via `core.offsets.initialize_offsets`.
2. `models.data_model.PlayerDataModel` builds categories and prepares live
   read/write helpers based on the loaded offsets.
3. `ui.app.PlayerEditorApp` builds screens and tools on top of the model.

## Package root files
- `__init__.py`: package metadata and `__version__` provider.
- `__main__.py`: `python -m nba2k26_editor` entrypoint, calls the GUI launcher.
- `autoload_extensions.json`: list of extension module paths to auto-load at
  startup (managed by the Extensions UI).
- `dual_base_mirror.py`: optional extension that mirrors player/team writes to
  alternate base tables and registers a player-panel settings widget.
- `README.md`: this document.

## Extensions and add-ons
- Extension hooks live in `core.extensions` and are used by the UI to insert
  player-panel widgets or full editor panels.
- `ui.extensions_ui` discovers `.py` files in the project root and the
  `Extentions` folder (spelling is intentional) and can restart the app to
  unload extensions.
- `dual_base_mirror.py` patches `GameMemory.write_bytes` to mirror writes to
  alternate bases; its settings are stored in `dual_base_mirror.json`.

## Import/export data flow
- Excel import/export uses `importing.excel_import` and template spreadsheets
  stored under `Offsets`.

## Subpackages
- `ai\`: AI assistant UI, control bridge, and NBA data loader.
- `core\`: shared config, conversions, offsets, dynamic base scanning, and
  extension registration.
- `entrypoints\`: executable entrypoints (GUI bootstrap).
- `importing\`: Excel import helpers and shared CSV parsing utilities.
- `memory\`: Win32 process and memory access.
- `models\`: data model and schema helpers.
- `ui\`: Tkinter UI screens, dialogs, and editor windows.

## Data and generated folders
- `Offsets\`: merged offsets bundle and reference spreadsheets.
- `NBA Player Data\`: NBA reference workbook for the AI assistant.
- `logs\`: runtime logs (memory read/write audit when dev logging is enabled).
- `build\`: PyInstaller intermediate artifacts.
- `dist\`: PyInstaller output executable.
- `__pycache__\`, `cache\`: Python caches (generated).

## Runtime config files
- `ai_settings.json`: persisted AI backend settings (remote/local).
- `autoload_extensions.json`: persisted list of autoload extensions.
- `dual_base_mirror.json`: dual-base mirror settings.

All are stored in the package root via `core.config.CONFIG_DIR` and are safe
to delete if you want to reset to defaults.
