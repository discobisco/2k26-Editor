## Plan: Remove Player-Scan Fallbacks and Related Behaviors

### Goal
Remove the following behaviors from the player scan pipeline:
- Abort `_scan_all_players()` when >50% of scanned names are non-ASCII.
- Fallback to `scan_team_players()` when the table scan returns empty but teams exist.
- Synthesize a team list from player data and add Free Agents if teams were not found earlier.
- Scan draft class players when `DRAFT_PTR_CHAINS` exist.

### Scope (Current Touchpoints)
- `nba2k26_editor/models/data_model.py`
  - `_scan_all_players()` non-ASCII ratio abort.
  - `refresh_players()` fallback roster scan.
  - `refresh_players()` team list synthesis/free agent insertion.
  - `refresh_players()` optional draft class scan.

### Proposed Changes (High Level)
1) `_scan_all_players()`
   - Remove the non-ASCII ratio check that returns `[]` when >50% invalid names are found.
2) `refresh_players()`
   - Remove the fallback roster scan via `scan_team_players()` when `players_all` is empty.
   - Remove team-list synthesis from player data when team list is empty.
   - Remove draft class scanning block gated by `DRAFT_PTR_CHAINS`.

### Steps
1) Edit `_scan_all_players()` to delete the non-ASCII ratio check and its early return.
2) Edit `refresh_players()`:
   - Delete the fallback roster scan branch that runs when `players_all` is empty.
   - Delete the team-list synthesis logic that runs when `self.team_list` is empty.
   - Delete the draft class scan block that populates `self.draft_players`.
3) Review any UI or downstream logic that expects draft players or synthesized team lists.
4) Run a manual smoke test:
   - Open the Players tab with a valid offsets file and game running.
   - Confirm player list loads only from the main table scan.

### Risks / Behavior Changes
- If the table scan is wrong or empty, players will not load at all (no fallback).
- Team list may remain empty if team scan fails and no synthesis is performed.
- Draft class players will never populate unless a separate feature reintroduces them.

### Validation Checklist
- Player tab loads without crashes.
- No unintended UI states (e.g., empty team dropdown) when the main scan fails.
- No references to `self.draft_players` cause errors after removal.
