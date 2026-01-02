# ui folder

This folder contains the Tkinter UI for the editor, including the main window,
screen builders, dialogs, and advanced editor windows.

## Architecture
- `app.py` defines `PlayerEditorApp`, which:
  - Tracks selection state, listbox references, and UI variables.
  - Builds screens via `build_home_screen`, `build_players_screen`,
    `_build_teams_screen`, `build_staff_screen`, `build_stadium_screen`,
    `build_ai_screen`, and `_build_excel_screen`.
  - Manages AI settings, local AI detection, and starts the HTTP control bridge.
  - Loads extensions via `extensions_ui` and registers extension hooks.
  - Runs dynamic base scans and applies base overrides with `initialize_offsets`.
  - Orchestrates player/team scanning, list refreshes, and save actions.
  - Launches tool windows (full editors, randomizer, batch edit, team shuffle,
    import/export dialogs, Excel hub).
  - Note: `_build_players_screen()` returns early; legacy code below the return
    is unreachable.

## Screens
- `home_screen.py`: overview tab with hook target selection, dynamic base scan,
  offsets loader, extension toggles, and AI Settings tab.
- `players_screen.py`: player list, search/filtering, and detail panel with
  full editor and copy tools.
- `teams_screen.py`: team list and editable team fields (module exists but
  the app currently uses its own `_build_teams_screen`).
- `staff_screen.py`: staff list and editor launch.
- `stadium_screen.py`: stadium list and editor launch.
- `ai_screen.py`: AI Assistant screen and control bridge status.

## Tool windows and dialogs
- `full_player_editor.py`: tabbed editor for player categories.
- `full_team_editor.py`: full team editor (strings, enums, colors, pointers).
- `full_staff_editor.py`: staff editor scaffold.
- `full_stadium_editor.py`: stadium editor scaffold.
- `batch_edit.py`: apply one field across a filtered set of players.
- `randomizer.py`: randomize ranges for attributes/tendencies/durability.
- `team_shuffle.py`: reassign players across teams.
- `dialogs.py`: import summary dialog, search entry, category selection dialog.

## Import/export flows
- `import_flows.py`:
  - Multi-file import UI for Excel and delimited data.
  - CSV category auto-detection for Attributes/Tendencies/Durability.
  - COY import flow with Google Sheet auto-download and missing-player summary.
- Excel hub in `app.py` provides a combined import/export window with progress
  feedback and optional match-by-name handling.

## Shared utilities
- `extensions_ui.py`: extension discovery, load/unload, autoload persistence.
- `theme.py`: ttk theme configuration.
- `widgets.py`: shared widget helpers (mousewheel binding, etc).

## Files
- `__init__.py`: package marker.
- `README.md`: this document.

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
