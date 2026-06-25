from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .draft_dependency import DraftClassDependency, ExistingPlayerGeneratorDraftDependency
from .imports import import_team_offsets
from .models import (
    ControlMode,
    DraftClassMode,
    FranchiseTeam,
    GMProfile,
    ImportedDataKind,
    ImportedSnapshot,
    OwnerProfile,
    RealismSettings,
    ReasonLog,
    SEASON_FLOW,
    SeasonPhase,
    StopPoint,
    TeamControl,
)
from .store import FranchiseStore
from .timeline import season_label

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "franchise_manager.sqlite"


@dataclass(frozen=True)
class FranchiseOverviewView:
    current_season: str
    current_phase: str
    league_champion: str
    upcoming_draft: str
    next_sim_stop: str
    active_user_team: str
    user_role: str


@dataclass(frozen=True)
class LeagueSnapshotView:
    standings_summary: tuple[str, ...] = ()
    top_teams: tuple[str, ...] = ()
    worst_teams: tuple[str, ...] = ()
    mvp_race: tuple[str, ...] = ()
    rookie_race: tuple[str, ...] = ()
    championship_favorites: tuple[str, ...] = ()


@dataclass(frozen=True)
class NextSimStopView:
    date_label: str
    reason: str
    priority: str
    teams_requesting_review: int


@dataclass(frozen=True)
class LeagueDashboardView:
    loaded: bool
    status: str
    overview: FranchiseOverviewView
    league_snapshot: LeagueSnapshotView
    owner_alerts: tuple[str, ...] = ()
    gm_alerts: tuple[str, ...] = ()
    next_sim_stop: NextSimStopView = field(default_factory=lambda: NextSimStopView("No franchise loaded", "Create or load a franchise", "N/A", 0))
    activity_feed: tuple[str, ...] = ()
    development_watch: tuple[str, ...] = ()


@dataclass(frozen=True)
class TeamDashboardView:
    team_id: str
    display_name: str
    owner: str
    gm: str
    owner_control: str
    gm_control: str
    recent_logs: tuple[str, ...]


class FranchiseManagerFacade:
    """Thin UI-facing facade for Franchise Manager operations.

    DPG calls this object. It returns lightweight view models and delegates all
    business state to FranchiseStore / franchise systems.
    """

    def __init__(self, db_path: str | Path | None = None, *, draft_dependency: DraftClassDependency | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self.draft_dependency = draft_dependency or ExistingPlayerGeneratorDraftDependency()
        self.store: FranchiseStore | None = None
        if self.db_path.exists():
            self.store = FranchiseStore(self.db_path)

    def close(self) -> None:
        if self.store is not None:
            self.store.close()
            self.store = None

    def create_franchise(self, *, start_season: int = 1947, end_season: int | None = None, commissioner_mode: bool = True, settings: RealismSettings | None = None) -> LeagueDashboardView:
        self.close()
        self.store = FranchiseStore(self.db_path)
        self.store.initialize_franchise(start_season=start_season, end_season=end_season, commissioner_mode=commissioner_mode, settings=settings)
        if not self.store.list_teams():
            self.store.add_team(_default_user_team())
        return self.get_league_dashboard(status="Franchise created.")

    def load_franchise(self, path: str | Path | None = None) -> LeagueDashboardView:
        if path is not None:
            self.db_path = Path(path)
        self.close()
        if not self.db_path.exists():
            return empty_league_dashboard(f"No franchise database found at {self.db_path}.")
        self.store = FranchiseStore(self.db_path)
        return self.get_league_dashboard(status="Franchise loaded.")

    def save_franchise(self) -> LeagueDashboardView:
        if self.store is None:
            return empty_league_dashboard("No franchise loaded to save.")
        return self.get_league_dashboard(status="Franchise saved.")

    def advance_phase(self) -> LeagueDashboardView:
        store = self._require_store()
        season = self._current_season()
        phase = store.current_phase(season)
        index = SEASON_FLOW.index(phase)
        next_index = index + 1
        if next_index >= len(SEASON_FLOW):
            season += 1
            store.ensure_season(season)
            next_phase = SeasonPhase.PRESEASON
        else:
            next_phase = SEASON_FLOW[next_index]
        store.set_current_phase(season, next_phase)
        return self.get_league_dashboard(status=f"Advanced to {next_phase.value.replace('_', ' ')}.")

    def import_2k_data_from_offsets(self, model: Any, *, team_limit: int | None = 30) -> LeagueDashboardView:
        store = self._require_store()
        season = self._current_season()
        stop = store.next_stop(season)
        stop_id = stop[0] if stop else None
        imported = import_team_offsets(model, team_limit=team_limit)
        store.import_2k_data(ImportedSnapshot(season=season, stop_id=stop_id, kind=ImportedDataKind.STANDINGS, payload=imported.standings_payload))
        store.import_2k_data(ImportedSnapshot(season=season, stop_id=stop_id, kind=ImportedDataKind.TEAM_STATS, payload=imported.team_stats_payload))
        return self.get_league_dashboard(status=f"Imported 2K team offsets: {imported.standings_rows} standings rows, {imported.team_stat_rows} team stat rows.")

    def import_manual_league_snapshot_file(self, path: str | Path, *, resolve_stop: bool = False) -> LeagueDashboardView:
        store = self._require_store()
        season = self._current_season()
        stop = store.next_stop(season)
        stop_id = stop[0] if stop else None
        snapshot_path = Path(path)
        standings_payload, team_stats_payload = _manual_snapshot_payload_from_json(snapshot_path)
        store.import_2k_data(ImportedSnapshot(season=season, stop_id=stop_id, kind=ImportedDataKind.STANDINGS, payload=standings_payload))
        if team_stats_payload:
            store.import_2k_data(ImportedSnapshot(season=season, stop_id=stop_id, kind=ImportedDataKind.TEAM_STATS, payload=team_stats_payload))
        if resolve_stop and stop_id is not None:
            store.resolve_stop(stop_id)
        store.add_reason_logs((
            ReasonLog(
                season=season,
                team_id="LEAGUE",
                actor="import",
                message=f"Imported manual league snapshot from {snapshot_path.name}: {len(standings_payload)} standings rows, {len(team_stats_payload)} team stat rows.",
                action="manual_import",
                evidence={
                    "path": str(snapshot_path),
                    "standings_rows": len(standings_payload),
                    "team_stat_rows": len(team_stats_payload),
                    "stop_id": stop_id,
                    "resolved_stop": bool(resolve_stop and stop_id is not None),
                },
            ),
        ))
        status = f"Imported manual league snapshot: {len(standings_payload)} standings rows, {len(team_stats_payload)} team stat rows."
        if resolve_stop and stop_id is not None:
            status += " Resolved current stop."
        return self.get_league_dashboard(status=status)

    def generate_draft_class(self, draft_year: int | None = None, *, mode: DraftClassMode | str = DraftClassMode.DRAFT_PICKS) -> LeagueDashboardView:
        store = self._require_store()
        season = self._current_season()
        target_draft_year = int(draft_year or season)
        draft_mode = mode if isinstance(mode, DraftClassMode) else DraftClassMode(str(mode))
        prospects = store.build_draft_class(target_draft_year, self.draft_dependency, mode=draft_mode)
        label = "draft picks" if draft_mode is DraftClassMode.DRAFT_PICKS else "rookie year"
        return self.get_league_dashboard(status=f"Generated {len(prospects)} draft prospects for {target_draft_year} by {label} through Player Generator dependency.")

    def run_owner_evaluations(self) -> LeagueDashboardView:
        store = self._require_store()
        evaluations = store.evaluate_all_teams(self._current_season())
        return self.get_league_dashboard(status=f"Ran owner evaluations for {len(evaluations)} teams.")

    def run_gm_evaluations(self) -> LeagueDashboardView:
        store = self._require_store()
        evaluations = store.evaluate_all_teams(self._current_season())
        return self.get_league_dashboard(status=f"Ran GM evaluations for {len(evaluations)} teams.")

    def run_player_progression(self) -> LeagueDashboardView:
        store = self._require_store()
        season = self._current_season()
        store.add_reason_logs((ReasonLog(season, "LEAGUE", "progression", "Progression review queued; import minutes, injuries, and morale before applying player changes.", "progression_review", {}),))
        return self.get_league_dashboard(status="Player progression review queued.")

    def get_next_sim_stop(self) -> NextSimStopView:
        if self.store is None:
            return NextSimStopView("No franchise loaded", "Create or load a franchise", "N/A", 0)
        season = self._current_season()
        stop = self.store.next_stop(season)
        if stop is None:
            return NextSimStopView("No open stops", "All current-season stops resolved", "N/A", 0)
        _, stop_point = stop
        requesting = sum(1 for _, candidate in self.store.list_stop_points(season, include_resolved=False) if candidate.team_id)
        return NextSimStopView(stop_point.date_label, stop_point.reason, stop_point.priority.value, requesting)

    def get_league_dashboard(self, *, status: str = "Franchise dashboard ready.") -> LeagueDashboardView:
        if self.store is None:
            return empty_league_dashboard("No franchise loaded.")
        season = self._current_season()
        phase = self.store.current_phase(season)
        teams = self.store.list_teams()
        next_stop = self.get_next_sim_stop()
        logs = self.store.reason_logs(season=season)
        owner_logs = tuple(log.message for log in logs if log.actor == "owner")[-5:]
        gm_logs = tuple(log.message for log in logs if log.actor == "gm")[-5:]
        activity = tuple(f"{log.actor}: {log.action} — {log.message}" for log in logs)[-8:]
        overview = FranchiseOverviewView(
            current_season=season_label(season),
            current_phase=phase.value.replace("_", " ").title(),
            league_champion="Not imported",
            upcoming_draft=f"{season} Draft",
            next_sim_stop=f"{next_stop.date_label} — {next_stop.reason}",
            active_user_team=_active_user_team(teams),
            user_role=_user_role(teams),
        )
        snapshot = self._snapshot_from_latest_standings(season)
        return LeagueDashboardView(
            loaded=True,
            status=status,
            overview=overview,
            league_snapshot=snapshot,
            owner_alerts=owner_logs or ("No owner alerts.",),
            gm_alerts=gm_logs or ("No GM alerts.",),
            next_sim_stop=next_stop,
            activity_feed=activity or ("No league activity yet.",),
            development_watch=("No progression reports yet.",),
        )

    def get_team_dashboard(self, team_id: str | None = None) -> TeamDashboardView:
        store = self._require_store()
        teams = store.list_teams()
        if not teams:
            return TeamDashboardView("", "No teams", "", "", "", "", ())
        selected = next((team for team in teams if team.team_id == team_id), teams[0])
        logs = tuple(log.message for log in store.reason_logs(season=self._current_season(), team_id=selected.team_id))[-5:]
        return TeamDashboardView(selected.team_id, selected.display_name, selected.owner.name, selected.gm.name, selected.control.owner.value, selected.control.gm.value, logs)

    def get_owner_report(self, team_id: str | None = None) -> tuple[str, ...]:
        team = self.get_team_dashboard(team_id)
        return tuple(log for log in team.recent_logs if "Owner" in log or "owner" in log) or ("No owner report available.",)

    def get_gm_report(self, team_id: str | None = None) -> tuple[str, ...]:
        team = self.get_team_dashboard(team_id)
        return tuple(log for log in team.recent_logs if "GM" in log or "gm" in log) or ("No GM report available.",)

    def get_draft_report(self, draft_year: int | None = None) -> tuple[str, ...]:
        store = self._require_store()
        year = int(draft_year or self._current_season())
        prospects = store.list_draft_class(year)
        if not prospects:
            return (f"No draft class generated for {year}.",)
        return tuple(f"{prospect.name} ({prospect.position}) — {prospect.historical_team}" for prospect in prospects[:20])

    def get_history_report(self) -> tuple[str, ...]:
        store = self._require_store()
        logs = store.reason_logs(season=self._current_season())
        return tuple(f"{log.actor}: {log.action}" for log in logs[-20:]) or ("No history events recorded.",)

    def _snapshot_from_latest_standings(self, season: int) -> LeagueSnapshotView:
        snapshots = self.store.snapshots_for_season(season) if self.store is not None else ()
        standings = next((snapshot.payload for snapshot in reversed(snapshots) if snapshot.kind == ImportedDataKind.STANDINGS), {})
        rows: list[tuple[str, int, int]] = []
        for team_id, values in standings.items():
            if isinstance(values, dict):
                rows.append((str(team_id), int(values.get("wins", 0) or 0), int(values.get("losses", 0) or 0)))
        rows.sort(key=lambda row: (row[1] / max(1, row[1] + row[2]), row[1]), reverse=True)
        if not rows:
            return LeagueSnapshotView(
                standings_summary=("No standings imported.",),
                top_teams=("No standings imported.",),
                worst_teams=("No standings imported.",),
                mvp_race=("No award data imported.",),
                rookie_race=("No rookie data imported.",),
                championship_favorites=("No favorites until standings are imported.",),
            )
        formatted = tuple(f"{team}: {wins}-{losses}" for team, wins, losses in rows)
        return LeagueSnapshotView(
            standings_summary=formatted[:8],
            top_teams=formatted[:3],
            worst_teams=tuple(reversed(formatted[-3:])),
            mvp_race=("No MVP race import yet.",),
            rookie_race=("No rookie race import yet.",),
            championship_favorites=formatted[:3],
        )

    def _require_store(self) -> FranchiseStore:
        if self.store is None:
            if self.db_path.exists():
                self.store = FranchiseStore(self.db_path)
            else:
                raise RuntimeError("No franchise loaded. Create or load a franchise first.")
        return self.store

    def _current_season(self) -> int:
        store = self._require_store()
        season = store.current_season()
        if season is None:
            raise RuntimeError("No current season set. Create or load a franchise first.")
        return season

    # PascalCase aliases for the UI/business contract named in the feature spec.
    CreateFranchise = create_franchise
    LoadFranchise = load_franchise
    SaveFranchise = save_franchise
    AdvancePhase = advance_phase
    Import2KDataFromOffsets = import_2k_data_from_offsets
    ImportManualLeagueSnapshotFile = import_manual_league_snapshot_file
    GenerateDraftClass = generate_draft_class
    RunOwnerEvaluations = run_owner_evaluations
    RunGMEvaluations = run_gm_evaluations
    RunPlayerProgression = run_player_progression
    GetNextSimStop = get_next_sim_stop
    GetLeagueDashboard = get_league_dashboard
    GetTeamDashboard = get_team_dashboard
    GetOwnerReport = get_owner_report
    GetGMReport = get_gm_report
    GetDraftReport = get_draft_report
    GetHistoryReport = get_history_report


def _manual_snapshot_payload_from_json(path: Path) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"manual league snapshot is not valid JSON: {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("manual league snapshot root must be a JSON object")
    standings_raw = loaded.get("standings")
    if not isinstance(standings_raw, dict) or not standings_raw:
        raise ValueError("manual league snapshot requires a non-empty standings object")
    standings = _coerce_standings_payload(standings_raw)
    team_stats_raw = loaded.get("team_stats", {})
    if team_stats_raw in (None, ""):
        team_stats_raw = {}
    if not isinstance(team_stats_raw, dict):
        raise ValueError("manual league snapshot team_stats must be an object when provided")
    return standings, _coerce_nested_int_payload(team_stats_raw, object_name="team_stats")


def _coerce_standings_payload(raw: dict[Any, Any]) -> dict[str, dict[str, int]]:
    standings: dict[str, dict[str, int]] = {}
    for team_id, values in raw.items():
        team_key = str(team_id).strip()
        if not team_key:
            raise ValueError("manual standings contains a blank team key")
        if not isinstance(values, dict):
            raise ValueError(f"manual standings row for {team_key} must be an object")
        if "wins" not in values or "losses" not in values:
            raise ValueError(f"manual standings row for {team_key} requires wins and losses")
        standings[team_key] = {
            "wins": _coerce_int(values["wins"], field_name=f"standings.{team_key}.wins"),
            "losses": _coerce_int(values["losses"], field_name=f"standings.{team_key}.losses"),
        }
    return standings


def _coerce_nested_int_payload(raw: dict[Any, Any], *, object_name: str) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    for team_id, values in raw.items():
        team_key = str(team_id).strip()
        if not team_key:
            raise ValueError(f"manual {object_name} contains a blank team key")
        if not isinstance(values, dict):
            raise ValueError(f"manual {object_name} row for {team_key} must be an object")
        payload[team_key] = {
            str(field_name).strip(): _coerce_int(value, field_name=f"{object_name}.{team_key}.{field_name}")
            for field_name, value in values.items()
            if str(field_name).strip()
        }
    return payload


def _coerce_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    try:
        return int(float(str(value).replace(",", "")))
    except Exception as exc:
        raise ValueError(f"{field_name} must be numeric: {value!r}") from exc


def empty_league_dashboard(status: str) -> LeagueDashboardView:
    return LeagueDashboardView(
        loaded=False,
        status=status,
        overview=FranchiseOverviewView("No franchise", "No phase", "N/A", "N/A", "N/A", "N/A", "N/A"),
        league_snapshot=LeagueSnapshotView(
            standings_summary=("No franchise loaded.",),
            top_teams=("No franchise loaded.",),
            worst_teams=("No franchise loaded.",),
            mvp_race=("No franchise loaded.",),
            rookie_race=("No franchise loaded.",),
            championship_favorites=("No franchise loaded.",),
        ),
        owner_alerts=("No franchise loaded.",),
        gm_alerts=("No franchise loaded.",),
        activity_feed=("No franchise loaded.",),
        development_watch=("No franchise loaded.",),
    )


def _default_user_team() -> FranchiseTeam:
    return FranchiseTeam(
        team_id="USER",
        display_name="User Franchise",
        owner=OwnerProfile(name="User Owner"),
        gm=GMProfile(name="User GM"),
        control=TeamControl(owner=ControlMode.USER, gm=ControlMode.USER),
    )


def _active_user_team(teams: tuple[FranchiseTeam, ...]) -> str:
    for team in teams:
        if team.control.owner.value == "user" or team.control.gm.value == "user":
            return team.display_name
    return "Commissioner"


def _user_role(teams: tuple[FranchiseTeam, ...]) -> str:
    for team in teams:
        owner = team.control.owner.value == "user"
        gm = team.control.gm.value == "user"
        if owner and gm:
            return "Owner + GM"
        if owner:
            return "Owner"
        if gm:
            return "GM"
    return "Commissioner"
