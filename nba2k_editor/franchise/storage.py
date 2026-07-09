from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.franchise.models import (
    FantasyDraftState,
    FantasyDraftStoredPick,
    FranchiseRecord,
    FranchiseSetup,
    FranchiseTeamOption,
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
            """
        )

    def replace_franchise(
        self,
        setup: FranchiseSetup,
        team_options: Iterable[FranchiseTeamOption],
        *,
        league_snapshot: dict[str, Any] | None = None,
        target_executable: str = "",
    ) -> FranchiseRecord:
        selected_indexes = set(setup.llm_gm_team_indexes)
        selected_indexes.discard(int(setup.user_team_index))
        selected_teams = tuple(option for option in team_options if option.team_index in selected_indexes)
        now = _utc_now_text()
        connection = self._connect()
        try:
            self.initialize(connection)
            connection.execute("DELETE FROM franchise_meta")
            connection.execute("DELETE FROM llm_gm_teams")
            connection.execute("DELETE FROM league_saves")
            connection.execute("DELETE FROM fantasy_draft_state")
            connection.execute("DELETE FROM fantasy_draft_picks")
            meta = {
                "start_year": str(int(setup.start_year)),
                "user_team_index": str(int(setup.user_team_index)),
                "keep_full_league_save": "1" if setup.keep_full_league_save else "0",
                "fantasy_draft": "1" if setup.fantasy_draft else "0",
                "created_at": now,
                "updated_at": now,
            }
            connection.executemany("INSERT INTO franchise_meta(key, value) VALUES(?, ?)", meta.items())
            connection.executemany(
                "INSERT INTO llm_gm_teams(team_index, label, display_label) VALUES(?, ?, ?)",
                ((team.team_index, team.label, team.display_label) for team in selected_teams),
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
                    "SELECT team_index, label, display_label FROM llm_gm_teams ORDER BY team_index"
                )
            )
            save_count = int(connection.execute("SELECT COUNT(*) FROM league_saves").fetchone()[0])
            connection.commit()
        finally:
            connection.close()
        setup = FranchiseSetup(
            start_year=int(meta.get("start_year", "2025")),
            keep_full_league_save=meta.get("keep_full_league_save", "0") == "1",
            llm_gm_team_indexes=tuple(team.team_index for team in teams),
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
        )

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
