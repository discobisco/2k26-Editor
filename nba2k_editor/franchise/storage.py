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
    TeamRecommendation,
)
from nba2k_editor.franchise.sim_phases import (
    STATUS_READY,
    STATUS_WAITING_FOR_GAME_ADVANCE,
    STATUS_WAITING_FOR_USER_TRADE,
    game_advance_instruction,
    franchise_phase_sequence,
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
            CREATE TABLE IF NOT EXISTS llm_gm_teams (
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
                raw_llm_response TEXT NOT NULL,
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS team_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_index INTEGER NOT NULL,
                team_label TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                owner_approval_required INTEGER NOT NULL,
                trade_with_user_team INTEGER NOT NULL DEFAULT 0,
                blocked_reason TEXT NOT NULL,
                raw_llm_response TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        recommendation_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(team_recommendations)")
        }
        if "trade_with_user_team" not in recommendation_columns:
            connection.execute(
                "ALTER TABLE team_recommendations ADD COLUMN trade_with_user_team INTEGER NOT NULL DEFAULT 0"
            )

    def replace_franchise(
        self,
        setup: FranchiseSetup,
        team_options: Iterable[FranchiseTeamOption],
        *,
        league_snapshot: dict[str, Any] | None = None,
        target_executable: str = "",
    ) -> FranchiseRecord:
        options_by_index = {int(option.team_index): option for option in team_options}
        llm_indexes = {int(index) for index in setup.llm_gm_team_indexes}
        llm_indexes.discard(int(setup.user_team_index))
        active_indexes = {*llm_indexes, int(setup.user_team_index)}
        missing_indexes = tuple(sorted(active_indexes.difference(options_by_index)))
        if missing_indexes:
            raise ValueError(f"franchise team indexes are not loaded: {missing_indexes}")
        active_teams = tuple(options_by_index[index] for index in sorted(active_indexes))
        llm_teams = tuple(options_by_index[index] for index in sorted(llm_indexes))
        franchise_id = uuid4().hex
        profile_directory = str((self.db_path.parent / "team_profiles" / franchise_id).resolve())
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute("DELETE FROM franchise_meta")
            connection.execute("DELETE FROM franchise_teams")
            connection.execute("DELETE FROM llm_gm_teams")
            connection.execute("DELETE FROM league_saves")
            connection.execute("DELETE FROM franchise_sim_state")
            connection.execute("DELETE FROM fantasy_draft_state")
            connection.execute("DELETE FROM fantasy_draft_picks")
            connection.execute("DELETE FROM team_recommendations")
            meta = {
                "franchise_id": franchise_id,
                "profile_directory": profile_directory,
                "start_year": str(int(setup.start_year)),
                "user_team_index": str(int(setup.user_team_index)),
                "keep_full_league_save": "1" if setup.keep_full_league_save else "0",
                "fantasy_draft": "1" if setup.fantasy_draft else "0",
                "created_at": now,
                "updated_at": now,
            }
            connection.executemany("INSERT INTO franchise_meta(key, value) VALUES(?, ?)", meta.items())
            connection.execute(
                """
                INSERT INTO franchise_sim_state(
                    id, sim_year, current_phase, status, expansion_draft_required,
                    expected_next_phase, expected_next_year, required_user_action, updated_at
                ) VALUES(1, ?, 'season', ?, 0, '', ?, '', ?)
                """,
                (int(setup.start_year), STATUS_READY, int(setup.start_year), now),
            )
            connection.executemany(
                "INSERT INTO franchise_teams(team_index, label, display_label) VALUES(?, ?, ?)",
                ((team.team_index, team.label, team.display_label) for team in active_teams),
            )
            connection.executemany(
                "INSERT INTO llm_gm_teams(team_index, label, display_label) VALUES(?, ?, ?)",
                ((team.team_index, team.label, team.display_label) for team in llm_teams),
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
            llm_gm_team_indexes = tuple(
                int(row[0])
                for row in connection.execute("SELECT team_index FROM llm_gm_teams ORDER BY team_index")
            )
            save_count = int(connection.execute("SELECT COUNT(*) FROM league_saves").fetchone()[0])
            connection.commit()
        finally:
            connection.close()
        setup = FranchiseSetup(
            start_year=int(meta.get("start_year", "2025")),
            keep_full_league_save=meta.get("keep_full_league_save", "0") == "1",
            llm_gm_team_indexes=llm_gm_team_indexes,
            fantasy_draft=meta.get("fantasy_draft", "0") == "1",
            user_team_index=int(meta.get("user_team_index", "0")),
        )
        return FranchiseRecord(
            setup=setup,
            team_options=teams,
            database_path=str(self.db_path),
            full_league_save_count=save_count,
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
            franchise_id=meta.get("franchise_id", ""),
            profile_directory=meta.get("profile_directory", ""),
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
        start_year = self.load().setup.start_year
        return self.sync_sim_state(sim_year=start_year, current_phase="season")

    def sync_sim_state(self, *, sim_year: int, current_phase: str) -> FranchiseSimState:
        phase_label(current_phase)
        existing_state = self.load_sim_state()
        expansion_draft_required = bool(existing_state and existing_state.expansion_draft_required)
        active_phase_keys = {
            phase.key
            for phase in franchise_phase_sequence(expansion_draft_required=expansion_draft_required)
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
        state = self.ensure_sim_state()
        if state.status != STATUS_READY:
            raise ValueError("franchise simulation is already paused")
        next_phase, year_increment = next_franchise_phase(
            state.current_phase,
            expansion_draft_required=state.expansion_draft_required,
        )
        next_year = state.sim_year + year_increment
        required_action = game_advance_instruction(next_phase, next_sim_year=next_year)
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
        phase_label(observed_phase)
        state = self.ensure_sim_state()
        if state.status != STATUS_WAITING_FOR_GAME_ADVANCE:
            raise ValueError("franchise simulation is not waiting for game progression")
        if str(observed_phase) != state.expected_next_phase or int(observed_sim_year) != state.expected_next_year:
            raise ValueError(
                f"expected {phase_label(state.expected_next_phase)} for true sim year {state.expected_next_year}"
            )
        now = _utc_now_text()
        expansion_required = False if str(observed_phase) == "season" else state.expansion_draft_required
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

    def pause_for_user_trade(self, required_user_action: str) -> FranchiseSimState:
        state = self.ensure_sim_state()
        if state.status != STATUS_READY:
            raise ValueError("franchise simulation is already paused")
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                UPDATE franchise_sim_state
                SET status = ?, required_user_action = ?, updated_at = ?
                WHERE id = 1
                """,
                (STATUS_WAITING_FOR_USER_TRADE, str(required_user_action), now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        paused = self.load_sim_state()
        if paused is None:
            raise RuntimeError("user-team trade pause was not saved")
        return paused

    def resume_after_user_trade(self) -> FranchiseSimState:
        state = self.ensure_sim_state()
        if state.status != STATUS_WAITING_FOR_USER_TRADE:
            raise ValueError("franchise simulation is not waiting for a user-team trade decision")
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute(
                """
                UPDATE franchise_sim_state
                SET status = ?, required_user_action = '', updated_at = ?
                WHERE id = 1
                """,
                (STATUS_READY, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        resumed = self.load_sim_state()
        if resumed is None:
            raise RuntimeError("user-team trade resume was not saved")
        return resumed

    def start_fantasy_draft(self, *, team_count: int, user_team_index: int) -> FantasyDraftState:
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute("DELETE FROM fantasy_draft_picks")
            connection.execute("DELETE FROM fantasy_draft_state")
            connection.execute(
                """
                INSERT INTO fantasy_draft_state(id, current_pick_number, team_count, user_team_index, started_at, updated_at)
                VALUES(1, 1, ?, ?, ?, ?)
                """,
                (int(team_count), int(user_team_index), now, now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        return FantasyDraftState(1, int(team_count), int(user_team_index), now, now)

    def load_fantasy_draft_state(self) -> FantasyDraftState | None:
        connection = self._connect()
        try:
            self.initialize(connection)
            row = connection.execute(
                "SELECT current_pick_number, team_count, user_team_index, started_at, updated_at FROM fantasy_draft_state WHERE id = 1"
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            return None
        return FantasyDraftState(int(row[0]), int(row[1]), int(row[2]), str(row[3]), str(row[4]))

    def list_fantasy_draft_picks(self) -> tuple[FantasyDraftStoredPick, ...]:
        connection = self._connect()
        try:
            self.initialize(connection)
            rows = connection.execute(
                """
                SELECT pick_number, round_number, team_index, team_label, player_index, player_label,
                       source_team_index, source_slot, source_slot_field, picked_by,
                       raw_llm_response, rationale, created_at
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
                raw_llm_response=str(row[10]),
                rationale=str(row[11]),
                created_at=str(row[12]),
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
                    source_team_index, source_slot, source_slot_field, picked_by,
                    raw_llm_response, rationale, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    str(pick.raw_llm_response),
                    str(pick.rationale),
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
            raw_llm_response=pick.raw_llm_response,
            rationale=pick.rationale,
            created_at=now,
        )

    def undo_last_fantasy_draft_pick(self, *, picked_by: str = "llm") -> FantasyDraftStoredPick | None:
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            row = connection.execute(
                """
                SELECT pick_number, round_number, team_index, team_label, player_index, player_label,
                       source_team_index, source_slot, source_slot_field, picked_by,
                       raw_llm_response, rationale, created_at
                FROM fantasy_draft_picks
                ORDER BY pick_number DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None or str(row[9]) != str(picked_by):
                connection.commit()
                return None
            connection.execute("DELETE FROM fantasy_draft_picks WHERE pick_number = ?", (int(row[0]),))
            connection.execute(
                "UPDATE fantasy_draft_state SET current_pick_number = ?, updated_at = ? WHERE id = 1",
                (int(row[0]), now),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
        finally:
            connection.close()
        return FantasyDraftStoredPick(
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
            raw_llm_response=str(row[10]),
            rationale=str(row[11]),
            created_at=str(row[12]),
        )

    def record_team_recommendation(self, recommendation: TeamRecommendation) -> TeamRecommendation:
        now = recommendation.created_at or _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            cursor = connection.execute(
                """
                INSERT INTO team_recommendations(
                    team_index, team_label, recommended_action, reasoning,
                    owner_approval_required, trade_with_user_team, blocked_reason,
                    raw_llm_response, status, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(recommendation.team_index),
                    str(recommendation.team_label),
                    str(recommendation.recommended_action),
                    str(recommendation.reasoning),
                    1 if recommendation.owner_approval_required else 0,
                    1 if recommendation.trade_with_user_team else 0,
                    str(recommendation.blocked_reason),
                    str(recommendation.raw_llm_response),
                    str(recommendation.status),
                    now,
                ),
            )
            connection.execute("INSERT OR REPLACE INTO franchise_meta(key, value) VALUES(?, ?)", ("updated_at", now))
            connection.commit()
            recommendation_id = int(cursor.lastrowid or 0)
        finally:
            connection.close()
        return TeamRecommendation(
            team_index=recommendation.team_index,
            team_label=recommendation.team_label,
            recommended_action=recommendation.recommended_action,
            reasoning=recommendation.reasoning,
            owner_approval_required=recommendation.owner_approval_required,
            trade_with_user_team=recommendation.trade_with_user_team,
            blocked_reason=recommendation.blocked_reason,
            raw_llm_response=recommendation.raw_llm_response,
            status=recommendation.status,
            created_at=now,
            recommendation_id=recommendation_id,
        )

    def list_team_recommendations(self) -> tuple[TeamRecommendation, ...]:
        connection = self._connect()
        try:
            self.initialize(connection)
            rows = connection.execute(
                """
                SELECT id, team_index, team_label, recommended_action, reasoning,
                       owner_approval_required, trade_with_user_team, blocked_reason,
                       raw_llm_response, status, created_at
                FROM team_recommendations
                ORDER BY id
                """
            ).fetchall()
            connection.commit()
        finally:
            connection.close()
        return tuple(
            TeamRecommendation(
                recommendation_id=int(row[0]),
                team_index=int(row[1]),
                team_label=str(row[2]),
                recommended_action=str(row[3]),
                reasoning=str(row[4]),
                owner_approval_required=bool(int(row[5])),
                trade_with_user_team=bool(int(row[6])),
                blocked_reason=str(row[7]),
                raw_llm_response=str(row[8]),
                status=str(row[9]),
                created_at=str(row[10]),
            )
            for row in rows
        )
