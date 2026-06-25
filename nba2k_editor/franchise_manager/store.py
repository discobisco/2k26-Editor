from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

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
from .objectives import ObjectiveDirective, objective_from_payload, objective_to_payload
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
from .world import DraftPickAsset, FranchisePlayer, InjuryStatus, PlayerContract, TeamContext, build_team_context

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
CREATE TABLE IF NOT EXISTS franchise_players (
    season INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, player_id)
);
CREATE TABLE IF NOT EXISTS franchise_contracts (
    season INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    salary INTEGER NOT NULL DEFAULT 0,
    years_remaining INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, player_id)
);
CREATE TABLE IF NOT EXISTS franchise_draft_picks (
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    draft_year INTEGER NOT NULL,
    draft_round INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, team_id, draft_year, draft_round, payload_json)
);
CREATE TABLE IF NOT EXISTS franchise_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS franchise_injuries (
    season INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    severity INTEGER NOT NULL DEFAULT 0,
    games_remaining INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, player_id)
);
CREATE TABLE IF NOT EXISTS team_finances (
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    payroll INTEGER NOT NULL DEFAULT 0,
    salary_cap INTEGER NOT NULL DEFAULT 0,
    luxury_tax_line INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, team_id)
);
CREATE TABLE IF NOT EXISTS staff_profiles (
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    role TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, team_id, role)
);
CREATE TABLE IF NOT EXISTS facility_profiles (
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, team_id, facility_type)
);
CREATE TABLE IF NOT EXISTS franchise_objectives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    objective_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS franchise_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    team_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS playoff_brackets (
    season INTEGER NOT NULL,
    bracket_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, bracket_id)
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
        evaluations = tuple(
            evaluate_team_at_stop(season=season, team=team, snapshots=self._evaluation_snapshots_for_team(season, team.team_id))
            for team in self.list_teams()
        )
        for evaluation in evaluations:
            self.add_reason_logs(evaluation.reason_logs)
        return evaluations

    def build_team_context(self, *, season: int, team: FranchiseTeam) -> TeamContext:
        return build_team_context(season=season, team=team, snapshots=self._evaluation_snapshots_for_team(season, team.team_id))

    def upsert_franchise_players(self, season: int, players: Iterable[FranchisePlayer | dict[str, Any]]) -> None:
        rows = []
        for player in players:
            payload = _player_payload(player)
            player_id = str(payload.get("player_id") or "").strip()
            team_id = str(payload.get("team_id") or "").strip()
            if not player_id or not team_id:
                raise ValueError("franchise player requires player_id and team_id")
            rows.append((season, player_id, team_id, json.dumps(payload, sort_keys=True)))
        self._conn.executemany(
            """
            INSERT INTO franchise_players(season, player_id, team_id, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(season, player_id) DO UPDATE SET
                team_id=excluded.team_id,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        self._conn.commit()

    def list_franchise_players(self, *, season: int, team_id: str | None = None) -> tuple[FranchisePlayer, ...]:
        sql = "SELECT * FROM franchise_players WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY team_id, player_id"
        return tuple(_player_from_payload(json.loads(row["payload_json"])) for row in self._conn.execute(sql, params))

    def upsert_contracts(self, season: int, contracts: Iterable[PlayerContract | dict[str, Any]]) -> None:
        rows = []
        for contract in contracts:
            payload = _contract_payload(contract)
            player_id = str(payload.get("player_id") or "").strip()
            team_id = str(payload.get("team_id") or "").strip()
            if not player_id or not team_id:
                raise ValueError("contract requires player_id and team_id")
            rows.append((season, player_id, team_id, int(payload.get("salary", 0) or 0), int(payload.get("years_remaining", 0) or 0), json.dumps(payload, sort_keys=True)))
        self._conn.executemany(
            """
            INSERT INTO franchise_contracts(season, player_id, team_id, salary, years_remaining, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(season, player_id) DO UPDATE SET
                team_id=excluded.team_id,
                salary=excluded.salary,
                years_remaining=excluded.years_remaining,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        self._conn.commit()

    def list_contracts(self, *, season: int, team_id: str | None = None) -> tuple[PlayerContract, ...]:
        sql = "SELECT * FROM franchise_contracts WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY team_id, player_id"
        return tuple(_contract_from_payload(json.loads(row["payload_json"])) for row in self._conn.execute(sql, params))

    def upsert_draft_picks(self, season: int, picks: Iterable[DraftPickAsset | dict[str, Any]]) -> None:
        rows = []
        for pick in picks:
            payload = _draft_pick_payload(pick)
            team_id = str(payload.get("team_id") or "").strip()
            if not team_id:
                raise ValueError("draft pick requires team_id")
            rows.append((season, team_id, int(payload.get("year", 0) or 0), int(payload.get("round", 1) or 1), json.dumps(payload, sort_keys=True)))
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO franchise_draft_picks(season, team_id, draft_year, draft_round, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()

    def list_draft_picks(self, *, season: int, team_id: str | None = None) -> tuple[DraftPickAsset, ...]:
        sql = "SELECT * FROM franchise_draft_picks WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY team_id, draft_year, draft_round, payload_json"
        return tuple(_draft_pick_from_payload(json.loads(row["payload_json"])) for row in self._conn.execute(sql, params))

    def upsert_injuries(self, season: int, injuries: Iterable[InjuryStatus | dict[str, Any]]) -> None:
        rows = []
        for injury in injuries:
            payload = _injury_payload(injury)
            player_id = str(payload.get("player_id") or "").strip()
            team_id = str(payload.get("team_id") or "").strip()
            if not player_id or not team_id:
                raise ValueError("injury requires player_id and team_id")
            rows.append((season, player_id, team_id, int(payload.get("severity", 0) or 0), int(payload.get("games_remaining", 0) or 0), json.dumps(payload, sort_keys=True)))
        self._conn.executemany(
            """
            INSERT INTO franchise_injuries(season, player_id, team_id, severity, games_remaining, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(season, player_id) DO UPDATE SET
                team_id=excluded.team_id,
                severity=excluded.severity,
                games_remaining=excluded.games_remaining,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        self._conn.commit()

    def list_injuries(self, *, season: int, team_id: str | None = None) -> tuple[InjuryStatus, ...]:
        sql = "SELECT * FROM franchise_injuries WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY team_id, player_id"
        return tuple(_injury_from_payload(json.loads(row["payload_json"])) for row in self._conn.execute(sql, params))

    def upsert_team_finances(self, season: int, team_id: str, *, payroll: int = 0, salary_cap: int = 0, luxury_tax_line: int = 0, **extra: Any) -> None:
        payload = {"team_id": team_id, "payroll": payroll, "salary_cap": salary_cap, "luxury_tax_line": luxury_tax_line, **extra}
        self._conn.execute(
            """
            INSERT INTO team_finances(season, team_id, payroll, salary_cap, luxury_tax_line, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(season, team_id) DO UPDATE SET
                payroll=excluded.payroll,
                salary_cap=excluded.salary_cap,
                luxury_tax_line=excluded.luxury_tax_line,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (season, team_id, payroll, salary_cap, luxury_tax_line, json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()

    def list_team_finances(self, *, season: int, team_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT payload_json FROM team_finances WHERE season = ? AND team_id = ?", (season, team_id)).fetchone()
        return {} if row is None else json.loads(row["payload_json"])

    def add_transaction(self, season: int, team_id: str, transaction_type: str, payload: dict[str, Any]) -> int:
        payload = {"team_id": team_id, "type": transaction_type, **dict(payload)}
        cur = self._conn.execute(
            "INSERT INTO franchise_transactions(season, team_id, transaction_type, payload_json) VALUES (?, ?, ?, ?)",
            (season, team_id, transaction_type, json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("failed to insert franchise transaction")
        return int(cur.lastrowid)

    def list_transactions(self, *, season: int, team_id: str | None = None) -> tuple[dict[str, Any], ...]:
        sql = "SELECT * FROM franchise_transactions WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY id"
        return tuple(json.loads(row["payload_json"]) for row in self._conn.execute(sql, params))

    def upsert_objectives(self, season: int, team_id: str, objectives: Iterable[ObjectiveDirective | dict[str, Any]]) -> None:
        self._conn.execute("DELETE FROM franchise_objectives WHERE season = ? AND team_id = ?", (season, team_id))
        rows = []
        for objective in objectives:
            payload = objective_to_payload(objective)
            objective_type = str(payload.get("objective_type") or payload.get("type") or "").strip()
            if not objective_type:
                raise ValueError("objective requires objective_type")
            payload["season"] = season
            payload["team_id"] = team_id
            status = str(payload.get("status") or "open")
            rows.append((season, team_id, objective_type, status, json.dumps(payload, sort_keys=True)))
        self._conn.executemany(
            "INSERT INTO franchise_objectives(season, team_id, objective_type, status, payload_json) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def list_objectives(self, *, season: int, team_id: str | None = None) -> tuple[ObjectiveDirective, ...]:
        sql = "SELECT payload_json FROM franchise_objectives WHERE season = ?"
        params: list[object] = [season]
        if team_id is not None:
            sql += " AND team_id = ?"
            params.append(team_id)
        sql += " ORDER BY id"
        return tuple(objective_from_payload(json.loads(row["payload_json"])) for row in self._conn.execute(sql, params))

    def _evaluation_snapshots_for_team(self, season: int, team_id: str) -> tuple[ImportedSnapshot, ...]:
        snapshots = list(self.snapshots_for_season(season))
        players = [_player_payload(player) for player in self.list_franchise_players(season=season, team_id=team_id)]
        injuries = [_injury_payload(injury) for injury in self.list_injuries(season=season, team_id=team_id)]
        contracts = [_contract_payload(contract) for contract in self.list_contracts(season=season, team_id=team_id)]
        draft_picks = [_draft_pick_payload(pick) for pick in self.list_draft_picks(season=season, team_id=team_id)]
        finances = self.list_team_finances(season=season, team_id=team_id)
        transactions = list(self.list_transactions(season=season, team_id=team_id))
        objectives = [objective_to_payload(objective) for objective in self.list_objectives(season=season, team_id=team_id)]
        if players:
            snapshots.append(ImportedSnapshot(season, None, ImportedDataKind.PLAYER_STATS, {"players": players}))
        if injuries:
            snapshots.append(ImportedSnapshot(season, None, ImportedDataKind.INJURIES, {"injuries": injuries}))
        if contracts or draft_picks or finances:
            contract_payload = dict(finances)
            contract_payload["contracts"] = contracts
            contract_payload["draft_picks"] = draft_picks
            snapshots.append(ImportedSnapshot(season, None, ImportedDataKind.CONTRACTS, contract_payload))
        if transactions:
            snapshots.append(ImportedSnapshot(season, None, ImportedDataKind.TRADES, {"transactions": transactions}))
        if objectives:
            snapshots.append(ImportedSnapshot(season, None, ImportedDataKind.OBJECTIVES, {"objectives": objectives}))
        return tuple(snapshots)

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


def _player_payload(player: FranchisePlayer | dict[str, Any]) -> dict[str, Any]:
    if isinstance(player, FranchisePlayer):
        payload = dict(player.raw)
        payload.update(
            {
                "player_id": player.player_id,
                "team_id": player.team_id,
                "name": player.name,
                "age": player.age,
                "overall": player.overall,
                "potential": player.potential,
                "minutes": player.minutes,
                "morale": player.morale,
                "development": player.development,
                "position": player.position,
            }
        )
        return _drop_none(payload)
    return _drop_none(dict(player))


def _player_from_payload(payload: dict[str, Any]) -> FranchisePlayer:
    return FranchisePlayer(
        player_id=str(payload.get("player_id") or payload.get("id") or ""),
        team_id=str(payload.get("team_id") or payload.get("team") or ""),
        name=str(payload.get("name") or payload.get("player") or payload.get("player_id") or ""),
        age=_optional_float(payload.get("age")),
        overall=_optional_float(payload.get("overall", payload.get("ovr"))),
        potential=_optional_float(payload.get("potential", payload.get("pot"))),
        minutes=_optional_float(payload.get("minutes", payload.get("mpg"))),
        morale=_optional_float(payload.get("morale")),
        development=_optional_float(payload.get("development", payload.get("development_score"))),
        position=str(payload.get("position") or payload.get("pos") or ""),
        raw=dict(payload),
    )


def _contract_payload(contract: PlayerContract | dict[str, Any]) -> dict[str, Any]:
    if isinstance(contract, PlayerContract):
        payload = dict(contract.raw)
        payload.update(
            {
                "player_id": contract.player_id,
                "team_id": contract.team_id,
                "salary": contract.salary,
                "years_remaining": contract.years_remaining,
                "expiring": contract.expiring,
            }
        )
        return _drop_none(payload)
    return _drop_none(dict(contract))


def _contract_from_payload(payload: dict[str, Any]) -> PlayerContract:
    years = _int_value(payload.get("years_remaining", payload.get("years")), 0)
    return PlayerContract(
        player_id=str(payload.get("player_id") or payload.get("id") or ""),
        team_id=str(payload.get("team_id") or payload.get("team") or ""),
        salary=_int_value(payload.get("salary", payload.get("current_salary")), 0),
        years_remaining=years,
        expiring=bool(payload.get("expiring")) or years == 1,
        raw=dict(payload),
    )


def _draft_pick_payload(pick: DraftPickAsset | dict[str, Any]) -> dict[str, Any]:
    if isinstance(pick, DraftPickAsset):
        payload = dict(pick.raw)
        payload.update(
            {
                "team_id": pick.team_id,
                "year": pick.year,
                "round": pick.round,
                "protection": pick.protection,
                "incoming_from": pick.incoming_from,
                "outgoing_to": pick.outgoing_to,
            }
        )
        return _drop_none(payload)
    return _drop_none(dict(pick))


def _draft_pick_from_payload(payload: dict[str, Any]) -> DraftPickAsset:
    return DraftPickAsset(
        team_id=str(payload.get("team_id") or payload.get("owner_team") or payload.get("team") or ""),
        year=_int_value(payload.get("year", payload.get("season")), 0),
        round=_int_value(payload.get("round", payload.get("draft_round")), 1),
        protection=str(payload.get("protection") or payload.get("protections") or ""),
        incoming_from=str(payload.get("incoming_from") or payload.get("from_team") or ""),
        outgoing_to=str(payload.get("outgoing_to") or ""),
        raw=dict(payload),
    )


def _injury_payload(injury: InjuryStatus | dict[str, Any]) -> dict[str, Any]:
    if isinstance(injury, InjuryStatus):
        payload = dict(injury.raw)
        payload.update(
            {
                "player_id": injury.player_id,
                "team_id": injury.team_id,
                "severity": injury.severity,
                "games_remaining": injury.games_remaining,
                "description": injury.description,
            }
        )
        return _drop_none(payload)
    return _drop_none(dict(injury))


def _injury_from_payload(payload: dict[str, Any]) -> InjuryStatus:
    return InjuryStatus(
        player_id=str(payload.get("player_id") or payload.get("id") or ""),
        team_id=str(payload.get("team_id") or payload.get("team") or ""),
        severity=_int_value(payload.get("severity", payload.get("injury_severity")), 0),
        games_remaining=_int_value(payload.get("games_remaining", payload.get("games_out")), 0),
        description=str(payload.get("description") or payload.get("injury") or ""),
        raw=dict(payload),
    )


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _int_value(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(round(float(str(value).replace(",", ""))))
    except ValueError:
        return default


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
