# College Dynasty Data and Projection Formats

College Mode keeps the canonical league in the Franchise SQLite database. NBA 2K is a temporary projection surface for 30 season teams and 16 Sweet 16 teams.

## Canonical catalog

Use **Import 365-Program Catalog** with one JSON object containing exactly 31 conferences and 365 programs. Program IDs, player IDs, and conference IDs are durable identities. Names are display-only.

```json
{
  "true_sim_year": 2025,
  "conferences": [
    {"conference_id": "conference-id", "name": "Conference Name"}
  ],
  "programs": [
    {
      "program_id": "stable-program-id",
      "conference_id": "conference-id",
      "name": "Program Name",
      "short_name": "Program",
      "team_fields": {
        "CITYNAME": "City Name"
      },
      "players": [
        {
          "player_id": "stable-player-id",
          "display_name": "Player Name",
          "roster_order": 1,
          "eligibility_remaining": 4,
          "status": "active",
          "entry_year": 2025,
          "player_fields": {
            "FIRSTNAME": "Player",
            "LASTNAME": "Name",
            "HEIGHT": 76,
            "WEIGHT": 205
          }
        }
      ]
    }
  ]
}
```

Each program may have at most 15 active players. `roster_order` is 1 through 15. A departed player remains canonical history but is excluded from projection.

Allowed `team_fields` are limited to team identity/presentation fields:

- `TEAMNAME`
- `CITYNAME`, `CITYSHORTNAME`, `CITYABBREV`
- `STATE`, `STATESHORTNAME`
- `LOGO1` through `LOGO7`, `MURALLOGO`
- `ARENAFILENAME`, `ARENANAME`, `ARENANICKNAME`
- `STADIUMARENAID`, `STADIUMCITYNAME`, `STADIUMCITYSHORTNAME`, `STADIUMSTATESHORTNAME`

Roster pointers (`PLAYER1` through `PLAYER15`) are never accepted as team identity data. Player `CURRENTTEAM`, `CONTRACTTEAM`, contract-year fields, and stat-ID links are projection-controlled and cannot be supplied in `player_fields`.

The repository does not ship an invented 365-program list. Import a season-appropriate authoritative catalog; this is required because conference membership changes by true simulation year.

## Incremental player updates

Use **Import Player Updates** to add recruits or update active canonical players without replacing the catalog or deleting season/tournament state:

```json
{
  "players": [
    {
      "player_id": "stable-new-player-id",
      "program_id": "stable-program-id",
      "display_name": "Player Name",
      "roster_order": 7,
      "eligibility_remaining": 4,
      "status": "active",
      "entry_year": 2026,
      "player_fields": {
        "FIRSTNAME": "Player",
        "LASTNAME": "Name"
      }
    }
  ]
}
```

A canonical player already marked `departed` cannot be restored to `active`. A new player must receive a new stable `player_id`.

## Season projection

1. Select a user program and fixed random seed.
2. **Plan 30-Team Season** persists the user program, its complete conference, and deterministic nonconference fillers.
3. **Capture 450 Linked Slots** requires all 30 physical teams to have 15 existing `PLAYER1..15` pointers and 450 unique player records.
4. **Preview Season Projection** performs a no-write preflight.
5. **Apply Season Projection** requires confirmation, runs the existing explicit player reset, then writes:
   - filler name `A Z`;
   - height 60 inches (5'0");
   - weight 100 pounds;
   - wingspan 60 inches / 152.4 cm;
   - four contract years for filler records;
   - remaining eligibility years for real canonical players;
   - canonical program team identity;
   - canonical player fields.
6. The apply is blocked if any captured team roster pointer changed. It never repairs or invents a missing roster link.
7. **Sync Season Players Out** reads each projected canonical player's declared field set back into SQLite.
8. **Record FA Departures** permanently marks projected players whose `CURRENTTEAM` raw pointer is zero as departed/ineligible.
9. **Advance Eligibility** decrements every still-active canonical player exactly once for the true simulation year, including players on the 335 programs outside the game.

## Tournament handoff

The tournament uses a 64-program external bracket. The program IDs must be supplied in exact bracket order; adjacent entries form Round 1 games.

```json
{"bracket_program_ids": ["program-slot-1", "program-slot-2"]}
```

The real file requires 64 unique IDs.

Opening-round result import accepts only rounds 1 and 2:

```json
{
  "results": [
    {"round_number": 1, "game_number": 1, "winner_program_id": "program-slot-1"}
  ]
}
```

After all 48 opening-round results are recorded, the 16 Round 2 winners are the Sweet 16. Enter the 16 physical NBA 2K playoff team indexes in exact bracket order, then:

1. **Map Sweet 16**
2. **Capture 240 Sweet 16 Slots**
3. **Preview Sweet 16 Projection**
4. **Apply Sweet 16 Projection**

Later in-game playoff results are reconciled with **Import In-Game Playoff Results**. Those files may contain only rounds 3 through 6. Completing Round 6 persists the national champion.
