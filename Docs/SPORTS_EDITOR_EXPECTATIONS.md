# Sports Editor Feature Expectations

Research summary for features people commonly want or expect from sports-game roster/editor tools such as NBA 2K, Madden, Football Manager, and OOTP.

## Core player editing

Users expect deep control over player records:

- Name, age, height, weight, position, handedness
- Team assignment and free agency
- Contract data
- Overall ratings and individual attributes
- Tendencies or behavior sliders
- Badges, traits, abilities, and special skills
- Hot zones, shot zones, or strengths
- Injuries, fatigue, durability, and health-related fields
- Appearance: cyberface/head ID, portrait/headshot ID, body type
- Gear, accessories, shoes, and visual equipment
- Signature animations, moves, jump shots, celebrations, or motion packages
- Hidden IDs and game-internal values where useful

For an NBA 2K-style editor, the common expectation is support for attributes, tendencies, badges, hot zones, gear, accessories, signatures, contracts, team assignment, portraits, and cyberfaces.

## Team and roster management

People usually expect more than a single-player field editor. Common roster operations include:

- Move a player to a team
- Assign free agents
- Trade or swap players
- Clone players
- Create or delete players when the game format supports it
- Edit rotations, depth charts, and lineups
- Edit coaches and staff
- Edit team names, cities, colors, arenas/courts, uniforms, and logos when supported
- Edit draft picks, salary cap, and contract rules where present
- Sort and filter by team, position, rating, age, contract, or other useful columns

## Spreadsheet and bulk-edit mode

Bulk editing is one of the largest power-user expectations.

Useful features:

- Quick-edit grid/table view
- Sortable columns
- Filters
- Multi-select rows
- Batch set values
- Batch add/subtract values, such as `+5 speed` for selected players
- Copy/paste from spreadsheets
- Export/import CSV or Excel
- Templates for copying one player's attribute, tendency, badge, or contract profile to others
- Find/replace for names, teams, IDs, shoes, cyberfaces, and other repeated fields

Football Manager, Madden, and OOTP-style communities show strong demand for import/export, table access, and mass-edit workflows. Even when official tools lack these features, users look for third-party editors that provide them.

## Safety and trust features

Sports editors touch fragile roster/save data. Users expect the editor to avoid silent damage.

Important safety features:

- Automatic backup before write
- Clear dirty state when data has changed
- Preview or diff before saving
- Undo/revert where possible
- Validation before write
- Range enforcement for numeric fields
- Enum/dropdown validation for known coded fields
- Warnings for unknown or unmapped fields
- No hidden transformations
- Log of changed fields
- Version/year compatibility detection
- Refuse or warn on unsupported file/game versions

Users will trust an editor more if it says `unknown` or `not mapped` than if it guesses.

## Advanced/modder features

Power users often want a raw-access layer in addition to polished screens.

Useful advanced features:

- Raw table viewer
- Field/schema viewer
- Offset, base, and stride visibility
- Search by player ID or internal ID
- Compare two roster files
- Diff two players
- Export selected records
- Import selected records
- Unknown field preservation
- Ability to edit newly discovered fields without waiting for a full UI rebuild
- Versioned metadata for offsets and fields
- Field provenance: where the value/label came from and how confident it is

Madden DB/franchise tools commonly expose raw DB/table editors, showing that advanced users accept raw power when it is honest and backed up.

## UX expectations

Users want fast access, not wizard-heavy workflows.

Expected UX features:

- Search box everywhere
- Fast filters by team, position, and name
- Clear grouping: Bio, Contract, Attributes, Tendencies, Badges, Gear, Appearance, Team
- Keyboard-friendly grid navigation
- Dropdowns for known values
- Numeric spinners/sliders only where useful
- Bulk operations without modal clutter
- Persistent column order and saved views
- Favorites or pinned fields for common edits
- Clear save/export buttons
- No surprise popups unless preventing data loss

For serious editors, a table/grid is often more valuable than a fancy form.

## NBA 2K-specific priority list

### P0 — expected immediately

- Load roster/save data
- Player list with search/filter
- Edit player identity
- Edit team assignment
- Edit attributes
- Edit tendencies
- Edit badges
- Edit contracts
- Edit accessories/gear
- Save safely with backup

### P1 — strong user demand

- Hot zones
- Signature animations
- Cyberface/headshot/portrait IDs
- Shoes
- Rotations/depth chart
- Staff/coaches
- Bulk grid editing
- CSV/Excel export/import
- Clone/copy player
- Compare player A vs player B

### P2 — power/modder features

- Raw field/table view
- Offset/schema inspector
- Unknown field preservation
- Roster diff
- Batch formulas
- Team/court/uniform/logo IDs
- Cross-year conversion helpers
- Mod package export

## Common user dislikes

Users commonly dislike:

- Crashes after save
- Editor silently changing unrelated fields
- Missing backup
- Values not matching in-game
- Fake labels for unknown fields
- Overall changes that do not match the underlying attributes
- No bulk edit
- Slow player search
- Bad dropdowns or wrong enum labels
- Forced workflows for simple edits
- Tool only working for one patch/version with no warning
- Losing hidden metadata during save

## Practical target

A strong sports editor should be:

> A safe roster editor with a polished player/team UI, spreadsheet-grade bulk editing, strong validation, backups/diffs, and an advanced raw-data view for modders.

For this NBA2K editor direction, the highest-value path is probably:

1. Make player list/search/filter excellent.
2. Make the full player editor complete and accurate.
3. Add bulk grid editing.
4. Add CSV/Excel export/import.
5. Add safe write backups/diffs.
6. Add raw/advanced inspector only after core screens are trustworthy.

## Source areas checked

Research touched NBA 2K modding/editor pages, Operation Sports/NLSC-style community references, Madden DB/franchise editor repositories, Football Manager editor/FMRTE discussions, and OOTP commissioner/player editor documentation.
