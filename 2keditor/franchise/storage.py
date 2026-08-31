from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from nba2k_editor.franchise.models import (
    FantasyDraftState,
    FantasyDraftStoredPick,
    FranchiseRecord,
    FranchiseSetup,
    FranchiseSimState,
    FranchiseTeamOption,
    LEAGUE_MODE_COLLEGE,
    LEAGUE_MODE_NBA,
    ManualDraftPick,
    normalize_league_mode,
)
from nba2k_editor.franchise.sim_phases import (
    STATUS_READY,
    STATUS_WAITING_FOR_GAME_ADVANCE,
    game_advance_instruction,
    franchise_phase_sequence,
    initial_phase,
    next_franchise_phase,
    phase_label,
)

DEFAULT_FRANCHISE_DB_PATH = Path("outputs") / "franchise" / "franchise.sqlite"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def franchise_sql_exists(db_path: str | Path = DEFAULT_FRANCHISE_DB_PATH) -> bool:
    return Path(db_path).is_file()


def base_team_options() -> tuple[FranchiseTeamOption, ...]:
    return tuple(FranchiseTeamOption(index, f"Team {index}", f"[{index}] Team {index}") for index in range(30))


def team_options_from_model(model: Any) -> tuple[FranchiseTeamOption, ...]:
    loaded = getattr(model, "loaded_items", {}).get("Teams", {}) if hasattr(model, "loaded_items") else {}
    options: list[FranchiseTeamOption] = []
    for item in loaded.values():
        index = int(getattr(item, "index"))
        if 0 <= index <= 29:
            label = str(getattr(item, "label", f"Team {index}") or f"Team {index}")
            display_label = str(getattr(item, "display_label", f"[{index}] {label}"))
            options.append(FranchiseTeamOption(index, label, display_label))
    if not options:
        return base_team_options()
    return tuple(sorted(options, key=lambda option: option.team_index))


class FranchiseRepository:
    def __init__(self, db_path: str | Path = DEFAULT_FRANCHISE_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def exists(self) -> bool:
        return franchise_sql_exists(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS franchise_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS franchise_teams (
                team_index INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                display_label TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS league_saves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                target_executable TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS franchise_sim_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                sim_year INTEGER NOT NULL,
                current_phase TEXT NOT NULL,
                status TEXT NOT NULL,
                expansion_draft_required INTEGER NOT NULL,
                expected_next_phase TEXT NOT NULL,
                expected_next_year INTEGER NOT NULL,
                required_user_action TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fantasy_draft_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_pick_number INTEGER NOT NULL,
                team_count INTEGER NOT NULL,
                user_team_index INTEGER NOT NULL,
                team_order_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fantasy_draft_picks (
                pick_number INTEGER PRIMARY KEY,
                round_number INTEGER NOT NULL,
                team_index INTEGER NOT NULL,
                team_label TEXT NOT NULL,
                player_index INTEGER NOT NULL,
                player_label TEXT NOT NULL,
                source_team_index INTEGER NOT NULL,
                source_slot INTEGER NOT NULL,
                source_slot_field TEXT NOT NULL,
                picked_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS manual_draft_picks (
                draft_year INTEGER NOT NULL,
                round_number INTEGER NOT NULL CHECK (round_number IN (1, 2)),
                original_team_index INTEGER NOT NULL REFERENCES franchise_teams(team_index),
                current_team_index INTEGER NOT NULL REFERENCES franchise_teams(team_index),
                PRIMARY KEY(draft_year, round_number, original_team_index)
            );
            CREATE TABLE IF NOT EXISTS college_conferences (
                conference_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS college_programs (
                program_id TEXT PRIMARY KEY,
                conference_id TEXT NOT NULL REFERENCES college_conferences(conference_id),
                name TEXT NOT NULL UNIQUE,
                short_name TEXT NOT NULL,
                team_fields_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS college_players (
                player_id TEXT PRIMARY KEY,
                program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                display_name TEXT NOT NULL,
                roster_order INTEGER NOT NULL,
                eligibility_remaining INTEGER NOT NULL CHECK (eligibility_remaining BETWEEN 0 AND 4),
                status TEXT NOT NULL CHECK (status IN ('active', 'departed')),
                player_fields_json TEXT NOT NULL,
                entry_year INTEGER NOT NULL,
                departure_year INTEGER
            );
            CREATE TABLE IF NOT EXISTS college_seasons (
                true_sim_year INTEGER PRIMARY KEY,
                user_program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                random_seed INTEGER NOT NULL,
                eligibility_advanced INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS college_team_projection (
                true_sim_year INTEGER NOT NULL REFERENCES college_seasons(true_sim_year) ON DELETE CASCADE,
                game_team_index INTEGER NOT NULL CHECK (game_team_index BETWEEN 0 AND 29),
                program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                selection_reason TEXT NOT NULL CHECK (selection_reason IN ('user', 'conference', 'nonconference')),
                PRIMARY KEY(true_sim_year, game_team_index),
                UNIQUE(true_sim_year, program_id)
            );
            CREATE TABLE IF NOT EXISTS college_player_projection (
                true_sim_year INTEGER NOT NULL,
                stage TEXT NOT NULL CHECK (stage IN ('season', 'sweet16')),
                game_team_index INTEGER NOT NULL CHECK (game_team_index BETWEEN 0 AND 29),
                roster_slot INTEGER NOT NULL CHECK (roster_slot BETWEEN 1 AND 15),
                slot_field TEXT NOT NULL,
                game_player_index INTEGER NOT NULL,
                canonical_player_id TEXT REFERENCES college_players(player_id),
                PRIMARY KEY(true_sim_year, stage, game_team_index, roster_slot),
                UNIQUE(true_sim_year, stage, game_player_index)
            );
            CREATE TABLE IF NOT EXISTS college_departures (
                player_id TEXT PRIMARY KEY REFERENCES college_players(player_id),
                program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                true_sim_year INTEGER NOT NULL,
                reason TEXT NOT NULL,
                game_player_index INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS college_tournament_entries (
                true_sim_year INTEGER NOT NULL,
                bracket_slot INTEGER NOT NULL CHECK (bracket_slot BETWEEN 1 AND 64),
                program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                PRIMARY KEY(true_sim_year, bracket_slot),
                UNIQUE(true_sim_year, program_id)
            );
            CREATE TABLE IF NOT EXISTS college_tournament_games (
                true_sim_year INTEGER NOT NULL,
                round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 6),
                game_number INTEGER NOT NULL,
                first_program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                second_program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                winner_program_id TEXT REFERENCES college_programs(program_id),
                PRIMARY KEY(true_sim_year, round_number, game_number)
            );
            CREATE TABLE IF NOT EXISTS college_sweet16_projection (
                true_sim_year INTEGER NOT NULL,
                bracket_order INTEGER NOT NULL CHECK (bracket_order BETWEEN 1 AND 16),
                game_team_index INTEGER NOT NULL CHECK (game_team_index BETWEEN 0 AND 29),
                program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                PRIMARY KEY(true_sim_year, bracket_order),
                UNIQUE(true_sim_year, game_team_index),
                UNIQUE(true_sim_year, program_id)
            );
            """
        )
        college_players_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'college_players'"
        ).fetchone()
        college_games_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'college_tournament_games'"
        ).fetchone()
        rebuild_college_players = bool(
            college_players_sql_row and "UNIQUE(program_id, roster_order)" in str(college_players_sql_row[0])
        )
        rebuild_college_games = bool(
            college_games_sql_row and "round_number IN (1, 2)" in str(college_games_sql_row[0])
        )
        if rebuild_college_players or rebuild_college_games:
            connection.commit()
            connection.execute("PRAGMA foreign_keys = OFF")
            if rebuild_college_players:
                connection.executescript(
                    """
                    CREATE TABLE college_players_new (
                        player_id TEXT PRIMARY KEY,
                        program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                        display_name TEXT NOT NULL,
                        roster_order INTEGER NOT NULL,
                        eligibility_remaining INTEGER NOT NULL CHECK (eligibility_remaining BETWEEN 0 AND 4),
                        status TEXT NOT NULL CHECK (status IN ('active', 'departed')),
                        player_fields_json TEXT NOT NULL,
                        entry_year INTEGER NOT NULL,
                        departure_year INTEGER
                    );
                    INSERT INTO college_players_new(
                        player_id, program_id, display_name, roster_order, eligibility_remaining,
                        status, player_fields_json, entry_year, departure_year
                    )
                    SELECT player_id, program_id, display_name, roster_order, eligibility_remaining,
                           status, player_fields_json, entry_year, departure_year
                    FROM college_players;
                    DROP TABLE college_players;
                    ALTER TABLE college_players_new RENAME TO college_players;
                    """
                )
            if rebuild_college_games:
                connection.executescript(
                    """
                    CREATE TABLE college_tournament_games_new (
                        true_sim_year INTEGER NOT NULL,
                        round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 6),
                        game_number INTEGER NOT NULL,
                        first_program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                        second_program_id TEXT NOT NULL REFERENCES college_programs(program_id),
                        winner_program_id TEXT REFERENCES college_programs(program_id),
                        PRIMARY KEY(true_sim_year, round_number, game_number)
                    );
                    INSERT INTO college_tournament_games_new(
                        true_sim_year, round_number, game_number, first_program_id,
                        second_program_id, winner_program_id
                    )
                    SELECT true_sim_year, round_number, game_number, first_program_id,
                           second_program_id, winner_program_id
                    FROM college_tournament_games;
                    DROP TABLE college_tournament_games;
                    ALTER TABLE college_tournament_games_new RENAME TO college_tournament_games;
                    """
                )
            connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_college_players_active_roster
            ON college_players(program_id, roster_order)
            WHERE status = 'active'
            """
        )
        fantasy_draft_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(fantasy_draft_state)")
        }
        if "team_order_json" not in fantasy_draft_columns:
            connection.execute(
                "ALTER TABLE fantasy_draft_state ADD COLUMN team_order_json TEXT NOT NULL DEFAULT '[]'"
            )
            existing_state = connection.execute(
                "SELECT team_count FROM fantasy_draft_state WHERE id = 1"
            ).fetchone()
            if existing_state is not None:
                team_count = int(existing_state[0])
                team_order = tuple(
                    int(row[0])
                    for row in connection.execute(
                        "SELECT team_index FROM franchise_teams ORDER BY team_index"
                    )
                )
                if len(team_order) != team_count:
                    raise ValueError(
                        "existing fantasy draft team count does not match its saved franchise teams"
                    )
                connection.execute(
                    "UPDATE fantasy_draft_state SET team_order_json = ? WHERE id = 1",
                    (json.dumps(team_order),),
                )
        college_season_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(college_seasons)")
        }
        if "eligibility_advanced" not in college_season_columns:
            connection.execute(
                "ALTER TABLE college_seasons ADD COLUMN eligibility_advanced INTEGER NOT NULL DEFAULT 0"
            )

    def replace_franchise(
        self,
        setup: FranchiseSetup,
        team_options: Iterable[FranchiseTeamOption],
        *,
        league_snapshot: dict[str, Any] | None = None,
        target_executable: str = "",
    ) -> FranchiseRecord:
        league_mode = normalize_league_mode(setup.league_mode)
        if league_mode == LEAGUE_MODE_COLLEGE and setup.fantasy_draft:
            raise ValueError("College mode does not use the NBA fantasy draft workflow.")
        active_teams = tuple(sorted(team_options, key=lambda option: int(option.team_index)))
        active_indexes = {int(option.team_index) for option in active_teams}
        if int(setup.user_team_index) not in active_indexes:
            raise ValueError("franchise teams do not include the user-controlled team")
        franchise_id = uuid4().hex
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
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
            connection.execute("DELETE FROM franchise_meta")
            connection.execute("DELETE FROM manual_draft_picks")
            connection.execute("DELETE FROM franchise_teams")
            connection.execute("DELETE FROM league_saves")
            connection.execute("DELETE FROM franchise_sim_state")
            connection.execute("DELETE FROM fantasy_draft_state")
            connection.execute("DELETE FROM fantasy_draft_picks")
            meta = {
                "franchise_id": franchise_id,
                "start_year": str(int(setup.start_year)),
                "user_team_index": str(int(setup.user_team_index)),
                "keep_full_league_save": "1" if setup.keep_full_league_save else "0",
                "fantasy_draft": "1" if setup.fantasy_draft else "0",
                "league_mode": league_mode,
                "created_at": now,
                "updated_at": now,
            }
            connection.executemany("INSERT INTO franchise_meta(key, value) VALUES(?, ?)", meta.items())
            connection.execute(
                """
                INSERT INTO franchise_sim_state(
                    id, sim_year, current_phase, status, expansion_draft_required,
                    expected_next_phase, expected_next_year, required_user_action, updated_at
                ) VALUES(1, ?, ?, ?, 0, '', ?, '', ?)
                """,
                (int(setup.start_year), initial_phase(league_mode), STATUS_READY, int(setup.start_year), now),
            )
            connection.executemany(
                "INSERT INTO franchise_teams(team_index, label, display_label) VALUES(?, ?, ?)",
                ((team.team_index, team.label, team.display_label) for team in active_teams),
            )
            if league_mode == LEAGUE_MODE_NBA:
                connection.executemany(
                    """
                    INSERT INTO manual_draft_picks(
                        draft_year, round_number, original_team_index, current_team_index
                    ) VALUES(?, ?, ?, ?)
                    """,
                    (
                        (draft_year, round_number, int(team.team_index), int(team.team_index))
                        for draft_year in range(int(setup.start_year) + 1, int(setup.start_year) + 6)
                        for round_number in (1, 2)
                        for team in active_teams
                    ),
                )

            if league_snapshot is not None:
                connection.execute(
                    "INSERT INTO league_saves(created_at, target_executable, payload_json) VALUES(?, ?, ?)",
                    (now, str(target_executable or league_snapshot.get("target_executable") or ""), json.dumps(league_snapshot, sort_keys=True)),
                )
            connection.commit()
        finally:
            connection.close()
        return self.load()

    def save_full_league_snapshot(self, snapshot: dict[str, Any], *, target_executable: str = "") -> None:
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                "INSERT INTO league_saves(created_at, target_executable, payload_json) VALUES(?, ?, ?)",
                (now, str(target_executable or snapshot.get("target_executable") or ""), json.dumps(snapshot, sort_keys=True)),
            )
            connection.execute(
                "INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)",
                ("updated_at", now),
            )
            connection.commit()
        finally:
            connection.close()

    def ensure_manual_draft_picks(
        self,
        *,
        start_year: int,
        team_options: Iterable[FranchiseTeamOption],
    ) -> tuple[ManualDraftPick, ...]:
        teams = tuple(sorted(team_options, key=lambda team: int(team.team_index)))
        if not teams:
            raise ValueError("manual draft-pick tracking requires franchise teams")
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.executemany(
                """
                INSERT OR IGNORE INTO manual_draft_picks(
                    draft_year, round_number, original_team_index, current_team_index
                ) VALUES(?, ?, ?, ?)
                """,
                (
                    (draft_year, round_number, int(team.team_index), int(team.team_index))
                    for draft_year in range(int(start_year) + 1, int(start_year) + 6)
                    for round_number in (1, 2)
                    for team in teams
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return self.list_manual_draft_picks()

    def list_manual_draft_picks(self) -> tuple[ManualDraftPick, ...]:
        connection = self._connect()
        try:
            self.initialize(connection)
            rows = connection.execute(
                """
                SELECT draft_year, round_number, original_team_index, current_team_index
                FROM manual_draft_picks
                ORDER BY draft_year, round_number, original_team_index
                """
            ).fetchall()
            connection.commit()
        finally:
            connection.close()
        return tuple(
            ManualDraftPick(
                draft_year=int(row[0]),
                round_number=int(row[1]),
                original_team_index=int(row[2]),
                current_team_index=int(row[3]),
            )
            for row in rows
        )

    def update_manual_draft_pick_owner(
        self,
        *,
        draft_year: int,
        round_number: int,
        original_team_index: int,
        current_team_index: int,
    ) -> ManualDraftPick:
        if int(round_number) not in (1, 2):
            raise ValueError("manual draft-pick round must be 1 or 2")
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            owner_exists = connection.execute(
                "SELECT 1 FROM franchise_teams WHERE team_index = ?",
                (int(current_team_index),),
            ).fetchone()
            if owner_exists is None:
                raise ValueError(f"current draft-pick owner is not a franchise team: {int(current_team_index)}")
            cursor = connection.execute(
                """
                UPDATE manual_draft_picks
                SET current_team_index = ?
                WHERE draft_year = ? AND round_number = ? AND original_team_index = ?
                """,
                (
                    int(current_team_index),
                    int(draft_year),
                    int(round_number),
                    int(original_team_index),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"manual draft pick not found: {int(draft_year)} round {int(round_number)} "
                    f"original team {int(original_team_index)}"
                )
            connection.execute(
                "INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)",
                ("updated_at", now),
            )
            connection.commit()
        finally:
            connection.close()
        return ManualDraftPick(
            draft_year=int(draft_year),
            round_number=int(round_number),
            original_team_index=int(original_team_index),
            current_team_index=int(current_team_index),
        )

    def load(self) -> FranchiseRecord:
        connection = self._connect()
        try:
            self.initialize(connection)
            meta = {key: value for key, value in connection.execute("SELECT key, value FROM franchise_meta")}
            teams = tuple(
                FranchiseTeamOption(int(index), str(label), str(display_label))
                for index, label, display_label in connection.execute(
                    "SELECT team_index, label, display_label FROM franchise_teams ORDER BY team_index"
                )
            )
            save_count = int(connection.execute("SELECT COUNT(*) FROM league_saves").fetchone()[0])
            connection.commit()
        finally:
            connection.close()
        setup = FranchiseSetup(
            start_year=int(meta.get("start_year", "2025")),
            keep_full_league_save=meta.get("keep_full_league_save", "0") == "1",
            fantasy_draft=meta.get("fantasy_draft", "0") == "1",
            user_team_index=int(meta.get("user_team_index", "0")),
            league_mode=normalize_league_mode(meta.get("league_mode", LEAGUE_MODE_NBA)),
        )
        return FranchiseRecord(
            setup=setup,
            team_options=teams,
            database_path=str(self.db_path),
            full_league_save_count=save_count,
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
            franchise_id=meta.get("franchise_id", ""),
        )

    def load_sim_state(self) -> FranchiseSimState | None:
        connection = self._connect()
        try:
            self.initialize(connection)
            row = connection.execute(
                """
                SELECT sim_year, current_phase, status, expansion_draft_required,
                       expected_next_phase, expected_next_year, required_user_action, updated_at
                FROM franchise_sim_state
                WHERE id = 1
                """
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            return None
        return FranchiseSimState(
            sim_year=int(row[0]),
            current_phase=str(row[1]),
            status=str(row[2]),
            expansion_draft_required=bool(int(row[3])),
            expected_next_phase=str(row[4]),
            expected_next_year=int(row[5]),
            required_user_action=str(row[6]),
            updated_at=str(row[7]),
        )

    def ensure_sim_state(self) -> FranchiseSimState:
        state = self.load_sim_state()
        if state is not None:
            return state
        setup = self.load().setup
        return self.sync_sim_state(sim_year=setup.start_year, current_phase=initial_phase(setup.league_mode))

    def sync_sim_state(self, *, sim_year: int, current_phase: str) -> FranchiseSimState:
        league_mode = self.load().setup.league_mode
        phase_label(current_phase, league_mode=league_mode)
        existing_state = self.load_sim_state()
        expansion_draft_required = bool(existing_state and existing_state.expansion_draft_required)
        active_phase_keys = {
            phase.key
            for phase in franchise_phase_sequence(
                expansion_draft_required=expansion_draft_required,
                league_mode=league_mode,
            )
        }
        if str(current_phase) not in active_phase_keys:
            raise ValueError("Expansion Draft is only active when an expansion team was added.")
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO franchise_sim_state(
                    id, sim_year, current_phase, status, expansion_draft_required,
                    expected_next_phase, expected_next_year, required_user_action, updated_at
                ) VALUES(1, ?, ?, ?, ?, '', ?, '', ?)
                """,
                (
                    int(sim_year),
                    str(current_phase),
                    STATUS_READY,
                    1 if expansion_draft_required else 0,
                    int(sim_year),
                    now,
                ),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        state = self.load_sim_state()
        if state is None:
            raise RuntimeError("franchise simulation state was not saved")
        return state

    def set_expansion_draft_required(self, required: bool) -> FranchiseSimState:
        if self.load().setup.league_mode == LEAGUE_MODE_COLLEGE and required:
            raise ValueError("College mode does not use the NBA Expansion Draft phase.")
        state = self.ensure_sim_state()
        if state.current_phase == "expansion_draft" and not required:
            raise ValueError("Expansion Draft cannot be disabled while it is the current game phase.")
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                "UPDATE franchise_sim_state SET expansion_draft_required = ?, updated_at = ? WHERE id = 1",
                (1 if required else 0, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        state = self.load_sim_state()
        if state is None:
            raise RuntimeError("franchise simulation state was not saved")
        return state

    def pause_for_game_advance(self) -> FranchiseSimState:
        league_mode = self.load().setup.league_mode
        state = self.ensure_sim_state()
        if state.status != STATUS_READY:
            raise ValueError("franchise simulation is already paused")
        next_phase, year_increment = next_franchise_phase(
            state.current_phase,
            expansion_draft_required=state.expansion_draft_required,
            league_mode=league_mode,
        )
        next_year = state.sim_year + year_increment
        required_action = game_advance_instruction(
            next_phase,
            next_sim_year=next_year,
            league_mode=league_mode,
        )
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                UPDATE franchise_sim_state
                SET status = ?, expected_next_phase = ?, expected_next_year = ?,
                    required_user_action = ?, updated_at = ?
                WHERE id = 1
                """,
                (STATUS_WAITING_FOR_GAME_ADVANCE, next_phase, next_year, required_action, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        paused = self.load_sim_state()
        if paused is None:
            raise RuntimeError("franchise simulation pause was not saved")
        return paused

    def sync_and_resume(self, *, observed_phase: str, observed_sim_year: int) -> FranchiseSimState:
        league_mode = self.load().setup.league_mode
        phase_label(observed_phase, league_mode=league_mode)
        state = self.ensure_sim_state()
        if state.status != STATUS_WAITING_FOR_GAME_ADVANCE:
            raise ValueError("franchise simulation is not waiting for game progression")
        if str(observed_phase) != state.expected_next_phase or int(observed_sim_year) != state.expected_next_year:
            raise ValueError(
                f"expected {phase_label(state.expected_next_phase, league_mode=league_mode)} for true sim year {state.expected_next_year}"
            )
        now = _utc_now_text()
        expansion_required = False if str(observed_phase) == initial_phase(league_mode) else state.expansion_draft_required
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                UPDATE franchise_sim_state
                SET sim_year = ?, current_phase = ?, status = ?, expansion_draft_required = ?,
                    expected_next_phase = '', expected_next_year = ?, required_user_action = '', updated_at = ?
                WHERE id = 1
                """,
                (
                    int(observed_sim_year),
                    str(observed_phase),
                    STATUS_READY,
                    1 if expansion_required else 0,
                    int(observed_sim_year),
                    now,
                ),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        resumed = self.load_sim_state()
        if resumed is None:
            raise RuntimeError("franchise simulation resume was not saved")
        return resumed


    def start_fantasy_draft(
        self,
        *,
        team_order: Iterable[int],
        user_team_index: int,
    ) -> FantasyDraftState:
        order = tuple(int(index) for index in team_order)
        if not order:
            raise ValueError("fantasy draft order must include at least one team")
        if len(set(order)) != len(order):
            raise ValueError("fantasy draft order cannot contain duplicate teams")
        if int(user_team_index) not in set(order):
            raise ValueError("fantasy draft order must include the user-controlled team")
        if any(index < 0 or index > 29 for index in order):
            raise ValueError("fantasy draft order contains a team index outside 0 through 29")
        connection = self._connect()
        try:
            self.initialize(connection)
            active_team_indexes = tuple(
                int(row[0])
                for row in connection.execute(
                    "SELECT team_index FROM franchise_teams ORDER BY team_index"
                )
            )
        finally:
            connection.close()
        if active_team_indexes and set(order) != set(active_team_indexes):
            raise ValueError("fantasy draft order must contain every active franchise team exactly once")
        team_count = len(order)
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute("DELETE FROM fantasy_draft_picks")
            connection.execute("DELETE FROM fantasy_draft_state")
            connection.execute(
                """
                INSERT INTO fantasy_draft_state(
                    id, current_pick_number, team_count, user_team_index,
                    team_order_json, started_at, updated_at
                )
                VALUES(1, 1, ?, ?, ?, ?, ?)
                """,
                (team_count, int(user_team_index), json.dumps(order), now, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        return FantasyDraftState(
            current_pick_number=1,
            team_count=team_count,
            user_team_index=int(user_team_index),
            team_order=order,
            started_at=now,
            updated_at=now,
        )

    def load_fantasy_draft_state(self) -> FantasyDraftState | None:
        connection = self._connect()
        try:
            self.initialize(connection)
            row = connection.execute(
                """
                SELECT current_pick_number, team_count, user_team_index,
                       team_order_json, started_at, updated_at
                FROM fantasy_draft_state
                WHERE id = 1
                """
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            return None
        team_order_value = json.loads(str(row[3]))
        if not isinstance(team_order_value, list):
            raise ValueError("saved fantasy draft order is not a JSON array")
        team_order = tuple(int(index) for index in team_order_value)
        if len(team_order) != int(row[1]) or len(set(team_order)) != len(team_order):
            raise ValueError("saved fantasy draft order is incomplete or contains duplicate teams")
        if int(row[2]) not in set(team_order):
            raise ValueError("saved fantasy draft order does not include the user-controlled team")
        return FantasyDraftState(
            current_pick_number=int(row[0]),
            team_count=int(row[1]),
            user_team_index=int(row[2]),
            team_order=team_order,
            started_at=str(row[4]),
            updated_at=str(row[5]),
        )

    def list_fantasy_draft_picks(self) -> tuple[FantasyDraftStoredPick, ...]:
        connection = self._connect()
        try:
            self.initialize(connection)
            rows = connection.execute(
                """
                SELECT pick_number, round_number, team_index, team_label, player_index, player_label,
                       source_team_index, source_slot, source_slot_field, picked_by, created_at
                FROM fantasy_draft_picks
                ORDER BY pick_number
                """
            ).fetchall()
            connection.commit()
        finally:
            connection.close()
        return tuple(
            FantasyDraftStoredPick(
                pick_number=int(row[0]),
                round_number=int(row[1]),
                team_index=int(row[2]),
                team_label=str(row[3]),
                player_index=int(row[4]),
                player_label=str(row[5]),
                source_team_index=int(row[6]),
                source_slot=int(row[7]),
                source_slot_field=str(row[8]),
                picked_by=str(row[9]),
                created_at=str(row[10]),
            )
            for row in rows
        )

    def record_fantasy_draft_pick(self, pick: FantasyDraftStoredPick) -> FantasyDraftStoredPick:
        now = pick.created_at or _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO fantasy_draft_picks(
                    pick_number, round_number, team_index, team_label, player_index, player_label,
                    source_team_index, source_slot, source_slot_field, picked_by, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(pick.pick_number),
                    int(pick.round_number),
                    int(pick.team_index),
                    str(pick.team_label),
                    int(pick.player_index),
                    str(pick.player_label),
                    int(pick.source_team_index),
                    int(pick.source_slot),
                    str(pick.source_slot_field),
                    str(pick.picked_by),
                    now,
                ),
            )
            connection.execute(
                "UPDATE fantasy_draft_state SET current_pick_number = MAX(current_pick_number, ?), updated_at = ? WHERE id = 1",
                (int(pick.pick_number) + 1, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        return FantasyDraftStoredPick(
            pick_number=pick.pick_number,
            round_number=pick.round_number,
            team_index=pick.team_index,
            team_label=pick.team_label,
            player_index=pick.player_index,
            player_label=pick.player_label,
            source_team_index=pick.source_team_index,
            source_slot=pick.source_slot,
            source_slot_field=pick.source_slot_field,
            picked_by=pick.picked_by,
            created_at=now,
        )
