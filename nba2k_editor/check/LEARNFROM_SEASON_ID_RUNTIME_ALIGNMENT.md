# LearnFrom Season ID runtime alignment

Source boundary: `/mnt/d/hermes/editorlearnfrom`.

## Evidence used

LearnFrom decoded player/career-stat fields show two separate shapes:

1. Player-owned Stat ID selector fields live on the player record:
   - `Current Year Stat ID` offset `296` / `0x128`, type `ushort`, group `Stats`.
   - `Player Stat ID 1` offset `298` / `0x12A`, type `ushort`, group `Stats`.
   - `Player Stat ID 31` offset `358` / `0x166`, type `ushort`, group `Stats`.

2. Career/stat detail fields are the data read after choosing one of those selector fields:
   - `Current Team` offset `0`, type `ulonglong`, group `Basic Info`, `team_address_dropdown=true`.
   - `Previous Team` offset `8`, type `ulonglong`, group `Basic Info`, `team_address_dropdown=true`.
   - `Games Played` offset `20`, type `bitfield`, group `Game Stats`.

Additional LearnFrom runtime names confirm this is a dedicated career-stats editor path, not a generic every-Stats-group path:

- `CAREER_STATS_FIELD_INFOS`
- `CAREER_STATS_STRIDE`
- `CareerStatEditorDialog.load_header_stats`
- `CareerStatEditorDialog.load_data`
- `CareerStatEditorDialog.save_field_to_memory`
- UI labels: `Edit Career Stat #`, `Stats ID`, `Career Stat`, `No Stat ID`.

## Current editor mapping that must match this

Current offsets flatten the LearnFrom selector fields and detail fields into:

`Players / Stats / Season IDs`

Within that group:

- selector rows: `CURRENTYEARSTATID`, `STATSID1..STATSID31`
- detail rows: non-selector fields such as `CURRENTTEAM`, `PREVIOUSTEAM`, `GAMESPLAYED`, `POINTS`, etc.

## Required runtime rule

Changing the Active Season Stat ID dropdown must refresh/read only the non-selector rows in `Players / Stats / Season IDs`.

Those detail rows are not relative to the selector field's address. LearnFrom shows a dedicated career-stats table path:

- roster root pointer comes from the LearnFrom roster signature/pointer slot;
- career-stats array begin pointer is read from `roster_base_addr + 0xA8`;
- career-stat detail record address is `career_stats_base + stat_id * CAREER_STATS_STRIDE`;
- detail field address is then `career_stat_record + field.offset`.

High-confidence LearnFrom constants used by the current editor:

- roster pointer slot RVA: `0x7E1E830` (`132245552`), from signature match `0x7E1E750 + 0xE0`;
- career-stats array begin offset from roster root: `0x98`;
- `CAREER_STATS_STRIDE`: `0x40` / `64`.

Do not route these unrelated groups through the selector:

- `Players / Stats / Season High`
- `Players / Stats / Career High`
- `Players / Stats / Awards`
- any future non-Season-ID stats group unless LearnFrom evidence says it is part of the career-stat edit path.

## Regression checks added

`tests/test_data_model_runtime_offsets.py` now has LearnFrom-shaped tests:

- selector fields are separate player-row fields;
- detail fields are non-selector rows in the same `Season IDs` group;
- choosing `STATS_ID#1` vs `STATS_ID#2` reads the selected Stat ID value from the player row, then reads detail values from the career-stats table;
- unrelated `Players / Stats / Edit` fields do not become selector-relative.
