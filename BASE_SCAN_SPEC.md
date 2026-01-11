# Dynamic Base Hunter Specification

Purpose
Build a standalone or embedded tool that finds updated base addresses for
player, team, staff, and stadium tables after game updates. The tool should
operate against a running NBA 2K process, derive candidate bases via memory
search, validate them using known field offsets, and emit overrides that can be
applied to the offsets loader.

Scope
- Targets: Player, Team, Staff, Stadium base tables.
- Platform: Windows only (uses Win32 process/memory APIs).
- Output: Base pointer overrides plus a scan report.
- This spec aligns with `nba2k26_editor/core/dynamic_bases.py` and validation
  logic in `nba2k26_editor/models/data_model.py`.

Non-goals
- Creating or updating offsets for individual fields.
- Writing to the game process.
- Building UI; CLI usage is sufficient.

Inputs
Required runtime data:
- `process_name`: e.g., `NBA2K26.exe`
- `pid` (optional): if known, bypass name lookup.
- `module_base` (optional): if known, bypass module scan.
- `search_window`: bytes around module or hint base to scan, default `0x8000000`.

Offsets-derived data (typically from `Offsets/offsets.json` or runtime loader):
- `player_stride`, `team_stride`, `staff_stride`, `stadium_stride`
- `player_name_offsets` (first/last), `player_name_length`, `player_name_encoding`
- `team_name_offset`, `team_name_length`, `team_name_encoding`
- `staff_name_offsets` (first/last or single name), `staff_name_length`, `staff_name_encoding`
- `stadium_name_offsets`, `stadium_name_length`, `stadium_name_encoding`
- Optional `name_lengths` map when offsets have different field sizes.

Known-name targets (small, curated lists):
- `player_first_names`, `player_last_names` (matched to the corresponding offsets).
- `staff_first_names`, `staff_last_names` (matched to the corresponding offsets).
- `team_names`: list of team names.
- `stadium_names`: list of stadium names or short names matching the offsets.

Hints (optional, previous bases):
- `player_base_hint`, `team_base_hint`, `staff_base_hint`, `stadium_base_hint`

Outputs
- `bases`: map of `{ "Player": int, "Team": int, "Staff": int, "Stadium": int }`
  containing the best candidates found.
- `report`: diagnostic details including scan ranges, hits, votes, and timings.

Suggested output JSON shape:
```json
{
  "bases": {
    "Player": 140737490968576,
    "Team": 140737491568832,
    "Staff": 140737492169088,
    "Stadium": 140737492769344
  },
  "report": {
    "pid": 12345,
    "elapsed_sec": 2.531,
    "player_hits": [{"target": "Tyrese Maxey", "address": "0x7FF6A1B2C3D0"}],
    "player_candidates": [{"address": "0x7FF6A1000000", "votes": 189}],
    "team_candidates": [{"address": "0x7FF6A1100000", "votes": 6}],
    "staff_candidates": [{"address": "0x7FF6A1200000", "votes": 42}],
    "stadium_candidates": [{"address": "0x7FF6A1300000", "votes": 4}]
  }
}
```

Memory Access Requirements
- Use `OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, ...)`.
- Enumerate memory via `VirtualQueryEx`.
- Only scan `MEM_COMMIT` pages with readable protection; skip `PAGE_GUARD`.
- Read memory blocks with `ReadProcessMemory`.
- Close handles when done.

Common Scan Strategy
1) Resolve PID and module base.
2) Build scan ranges:
   - Window around module base (if known).
   - Window around previous base hint (if provided).
   - Full high-memory sweep fallback (start at `0x100000000`).
3) Scan for known names at each table's name offset(s) to create candidate bases.
4) Score candidates (votes).
5) Validate top candidates using field offsets and encoding.
6) Emit best base per table plus a report.

Candidate Voting Model
- A hit is a confirmed name found at a known name offset within a record.
- For each hit, generate candidates by stepping backward in `stride` increments.
- Count votes per base; prefer the highest vote count above a threshold.
- Default: 600 steps backward, min votes 151 for player targets.

Unified Name-Offset Scan Algorithm (applies to Player/Team/Staff/Stadium)
Reference: `nba2k26_editor/core/dynamic_bases.py` (`_scan_player_names`) as a template.

Inputs:
- `stride`
- `name_offsets`: one or more offsets within a record.
- `name_length`, `name_encoding`
- `name_lists`: targets per offset (do not cross-match first names to last-name offsets).

Algorithm:
1) For each `(name_offset, name_list)` pair, encode names as UTF-16LE
   null-terminated bytes.
2) For each memory region, search for each encoded name.
3) For each hit, compute `record_addr = hit_address - name_offset`.
4) Generate candidate bases: `base = record_addr - i * stride` for `i` in `0..599`.
5) Tally votes per base and keep the top candidates.
6) Validate the top candidate by sampling multiple records:
   - Read the name field at `base + name_offset`.
   - Require non-empty, printable output.
   - Require multiple matches against the known name list.
7) If multiple name offsets are provided (first/last), require at least one
   record where both offsets decode to printable strings, and prefer candidates
   where both offsets match known names.
8) If offsets have different lengths, use a per-offset `name_lengths` map
   during validation instead of a single `name_length`.

Per-Table Inputs And Thresholds
- Player: `player_stride`, `player_name_offsets` (first + last),
  `player_first_names`, `player_last_names`; suggested min votes >= 151.
- Team: `team_stride`, `team_name_offset`, `team_names`; lower min-vote
  threshold (e.g., 4-8) with multiple name matches.
- Staff: `staff_stride`, `staff_name_offsets` (first + last or single),
  `staff_first_names`, `staff_last_names`; moderate threshold.
- Stadium: `stadium_stride`, `stadium_name_offsets`, `stadium_names`; low
  threshold with multiple name matches.

Offsets List Findings (2K26)
- Player: `Vitals.First Name` at `0x6C28` (27688), length 20, `WString`.
- Player: `Vitals.Last Name` at `0x6C00` (27648), length 20, `WString`.
- Team: `Team Vitals.Team Name` at `0x2E2` (738), length 24, `WString`.
- Stadium: `Stadium.City Short Name` at `0x380` (896), length 9, `WString`.
- Stadium: `Stadium.State Short Name` at `0x392` (914), length 8, `WString`.
- Staff: no first/last name fields are present in `Offsets/offsets.json` for 2K26;
  add them to the offsets list or scanning by name is unavailable.

Validation Rules
Use the same validation logic as `PlayerDataModel`:
- Player: read first/last name offsets and ensure non-empty, printable text.
- Team: read team name at `team_name_offset`; ensure printable output.
- Staff/Stadium: read name at the configured offset; ensure printable output.

Validation helpers should reject candidates when:
- Address is null or negative.
- Read fails or returns zero bytes.
- Decoded names contain control characters.

Integration With Offsets Loader
- Apply found bases as overrides and mark them absolute and direct:
  `{ "address": base, "absolute": true, "direct_table": true, "finalOffset": 0 }`
- In-app flow uses `_apply_base_pointer_overrides` in
  `nba2k26_editor/core/offsets.py`.
- External tool should emit JSON compatible with that structure.

Recommended Config File
```json
{
  "process_name": "NBA2K26.exe",
  "search_window": 134217728,
  "player": {
    "stride": 1176,
    "name_offsets": { "first": 27688, "last": 27648 },
    "name_length": 20,
    "encoding": "utf16",
    "first_names": ["Tyrese", "Victor"],
    "last_names": ["Maxey", "Wembanyama"]
  },
  "team": {
    "stride": 5672,
    "name_offset": 738,
    "name_length": 24,
    "encoding": "utf16",
    "names": ["76ers", "Bucks", "Bulls", "Celtics", "Lakers", "Warriors"]
  },
  "staff": {
    "stride": 0,
    "name_offsets": { "first": null, "last": null },
    "name_length": 0,
    "encoding": "utf16",
    "first_names": ["Erik", "Steve"],
    "last_names": ["Spoelstra", "Kerr"]
  },
  "stadium": {
    "stride": 0,
    "name_offsets": { "city_short": 896, "state_short": 914 },
    "name_lengths": { "city_short": 9, "state_short": 8 },
    "name_length": 9,
    "encoding": "utf16",
    "names": ["NY", "LA"]
  },
  "hints": {
    "player_base": 0,
    "team_base": 0,
    "staff_base": 0,
    "stadium_base": 0
  }
}
```

Notes:
- Staff name offsets are missing in `Offsets/offsets.json` for 2K26; add them
  before relying on name-offset scanning for staff bases.
- Stadium uses city/state short names from the offsets list; short strings
  increase false positives, so tighten validation and require multiple matches.
- Prefer stable, common names to reduce false positives.

Failure Handling
- If no candidates exceed the vote threshold, emit the top candidates with
  votes and mark the result as inconclusive.
- If only hints are available, return them with a `fallback_offsets` flag.
- Log elapsed time, scanned ranges, and read failures for diagnostics.

Testing Checklist
- Scan with known working bases and confirm output matches.
- Validate candidate addresses by reading multiple records.
- Verify that applying overrides produces correct live reads in the editor.
