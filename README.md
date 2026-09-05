# DB2K Editor

An unofficial Windows desktop editor for live NBA 2K game data. DB2K Editor attaches to a running game process, loads version-aware field definitions, and provides a PyQt6 interface for editing roster, league, record, and presentation data.

The current editor is centered on NBA 2K26. Target detection and offset metadata also include NBA 2K22, NBA 2K23, NBA 2K24, and NBA 2K25; available fields depend on the version data present in the bundled offset files.

> [!WARNING]
> This application writes directly to a running game process. Back up important saves, test changes on a disposable roster, and use the editor only in local/offline play. You are responsible for any save corruption, game instability, or account consequences.

## Features

- Automatic detection of supported running NBA 2K processes
- Live, schema-driven reads and writes through authored JSON offsets
- Editors for:
  - Players
  - Teams
  - Staff
  - Stadiums
  - Jerseys
  - Shoes
  - NBA History
  - NBA Records
- Player search, team filtering, multi-selection, and batch editing
- Player movement, roster-slot management, and roster snapshot export/apply workflows
- Player and team record editing
- Player season-stat selection and Stat ID reset tools
- Historical Player Generator with preview, draft-class generation, player-pool synchronization, and live import workflows

- Background loading and cancellable long-running operations
- PyInstaller configuration for a standalone Windows executable

## Requirements

- Windows 10 or Windows 11, 64-bit
- Python 3.11 or newer
- A supported NBA 2K game running on Windows
- Python packages:
  - `PyQt6`
  - `psutil`
  - `numpy`

Development and packaging also use `pytest` and `PyInstaller`.


The repository does not currently include a dependency lockfile. Create a Windows virtual environment and install the dependencies explicitly:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install PyQt6 psutil numpy
```

For tests and executable builds:

```bat
.venv\Scripts\python.exe -m pip install pytest pyinstaller
```

## Quick Start

1. Open a terminal in the repository root.
2. Create the Windows virtual environment and install the packages listed above.
3. Start the supported NBA 2K game.
4. Load the roster, league, or game state you want to edit.
5. Launch DB2K Editor:

```bat
run_editor.bat
```

You can also launch it directly:

```bat
.venv\Scripts\python.exe launch_editor.py
```

The default `auto` target detects the supported NBA 2K executable that is currently running. To request a specific target:

```bat
.venv\Scripts\python.exe launch_editor.py --target NBA2K26.exe
```

To open the interface without the initial attach/list load, use:

```bat
.venv\Scripts\python.exe launch_editor.py --no-load-on-start
```

### Launching from WSL

The repository can be managed from WSL, but live game-memory access runs through Windows. When a Windows `.venv` exists at the project root, the launcher automatically relaunches itself with `.venv\Scripts\python.exe`:

```bash
python3 launch_editor.py
```

## Using the Editor

1. Confirm that the correct game target is shown as attached.
2. Load or refresh the domain you want to edit.
3. Select a record by its stable list index.
4. Open the record editor and change only the required fields.
5. Review the displayed values before saving.
6. Save in-game after confirming the result.

Offset definitions are version-specific. A field that lacks valid metadata for the attached game version should not be treated as writable.

## Player Generator Data

The Player Generator can use local SQLite datasets and generated model artifacts under:

```text
nba2k_editor/Player Generator/NBA Player Data/
```

Large datasets and generated subdirectories are intentionally excluded by `.gitignore`, so a fresh Git clone may not contain the historical source databases or trained artifacts required by every generator workflow. The normal live editor and bundled offset JSON files are separate from those local datasets.

Do not commit licensed, private, or generated datasets unless you have the right to redistribute them.


## Project Structure

```text
.
├── launch_editor.py                 # Main launcher and WSL-to-Windows relaunch
├── run_editor.bat                   # Windows launcher
├── NBA2KEditor.spec                 # PyInstaller build definition
├── nba2k_editor/
│   ├── core/                        # Addressing, conversions, field I/O, offsets
│   │   └── Offsets/                 # Version-aware JSON field definitions
│   ├── memory/                      # Win32 process and memory primitives
│   ├── models/                      # Editor state, scanning, routing, and writes
│   ├── ui/                          # PyQt6 application, theme, and widgets
│   ├── franchise/                   # Franchise state and simulation workflows
│   ├── Player Generator/            # Historical player generation pipeline
│   └── entrypoints/                 # GUI and runtime-cleanup entrypoints
├── tests/                           # Automated tests
└── Docs/                            # Technical notes and research references
```

## Testing

Run the automated test suite from the repository root:

```bat
.venv\Scripts\python.exe -m pytest -q
```

Most model and UI tests use controlled test doubles. Tests that require a running game or explicit live-memory proof must be run separately in a controlled environment.

## Building the Windows Executable

Install `PyInstaller`, then build from the repository root:

```bat
.venv\Scripts\python.exe -m PyInstaller --clean NBA2KEditor.spec
```

The executable is written to:

```text
dist/DB2kEditor.exe
```

The build spec includes local offset resources and includes Player Generator datasets only when those files exist in the expected local paths.

## Development Notes

- Live memory behavior is Windows-only.
- Offset JSON files are the source of truth for bases, pointer chains, strides, field layouts, dropdowns, and per-version field metadata.
- UI code should remain presentation-focused; scanning, identity, routing, and write behavior belong in the model/core layers.
- Do not add guessed offsets, silent fallbacks, or substitute write paths.
- Validate live-memory changes against the exact affected game version and field.

See [Docs/CURRENT_EDITOR_TECHNICAL_INVENTORY.md](Docs/CURRENT_EDITOR_TECHNICAL_INVENTORY.md) for a deeper technical capability map.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by 2K Games, Visual Concepts, Take-Two Interactive, the NBA, or the NBPA. All product names and trademarks belong to their respective owners.
