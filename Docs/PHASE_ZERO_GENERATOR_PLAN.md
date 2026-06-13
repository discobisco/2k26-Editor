# Phase Zero Player/Team/Roster Generator Implementation Plan

> **For Hermes:** Use the repo `AGENTS.md` contract and the `gpt-trial-run-orchestrator` workflow. Keep generator data ownership separate from live editor write logic. Do not add fallback/random output.

**Goal:** Implement Phase 0 from `nba2k_editor/EDITOR_TODO.md`: a deterministic player/team/roster generator backed by the current `nba2k_editor/Player Generator/` data, with local exported-2K data storage, preview/diff/validation/backup gates, and an explicit apply bridge to live roster writes.

**Architecture:** Build the generator as a separate backend area inside `nba2k_editor/Player Generator/`, next to the source data it owns. That folder owns source-data discovery/parsing, input contracts, deterministic rule outputs, local export database, generated proposal models, preview/diff/validation, and analysis views. Existing live editor write logic remains in `models/`, `core/`, and `memory/`; the generator can only apply output through a narrow bridge that consumes validated proposals and requires explicit overwrite mode plus backup/snapshot evidence.

**Tech Stack:** Python stdlib first (`dataclasses`, `pathlib`, `csv`, `json`, `sqlite3`, `zipfile`, `xml.etree.ElementTree`, `unittest`). No Excel runtime dependency in the first slice. Tests live under top-level `tests/`.

---

## Phase 0 checklist coverage map

| TODO line | Requirement | Plan lane |
|---:|---|---|
| 9 | Add player generator | Tasks 5-8 |
| 10 | Use current data inside `nba2k_editor/Player Generator/` | Tasks 1-3 |
| 11 | Use player stats and team stats from selected target year | Tasks 4-6 |
| 12 | Derive values from target-year evidence/rules; no random attributes/tendencies | Tasks 5-7 |
| 13 | Add team generator | Tasks 9-10 |
| 14 | Add roster generator | Tasks 11-12 |
| 15 | Define input contracts before implementation | Tasks 1-2 |
| 16 | Explicit overwrite-current-roster mode | Tasks 12-14 |
| 17 | Local player-data DB populated from exported editor reads | Tasks 15-16 |
| 18 | Export-from-game/player-data flow | Tasks 15-17 |
| 19 | Use collected 2K data to refine formulas/ranges/archetypes/tendencies | Tasks 18-20 |
| 20 | Store exported data with source metadata | Task 15 |
| 21 | DB-backed analysis views | Tasks 18-20 |
| 22 | Roster overwrite gated by preview/diff, validation, backup/snapshot | Tasks 13-14 |
| 23 | Separate generator ownership from live editor writes with explicit approved bridge | Tasks 1, 12-14 |
| UI access | Add UI entry point after proposal/preview/validation gates exist | Task 21 |

---

## Non-goals / hard boundaries

- Do not write live game memory from generator code during source-data, formula, preview, or database tasks.
- Do not import or inspect Excel with third-party libraries in the first slice. Use stdlib workbook metadata only until a real parser contract is chosen.
- Do not randomize attributes, tendencies, rosters, signatures, or team values.
- Do not put tests under `nba2k_editor/`; use top-level `tests/`.
- Do not move or rewrite the existing `Player Generator/` data artifacts.
- Do not add fallback data if a required player/team/stat source is missing. Fail loud.

---

## Task 1: Create generator package and source-data inventory seam

**Objective:** Add a read-only generator package that can locate the current source-data artifacts without importing workbook libraries or touching live memory.

**Files:**
- Create: `nba2k_editor/Player Generator/__init__.py`
- Create: `nba2k_editor/Player Generator/source_data.py`
- Test: `tests/test_generator_source_data.py`

**Steps:**
1. Write `test_default_source_inventory_uses_current_player_generator_folder` asserting the default root is `nba2k_editor/Player Generator/NBA Player Data` and required files exist.
2. Write `test_workbook_sheet_inventory_reads_xlsx_metadata_with_stdlib` asserting workbook sheet names include `Player Per Game`, `Team Stats Per Game`, and `Advanced`.
3. Write `test_sidecar_inventory_reads_portraits_and_logos` asserting sidecar counts are non-zero and parsed from existing `.txt` files.
4. Implement `GeneratorSourceInventory.from_default()` and `read_workbook_sheets()` using `zipfile` + XML only.
5. Run `python3 -m unittest tests.test_generator_source_data -v`.

**Acceptance:** Tests pass. No generator module imports `random`, `openpyxl`, `pandas`, `xlrd`, `xlsxwriter`, or live `GameMemory`.

---

## Task 2: Define generator input contracts before formulas

**Objective:** Make selected target year, source root, output target, and validation/readback mode explicit before player/team generation exists.

**Files:**
- Create: `nba2k_editor/Player Generator/contracts.py`
- Test: `tests/test_generator_contracts.py`

**Steps:**
1. Add `GeneratorInputContract` dataclass with `season`, `source_root`, `output_target`, and optional `roster_label`.
2. Add allowed output targets: `proposal`, `preview`, `overwrite_current_roster`.
3. Reject missing/zero season, missing source root, unknown output target, and overwrite mode without `roster_label`.
4. Add a `validate()` method returning a normalized copy or raising `ValueError`/`FileNotFoundError`.
5. Run `python3 -m unittest tests.test_generator_contracts -v`.

**Acceptance:** There is no default season. Contract validation blocks implementation from silently guessing year/source/output.

---

## Task 3: Build source-table availability contract

**Objective:** Map source tables required by Phase 0 without parsing every row yet.

**Files:**
- Modify: `nba2k_editor/Player Generator/source_data.py`
- Test: `tests/test_generator_source_data.py`

**Required tables:**
- Player identity: `Player Info`, `Player Season Info`
- Player stats: `Player Per Game`, `Player Per 100 Poss`, `Advanced`, `Player Shooting`, `Player Play by Play`
- Team stats: `Team Stats Per Game`, `Team Stats Per 100 Pos`, `Team Summaries`, `Opponent Stats Per Game`, `Opponent Stats Per 100 Poss`

**Steps:**
1. Add `required_phase_zero_sheets()`.
2. Add `missing_required_sheets()` against workbook metadata.
3. Test the current workbook has all required Phase 0 sheets or reports exact missing names.
4. Run source-data tests.

**Acceptance:** Missing source tables are reported as availability metadata before formula code runs; older seasons may have missing modern stat rows and must be represented explicitly rather than treated as fatal by default.

---

## Task 4: Add deterministic row-reading adapter for selected season

**Objective:** Parse only needed workbook sheets into row dictionaries keyed by selected season/player/team.

**Files:**
- Create: `nba2k_editor/Player Generator/workbook_reader.py`
- Test: `tests/test_generator_workbook_reader.py`

**Steps:**
1. Write stdlib `.xlsx` worksheet row reader for header + values.
2. Read selected sheet rows with `season == contract.season`.
3. Preserve `NA`/blank as `None`.
4. Return rows without interpreting formulas or mutating files.
5. Test one player-stat sheet and one team-stat sheet for season `2025`.

**Acceptance:** Selected-year filtering works and no rows from other seasons leak into generation inputs.

---

## Task 5: Add player stat evidence model

**Objective:** Combine selected-year player rows across workbook sheets into evidence objects, including the full selected-season player roster for the player's team and matching team context stats.

**Files:**
- Create: `nba2k_editor/Player Generator/player_evidence.py`
- Test: `tests/test_generator_player_evidence.py`

**Steps:**
1. Define `PlayerEvidence` with `player_id`, `season`, `team`, identity, season info, basic stats, advanced stats, shooting profile, play-by-play profile, full selected-team roster, matching team stats, matching opponent/team-context stats, and `missing_sources`.
2. Join player rows on `season + player_id + team` unless explicitly handling aggregate rows.
3. Build `team_roster` from all `Player Season Info` rows with the same selected `season + team`, preserving every teammate row as source evidence.
4. Join team context rows on `season + team abbreviation` using the player's selected team value.
5. Preserve partial evidence for seasons/players where modern sheets are unavailable; do not fail just because 1947-style data lacks shooting/play-by-play/advanced/per-100 rows.
6. Mark each missing sheet/profile in `missing_sources` so downstream rules can skip unsupported formulas instead of inventing values.
7. Test that evidence for a known 2025 player includes player stats, the full selected-team roster, and matching team/opponent context stats.
8. Test that evidence for an older season/player returns partial evidence with missing-source markers instead of raising.

**Acceptance:** Player generation receives one deterministic evidence object per player/season/team, with explicit full-team roster context, matching team-stat context, and explicit missing-source metadata for eras that lack modern stat tables.

---

## Task 6: Add full-team roster evidence model

**Objective:** Build selected-season full player roster evidence for a team abbreviation; team stats are context on each roster/player evidence object, not a standalone replacement for the roster.

**Files:**
- Create: `nba2k_editor/Player Generator/roster_evidence.py`
- Test: `tests/test_generator_roster_evidence.py`

**Steps:**
1. Define `TeamRosterEvidence` with `season`, `team`, `roster_rows`, `player_ids`, `player_count`, and `missing_sources`.
2. Build roster rows from all `Player Season Info` rows matching `season + team`.
3. Preserve every selected-team player row; do not collapse the team to one metadata record.
4. Attach aggregate missing-source metadata from player evidence availability where needed.
5. Test current 2025 NYK roster includes the full player list source rows.
6. Test 1947 PIT roster evidence exists and records era-limited missing modern sources without failing.

**Acceptance:** The generator has a first-class full-team roster evidence object for downstream roster proposal assembly.

---

## Task 7: Add deterministic formula/rule layer for player attributes and tendencies

**Objective:** Produce player attribute/tendency proposals from target-year evidence and explicit rule functions only.

**Files:**
- Create: `nba2k_editor/Player Generator/player_rules.py`
- Test: `tests/test_generator_player_rules.py`

**Steps:**
1. Define formula functions with explicit inputs and clamp ranges matching editor display domains: attributes/durability `25..99`, tendencies `0..100`.
2. Cover the full authored 2K field set from `core/Offsets/offsets_players.json`: all `Players/Attributes/*` normalized names and all `Players/Tendencies/*` normalized names, emitted as domain-qualified keys such as `Attributes/3POINT` and `Tendencies/3POINTSHOT`.
3. Add a separate profile/vitals proposal pass for authored Vitals fields that come directly from workbook identity context: `Vitals/FIRSTNAME`, `Vitals/LASTNAME`, `Vitals/HEIGHT`, `Vitals/HEIGHTCM`, `Vitals/WEIGHT`, `Vitals/WEIGHTKG`, `Vitals/POSITION`, `Vitals/COLLEGEFROM`, and `Vitals/YEARSPRO`.
4. Use league/team-relative normalization over selected-year population for ratings/tendencies, while keeping profile/vitals fields direct source transforms rather than scored formulas.
5. Add tests proving identical evidence returns identical output and no `random` import exists.
6. Add tests proving changed player/team evidence changes derived values.

**Acceptance:** Generated attributes/tendencies are deterministic and traceable to evidence/rules.

---

## Task 8: Add player generator write-contract proposal object

**Objective:** Return a player proposal aligned with the main editor's existing field write/readback contract: domain-qualified player field entries plus display candidates, source evidence, and formula explanations. This is not a loose ratings dict, not a copy/paste system, and not a live-memory write.

**Files:**
- Create: `nba2k_editor/Player Generator/player_generator.py`
- Test: `tests/test_generator_player_generator.py`

**Steps:**
1. Define `GeneratedPlayerProposal` with identity, target season, team, and an ordered tuple of player field candidates.
2. Define each candidate as a write-contract unit: `domain="Players"`, section/group context, normalized field name, domain-qualified key such as `Attributes/3POINT`, proposed display value, source rule, and evidence keys.
3. Build candidates only from the predetermined generator pipeline: workbook/source stats feed fixed rule outputs, and those fixed outputs line up with authored `Players` fields in `core/Offsets/offsets_players.json`. There is no user-provided/generated-extra field path.
4. Generate from selected-year `PlayerEvidence` + `player_rules`, and pass a full same-season comparison population into the rules so a 2025 player is compared against 2025 players. The comparison population must merge the selected-year player sheets (`Player Per Game`, `Player Per 100 Poss`, `Advanced`, `Player Shooting`, `Player Play by Play`) and joined selected-year team context (`Team Stats Per Game`, `Team Stats Per 100 Pos`, `Team Summaries`, `Opponent Stats Per Game`, `Opponent Stats Per 100 Poss`).
5. Keep attributes in the editor display range `25..99` and tendencies in `0..100`.
6. Include formula/source metadata for every generated field candidate.
7. Test the proposal can be consumed by the later apply bridge using the main editor write/readback contract: iterate candidates, find the matching authored field entry, then pass its display value to the normal player write/readback seam.
8. Test proposal contains no live-memory handle, record address, subprocess call, copy/paste claim, or direct write action.

**Acceptance:** Player generator returns a write-contract player-field proposal that lines up with the main app's existing player field write/readback seam, while still requiring a later explicit apply bridge before any roster write.

---

## Task 9: Add full-roster generator rules

**Objective:** Generate selected-team full roster proposals from `TeamRosterEvidence` and per-player evidence/rules.

**Files:**
- Create: `nba2k_editor/Player Generator/roster_rules.py`
- Create: `nba2k_editor/Player Generator/roster_generator.py`
- Test: `tests/test_generator_roster_generator.py`

**Steps:**
1. Define deterministic roster proposal fields from full-team roster evidence.
2. Include team abbreviation/name/logo sidecar references only as context for the roster proposal.
3. Preserve player assignment for every selected-team roster row.
4. Test current source data can create a full roster proposal for a selected team/year.

**Acceptance:** `team` generation means full player roster generation for the selected team, not a standalone team metadata record.

---

## Task 10: Add local generated-output schema

**Objective:** Normalize generated player/full-roster proposals into a serializable schema for preview/diff/apply.

**Files:**
- Create: `nba2k_editor/Player Generator/proposals.py`
- Test: `tests/test_generator_proposals.py`

**Steps:**
1. Add proposal dataclasses for generated player write-contract candidates and full-roster proposal groups.
2. Include domain, record identity, authored section/group path, field normalized name, display value, raw candidate if known, source rule, confidence/warnings.
3. Keep the schema aligned with the main editor write/readback path: proposal candidates identify authored player fields and carry display values that the apply bridge can hand to `write_entry_value` / write-readback, instead of inventing a second write format or claiming a copy/paste system exists.
4. Add JSON serialization tests.

**Acceptance:** Preview and apply use the same predetermined proposal object, not one-off dict shapes.

---

## Task 11: Add roster generator assembly

**Objective:** Build roster proposals from generated players/full-team roster evidence without applying anything.

**Files:**
- Create: `nba2k_editor/Player Generator/roster_generator.py`
- Test: `tests/test_generator_roster_generator.py`

**Steps:**
1. Define `GeneratedRosterProposal` with selected season, selected team, player proposals, source roster rows, and assignment map.
2. Assemble from selected-year full-team roster evidence.
3. Reject duplicate `(season, player_id, team)` rows unless explicit aggregate handling is implemented.
4. Test roster proposal count and team assignment consistency.

**Acceptance:** Roster generator produces a previewable proposal only.

---

## Task 12: Add explicit apply bridge interface

**Objective:** Define the only approved seam from generated output to live editor write logic.

**Files:**
- Create: `nba2k_editor/Player Generator/apply_bridge.py`
- Test: `tests/test_generator_apply_bridge.py`

**Steps:**
1. Define `RosterApplyBridge` protocol/interface taking `GeneratedRosterProposal` and validated overwrite contract.
2. Require explicit mode `overwrite_current_roster`.
3. Do not import `GameMemory` here; depend on a passed editor adapter/protocol.
4. Test bridge refuses non-overwrite mode and missing validation artifacts.

**Acceptance:** Generator code still does not own live write primitives.

---

## Task 13: Add preview/diff and validation gates

**Objective:** Gate roster overwrite behind deterministic diff and validation output.

**Files:**
- Create: `nba2k_editor/Player Generator/preview.py`
- Create: `nba2k_editor/Player Generator/validation.py`
- Test: `tests/test_generator_preview_validation.py`

**Steps:**
1. Diff current editor-read values vs proposal values by domain/record/field.
2. Validate required fields, ranges, duplicate identities, and unresolved field mappings.
3. Return structured errors; do not silently drop fields.
4. Test overwrite cannot proceed when preview or validation is missing/red.

**Acceptance:** Overwrite path has machine-checkable stop/go gates.

---

## Task 14: Add backup/snapshot requirement before overwrite

**Objective:** Require a current roster/editor snapshot before applying generated output.

**Files:**
- Create: `nba2k_editor/Player Generator/snapshot.py`
- Modify: `nba2k_editor/Player Generator/apply_bridge.py`
- Test: `tests/test_generator_snapshot_gate.py`

**Steps:**
1. Define snapshot metadata object with target, roster/session label, domains, record count, timestamp, storage path.
2. Bridge requires snapshot metadata before applying.
3. Test missing snapshot blocks overwrite.

**Acceptance:** No overwrite call can be made without a backup/snapshot artifact.

---

## Task 15: Add local exported-2K player-data database schema

**Objective:** Store exported in-game/editor reads with required source metadata.

**Files:**
- Create: `nba2k_editor/Player Generator/export_db.py`
- Test: `tests/test_generator_export_db.py`

**Schema fields:**
- game target
- roster/session label
- player ID/signature ID
- team
- domain
- field normalized/display names
- raw value
- display value
- export timestamp

**Steps:**
1. Create SQLite schema and migration initializer.
2. Insert exported field rows transactionally.
3. Query by target/session/player/team/field.
4. Test all metadata fields are required and persisted.

**Acceptance:** Local DB can be populated from exported editor reads.

---

## Task 16: Add export-from-editor read adapter

**Objective:** Pull current editor/player data into export rows without coupling DB code to UI.

**Files:**
- Create: `nba2k_editor/Player Generator/export_from_editor.py`
- Test: `tests/test_generator_export_from_editor.py`

**Steps:**
1. Define an editor-read protocol with selected domain records and field read results.
2. Convert read results into `export_db` rows.
3. Include target/session/player/team/timestamp metadata.
4. Test with fake editor adapter; no live memory required in unit test.

**Acceptance:** Current roster/player data can train/improve the builder through DB rows.

---

## Task 17: Add CLI or entrypoint command for exports

**Objective:** Make export flow callable without the UI.

**Files:**
- Create: `nba2k_editor/entrypoints/generator.py`
- Test: `tests/test_generator_entrypoint.py`

**Steps:**
1. Add `--export-current-player-data` with target/session/db path arguments.
2. Require explicit session label.
3. Refuse export when editor adapter cannot attach/read.
4. Test parser behavior and refusal paths.

**Acceptance:** Export flow exists as a controlled backend command.

---

## Task 18: Add analysis query layer for exported 2K data

**Objective:** Use collected 2K data to inspect ranges/archetypes/tendencies/signatures/contracts/gear/team context.

**Files:**
- Create: `nba2k_editor/Player Generator/analysis.py`
- Test: `tests/test_generator_analysis.py`

**Steps:**
1. Add field range query by target/version/domain/field.
2. Add archetype grouping query by selected fields.
3. Add tendency/rating distribution query.
4. Test queries against a temp SQLite DB with exported rows.

**Acceptance:** Formula refinement can use real exported 2K data.

---

## Task 19: Feed analysis into generator rules as optional calibration

**Objective:** Allow generated formulas to use exported 2K ranges/archetypes without requiring them.

**Files:**
- Modify: `nba2k_editor/Player Generator/player_rules.py`
- Modify: `nba2k_editor/Player Generator/team_rules.py`
- Test: `tests/test_generator_rule_calibration.py`

**Steps:**
1. Define `RuleCalibration` object from analysis queries.
2. Rules accept calibration explicitly.
3. Missing calibration does not fabricate data; it uses the source-stat formulas only.
4. Test calibration changes bounded outputs predictably.

**Acceptance:** Exported data can refine formulas over time while preserving deterministic output.

---

## Task 20: Add database-backed analysis views

**Objective:** Expose analysis results in backend form first; UI can consume later.

**Files:**
- Create: `nba2k_editor/Player Generator/analysis_views.py`
- Test: `tests/test_generator_analysis_views.py`

**Views:**
- archetypes
- rating ranges
- tendencies
- badges
- signatures
- contracts
- gear
- team context

**Steps:**
1. Return structured rows for each view.
2. Include source DB query metadata.
3. Test every view has stable keys and empty-data behavior is explicit.

**Acceptance:** Analysis views exist without adding main-navigation UI clutter.

---

## Task 21: Add UI access to the generator workflow

**Objective:** Add a user-facing UI entry point for the Player Generator only after roster proposal, preview/diff, validation, and snapshot/overwrite gates exist.

**Files:**
- Modify: `nba2k_editor/ui/dpg_editor.py` or the current approved UI owner for generator entry points
- Test: `tests/test_generator_ui_contract.py`

**Steps:**
1. Add a UI entry point that opens the generator workflow without moving generator ownership out of `nba2k_editor/Player Generator/`.
2. Require explicit selected season and selected team/full roster input before generation.
3. Display generated full-team roster proposal, preview/diff result, validation status, and missing-source metadata.
4. Keep apply/overwrite disabled until preview, validation, and snapshot gates are green.
5. Route apply through `RosterApplyBridge`; do not let UI code write live memory directly.
6. Test the UI contract with a fake generator/apply adapter so no live memory or Dear PyGui runtime is required for unit validation.

**Acceptance:** The generator is accessible from the editor UI, but UI code only coordinates selection/preview/apply state and cannot bypass backend gates.

---

## First execution slice

Start with Tasks 1-2 only. These establish the hard contracts Phase 0 needs before any formula, database, export, or live-apply work:

1. `nba2k_editor/Player Generator/source_data.py`
2. `nba2k_editor/Player Generator/contracts.py`
3. `tests/test_generator_source_data.py`
4. `tests/test_generator_contracts.py`

Validation commands for the first slice:

```bash
python3 -m unittest tests.test_generator_source_data tests.test_generator_contracts -v
python3 -m compileall -q nba2k_editor
python3 - <<'PY'
from pathlib import Path
for path in Path('nba2k_editor/Player Generator').glob('*.py'):
    text = path.read_text(encoding='utf-8')
    banned = ['import random', 'openpyxl', 'pandas', 'xlrd', 'xlsxwriter', 'GameMemory']
    hits = [word for word in banned if word in text]
    if hits:
        raise SystemExit(f'{path}: banned generator dependency {hits}')
print('generator dependency guard passed')
PY
```

Expected result: unit tests pass, compileall passes, and dependency guard passes.
