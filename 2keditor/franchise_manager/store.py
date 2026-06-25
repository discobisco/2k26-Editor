from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .ai import evaluate_team_at_stop
from .draft_dependency import DraftClassDependency
from .models import (
    ControlMode,
    DraftClassMode,
    DraftProspect,
    FranchiseTeam,
    GMProfile,
    ImportedDataKind,
    ImportedSnapshot,
    OwnerProfile,
    ReasonLog,
    RealismSettings,
    SeasonPhase,
    StopPoint,
    StopPriority,
    TeamControl,
    TeamEvaluation,
    validate_profile_scores,
)
from .progression import (
    HistoricalStatsProvider,
    InGamePlayerSnapshot,
    PlayerProgressionReport,
    evaluate_player_progression,
    report_from_storage_payload,
    report_to_storage_payload,
    snapshot_from_storage_payload,
    snapshot_to_storage_payload,
)
from .timeline import default_stop_points

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS franchise_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seasons (
    season INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    current_phase TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    owner_json TEXT NOT NULL,
    gm_json TEXT NOT NULL,
    control_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stop_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    phase TEXT NOT NULL,
    date_label TEXT NOT NULL,
    reason TEXT NOT NULL,
    priority TEXT NOT NULL,
    team_id TEXT,
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    stop_id INTEGER,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reason_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT NOT NULL,
    action TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS draft_prospects (
    draft_year INTEGER NOT NULL,
    rookie_season INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    historical_team TEXT NOT NULL,
    ratings_json TEXT NOT NULL,
    tendencies_json TEXT NOT NULL,
    badges_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY (draft_year, player_id)
);
CREATE TABLE IF NOT EXISTS player_stat_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    stop_id INTEGER,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS player_progression_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    snapshot_id INTEGER,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class FranchiseStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def initialize_franchise(self, *, start_season: int, end_season: int | None = None, commissioner_mode: bool = False, settings: RealismSettings | None = None) -> None:
        if start_season < 1947:
            raise ValueError("start season must be 1947 or later")
        if end_season is not None and end_season < start_season:
            raise ValueError("end season must be >= start season")
        meta = {
            "start_season": start_season,
            "current_season": start_season,
            "end_season": end_season,
            "commissioner_mode": commissioner_mode,
            "settings": (settings or RealismSettings()).__dict__,
        }
        self._conn.execute("DELETE FROM franchise_meta")
        for key, value in meta.items():
            self._conn.execute("INSERT INTO franchise_meta(key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.ensure_season(start_season)
        self._conn.commit()

    def meta_value(self, key: str, default: object = None) -> object:
        row = self._conn.execute("SELECT value FROM franchise_meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row["value"])

    def set_meta_value(self, key: str, value: object) -> None:
        self._conn.execute(
            "INSERT INTO franchise_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def current_season(self) -> int | None:
        value = self.meta_value("current_season")
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("stored current_season is invalid")
        return int(value)

    def current_phase(self, season: int) -> SeasonPhase:
        row = self._conn.execute("SELECT current_phase FROM seasons WHERE season = ?", (season,)).fetchone()
        return SeasonPhase.PRESEASON if row is None else SeasonPhase(row["current_phase"])

    def set_current_phase(self, season: int, phase: SeasonPhase) -> None:
        self.ensure_season(season)
        self._conn.execute("UPDATE seasons SET current_phase = ? WHERE season = ?", (phase.value, season))
        self.set_meta_value("current_season", season)

    def ensure_season(self, season: int) -> None:
        from .timeline import season_label

        self._conn.execute(
            "INSERT OR IGNORE INTO seasons(season, label, current_phase) VALUES (?, ?, ?)",
            (season, season_label(season), SeasonPhase.PRESEASON.value),
        )
        if not self.list_stop_points(season):
            self.add_stop_points(default_stop_points(season))

    def add_team(self, team: FranchiseTeam) -> None:
        validate_profile_scores(team.owner)
        validate_profile_scores(team.gm)
        self._conn.execute(
            """
            INSERT INTO teams(team_id, display_name, owner_json, gm_json, control_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                display_name=excluded.display_name,
                owner_json=excluded.owner_json,
                gm_json=excluded.gm_json,
                control_json=excluded.control_json
            """,
            (
                team.team_id,
                team.display_name,
                json.dumps(team.owner.__dict__),
                json.dumps(_gm_to_json(team.gm)),
                json.dumps({"owner": team.control.owner.value, "gm": team.control.gm.value}),
            ),
        )
        self._conn.commit()

    def list_teams(self) -> tuple[FranchiseTeam, ...]:
        rows = self._conn.execute("SELECT * FROM teams ORDER BY team_id").fetchall()
        return tuple(_team_from_row(row) for row in rows)

    def add_stop_points(self, stops: Iterable[StopPoint]) -> None:
        self._conn.executemany(
            """
            INSERT INTO stop_points(season, phase, date_label, reason, priority, team_id, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (stop.season, stop.phase.value, stop.date_label, stop.reason, stop.priority.value, stop.team_id, int(stop.resolved))
                for stop in stops
            ],
        )
        self._conn.commit()

    def list_stop_points(self, season: int, *, include_resolved: bool = True) -> tuple[tuple[int, StopPoint], ...]:
        sql = "SELECT * FROM stop_points WHERE season = ?"
        params: list[object] = [season]
        if not include_resolved:
            sql += " AND resolved = 0"
        sql += " ORDER BY id"
        return tuple((int(row["id"]), _stop_from_row(row)) for row in self._conn.execute(sql, params))

    def next_stop(self, season: int) -> tuple[int, StopPoint] | None:
        row = self._conn.execute("SELECT * FROM stop_points WHERE season = ? AND resolved = 0 ORDER BY id LIMIT 1", (season,)).fetchone()
        return None if row is None else (int(row["id"]), _stop_from_row(row))

    def resolve_stop(self, stop_id: int) -> None:
        self._conn.execute("UPDATE stop_points SET resolved = 1 WHERE id = ?", (stop_id,))
        self._conn.commit()

    def import_2k_data(self, snapshot: ImportedSnapshot) -> int:
        cur = self._conn.execute(
            "INSERT INTO imports(season, stop_id, kind, payload_json) VALUES (?, ?, ?, ?)",
            (snapshot.season, snapshot.stop_id, snapshot.kind.value, json.dumps(snapshot.payload, sort_keys=True)),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("failed to insert imported 2K data snapshot")
        return int(cur.lastrowid)

    def snapshots_for_season(self, season: int) -> tuple[ImportedSnapshot, ...]:
        rows = self._conn.execute("SELECT * FROM imports WHERE season = ? ORDER BY id", (season,)).fetchall()
        return tuple(
            ImportedSnapshot(int(row["season"]), row["stop_id"], ImportedDataKind(row["kind"]), json.loads(row["payload_json"]))
            for row in rows
        )

    def evaluate_all_teams(self, season: int) -> tuple[TeamEvaluation, ...]:
        snapshots = self.snapshots_for_season(season)
        evaluations = tuple(evaluate_team_at_stop(season=season, team=team, snapshots=snapshots) for team in self.list_teams())
        for evaluation in evaluations:
            self.add_reason_logs(evaluation.reason_logs)
        return evaluations

    def add_reason_logs(self, logs: Iterable[ReasonLog]) -> None:
        self._conn.executemany(
            "INSERT INTO reason_logs(season, team_id, actor, message, action, evidence_json) VALUES (?, ?, ?, ?, ?, ?)",
            [(log.season, log.team_id, log.actor, log.message, log.action, json.dumps(log.evidence, sort_keys=True)) for log in logs],
        )
        self._conn.commit()

    def reason_logs(self, *, season: int | None = None, team_id: str | None = None) -> tuple[ReasonLog, ...]:
        sql = "SELECT * FROM reason_logs WHERE 1=1"
        params: list[object] = []
        if season is not None:
            sql += " AND season = ?"
            params.append(season)
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return tuple(
            ReasonLog(int(row["season"]), row["team_id"], row["actor"], row["message"], row["action"], json.loads(row["evidence_json"]))
            for row in rows
        )

    def build_draft_class(self, draft_year: int, dependency: DraftClassDependency, *, mode: DraftClassMode = DraftClassMode.DRAFT_PICKS) -> tuple[DraftProspect, ...]:
        draft_mode = mode if isinstance(mode, DraftClassMode) else DraftClassMode(str(mode))
        prospects = dependency.generate_draft_class(draft_year, mode=draft_mode)
        self._conn.executemany(
            """
            INSERT INTO draft_prospects(draft_year, rookie_season, player_id, name, position, historical_team, ratings_json, tendencies_json, badges_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(draft_year, player_id) DO UPDATE SET
                rookie_season=excluded.rookie_season,
                name=excluded.name,
                position=excluded.position,
                historical_team=excluded.historical_team,
                ratings_json=excluded.ratings_json,
                tendencies_json=excluded.tendencies_json,
                badges_json=excluded.badges_json,
                metadata_json=excluded.metadata_json
            """,
            [
                (
                    prospect.draft_year,
                    prospect.rookie_season,
                    prospect.player_id,
                    prospect.name,
                    prospect.position,
                    prospect.historical_team,
                    json.dumps(prospect.ratings, sort_keys=True),
                    json.dumps(prospect.tendencies, sort_keys=True),
                    json.dumps(prospect.badges, sort_keys=True),
                    json.dumps(prospect.metadata, sort_keys=True),
                )
                for prospect in prospects
            ],
        )
        self._conn.commit()
        return prospects

    def list_draft_class(self, draft_year: int) -> tuple[DraftProspect, ...]:
        rows = self._conn.execute("SELECT * FROM draft_prospects WHERE draft_year = ? ORDER BY name", (draft_year,)).fetchall()
        return tuple(_draft_prospect_from_row(row) for row in rows)

    def add_player_stat_snapshot(self, snapshot: InGamePlayerSnapshot, *, stop_id: int | None = None) -> int:
        payload = snapshot_to_storage_payload(snapshot)
        cur = self._conn.execute(
            """
            INSERT INTO player_stat_snapshots(season, stop_id, player_id, team_id, snapshot_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (snapshot.season, stop_id, snapshot.player_id, snapshot.team_id, json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("failed to insert player stat snapshot")
        return int(cur.lastrowid)

    def player_stat_snapshots(self, *, season: int | None = None, player_id: str | None = None) -> tuple[tuple[int, InGamePlayerSnapshot], ...]:
        sql = "SELECT * FROM player_stat_snapshots WHERE 1=1"
        params: list[object] = []
        if season is not None:
            sql += " AND season = ?"
            params.append(season)
        if player_id is not None:
            sql += " AND player_id = ?"
            params.append(player_id)
        sql += " ORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return tuple((int(row["id"]), snapshot_from_storage_payload(json.loads(row["snapshot_json"]))) for row in rows)

    def evaluate_player_progression_snapshot(
        self,
        snapshot: InGamePlayerSnapshot,
        historical_provider: HistoricalStatsProvider | None = None,
        *,
        stop_id: int | None = None,
        historical_season: int | None = None,
    ) -> PlayerProgressionReport:
        snapshot_id = self.add_player_stat_snapshot(snapshot, stop_id=stop_id)
        report = evaluate_player_progression(snapshot, historical_provider, historical_season=historical_season)
        self.add_player_progression_report(report, snapshot_id=snapshot_id)
        return report

    def add_player_progression_report(self, report: PlayerProgressionReport, *, snapshot_id: int | None = None) -> int:
        payload = report_to_storage_payload(report)
        cur = self._conn.execute(
            """
            INSERT INTO player_progression_reports(season, player_id, team_id, snapshot_id, report_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report.season, report.player_id, report.team_id, snapshot_id, json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("failed to insert player progression report")
        return int(cur.lastrowid)

    def player_progression_reports(self, *, season: int | None = None, player_id: str | None = None) -> tuple[PlayerProgressionReport, ...]:
        sql = "SELECT * FROM player_progression_reports WHERE 1=1"
        params: list[object] = []
        if season is not None:
            sql += " AND season = ?"
            params.append(season)
        if player_id is not None:
            sql += " AND player_id = ?"
            params.append(player_id)
        sql += " ORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return tuple(report_from_storage_payload(json.loads(row["report_json"])) for row in rows)


def _gm_to_json(gm: GMProfile) -> dict:
    data = dict(gm.__dict__)
    data["position_preferences"] = list(gm.position_preferences)
    return data


def _team_from_row(row: sqlite3.Row) -> FranchiseTeam:
    owner_data = json.loads(row["owner_json"])
    gm_data = json.loads(row["gm_json"])
    control_data = json.loads(row["control_json"])
    gm_data["position_preferences"] = tuple(gm_data.get("position_preferences", ()))
    return FranchiseTeam(
        team_id=row["team_id"],
        display_name=row["display_name"],
        owner=OwnerProfile(**owner_data),
        gm=GMProfile(**gm_data),
        control=TeamControl(owner=ControlMode(control_data.get("owner", "ai")), gm=ControlMode(control_data.get("gm", "ai"))),
    )


def _stop_from_row(row: sqlite3.Row) -> StopPoint:
    return StopPoint(
        season=int(row["season"]),
        phase=SeasonPhase(row["phase"]),
        date_label=row["date_label"],
        reason=row["reason"],
        priority=StopPriority(row["priority"]),
        team_id=row["team_id"],
        resolved=bool(row["resolved"]),
    )


def _draft_prospect_from_row(row: sqlite3.Row) -> DraftProspect:
    return DraftProspect(
        draft_year=int(row["draft_year"]),
        rookie_season=int(row["rookie_season"]),
        player_id=row["player_id"],
        name=row["name"],
        position=row["position"],
        historical_team=row["historical_team"],
        ratings=json.loads(row["ratings_json"]),
        tendencies=json.loads(row["tendencies_json"]),
        badges=json.loads(row["badges_json"]),
        metadata=json.loads(row["metadata_json"]),
    )
