from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.models import (
    COLLEGE_PLAYER_ACTIVE,
    COLLEGE_PLAYER_DEPARTED,
    CollegeConference,
    CollegePlayer,
    CollegePlayerProjection,
    CollegeProgram,
    CollegeTeamProjection,
    CollegeTournamentGame,
    LEAGUE_MODE_COLLEGE,
)
from nba2k_editor.franchise.storage import FranchiseRepository, _utc_now_text


COLLEGE_CONFERENCE_COUNT = 31
COLLEGE_PROGRAM_COUNT = 365
COLLEGE_GAME_TEAM_COUNT = 30
COLLEGE_ROSTER_SIZE = 15
COLLEGE_SEASON_PLAYER_SLOT_COUNT = COLLEGE_GAME_TEAM_COUNT * COLLEGE_ROSTER_SIZE
COLLEGE_TOURNAMENT_FIELD_SIZE = 64
COLLEGE_SWEET16_SIZE = 16
PROJECTION_STAGE_SEASON = "season"
PROJECTION_STAGE_SWEET16 = "sweet16"
COLLEGE_TEAM_IDENTITY_FIELDS = frozenset(
    {
        "TEAMNAME",
        "CITYNAME",
        "CITYSHORTNAME",
        "CITYABBREV",
        "STATE",
        "STATESHORTNAME",
        "LOGO1",
        "LOGO2",
        "LOGO3",
        "LOGO4",
        "LOGO5",
        "LOGO6",
        "LOGO7",
        "MURALLOGO",
        "ARENAFILENAME",
        "ARENANAME",
        "ARENANICKNAME",
        "STADIUMARENAID",
        "STADIUMCITYNAME",
        "STADIUMCITYSHORTNAME",
        "STADIUMSTATESHORTNAME",
    }
)
COLLEGE_PLAYER_PROJECTION_CONTROLLED_FIELDS = frozenset(
    {
        "CURRENTTEAM",
        "CONTRACTTEAM",
        "CONTRACTLENGTH",
        "YEARSLEFT",
        "ORIGINALCONTRACTYEARS",
        "CURRENTYEARSTATID",
        *(f"STATSID{index}" for index in range(1, 32)),
    }
)


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _json_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def college_catalog_from_payload(
    payload: dict[str, Any],
) -> tuple[tuple[CollegeConference, ...], tuple[CollegeProgram, ...], tuple[CollegePlayer, ...]]:
    conferences_payload = payload.get("conferences")
    programs_payload = payload.get("programs")
    if not isinstance(conferences_payload, list) or not isinstance(programs_payload, list):
        raise ValueError("college catalog requires conferences and programs arrays")
    conferences = tuple(
        CollegeConference(
            conference_id=_required_text(row.get("conference_id"), "conference_id"),
            name=_required_text(row.get("name"), "conference name"),
        )
        for row in conferences_payload
        if isinstance(row, dict)
    )
    if len(conferences) != len(conferences_payload):
        raise ValueError("every conference row must be an object")
    players: list[CollegePlayer] = []
    programs: list[CollegeProgram] = []
    for row in programs_payload:
        if not isinstance(row, dict):
            raise ValueError("every program row must be an object")
        program_id = _required_text(row.get("program_id"), "program_id")
        name = _required_text(row.get("name"), "program name")
        programs.append(
            CollegeProgram(
                program_id=program_id,
                conference_id=_required_text(row.get("conference_id"), "program conference_id"),
                name=name,
                short_name=_required_text(row.get("short_name") or name, "program short_name"),
                team_fields=_json_object(row.get("team_fields", {}), "team_fields"),
            )
        )
        player_rows = row.get("players", [])
        if not isinstance(player_rows, list):
            raise ValueError(f"players for {program_id} must be an array")
        for roster_order, player_row in enumerate(player_rows, start=1):
            if not isinstance(player_row, dict):
                raise ValueError(f"every player for {program_id} must be an object")
            eligibility = int(player_row.get("eligibility_remaining", 4))
            players.append(
                CollegePlayer(
                    player_id=_required_text(player_row.get("player_id"), "player_id"),
                    program_id=program_id,
                    display_name=_required_text(player_row.get("display_name"), "player display_name"),
                    roster_order=int(player_row.get("roster_order", roster_order)),
                    eligibility_remaining=eligibility,
                    status=_required_text(player_row.get("status", COLLEGE_PLAYER_ACTIVE), "player status"),
                    player_fields=_json_object(player_row.get("player_fields", {}), "player_fields"),
                    entry_year=int(player_row.get("entry_year", payload.get("true_sim_year", 0))),
                    departure_year=(
                        int(player_row["departure_year"])
                        if player_row.get("departure_year") is not None
                        else None
                    ),
                )
            )
    return conferences, tuple(programs), tuple(players)


def load_college_catalog(path: str | Path) -> tuple[tuple[CollegeConference, ...], tuple[CollegeProgram, ...], tuple[CollegePlayer, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("college catalog root must be an object")
    return college_catalog_from_payload(payload)


def college_player_updates_from_payload(payload: dict[str, Any]) -> tuple[CollegePlayer, ...]:
    rows = payload.get("players")
    if not isinstance(rows, list):
        raise ValueError("college player update requires a players array")
    updates: list[CollegePlayer] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every college player update must be an object")
        updates.append(
            CollegePlayer(
                player_id=_required_text(row.get("player_id"), "player_id"),
                program_id=_required_text(row.get("program_id"), "program_id"),
                display_name=_required_text(row.get("display_name"), "player display_name"),
                roster_order=int(_required_text(row.get("roster_order"), "roster_order")),
                eligibility_remaining=int(row.get("eligibility_remaining", 4)),
                status=_required_text(row.get("status", COLLEGE_PLAYER_ACTIVE), "player status"),
                player_fields=_json_object(row.get("player_fields", {}), "player_fields"),
                entry_year=int(row.get("entry_year", 0)),
                departure_year=int(row["departure_year"]) if row.get("departure_year") is not None else None,
            )
        )
    return tuple(updates)


def load_college_player_updates(path: str | Path) -> tuple[CollegePlayer, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("college player update root must be an object")
    return college_player_updates_from_payload(payload)


class CollegeDynastyRepository:
    """Canonical college universe stored in the existing franchise SQLite database."""

    def __init__(self, franchise_repository: FranchiseRepository) -> None:
        self.franchise_repository = franchise_repository

    def _connect(self):
        connection = self.franchise_repository._connect()
        self.franchise_repository.initialize(connection)
        return connection

    def _require_college_mode(self) -> None:
        if self.franchise_repository.load().setup.league_mode != LEAGUE_MODE_COLLEGE:
            raise ValueError("College dynasty systems require College Mode")

    def replace_catalog(
        self,
        conferences: Iterable[CollegeConference],
        programs: Iterable[CollegeProgram],
        players: Iterable[CollegePlayer] = (),
    ) -> None:
        self._require_college_mode()
        conference_rows = tuple(conferences)
        program_rows = tuple(programs)
        player_rows = tuple(players)
        if len(conference_rows) != COLLEGE_CONFERENCE_COUNT:
            raise ValueError(f"college catalog requires exactly {COLLEGE_CONFERENCE_COUNT} conferences")
        if len(program_rows) != COLLEGE_PROGRAM_COUNT:
            raise ValueError(f"college catalog requires exactly {COLLEGE_PROGRAM_COUNT} programs")
        conference_ids = tuple(row.conference_id for row in conference_rows)
        program_ids = tuple(row.program_id for row in program_rows)
        if len(set(conference_ids)) != len(conference_ids):
            raise ValueError("college conference IDs must be unique")
        if len({row.name.casefold() for row in conference_rows}) != len(conference_rows):
            raise ValueError("college conference names must be unique")
        if len(set(program_ids)) != len(program_ids):
            raise ValueError("college program IDs must be unique")
        if len({row.name.casefold() for row in program_rows}) != len(program_rows):
            raise ValueError("college program names must be unique")
        conference_id_set = set(conference_ids)
        for program in program_rows:
            if program.conference_id not in conference_id_set:
                raise ValueError(f"unknown conference {program.conference_id} for {program.program_id}")
            unsafe_team_fields = tuple(
                sorted(
                    field_name
                    for field_name in (str(value).upper() for value in program.team_fields)
                    if field_name not in COLLEGE_TEAM_IDENTITY_FIELDS
                )
            )
            if unsafe_team_fields:
                raise ValueError(
                    f"unsupported team identity fields for {program.program_id}: {unsafe_team_fields}"
                )
        self._validate_players(player_rows, set(program_ids))
        connection = self._connect()
        try:
            for table in (
                "college_player_projection",
                "college_sweet16_projection",
                "college_tournament_games",
                "college_tournament_entries",
                "college_departures",
                "college_team_projection",
                "college_seasons",
                "college_players",
                "college_programs",
                "college_conferences",
            ):
                connection.execute(f"DELETE FROM {table}")
            connection.executemany(
                "INSERT INTO college_conferences(conference_id, name) VALUES(?, ?)",
                ((row.conference_id, row.name) for row in conference_rows),
            )
            connection.executemany(
                """
                INSERT INTO college_programs(program_id, conference_id, name, short_name, team_fields_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    (
                        row.program_id,
                        row.conference_id,
                        row.name,
                        row.short_name,
                        json.dumps(row.team_fields, sort_keys=True),
                    )
                    for row in program_rows
                ),
            )
            self._insert_players(connection, player_rows)
            connection.commit()
        finally:
            connection.close()

    def _validate_players(self, players: tuple[CollegePlayer, ...], program_ids: set[str]) -> None:
        player_ids: set[str] = set()
        roster_keys: set[tuple[str, int]] = set()
        active_counts: dict[str, int] = {}
        for player in players:
            if player.player_id in player_ids:
                raise ValueError(f"duplicate college player ID: {player.player_id}")
            player_ids.add(player.player_id)
            if player.program_id not in program_ids:
                raise ValueError(f"unknown program {player.program_id} for player {player.player_id}")
            if not 1 <= int(player.roster_order) <= COLLEGE_ROSTER_SIZE:
                raise ValueError(f"roster_order must be 1-{COLLEGE_ROSTER_SIZE}: {player.player_id}")
            if not 0 <= int(player.eligibility_remaining) <= 4:
                raise ValueError(f"eligibility_remaining must be 0-4: {player.player_id}")
            if player.status not in {COLLEGE_PLAYER_ACTIVE, COLLEGE_PLAYER_DEPARTED}:
                raise ValueError(f"invalid player status: {player.status}")
            if player.status == COLLEGE_PLAYER_ACTIVE:
                roster_key = (player.program_id, int(player.roster_order))
                if roster_key in roster_keys:
                    raise ValueError(f"duplicate active roster order for {player.program_id}: {player.roster_order}")
                roster_keys.add(roster_key)
                if int(player.eligibility_remaining) == 0:
                    raise ValueError(f"active player must have eligibility remaining: {player.player_id}")
                active_counts[player.program_id] = active_counts.get(player.program_id, 0) + 1
                if active_counts[player.program_id] > COLLEGE_ROSTER_SIZE:
                    raise ValueError(f"{player.program_id} has more than {COLLEGE_ROSTER_SIZE} active players")
            unsafe_player_fields = tuple(
                sorted(
                    field_name
                    for field_name in (str(value).upper() for value in player.player_fields)
                    if field_name in COLLEGE_PLAYER_PROJECTION_CONTROLLED_FIELDS
                )
            )
            if unsafe_player_fields:
                raise ValueError(
                    f"projection-controlled player fields are not allowed for {player.player_id}: {unsafe_player_fields}"
                )

    def _insert_players(self, connection, players: tuple[CollegePlayer, ...]) -> None:
        connection.executemany(
            """
            INSERT INTO college_players(
                player_id, program_id, display_name, roster_order, eligibility_remaining,
                status, player_fields_json, entry_year, departure_year
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row.player_id,
                    row.program_id,
                    row.display_name,
                    int(row.roster_order),
                    int(row.eligibility_remaining),
                    row.status,
                    json.dumps(row.player_fields, sort_keys=True),
                    int(row.entry_year),
                    row.departure_year,
                )
                for row in players
            ),
        )

    def upsert_players(self, players: Iterable[CollegePlayer]) -> tuple[str, ...]:
        player_rows = tuple(players)
        if not player_rows:
            return ()
        programs = {row.program_id for row in self.list_programs()}
        if len(programs) != COLLEGE_PROGRAM_COUNT:
            raise ValueError("import the complete college catalog before updating players")
        existing = {row.player_id: row for row in self.list_players()}
        for player in player_rows:
            prior = existing.get(player.player_id)
            if prior is not None and prior.status == COLLEGE_PLAYER_DEPARTED and player.status == COLLEGE_PLAYER_ACTIVE:
                raise ValueError(f"departed college player cannot be restored: {player.player_id}")
            existing[player.player_id] = player
        self._validate_players(tuple(existing.values()), programs)
        connection = self._connect()
        try:
            connection.executemany(
                """
                INSERT INTO college_players(
                    player_id, program_id, display_name, roster_order, eligibility_remaining,
                    status, player_fields_json, entry_year, departure_year
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    program_id = excluded.program_id,
                    display_name = excluded.display_name,
                    roster_order = excluded.roster_order,
                    eligibility_remaining = excluded.eligibility_remaining,
                    status = excluded.status,
                    player_fields_json = excluded.player_fields_json,
                    entry_year = excluded.entry_year,
                    departure_year = excluded.departure_year
                """,
                (
                    (
                        row.player_id,
                        row.program_id,
                        row.display_name,
                        int(row.roster_order),
                        int(row.eligibility_remaining),
                        row.status,
                        json.dumps(row.player_fields, sort_keys=True),
                        int(row.entry_year),
                        row.departure_year,
                    )
                    for row in player_rows
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(row.player_id for row in player_rows)

    def catalog_counts(self) -> tuple[int, int, int]:
        connection = self._connect()
        try:
            conference_count = int(connection.execute("SELECT COUNT(*) FROM college_conferences").fetchone()[0])
            program_count = int(connection.execute("SELECT COUNT(*) FROM college_programs").fetchone()[0])
            player_count = int(connection.execute("SELECT COUNT(*) FROM college_players").fetchone()[0])
            return conference_count, program_count, player_count
        finally:
            connection.close()

    def list_programs(self) -> tuple[CollegeProgram, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT program_id, conference_id, name, short_name, team_fields_json
                FROM college_programs
                ORDER BY name COLLATE NOCASE, program_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegeProgram(str(row[0]), str(row[1]), str(row[2]), str(row[3]), json.loads(row[4]))
            for row in rows
        )

    def list_conferences(self) -> tuple[CollegeConference, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT conference_id, name FROM college_conferences ORDER BY name COLLATE NOCASE"
            ).fetchall()
        finally:
            connection.close()
        return tuple(CollegeConference(str(row[0]), str(row[1])) for row in rows)

    def list_players(self, program_id: str | None = None, *, active_only: bool = False) -> tuple[CollegePlayer, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if program_id is not None:
            clauses.append("program_id = ?")
            parameters.append(str(program_id))
        if active_only:
            clauses.append("status = 'active'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT player_id, program_id, display_name, roster_order, eligibility_remaining,
                       status, player_fields_json, entry_year, departure_year
                FROM college_players
                {where}
                ORDER BY program_id, roster_order, player_id
                """,
                parameters,
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegePlayer(
                player_id=str(row[0]),
                program_id=str(row[1]),
                display_name=str(row[2]),
                roster_order=int(row[3]),
                eligibility_remaining=int(row[4]),
                status=str(row[5]),
                player_fields=json.loads(row[6]),
                entry_year=int(row[7]),
                departure_year=int(row[8]) if row[8] is not None else None,
            )
            for row in rows
        )

    def plan_season(
        self,
        *,
        true_sim_year: int,
        user_program_id: str,
        random_seed: int,
    ) -> tuple[CollegeTeamProjection, ...]:
        self._require_college_mode()
        existing = self.list_team_projection(true_sim_year)
        if existing:
            return existing
        programs = self.list_programs()
        if len(programs) != COLLEGE_PROGRAM_COUNT:
            raise ValueError("import the complete 365-program college catalog before planning a season")
        by_id = {row.program_id: row for row in programs}
        user_program = by_id.get(str(user_program_id))
        if user_program is None:
            raise ValueError(f"unknown user program: {user_program_id}")
        conference_programs = sorted(
            (row for row in programs if row.conference_id == user_program.conference_id),
            key=lambda row: (row.name.casefold(), row.program_id),
        )
        if len(conference_programs) > COLLEGE_GAME_TEAM_COUNT:
            raise ValueError("the user's conference has more than 30 programs and cannot fit in the game projection")
        selected_ids = {row.program_id for row in conference_programs}
        nonconference = [row for row in programs if row.program_id not in selected_ids]
        random.Random(int(random_seed)).shuffle(nonconference)
        selected_nonconference = nonconference[: COLLEGE_GAME_TEAM_COUNT - len(conference_programs)]
        franchise = self.franchise_repository.load()
        user_team_index = int(franchise.setup.user_team_index)
        available_indexes = [index for index in range(COLLEGE_GAME_TEAM_COUNT) if index != user_team_index]
        ordered_programs = [
            user_program,
            *(row for row in conference_programs if row.program_id != user_program.program_id),
            *selected_nonconference,
        ]
        if len(ordered_programs) != COLLEGE_GAME_TEAM_COUNT:
            raise RuntimeError("college season selection did not produce 30 programs")
        mapping: list[tuple[int, CollegeProgram, str]] = [(user_team_index, user_program, "user")]
        for game_team_index, program in zip(available_indexes, ordered_programs[1:], strict=True):
            reason = "conference" if program.conference_id == user_program.conference_id else "nonconference"
            mapping.append((game_team_index, program, reason))
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO college_seasons(true_sim_year, user_program_id, random_seed, eligibility_advanced, created_at) VALUES(?, ?, ?, 0, ?)",
                (int(true_sim_year), user_program.program_id, int(random_seed), _utc_now_text()),
            )
            connection.executemany(
                """
                INSERT INTO college_team_projection(true_sim_year, game_team_index, program_id, selection_reason)
                VALUES(?, ?, ?, ?)
                """,
                (
                    (int(true_sim_year), game_team_index, program.program_id, reason)
                    for game_team_index, program, reason in mapping
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return self.list_team_projection(true_sim_year)

    def list_team_projection(self, true_sim_year: int) -> tuple[CollegeTeamProjection, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT projection.true_sim_year, projection.game_team_index, projection.program_id,
                       programs.name, projection.selection_reason
                FROM college_team_projection AS projection
                JOIN college_programs AS programs ON programs.program_id = projection.program_id
                WHERE projection.true_sim_year = ?
                ORDER BY projection.game_team_index
                """,
                (int(true_sim_year),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegeTeamProjection(int(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4]))
            for row in rows
        )

    def _stage_program_mapping(self, true_sim_year: int, stage: str) -> dict[int, str]:
        connection = self._connect()
        try:
            if stage == PROJECTION_STAGE_SEASON:
                rows = connection.execute(
                    "SELECT game_team_index, program_id FROM college_team_projection WHERE true_sim_year = ?",
                    (int(true_sim_year),),
                ).fetchall()
            elif stage == PROJECTION_STAGE_SWEET16:
                rows = connection.execute(
                    "SELECT game_team_index, program_id FROM college_sweet16_projection WHERE true_sim_year = ?",
                    (int(true_sim_year),),
                ).fetchall()
            else:
                raise ValueError(f"unknown college projection stage: {stage}")
        finally:
            connection.close()
        return {int(row[0]): str(row[1]) for row in rows}

    def capture_projection_slots(self, model: Any, *, true_sim_year: int, stage: str = PROJECTION_STAGE_SEASON) -> tuple[CollegePlayerProjection, ...]:
        program_mapping = self._stage_program_mapping(true_sim_year, stage)
        expected_team_count = COLLEGE_GAME_TEAM_COUNT if stage == PROJECTION_STAGE_SEASON else COLLEGE_SWEET16_SIZE
        if len(program_mapping) != expected_team_count:
            raise ValueError(f"{stage} projection requires {expected_team_count} mapped teams")
        teams_by_index = {
            int(item.index): item
            for item in getattr(model, "loaded_items", {}).get("Teams", {}).values()
            if int(item.index) in program_mapping
        }
        missing_teams = tuple(sorted(set(program_mapping).difference(teams_by_index)))
        if missing_teams:
            raise ValueError(f"projection team indexes are not loaded: {missing_teams}")
        rows = model.player_roster_slot_items_for_team_items(tuple(teams_by_index[index] for index in sorted(teams_by_index)))
        slots_by_team: dict[int, dict[int, tuple[Any, dict[str, Any]]]] = {index: {} for index in program_mapping}
        for player, placement in rows:
            team_index = int(placement["team_index"])
            if team_index not in slots_by_team:
                continue
            roster_slot = int(placement["team_slot"])
            slots_by_team[team_index][roster_slot] = (player, placement)
        for team_index, slots in slots_by_team.items():
            if tuple(sorted(slots)) != tuple(range(1, COLLEGE_ROSTER_SIZE + 1)):
                raise ValueError(
                    f"Team {team_index} must have all 15 existing PLAYER slots populated before projection; found {len(slots)}"
                )
        all_game_player_indexes = [
            int(player.index)
            for slots in slots_by_team.values()
            for player, _placement in slots.values()
        ]
        expected_slot_count = expected_team_count * COLLEGE_ROSTER_SIZE
        if len(all_game_player_indexes) != expected_slot_count or len(set(all_game_player_indexes)) != expected_slot_count:
            raise ValueError(f"projection requires {expected_slot_count} unique reserved player records")
        active_players = self.list_players(active_only=True)
        players_by_program: dict[str, list[CollegePlayer]] = {}
        for player in active_players:
            if player.eligibility_remaining > 0:
                players_by_program.setdefault(player.program_id, []).append(player)
        for players in players_by_program.values():
            players.sort(key=lambda row: (row.roster_order, row.player_id))
        projection_rows: list[CollegePlayerProjection] = []
        for team_index in sorted(program_mapping):
            program_players = players_by_program.get(program_mapping[team_index], [])
            if len(program_players) > COLLEGE_ROSTER_SIZE:
                raise ValueError(f"{program_mapping[team_index]} has more than 15 active players")
            for roster_slot in range(1, COLLEGE_ROSTER_SIZE + 1):
                game_player, placement = slots_by_team[team_index][roster_slot]
                canonical_player = program_players[roster_slot - 1] if roster_slot <= len(program_players) else None
                projection_rows.append(
                    CollegePlayerProjection(
                        true_sim_year=int(true_sim_year),
                        stage=stage,
                        game_team_index=team_index,
                        roster_slot=roster_slot,
                        slot_field=str(placement["team_slot_field"]),
                        game_player_index=int(game_player.index),
                        canonical_player_id=canonical_player.player_id if canonical_player else None,
                    )
                )
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM college_player_projection WHERE true_sim_year = ? AND stage = ?",
                (int(true_sim_year), stage),
            )
            connection.executemany(
                """
                INSERT INTO college_player_projection(
                    true_sim_year, stage, game_team_index, roster_slot, slot_field,
                    game_player_index, canonical_player_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        row.true_sim_year,
                        row.stage,
                        row.game_team_index,
                        row.roster_slot,
                        row.slot_field,
                        row.game_player_index,
                        row.canonical_player_id,
                    )
                    for row in projection_rows
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(projection_rows)

    def list_player_projection(self, true_sim_year: int, *, stage: str = PROJECTION_STAGE_SEASON) -> tuple[CollegePlayerProjection, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT true_sim_year, stage, game_team_index, roster_slot, slot_field,
                       game_player_index, canonical_player_id
                FROM college_player_projection
                WHERE true_sim_year = ? AND stage = ?
                ORDER BY game_team_index, roster_slot
                """,
                (int(true_sim_year), stage),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegePlayerProjection(
                int(row[0]), str(row[1]), int(row[2]), int(row[3]), str(row[4]), int(row[5]),
                str(row[6]) if row[6] is not None else None,
            )
            for row in rows
        )

    def sync_projected_players_from_game(
        self,
        model: Any,
        *,
        true_sim_year: int,
        stage: str = PROJECTION_STAGE_SEASON,
    ) -> tuple[str, ...]:
        """Read only the canonical player's declared field set back from its temporary game record."""
        projections = tuple(
            row
            for row in self.list_player_projection(true_sim_year, stage=stage)
            if row.canonical_player_id is not None
        )
        canonical_players = {row.player_id: row for row in self.list_players()}
        game_players = {
            int(item.index): item
            for item in getattr(model, "loaded_items", {}).get("Players", {}).values()
        }
        updates: list[tuple[str, dict[str, Any]]] = []
        for projection in projections:
            player_id = str(projection.canonical_player_id)
            canonical = canonical_players.get(player_id)
            if canonical is None:
                raise ValueError(f"unknown canonical player: {player_id}")
            game_player = game_players.get(projection.game_player_index)
            if game_player is None:
                raise ValueError(f"projected player index is not loaded: {projection.game_player_index}")
            field_values: dict[str, Any] = {}
            for field_name in canonical.player_fields:
                entry = model._field_by_normalized_name("Players", field_name)
                if entry is None:
                    raise ValueError(f"Players field is unavailable for {player_id}: {field_name}")
                payload = model.read_entry_value_for_item(entry, game_player)
                field_values[str(field_name)] = payload.get("display_value", payload.get("raw_value"))
            updates.append((player_id, field_values))
        connection = self._connect()
        try:
            connection.executemany(
                "UPDATE college_players SET player_fields_json = ? WHERE player_id = ?",
                ((json.dumps(fields, sort_keys=True), player_id) for player_id, fields in updates),
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(player_id for player_id, _fields in updates)

    def record_free_agent_departures(self, model: Any, *, true_sim_year: int) -> tuple[str, ...]:
        projections = tuple(
            row for row in self.list_player_projection(true_sim_year) if row.canonical_player_id is not None
        )
        current_team_entry = model._field_by_normalized_name("Players", "CURRENTTEAM")
        if current_team_entry is None:
            raise ValueError("Players CURRENTTEAM field is not available")
        players_by_index = {
            int(item.index): item for item in getattr(model, "loaded_items", {}).get("Players", {}).values()
        }
        departed: list[tuple[str, int]] = []
        for projection in projections:
            item = players_by_index.get(projection.game_player_index)
            if item is None:
                raise ValueError(f"projected player index is not loaded: {projection.game_player_index}")
            current_team = int(model.read_entry_value_for_item(current_team_entry, item).get("raw_value") or 0)
            if current_team == 0:
                departed.append((str(projection.canonical_player_id), projection.game_player_index))
        if not departed:
            return ()
        connection = self._connect()
        try:
            for player_id, game_player_index in departed:
                row = connection.execute(
                    "SELECT program_id FROM college_players WHERE player_id = ?",
                    (player_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"unknown canonical player: {player_id}")
                connection.execute(
                    """
                    UPDATE college_players
                    SET status = 'departed', eligibility_remaining = 0, departure_year = ?
                    WHERE player_id = ?
                    """,
                    (int(true_sim_year), player_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO college_departures(
                        player_id, program_id, true_sim_year, reason, game_player_index, created_at
                    ) VALUES(?, ?, ?, 'free_agency', ?, ?)
                    """,
                    (player_id, str(row[0]), int(true_sim_year), game_player_index, _utc_now_text()),
                )
            connection.commit()
        finally:
            connection.close()
        return tuple(player_id for player_id, _index in departed)

    def advance_eligibility(self, *, true_sim_year: int) -> tuple[str, ...]:
        """Advance every still-active canonical player once after the season closes."""
        connection = self._connect()
        try:
            season = connection.execute(
                "SELECT eligibility_advanced FROM college_seasons WHERE true_sim_year = ?",
                (int(true_sim_year),),
            ).fetchone()
            if season is None:
                raise ValueError(f"college season is not planned: {true_sim_year}")
            if bool(int(season[0])):
                return ()
            exhausting = tuple(
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    """
                    SELECT player_id, program_id
                    FROM college_players
                    WHERE status = 'active' AND eligibility_remaining = 1 AND entry_year <= ?
                    ORDER BY player_id
                    """,
                    (int(true_sim_year),),
                )
            )
            connection.execute(
                """
                UPDATE college_players
                SET eligibility_remaining = eligibility_remaining - 1
                WHERE status = 'active' AND eligibility_remaining > 1 AND entry_year <= ?
                """,
                (int(true_sim_year),),
            )
            for player_id, program_id in exhausting:
                connection.execute(
                    """
                    UPDATE college_players
                    SET eligibility_remaining = 0, status = 'departed', departure_year = ?
                    WHERE player_id = ?
                    """,
                    (int(true_sim_year), player_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO college_departures(
                        player_id, program_id, true_sim_year, reason, game_player_index, created_at
                    ) VALUES(?, ?, ?, 'eligibility_exhausted', -1, ?)
                    """,
                    (player_id, program_id, int(true_sim_year), _utc_now_text()),
                )
            connection.execute(
                "UPDATE college_seasons SET eligibility_advanced = 1 WHERE true_sim_year = ?",
                (int(true_sim_year),),
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(player_id for player_id, _program_id in exhausting)

    def create_tournament(self, *, true_sim_year: int, bracket_program_ids: Iterable[str]) -> tuple[CollegeTournamentGame, ...]:
        program_ids = tuple(str(value) for value in bracket_program_ids)
        if len(program_ids) != COLLEGE_TOURNAMENT_FIELD_SIZE or len(set(program_ids)) != COLLEGE_TOURNAMENT_FIELD_SIZE:
            raise ValueError("college tournament requires 64 unique programs in exact bracket order")
        known_ids = {row.program_id for row in self.list_programs()}
        missing = tuple(program_id for program_id in program_ids if program_id not in known_ids)
        if missing:
            raise ValueError(f"unknown tournament programs: {missing}")
        connection = self._connect()
        try:
            connection.execute("DELETE FROM college_sweet16_projection WHERE true_sim_year = ?", (int(true_sim_year),))
            connection.execute("DELETE FROM college_tournament_games WHERE true_sim_year = ?", (int(true_sim_year),))
            connection.execute("DELETE FROM college_tournament_entries WHERE true_sim_year = ?", (int(true_sim_year),))
            connection.executemany(
                "INSERT INTO college_tournament_entries(true_sim_year, bracket_slot, program_id) VALUES(?, ?, ?)",
                ((int(true_sim_year), slot, program_id) for slot, program_id in enumerate(program_ids, start=1)),
            )
            connection.executemany(
                """
                INSERT INTO college_tournament_games(
                    true_sim_year, round_number, game_number, first_program_id, second_program_id, winner_program_id
                ) VALUES(?, 1, ?, ?, ?, NULL)
                """,
                (
                    (int(true_sim_year), game_number, program_ids[(game_number - 1) * 2], program_ids[(game_number - 1) * 2 + 1])
                    for game_number in range(1, 33)
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return self.list_tournament_games(true_sim_year, round_number=1)

    def list_tournament_games(self, true_sim_year: int, *, round_number: int | None = None) -> tuple[CollegeTournamentGame, ...]:
        where = "WHERE true_sim_year = ?"
        parameters: list[object] = [int(true_sim_year)]
        if round_number is not None:
            where += " AND round_number = ?"
            parameters.append(int(round_number))
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT true_sim_year, round_number, game_number, first_program_id,
                       second_program_id, winner_program_id
                FROM college_tournament_games
                {where}
                ORDER BY round_number, game_number
                """,
                parameters,
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegeTournamentGame(
                int(row[0]), int(row[1]), int(row[2]), str(row[3]), str(row[4]),
                str(row[5]) if row[5] is not None else None,
            )
            for row in rows
        )

    def record_tournament_winner(
        self,
        *,
        true_sim_year: int,
        round_number: int,
        game_number: int,
        winner_program_id: str,
    ) -> None:
        if int(round_number) not in {1, 2, 3, 4, 5, 6}:
            raise ValueError("college tournament round must be between 1 and 6")
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT first_program_id, second_program_id
                FROM college_tournament_games
                WHERE true_sim_year = ? AND round_number = ? AND game_number = ?
                """,
                (int(true_sim_year), int(round_number), int(game_number)),
            ).fetchone()
            if row is None:
                raise ValueError("tournament game does not exist")
            participants = {str(row[0]), str(row[1])}
            if str(winner_program_id) not in participants:
                raise ValueError("tournament winner must be one of the game's two programs")
            connection.execute(
                """
                UPDATE college_tournament_games
                SET winner_program_id = ?
                WHERE true_sim_year = ? AND round_number = ? AND game_number = ?
                """,
                (str(winner_program_id), int(true_sim_year), int(round_number), int(game_number)),
            )
            connection.commit()
        finally:
            connection.close()
        self._create_next_round_if_ready(true_sim_year, int(round_number))

    def _create_next_round_if_ready(self, true_sim_year: int, completed_round: int) -> None:
        games_per_round = {1: 32, 2: 16, 3: 8, 4: 4, 5: 2, 6: 1}
        if completed_round >= 6:
            return
        games = self.list_tournament_games(true_sim_year, round_number=completed_round)
        expected_games = games_per_round[completed_round]
        if len(games) != expected_games or any(game.winner_program_id is None for game in games):
            return
        next_round = completed_round + 1
        next_game_count = games_per_round[next_round]
        connection = self._connect()
        try:
            existing = int(
                connection.execute(
                    "SELECT COUNT(*) FROM college_tournament_games WHERE true_sim_year = ? AND round_number = ?",
                    (int(true_sim_year), next_round),
                ).fetchone()[0]
            )
            if existing:
                return
            winners = tuple(str(game.winner_program_id) for game in games)
            connection.executemany(
                """
                INSERT INTO college_tournament_games(
                    true_sim_year, round_number, game_number, first_program_id, second_program_id, winner_program_id
                ) VALUES(?, ?, ?, ?, ?, NULL)
                """,
                (
                    (
                        int(true_sim_year),
                        next_round,
                        game_number,
                        winners[(game_number - 1) * 2],
                        winners[(game_number - 1) * 2 + 1],
                    )
                    for game_number in range(1, next_game_count + 1)
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def sweet16_program_ids(self, true_sim_year: int) -> tuple[str, ...]:
        games = self.list_tournament_games(true_sim_year, round_number=2)
        if len(games) != COLLEGE_SWEET16_SIZE or any(game.winner_program_id is None for game in games):
            return ()
        return tuple(str(game.winner_program_id) for game in games)

    def champion_program_id(self, true_sim_year: int) -> str | None:
        games = self.list_tournament_games(true_sim_year, round_number=6)
        if len(games) != 1:
            return None
        return games[0].winner_program_id

    def plan_sweet16_projection(
        self,
        *,
        true_sim_year: int,
        playoff_team_indexes: Iterable[int],
    ) -> tuple[CollegeTeamProjection, ...]:
        sweet16 = self.sweet16_program_ids(true_sim_year)
        if len(sweet16) != COLLEGE_SWEET16_SIZE:
            raise ValueError("record winners for both external tournament rounds before mapping the Sweet 16")
        team_indexes = tuple(int(value) for value in playoff_team_indexes)
        if len(team_indexes) != COLLEGE_SWEET16_SIZE or len(set(team_indexes)) != COLLEGE_SWEET16_SIZE:
            raise ValueError("Sweet 16 projection requires 16 unique in-game playoff team indexes")
        if any(index < 0 or index >= COLLEGE_GAME_TEAM_COUNT for index in team_indexes):
            raise ValueError("playoff team indexes must be between 0 and 29")
        connection = self._connect()
        try:
            connection.execute("DELETE FROM college_player_projection WHERE true_sim_year = ? AND stage = 'sweet16'", (int(true_sim_year),))
            connection.execute("DELETE FROM college_sweet16_projection WHERE true_sim_year = ?", (int(true_sim_year),))
            connection.executemany(
                """
                INSERT INTO college_sweet16_projection(true_sim_year, bracket_order, game_team_index, program_id)
                VALUES(?, ?, ?, ?)
                """,
                (
                    (int(true_sim_year), order, team_index, program_id)
                    for order, (team_index, program_id) in enumerate(zip(team_indexes, sweet16, strict=True), start=1)
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return self.list_sweet16_projection(true_sim_year)

    def list_sweet16_projection(self, true_sim_year: int) -> tuple[CollegeTeamProjection, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT mapping.game_team_index, mapping.program_id, programs.name
                FROM college_sweet16_projection AS mapping
                JOIN college_programs AS programs ON programs.program_id = mapping.program_id
                WHERE mapping.true_sim_year = ?
                ORDER BY mapping.bracket_order
                """,
                (int(true_sim_year),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollegeTeamProjection(int(true_sim_year), int(row[0]), str(row[1]), str(row[2]), "sweet16")
            for row in rows
        )


__all__ = [
    "COLLEGE_CONFERENCE_COUNT",
    "COLLEGE_GAME_TEAM_COUNT",
    "COLLEGE_PROGRAM_COUNT",
    "COLLEGE_ROSTER_SIZE",
    "COLLEGE_SEASON_PLAYER_SLOT_COUNT",
    "COLLEGE_SWEET16_SIZE",
    "COLLEGE_TOURNAMENT_FIELD_SIZE",
    "COLLEGE_TEAM_IDENTITY_FIELDS",
    "COLLEGE_PLAYER_PROJECTION_CONTROLLED_FIELDS",
    "PROJECTION_STAGE_SEASON",
    "PROJECTION_STAGE_SWEET16",
    "CollegeDynastyRepository",
    "college_catalog_from_payload",
    "college_player_updates_from_payload",
    "load_college_catalog",
    "load_college_player_updates",
]
