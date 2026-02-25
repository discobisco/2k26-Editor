# Offsets folder

## Purpose and Ownership
- Offsets payloads/dropdowns/templates that define runtime field and import schemas.
- Treated as versioned project data, not executable Python module code.

## Technical Deep Dive
Offsets artifacts are loaded by runtime services and workflows rather than imported as Python modules.
This folder currently contains 18 tracked artifacts used by editor features.

## Artifact Tree
- `dropdowns.json`
- `ImportJerseys.xlsx`
- `ImportNBAHistory.xlsx`
- `ImportNBARecords.xlsx`
- `ImportPlayers.xlsx`
- `ImportShoes.xlsx`
- `ImportStadiums.xlsx`
- `ImportStaff.xlsx`
- `ImportTeams.xlsx`
- `offsets_history.json`
- `offsets_jersey.json`
- `offsets_league.json`
- `offsets_players.json`
- `offsets_shoes.json`
- `offsets_stadiums.json`
- `offsets_staff.json`
- `offsets_teams.json`
- `StatsImport.xlsx`

## Producers and Consumers
- Producers: maintainers updating data artifacts after feature/game updates.
- Consumers: `nba2k_editor/core/offsets.py`
- Consumers: `nba2k_editor/importing/excel_import.py`

## Update Workflow
1. Update artifacts in place while preserving expected naming/format conventions.
2. Run relevant runtime path and pytest suites that consume these artifacts.
3. Validate output behavior in UI/CLI workflows that load these files.

## Validation Checklist
- Confirm all expected files are present and readable.
- Confirm consumer modules can load/parse artifacts without runtime errors.
- Run targeted tests for workflows that depend on this folder.
