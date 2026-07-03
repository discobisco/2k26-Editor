# Franchise Manager Missing Data / Offset Hunt Report

This report belongs to the fresh `nba2k_editor.franchise` Franchise Manager layer.

Runtime code ignores unavailable optional data instead of blocking import or generating placeholder UI text. Missing franchise-critical data is tracked here only until the existing editor field registry, offset schema, live read path, or write path proves support.

| Field / system | Why needed | Current behavior | Read-only enough? | Write eventually needed? | Priority | Verification path | Current status |
|---|---|---|---:|---:|---|---|---|
| Current season year | Era, draft class timing, history, reports | Not supplied to runtime snapshot | Yes | No | Critical | Locate existing league/season field in offset schema or editor registry | Missing field / unsupported by current editor |
| Current calendar date | Sim stop timing, trade deadline, offseason phase | Not supplied to runtime snapshot | Yes | No | Critical | Locate date/week/day fields through existing data model | Missing field / unsupported by current editor |
| Current franchise phase | Regular season vs offseason routing | LLM sees no confirmed phase unless persisted externally | Yes | No | Critical | Existing league/franchise phase read path | Missing field / unsupported by current editor |
| Offseason phase | League meetings, staff, combine, draft, free agency sequencing | LLM must infer only from persisted franchise state if present | Yes | No | Critical | Franchise persistence / league state field | Missing field / unsupported by current editor |
| Playoff round | Playoff-specific pressure and sim stops | Not supplied | Yes | No | Important | League playoff state field | Missing field / unsupported by current editor |
| League ruleset / era rules | Historical/MyEras gating | Prompt tells LLM to be era-aware; no confirmed rule data supplied | Yes | Eventually | Critical | Existing league/rules offsets or persisted franchise config | Missing field / unsupported by current editor |
| Salary cap | CFO/free agency/tax decisions | Not supplied unless a discovered team/league field maps to cap | Yes | No | Critical | League financial fields in current offsets/editor registry | Missing field / unsupported by current editor |
| Luxury tax line | Owner/CFO pressure | Not supplied | Yes | No | Critical | League financial fields | Missing field / unsupported by current editor |
| Hard cap / apron values | Modern cap restrictions | Not supplied | Yes | No | Important | League financial fields | Missing field / unsupported by current editor |
| Draft order | Draft room and pick trade leverage | Not supplied | Yes | Eventually | Critical | Draft/pick fields or existing draft class systems | Missing field / unsupported by current editor |
| Pick ownership | Asset tracking and trade logic | Not supplied | Yes | Eventually | Critical | Existing pick ownership data or new editor support | Missing field / unsupported by current editor |
| Trade deadline date/state | Trade deadline room and sim stops | Not supplied | Yes | No | Critical | League date/deadline fields | Missing field / unsupported by current editor |
| Free agency state | FA phase gating | Not supplied | Yes | No | Important | League offseason/free-agency fields | Missing field / unsupported by current editor |
| Moratorium state | FA restrictions | Not supplied | Yes | No | Nice-to-have | League offseason fields | Missing field / unsupported by current editor |
| Expansion state | Expansion draft and league meetings | Not supplied | Yes | Eventually | Important | League/team count/expansion metadata | Missing field / unsupported by current editor |
| Relocation/rebrand state | Owner politics and identity changes | Not supplied | Yes | Eventually | Important | Team identity/write support | Missing field / unsupported by current editor |
| Team wins/losses | Sim negotiation and owner pressure | Read when matching Teams fields exist | Yes | No | Critical | `EditorDataModel.grouped_fields("Teams")` + `read_entry_value` | Partially supported by discovered Teams fields |
| Team conference/division rank | Playoff pressure | Read when matching Teams fields exist | Yes | No | Important | Teams fields | Partially supported if authored fields exist |
| Team playoff seed | Playoff pressure | Read when matching Teams field exists | Yes | No | Important | Teams fields | Partially supported if authored field exists |
| Team city / name | Front-office identity | Read from Teams fields when available; otherwise record label | Yes | Eventually for rebrand | Critical | Teams `CITYNAME`/`TEAMNAME` fields | Partially supported |
| Team cap room/payroll | CFO/free agency | Read only if matching Teams fields exist | Yes | No | Critical | Teams/league financial fields | Mostly missing / partially probed |
| Team luxury tax / hard cap status | CFO/owner restrictions | Not supplied | Yes | No | Critical | Teams/league financial fields | Missing field / unsupported by current editor |
| Team morale/chemistry | coach/GM conflict | Not supplied | Yes | Eventually | Important | Teams/player morale fields | Missing field / unsupported by current editor |
| Team injuries | trainer pressure | Not supplied as team-level state | Yes | No | Important | Player injury fields aggregated by team | Missing field / unsupported by current editor |
| Team rotation/minutes | coach pressure | Not supplied | Yes | Eventually | Important | Existing rotation/minutes write/read path | Missing field / unsupported by current editor |
| Team staff/coach IDs | staff phase | Not supplied | Yes | Eventually | Important | Staff domain + Teams staff linkage | Missing field / unsupported by current editor |
| Team owner/governor data | owner profile continuity | LLM may create/persist profiles, but no 2K owner data supplied | Yes | Eventually | Important | Staff/owner fields or persisted franchise records | Missing field / unsupported by current editor |
| Market size / fan interest | relocation, ownership pressure | Not supplied | Yes | No | Important | Team financial/market fields | Missing field / unsupported by current editor |
| Player roster membership | Team imports and front offices | Uses existing Team `PLAYER#` roster-slot seam | Yes | Eventually for roster writes | Critical | `player_roster_slot_items_for_team_items(team_items)` | Supported for loaded Teams/Players |
| Player first/last name | roster identity | Read from Players fields when available | Yes | No | Critical | Players `FIRSTNAME`/`LASTNAME` | Supported if authored fields exist |
| Player unique ID | persistent identity | Read from Players fields when available, else index fallback | Yes | No | Important | Players `UNIQUEID`/`PLAYERID` | Partially supported |
| Player OVR/potential/position/age | front-office analysis | Read when matching Players fields exist | Yes | No | Important | Players fields | Partially supported |
| Contract years/salary | FA/trade/cap decisions | Not supplied except salary alias if authored | Yes | Eventually | Critical | Player contract fields | Missing field / unsupported by current editor |
| Bird rights / option years / no-trade clause | FA/trade restrictions | Not supplied | Yes | Eventually | Critical | Player contract/right fields | Missing field / unsupported by current editor |
| Player morale/role/minutes expectation | conflict and FA interest | Not supplied | Yes | Eventually | Important | Player morale/role fields | Missing field / unsupported by current editor |
| Injury status/type/duration/fatigue | trainer/scouting/FA risk | Not supplied | Yes | No | Important | Player injury fields | Missing field / unsupported by current editor |
| Hot/cold status | sim stop and coach pressure | Not supplied | Yes | No | Nice-to-have | Player status fields | Missing field / unsupported by current editor |
| Peak/progression/regression | long-term planning | Not supplied | Yes | No | Important | Player development fields | Missing field / unsupported by current editor |
| Tendencies/badges | scouting/team fit | Not supplied to franchise snapshot yet | Yes | No | Important | Existing Players field registry | Not wired into snapshot |
| Player personality fields | morale/conflict | Not supplied | Yes | No | Nice-to-have | Player personality/morale fields | Missing field / unsupported by current editor |
| Draft rights / rookie status | draft/FA rights | Not supplied | Yes | Eventually | Important | Player/draft fields | Missing field / unsupported by current editor |
| Draft class data | scouting/combine/draft | Prompt requests using existing Player Generator/draft data, but snapshot does not yet import it | Yes | No | Critical | Existing Player Generator / Draft Class domain | Not wired into franchise snapshot |
| Combine measurements/testing | scouting combine | Not supplied | Yes | No | Important | Draft class/player generator/source data | Missing field / unsupported by current editor |
| Individual workout results | draft uncertainty | Not supplied | Yes | No | Important | Franchise persistence / manual input | Missing field / unsupported by current editor |
| Team-slot player move / one-player-for-nothing trade | real roster movement | Explicit apply writes source Team `PLAYER#` compaction, target Team `PLAYER#` append, and Player `CURRENTTEAM` through existing `write_entry_value` | No | Yes | Critical | Franchise service preview/apply tests plus live Team slot writes | Partially supported for loaded Players/Teams with empty target slot |
| Multi-player trade execution | real transaction writes | LLM records can hold multiple player assets; current application preflights every asset write plan before writing and supports loaded player-for-player packages by removing all outgoing players before appending incoming players into opened Team `PLAYER#` slots; no rollback after an external write failure yet | No | Yes | Critical | Add rollback/failure recovery around existing write path | Partially supported for loaded player packages |
| Free-agent signing | real roster writes | Can move a loaded player to a Team slot if represented as a roster move; true free-agent pool/source state not proven | No | Yes | Critical | Prove free-agent player source state before enabling as signing flow | Partially supported as loaded-player move only |
| Waive/release | real roster writes | Source Team `PLAYER#` compaction exists, but correct free-agent/no-team `CURRENTTEAM` target is not proven | No | Yes | Critical | Verify no-team/free-agent pointer semantics | Unsupported until destination state is proven |
| Rotation assignment | real rotation writes | Team slot roster movement exists; rotation/minutes ordering fields are not wired | No | Yes | Important | Existing rotation/minutes write path | Unsupported by current editor |
| G League assignment | roster control | No write action exposed | No | Yes | Nice-to-have | Existing player/team assignment fields | Unsupported by current editor |
| Draft pick transfer | trades/draft | No write action exposed | No | Yes | Critical | Pick ownership write path | Unsupported by current editor |
| Staff hiring/firing | staff phase | LLM can generate decisions; no 2K write action exposed | No | Yes | Important | Staff domain write support | Unsupported by current editor |
| Rule change/voting | league meetings | LLM can generate/persist votes; no game rules write exposed | No | Eventually | Important | Existing rules/config write support | Unsupported by current editor |
| Expansion draft | expansion phase | LLM can generate/persist plan; no team creation/write support | No | Eventually | Important | Team creation/protection list support | Unsupported by current editor |
| Relocation/rebranding | owner phase | LLM can generate/persist request; no team identity write support exposed | No | Eventually | Important | Existing Team identity write path | Unsupported by current editor |
