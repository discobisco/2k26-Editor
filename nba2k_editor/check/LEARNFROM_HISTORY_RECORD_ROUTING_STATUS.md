# LearnFrom History/Records/HOF routing status

Source: `/mnt/d/hermes/editorlearnfrom/_analysis/NBA2K26_history_record_routing_extract.md`.

## Confirmed LearnFrom routing evidence

- History pointer slot: `0x2e8`
- History stride: `0xa8`
- Record begin pointer slot: `0x2c8`
- Record end pointer slot: `0x2d8`
- Record stride: `0x98`
- Hall of Fame begin pointer slot: `0x338`
- Hall of Fame end pointer slot: `0x348`
- Hall of Fame stride: `0x6c`

## History type routing

- Season awards: `8..21`
- Past champions: `1`
- League leaders: `2..7`
- Hall of Famers: `255`

## Record routing

- Record categories: `single_regular`, `single_playoffs`, `season`, `career`
- Team embedded records: first record row whose first 4 bytes equal the current team address; then `510` consecutive records belong to that team block.

## Current editor status

- `nba2k_editor/core/Offsets/offsets_history.json` already contains the core History and Record field offsets from LearnFrom:
  - History fields such as `TYPE`, `SEASON`, `TEAMLOGO`, `TEAMNAME`, `TEAMCITY`, `RESULT`, `FIRSTNAME`, `LASTNAME`.
  - Record fields such as `TEAMLOGO`, `SIGNATUREID`, `FIRSTNAME`, `LASTNAME`, `DATA`, `DAY`, `MONTH`, `YEAR`.
- `nba2k_editor/core/Offsets/offsets_league.json` already has stride constants:
  - `recordSize: 152`
  - `historySize: 168`
  - `hallOfFameSize: 108`
- `nba2k_editor/ui/dpg_editor.py` currently owns History/Records presentation constants and row ranges.
- `nba2k_editor/models/data_model.py` currently owns History/Records summary specs, sparse invalid streaks, and NBA Records plausibility checks.

## Next implementation slice

Move the LearnFrom routing values above into declared metadata/model-owned table contracts, then have UI consume those contracts instead of owning row/type/column constants.

Architecture boundary remains unchanged:

- keep authored base pointers;
- no runtime signature scan;
- no roster-base scan lane.
