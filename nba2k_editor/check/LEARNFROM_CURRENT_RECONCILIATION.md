# LearnFrom/current reconciliation report

Generated from `/mnt/d/hermes/editorlearnfrom/_analysis` against current split offset JSON in `nba2k_editor/core/Offsets`.

## Counts
- LearnFrom mapped rows checked: `715`
- Confirmed same-label/same-address current matches: `558`
- Missing same-label current metadata: `113`
- Same-label address/bit conflicts needing review/live validation: `44`

## Confirmed concrete change candidates
- Staff Current Team found at `Staff / Attributes / Attributes / CURRENTTEAM / 2K26`: address `0x18`, type `uint64`, `team_address_dropdown=True` after Phase 2 implementation.
  - LearnFrom row 35 in `generated_dropdown_non_concrete_targets_for_review.md` is now applied.

## Already-present/no-change checks
- Dunk package dropdown counts from merged current layout:
  - `DUNKPACKAGE5 69`
  - `DUNKPACKAGE6 69`
  - `DUNKPACKAGE7 69`
  - `DUNKPACKAGE8 69`
  - `DUNKPACKAGE9 69`
  - `DUNKPACKAGE10 69`
  - `DUNKPACKAGE11 69`
  - `DUNKPACKAGE12 69`
  - `DUNKPACKAGE13 69`
  - `DUNKPACKAGE14 69`
  - `DUNKPACKAGE15 69`
  - `GOTODUNKPACKAGE 69`
  - `DUNKPACKAGE2 69`
  - `DUNKPACKAGE3 69`
  - `DUNKPACKAGE4 69`

## Missing metadata buckets
- `('Staff', 'staff_infos', '')`: `41`
- `('Players', '__main__', 'Stats')`: `31`
- `('Players', 'player_tendencies', 'Jump Shooting')`: `15`
- `('Players', 'player_infos', '')`: `9`
- `('Players', 'player_attributes', '')`: `8`
- `('Players', 'player_infos', 'Vitals')`: `5`
- `('Players', 'player_tendencies', 'Freelance')`: `1`
- `('Stadiums', 'stadium_infos', '')`: `1`
- `('Teams', 'team_infos', '')`: `1`
- `('Players', '__main__', None)`: `1`

## Conflict buckets requiring review/live validation
- `('Players', 'player_signature', '')`: `23`
- `('Players', 'player_badges', '')`: `4`
- `('Players', 'player_hot_zones', '')`: `3`
- `('Players', 'player_tendencies', 'Layups And Dunks')`: `3`
- `('Players', 'player_infos', 'Vitals')`: `2`
- `('Players', 'player_tendencies', 'Post Game')`: `2`
- `('Teams', 'team_infos', '')`: `2`
- `('Players', 'player_attributes', '')`: `1`
- `('Players', 'player_infos', '')`: `1`
- `('Players', 'player_signature', 'Signature: Jump Shooting')`: `1`
- `('Players', 'player_tendencies', 'Jump Shooting')`: `1`
- `('Players', 'player_tendencies', 'Passing')`: `1`

## Rules applied
- No production JSON edit from flat LearnFrom comparison alone.
- Same-label conflicts are evidence-only until live validation or explicit user approval.
- Keep authored base pointers; no runtime signature scan / roster-base scan lane.
