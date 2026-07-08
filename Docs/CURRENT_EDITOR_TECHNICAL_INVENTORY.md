# Current Editor Technical Inventory

Scope: `/mnt/d/hermes/gpt trial run/nba2k_editor` as it exists in the working tree. This is a technical capability map, not a cleanup plan.

Static evidence summary:

- Python files scanned: `38`.
- Authored offset field rows counted from `core/Offsets/offsets_*.json`: `1323`.
- Offset domain field counts: `offsets_history.json=20, offsets_jersey.json=88, offsets_league.json=0, offsets_players.json=801, offsets_shoes.json=22, offsets_stadiums.json=30, offsets_staff.json=81, offsets_teams.json=281`.
- Primary GUI: `nba2k_editor/ui/qt_app.py`.
- Primary live model: `nba2k_editor/models/data_model.py` (`1384` lines).

## 1. Application shell and launch

- Provides a PyQt6 desktop editor (`QtEditorApp`) with screen navigation, status labels, operation dialogs, cancellable background operation plumbing, and per-screen list/detail/editor windows. Evidence: `ui/qt_app.py`.
- CLI entrypoints route into the GUI: `__main__.py` and `entrypoints/gui.py`. Evidence: `__main__.py:20`, `entrypoints/gui.py:24`.
- Startup can delete runtime cache dirs before launching. Evidence: `entrypoints/runtime_cleanup.py:5`, `entrypoints/gui.py:26`.

## 2. Process/memory layer

- Attaches to a target NBA2K process by executable name and exposes read/write primitives over Windows process memory through WSL/ctypes-compatible Win32 wrappers. Evidence: `memory/game_memory.py:15`, `memory/game_memory.py:49`, `memory/win32.py:1`.
- Target labels cover NBA2K22 through NBA2K26 in offset bootstrap. Evidence: `core/offsets.py:18-25`.
- The model owns target selection, attach, runtime status, domain scan, read, write, and record address calculation. Evidence: `models/data_model.py:256`, `models/data_model.py:272`, `models/data_model.py:972`, `models/data_model.py:1004`, `models/data_model.py:1013`, `models/data_model.py:1311`.

## 3. Offset/schema system

- Uses split authored JSON sources per domain, with `Players` and `Draft Class` sharing `offsets_players.json`, `NBA History` and `NBA Records` sharing `offsets_history.json`, and separate Teams/Staff/Stadiums/Jerseys/Shoes files. Evidence: `core/offsets.py:50-63`.
- Loads target-specific base pointers, pointer chains, row sizes/strides, dropdown metadata, and field version payloads. Evidence: `core/offsets.py:33-48`, `core/offsets.py:373`, `core/offsets.py:399`, `core/offsets.py:448`.
- Preserves field identity with section/group/display/name/version metadata in `FieldEntry`. Evidence: `models/schema.py:8`, `models/schema.py:40`.
- Supports raw/display conversion, bitfield extraction/writes, mapped list/dropdown values, id-prefixed options, body/rating/year/height/weight/injury conversions. Evidence: `core/field_io.py:24`, `core/field_io.py:95`, `core/field_io.py:145`, `core/conversions.py:1`, `core/conversions.py:93`, `core/conversions.py:166`, `core/conversions.py:263`.

## 4. Live editable domains

Current authored editor domains:

| Domain | Source | Technical behavior | Field count |
|---|---|---|---:|
| Players | `offsets_players.json` | Scans player rows, labels by names, reads/writes grouped fields, handles team filters, stat selectors, roster snapshots, reset values. | 801 |
| Draft Class | `offsets_players.json` | Uses draft-class base/stride/max count while reusing player field schema. | included above |
| Teams | `offsets_teams.json` | Scans teams, displays/saves team summary values, owns Team `PLAYER#` slot membership, Team Records actions. | 281 |
| Staff | `offsets_staff.json` | Generic scan/list/edit via field schema. | 81 |
| Stadiums | `offsets_stadiums.json` | Generic scan/list/edit via field schema. | 30 |
| Jerseys | `offsets_jersey.json` | Generic scan/list/edit with jersey vitals/colors. | 88 |
| Shoes | `offsets_shoes.json` | Generic scan/list/edit and shoe dropdown relation for player shoe fields. | 22 |
| NBA History | `offsets_history.json` | Separate History screen rows, tabs/sections, generic edit selected row. | 20 total history/records |
| NBA Records | `offsets_history.json` | Record cards/tables, data value editing, zeroing, Team Records grouping. | included above |

Evidence: `models/data_model.py:565`, `models/data_model.py:838`, `ui/qt_app.py`.

## 5. Player workflow

- Player list supports team filter and text search. Evidence: `ui/qt_app.py`, `models/data_model.py:381-384`.
- Player editor uses grouped tabs/sections and shared `read_entry_value` / `write_entry_value` path for saves. Evidence: `ui/qt_app.py`, `models/data_model.py:1004`, `models/data_model.py:1013`.
- Multi-selection/batch editing is supported through selected editor items and dirty-row tracking. Evidence: `ui/qt_app.py`.
- Supports player reset values and bulk Stat ID reset to `65535`. Evidence: `models/data_model.py:1020`, `models/data_model.py:1051`, `ui/qt_app.py`.
- Exports and applies player roster snapshots, including source/target team range/mode UI and cancellable long operation support. Evidence: `models/data_model.py:1093`, `models/data_model.py:1169`, `ui/qt_app.py`.

## 6. Team workflow

- Team screen has refresh, selected team summary fields, save, edit, and zero all Team Record data actions. Evidence: `ui/qt_app.py`.
- Team/player roster relation is represented through Team `PLAYER#` slots and player current-team pointer reads. Evidence: `models/data_model.py:299-341`, `models/data_model.py:344-353`.
- Team Records row routing is isolated in `models/team_record_routing.py`. Evidence: `models/team_record_routing.py:8`, `models/team_record_routing.py:54`, `models/team_record_routing.py:86`.

## 7. NBA History and NBA Records workflow

- History screen presents selectable sections and tabbed stat/history tables, with edit selected row. Evidence: `ui/qt_app.py`.
- Records screen presents sections, stat tabs, cards/tables, editable `Data` values, save, and zero actions. Evidence: `ui/qt_app.py`, `models/data_model.py:813-830`.

## 8. Player Generator

- Reads bundled/static player data through SQLite/workbook source helpers. Evidence: `Player Generator/workbook_sqlite.py:11`, `Player Generator/sql_sources.py:1`, `Player Generator/source_data.py:1`.
- Builds season/context indexes, draft-class proposals, generated player proposals, attribute/tendency/profile rules, and nearest-neighbor stat suggestions. Evidence: `Player Generator/player_generator.py:56`, `Player Generator/player_generator.py:142`, `Player Generator/player_rules.py:35`, `Player Generator/stat_neighbor_framework.py:49`.
- Tracks a generated-player pool SQL database and can sync current roster into the pool. Evidence: `Player Generator/player_generation_pool.py:48`, `Player Generator/player_generation_pool.py:120`, `ui/qt_app.py`.
- UI exposes Load Source, Add Current Roster to Pool SQL, Sync Player Pool SQL, Display Preview, Import Generated Players, and Import Matched Names. Evidence: `ui/qt_app.py`.
- Import path writes generated proposals to live game fields through the shared model write seam. Evidence: `Player Generator/game_port.py:36`, `Player Generator/game_port.py:84`, `Player Generator/game_port.py:159`.

## 9. Things this editor explicitly is not doing

- No 3D venue/IFF/SCNE visual preview surface is present under `nba2k_editor`.
- No archive browser/search/extract UI for installed NBA 2K game archives is present.
- No Mod Manager/package library/runtime redirect UI is present.
- No WebView2/HTML/Three.js viewer is present.
- No runtime DLL companion/hook IPC is present.
- No legacy 2K9-2K14 roster-file editing pipeline is present.

Those absences are based on scanned `nba2k_editor/**/*.py` and available project docs, not on a runtime UI launch.
