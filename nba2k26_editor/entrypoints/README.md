# entrypoints folder

This folder defines executable entrypoints for launching the editor.

## Files
- `__init__.py`: package marker for entrypoint modules.
- `gui.py`: GUI launcher for the editor.

## GUI launch flow (gui.py)
- Validates that the platform is Windows and shows a message if unsupported.
- Creates `GameMemory` and attempts to open the NBA 2K process.
- Chooses offsets target based on the detected module name, falling back to
  `MODULE_NAME` when no process is found.
- Calls `initialize_offsets(..., force=True)` and warns on `OffsetSchemaError`.
- Logs which offsets file was loaded to stdout (including custom files).
- Builds `PlayerDataModel` and `PlayerEditorApp`, then enters the Tk main loop.

## Entry point usage
- `python -m nba2k26_editor.entrypoints.gui`
- `python launch_editor.py`
- `run_editor.bat`

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
