# NBA2K Editor TODO

Evidence source: live repo inspection plus `python3 -m nba2k_editor.entrypoints.gui --target NBA2K26.exe --verify-edits`.

Ordered from easiest to implement to hardest to implement.

## 0. Player/team/roster generator

- [ ] Add player generator.
- [ ] Player generator must use the current data inside `nba2k_editor/Player Generator/` as its source data.
- [ ] Player generator must use both player stats and team stats from the selected target year to build attributes and tendencies.
- [ ] Player generator must derive values from target-year evidence/rules and must not randomly assign attributes or tendencies.
- [ ] Add team generator.
- [ ] Add roster generator.
- [ ] Define generator input contracts before implementation: source data from `nba2k_editor/Player Generator/`, required fields, output target, and validation/readback path.
- [ ] Add explicit overwrite-current-roster mode for generated player/team/roster output.
- [ ] Build a local player-data database populated from exported in-game/player-editor reads.
- [ ] Add export-from-game/player-data flow so current roster/player data can train or improve the player builder.
- [ ] Use collected 2K player data to refine builder formulas, ranges, archetypes, and tendency/attribute mappings over time.
- [ ] Store exported player data with source metadata: game target, roster/session label, player ID/signature ID, team, field names, raw values, display values, and export timestamp.
- [ ] Add database-backed analysis views for improving generator rules: archetypes, rating ranges, tendencies, badges, signatures, contracts, gear, and team context.
- [ ] Gate roster overwrite behind preview/diff, validation, and backup/snapshot before write.
- [ ] Keep generator data ownership separate from live editor write logic, with an explicit approved bridge for applying generated output to the current roster.

## Current verified baseline

- [x] Dear PyGui live-memory editor exists.
- [x] Package compiles with `python3 -m compileall -q nba2k_editor`.
- [x] `NBA2K26.exe` verify-edits path works.
- [x] UI has Home, Players, Teams, NBA History, NBA Records, Staff, Stadiums, Jerseys, Shoes.
- [x] UI exposes NBA 2K22, NBA 2K23, NBA 2K24, NBA 2K25, NBA 2K26.
- [x] 2K26 coverage: 778 total fields, 768 writable fields, 1 implementation-required field.
- [x] Player screen has list, team filter, search, detail preview, Edit Player.
- [x] Player edit window has grouped field tabs, current/new values, address/status, reload, save with readback.
- [x] Player multi-select supports Ctrl/Shift selection and batch write across selected records.
- [x] Team screen has list, editable summary fields, Save Fields, Edit Team.
- [x] Team editor includes Team Records tab.
- [x] NBA History screen covers Season Awards, Past Champions, League Leaders, Hall of Famers.
- [x] NBA Records screen covers Single Game Regular, Single Game Playoffs, Season, Career.
- [x] Backend supports process attach, memory read/write, pointer/base/stride addressing, authored offsets, dropdowns, strings, colors, ratings/tendency conversions, height/weight/year conversions, injury duration conversion, result-score parsing.

## 1. Documentation / labeling / low-risk UI polish

- [ ] Document or intentionally handle readonly player fields: Signature ID, Unique Signature ID, Current Team in Stats/Season IDs.
- [ ] Document or intentionally handle readonly Team Unique ID.
- [ ] Document or intentionally handle readonly Staff fields.
- [ ] Decide whether Shoes should stay readonly or get writable support.
- [ ] Add clearer warnings when no live process is attached.
- [ ] Rename UI labels if needed: current app title is `Offline Player Data Editor`, but implementation is live-memory attach/read/write.
- [ ] Improve save messaging for multi-select batch writes.
- [ ] Add target-readiness indicators so 2K22-2K25 are not presented as equally ready until verified.

## 2. Validation / tests that do not require new product behavior

- [x] Keep `python3 -m compileall -q nba2k_editor` passing.
- [x] Keep `python3 -m nba2k_editor.entrypoints.gui --target NBA2K26.exe --verify-edits` passing.
- [ ] Add focused tests for conversions and field read/write mapping where mock memory can prove behavior.
- [ ] Add live-memory verification notes only from actual runtime evidence, not inferred field names.
- [ ] Validate NBA History edits with live in-game/readback evidence before treating them as safe user-facing edits.
- [ ] Validate NBA Records edits with live in-game/readback evidence before treating them as safe user-facing edits.
- [ ] Validate team record edits with live in-game/readback evidence before treating them as safe user-facing edits.

## 3. Small targeted fixes

- [ ] Resolve the lone 2K26 implementation-required player field: `Players / Vitals / Vitals / College/From` (`ptr_string`).
- [ ] Fix `NBA2K25.exe` verify-edits failure: missing `staffSize`.
- [ ] Fix `NBA2K22.exe` verify-edits failure: missing `playerSize`.
- [ ] Fix `NBA2K23.exe` verify-edits failure: missing `playerSize`.
- [ ] Fix `NBA2K24.exe` verify-edits failure: missing `playerSize`.
- [ ] Add verify-edits checks for every target once 2K22-2K25 configs are corrected.

## 4. Safety before bigger editing features

- [ ] Add visible changed-field log for each save/readback operation.
- [ ] Add preview/diff before save for single-record and multi-record writes.
- [ ] Add undo/revert for the current editor window or last write batch.
- [ ] Add automatic backup/snapshot before any write operation.

## 5. Small player/team workflow improvements

- [ ] Add player compare screen.
- [ ] Add clone/copy player workflow.
- [ ] Add free-agent assignment workflow if current team/free-agent representation is verified.
- [ ] Add trade/swap workflow if it can be mapped without hidden side effects.

## 6. Grid/list usability

- [ ] Add persistent column order/saved views.
- [ ] Add favorites/pinned fields for common edits.
- [ ] Add sortable columns in grid views.
- [ ] Add column filters beyond current player search/team filter.
- [ ] Add true spreadsheet-style grid editing.

## 7. Import/export and record snapshots

- [ ] Add export of selected records with raw + display values.
- [ ] Add CSV export for selected domain/records.
- [ ] Add CSV import with validation and preview.
- [ ] Add Excel-compatible export/import if CSV proves insufficient.
- [ ] Add copy/paste from spreadsheet into selected rows/fields.
- [ ] Add batch set value operation.
- [ ] Add batch add/subtract numeric operation.
- [ ] Add field templates for copying one player profile section to another player.
- [ ] Add roster diff between two loaded snapshots if file/snapshot support exists.

## 8. Advanced/modder tooling

- [ ] Add raw table/schema inspector UI.
- [ ] Show base pointer, stride, record address, and field address in an advanced view.
- [ ] Add field provenance display: source offsets file, version payload, type, dropdown source, readonly/writeable state.
- [ ] Add unknown/unmapped field reporting instead of guessing labels.
- [ ] Add import of selected records with validation/readback.

## 9. High-risk roster/game-structure workflows

- [ ] Add lineup/rotation/depth-chart workflow after identifying authoritative fields.
- [ ] Add create/delete player only if the game data model supports it safely.
- [ ] Add roster-file open/save.
- [ ] Add mod package/export format only after import/export contracts are stable.

## Current capability details

### Player editor currently has

- [x] Player list.
- [x] Team filter.
- [x] Player search.
- [x] Player detail preview: OVR, Team, Position, Number, Height, Weight, Face ID, Unique ID.
- [x] Ctrl/Shift multi-select selection behavior.
- [x] Edit window with Current/New/Address columns.
- [x] Save with readback.
- [x] Batch write of edited field across selected records.
- [x] Vitals groups: ID, Body, Vitals, Health, Team, Type.
- [x] Gear groups: Shoes/Gear, Upper Body Accessories, Lower Body Accessories.
- [x] Attributes groups: Offense, Defense, Athleticism, Durability, Mental, Misc, Rebounding.
- [x] Tendencies groups: Jump Shooting, Layups And Dunks, Drive Setup, Driving, Passing, Post Game, Freelance, Defense, Hot Zones.
- [x] Signature groups: Jump Shooting, Layups And Dunks, Post Game, Ball Handling, Misc.
- [x] Contract groups: Contract Terms, Contract Options, Contract Status, Salary.
- [x] Badge groups: Inside Scoring, Outside Scoring, Playmaking, Defending, Athleticism, Rebounding, Personality, General.
- [x] Stats groups: Season High, Career High, Awards, Season IDs.

### Team editor currently has

- [x] Team list.
- [x] Editable summary fields: Team Name, City Name, City Abbrev.
- [x] Save Fields button.
- [x] Edit Team button.
- [x] Team editor window.
- [x] Team Records tab.
- [x] Team groups: Vitals, Jerseys, Team Players, Team Stadium.

### NBA History currently has

- [x] Season Awards section.
- [x] Past Champions section.
- [x] League Leaders section.
- [x] Hall of Famers section.
- [x] Award tabs include MVP, Rookie of the Year, Sixth Man, Defensive Player, Most Improved, Clutch Player, All-NBA, All-Defensive, All-Rookie, Coach of the Year.

### NBA Records currently has

- [x] Single Game Regular section.
- [x] Single Game Playoffs section.
- [x] Season section.
- [x] Career section.
- [x] Base stat tabs: Points, FG Made, 3PT Made, FT Made, Rebounds, Assists, Blocks, Steals, Minutes, Turnovers.
- [x] Extended Season/Career stat tabs include PPG, FG%, RPG, APG, triple doubles, and related stats.

### Backend currently has

- [x] Live process attach.
- [x] Process/module detection.
- [x] Pointer/base/stride addressing.
- [x] Read/write memory primitives.
- [x] Authored offset JSON resources.
- [x] Dropdown mapping.
- [x] Address dropdowns for teams/stadiums/uniforms.
- [x] Shoe dropdown mapping from loaded Shoes list.
- [x] Attribute 25-99 conversions.
- [x] Tendency 0-100 conversions.
- [x] Potential conversions.
- [x] Min/max potential-like conversions.
- [x] Body scale conversions.
- [x] Injury duration day conversions.
- [x] Height raw/inches conversions.
- [x] Pounds/kg conversions.
- [x] Year offset conversions.
- [x] Result score parsing.
- [x] Color, hex bytes, string, and wstring handling.

## Missing capability checklist

- [ ] CSV/Excel import/export.
- [ ] Backup before write.
- [ ] Undo/revert.
- [ ] Roster-file open/save.
- [ ] Clone player.
- [ ] Create/delete player.
- [ ] Trade workflow.
- [ ] Lineup/rotation/depth-chart workflow.
- [ ] Roster diff.
- [ ] Player comparison screen.
- [ ] Raw table/schema inspector UI.
- [ ] True spreadsheet grid bulk editor.
- [ ] Mod package export.
- [ ] 2K22-2K25 verified support.
