You are updating the existing 2K roster editor codebase.

Goal: remove old compatibility/write-wrapper methods and route all affected write operations through standardized apply calls.

Do not guess offsets, field layouts, memory layout, record structure, or UI wiring. Inspect the current code and make only code-grounded changes. If a standardized call already exists, use it. If a narrow standardized call is missing, create the smallest central apply function needed and route feature code through it.

Primary objective:
There should not be separate reset/save/stat-id mini write paths that directly write values. Feature-level functions should build a snapshot/change-set and pass it into the standardized apply path.

Required changes:

1. Remove `reset_player_editor_values(...)` as a compatibility write wrapper.

Current issue:
`reset_player_editor_values(...)` now routes through `apply_player_roster_snapshot(...)`, but it still exists as an old reset-specific wrapper.

Required fix:
Find every caller of `reset_player_editor_values(...)`.
Replace those callers so the reset button/action builds the proper reset snapshot and calls the standardized apply path directly.
After all callers are migrated, delete `reset_player_editor_values(...)`.

Expected end state:
The reset UI action should directly use the same apply pipeline as normal player-editor writes.
There should be no reset-specific write wrapper kept just for compatibility.

2. Remove `_player_editor_reset_value(...)` as a reset-only helper.

Current issue:
`_player_editor_reset_value(...)` still exists as reset-specific value-selection logic.

Required fix:
Move reset value selection into the standardized snapshot-building step.
The reset path should construct the same type of snapshot/change-set used by normal player editor writes.
Do not keep a separate reset-only helper unless it is part of a generic snapshot/default-value builder that is also used by non-reset flows.

Expected end state:
Reset values are generated as part of snapshot construction, not through a reset-only value helper.

3. Refactor `set_all_players_stat_ids_to_no_stats(...)`.

Current issue:
`set_all_players_stat_ids_to_no_stats(...)` loops players and calls `write_entry_value(...)` directly.

Required fix:
Change it so it builds a player-roster snapshot/change-set for the affected players and routes the write through `apply_player_roster_snapshot(...)` or the existing standardized player apply function.

Rules:

* No direct `write_entry_value(...)` calls inside `set_all_players_stat_ids_to_no_stats(...)`.
* Preserve the existing behavior and target scope.
* Preserve existing user-visible result messages/logging unless they are tied to the removed direct-write implementation.
* Do not change the meaning of “No Stats”; use the current code’s existing value/source of truth.

Expected end state:
Bulk stat ID clearing uses the same standardized player write pipeline as other player roster edits.

4. Refactor `save_selected_team_summary(...)`.

Current issue:
`save_selected_team_summary(...)` loops team summary fields and calls `write_entry_value(...)` directly.

Required fix:
Route team summary writes through a standardized apply function.

Preferred approach:
If there is already a standardized team apply/save function, use it.

If there is not one:
Create a narrow standardized function such as `apply_team_summary_snapshot(...)` or an equivalent name that matches the codebase naming style.
This function should be the only team-summary-level place that performs the actual write loop.

Rules:

* No direct `write_entry_value(...)` calls inside `save_selected_team_summary(...)`.
* `save_selected_team_summary(...)` should collect/validate UI values, build a team summary snapshot/change-set, and pass it to the standardized apply function.
* Do not mix player roster snapshot logic with team summary logic unless the current code already has a safe shared abstraction.
* Do not invent new team fields or offsets.

Expected end state:
Team summary save is no longer a separate mini-save path. It uses a centralized apply pipeline.

5. Remove the internal bypass inside `apply_player_roster_snapshot(...)`.

Current issue:
Inside `apply_player_roster_snapshot(...)`, Draft Class target writes call `_write_field_at_record_address(...)` directly, while normal Players writes go through `write_entry_value(...)`.

Required fix:
Normalize this so both Players and Draft Class targets go through the same internal write adapter/pipeline.

Acceptable implementation:
Create or use a single internal low-level write adapter that handles both normal player records and draft-class record-address writes.

Rules:

* Feature-level code must not call `_write_field_at_record_address(...)` directly.
* `apply_player_roster_snapshot(...)` should not have a special bypass that skips the standard write adapter.
* If Draft Class writes require address-based writing, encapsulate that inside the standard internal adapter, not inside a feature-specific branch.
* Preserve existing Draft Class write behavior.

Expected end state:
`apply_player_roster_snapshot(...)` has one standardized write path for all player-like targets.
Draft Class may still require different address resolution internally, but that difference must be hidden behind the shared write adapter.

Global rules:

* Do not guess current layout.
* Do not guess offsets.
* Do not change unrelated UI behavior.
* Do not rename public UI labels unless required by code cleanup.
* Do not remove working functionality.
* Do not add fallback paths that bypass the standardized apply calls.
* Do not keep old compatibility methods unless an active caller cannot be migrated. If that happens, report the caller and why it could not be migrated.
* Search the repo for all usages of:

  * `reset_player_editor_values`
  * `_player_editor_reset_value`
  * `set_all_players_stat_ids_to_no_stats`
  * `save_selected_team_summary`
  * `write_entry_value`
  * `_write_field_at_record_address`
  * `apply_player_roster_snapshot`

Implementation checklist:

1. Map current write paths.
2. Identify all direct write calls in feature-level methods.
3. Create or reuse standardized snapshot/change-set builders.
4. Route reset, bulk stat ID clearing, and team summary save through standardized apply functions.
5. Normalize Draft Class and Players writes behind one internal write adapter.
6. Remove obsolete reset-specific methods after caller migration.
7. Run a search to verify removed methods are gone or unused.
8. Run a search to verify direct `write_entry_value(...)` calls only exist inside approved low-level apply/write adapter functions.
9. Run a search to verify `_write_field_at_record_address(...)` is only used inside the standardized low-level adapter, not feature-level logic.
10. Run existing tests or at minimum perform syntax/import validation.

Acceptance criteria:

* `reset_player_editor_values(...)` is deleted or has zero callers and is removed before final.
* `_player_editor_reset_value(...)` is deleted or replaced by a generic snapshot/default-value builder.
* `set_all_players_stat_ids_to_no_stats(...)` does not call `write_entry_value(...)` directly.
* `save_selected_team_summary(...)` does not call `write_entry_value(...)` directly.
* `apply_player_roster_snapshot(...)` no longer contains a Draft Class direct-write bypass.
* Player editor saves, reset, bulk stat ID clearing, team summary saving, and Draft Class writes still work through standardized apply calls.
* No offset, record layout, or field mapping changes were invented.
* Final response includes:

  * files changed
  * methods removed
  * write paths standardized
  * any remaining direct-write calls and why they are allowed
  * validation performed
