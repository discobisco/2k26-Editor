from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

_DEFAULT_HISTORICAL_DB = Path(__file__).resolve().parents[1] / "Player Generator" / "NBA Player Data" / "NBA_DATA_Master.sqlite"


@dataclass(frozen=True)
class InGamePlayerSnapshot:
    """Franchise-owned player state imported from NBA 2K.

    This stores the mutable in-franchise world: 2K attributes, tendencies,
    simulated in-game production, and role/context. It intentionally does not
    store Basketball-Reference/historical rows.
    """

    season: int
    player_id: str
    team_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    tendencies: dict[str, Any] = field(default_factory=dict)
    in_game_stats: dict[str, Any] = field(default_factory=dict)
    role: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoricalPlayerStatLink:
    player_id: str
    season: int
    source_database: str
    source_tables: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalPlayerBaseline:
    """In-memory only historical lookup result.

    Franchise DB stores HistoricalPlayerStatLink, not these stat dicts.
    """

    link: HistoricalPlayerStatLink
    player_info: dict[str, Any] = field(default_factory=dict)
    season_info: dict[str, Any] = field(default_factory=dict)
    per_game: dict[str, Any] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)
    advanced: dict[str, Any] = field(default_factory=dict)
    shooting: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillAdjustment:
    category: str
    field_name: str
    current_value: int | float | None
    delta: int
    target_value: int | float | None
    direction: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerProgressionReport:
    season: int
    player_id: str
    team_id: str
    historical_link: HistoricalPlayerStatLink
    role_summary: dict[str, Any]
    progression: tuple[SkillAdjustment, ...]
    regression: tuple[SkillAdjustment, ...]
    reasons: tuple[str, ...]


class HistoricalStatsProvider(Protocol):
    def player_baseline(self, *, player_id: str, season: int) -> HistoricalPlayerBaseline: ...


class HistoricalSQLiteStatsProvider:
    """Read-only link to the generator's historical source database."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else _DEFAULT_HISTORICAL_DB

    def player_baseline(self, *, player_id: str, season: int) -> HistoricalPlayerBaseline:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"missing historical player source database: {self.database_path}")
        selected_player = str(player_id).strip().upper()
        if not selected_player:
            raise ValueError("player_id is required")
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            tables = _workbook_tables(connection)
            info = _first_player_row(connection, tables, "Player Info", selected_player)
            season_info = _best_season_player_row(connection, tables, "Player Season Info", selected_player, season)
            source_team = str(season_info.get("team") or "").strip().upper()
            per_game = _best_season_player_row(connection, tables, "Player Per Game", selected_player, season, team=source_team)
            totals = _best_season_player_row(connection, tables, "Player Totals", selected_player, season, team=source_team, required=False)
            advanced = _best_season_player_row(connection, tables, "Advanced", selected_player, season, team=source_team, required=False)
            shooting = _best_season_player_row(connection, tables, "Player Shooting", selected_player, season, team=source_team, required=False)
        source_tables = tuple(
            sheet
            for sheet, row in (
                ("Player Info", info),
                ("Player Season Info", season_info),
                ("Player Per Game", per_game),
                ("Player Totals", totals),
                ("Advanced", advanced),
                ("Player Shooting", shooting),
            )
            if row
        )
        return HistoricalPlayerBaseline(
            link=HistoricalPlayerStatLink(
                player_id=selected_player,
                season=int(season),
                source_database=str(self.database_path),
                source_tables=source_tables,
            ),
            player_info=info,
            season_info=season_info,
            per_game=per_game,
            totals=totals,
            advanced=advanced,
            shooting=shooting,
        )


def evaluate_player_progression(
    snapshot: InGamePlayerSnapshot,
    historical_provider: HistoricalStatsProvider | None = None,
    *,
    historical_season: int | None = None,
) -> PlayerProgressionReport:
    provider = historical_provider or HistoricalSQLiteStatsProvider()
    baseline = provider.player_baseline(player_id=snapshot.player_id, season=int(historical_season or snapshot.season))
    role_summary = _role_summary(snapshot)
    progression: list[SkillAdjustment] = []
    regression: list[SkillAdjustment] = []
    reasons: list[str] = []

    three_adjustments, three_reasons = _three_point_adjustments(snapshot, baseline, role_summary)
    for adjustment in three_adjustments:
        if adjustment.delta >= 0:
            progression.append(adjustment)
        else:
            regression.append(adjustment)
    reasons.extend(three_reasons)

    if not progression and not regression:
        reasons.append("No skill changes recommended; in-game production is explained by role context or lacks enough sample.")

    return PlayerProgressionReport(
        season=snapshot.season,
        player_id=snapshot.player_id,
        team_id=snapshot.team_id,
        historical_link=baseline.link,
        role_summary=role_summary,
        progression=tuple(progression),
        regression=tuple(regression),
        reasons=tuple(reasons),
    )


def report_to_storage_payload(report: PlayerProgressionReport) -> dict[str, Any]:
    """Serialize a report without copying IRL stat values into franchise DB."""

    return {
        "season": report.season,
        "player_id": report.player_id,
        "team_id": report.team_id,
        "historical_link": {
            "player_id": report.historical_link.player_id,
            "season": report.historical_link.season,
            "source_database": report.historical_link.source_database,
            "source_tables": list(report.historical_link.source_tables),
        },
        "role_summary": dict(report.role_summary),
        "progression": [_adjustment_payload(adjustment) for adjustment in report.progression],
        "regression": [_adjustment_payload(adjustment) for adjustment in report.regression],
        "reasons": list(report.reasons),
    }


def report_from_storage_payload(payload: dict[str, Any]) -> PlayerProgressionReport:
    link_data = dict(payload.get("historical_link") or {})
    link = HistoricalPlayerStatLink(
        player_id=str(link_data.get("player_id") or payload.get("player_id") or ""),
        season=int(link_data.get("season") or payload.get("season") or 0),
        source_database=str(link_data.get("source_database") or ""),
        source_tables=tuple(str(table) for table in link_data.get("source_tables") or ()),
    )
    return PlayerProgressionReport(
        season=int(payload["season"]),
        player_id=str(payload["player_id"]),
        team_id=str(payload.get("team_id") or ""),
        historical_link=link,
        role_summary=dict(payload.get("role_summary") or {}),
        progression=tuple(_adjustment_from_payload(row) for row in payload.get("progression") or ()),
        regression=tuple(_adjustment_from_payload(row) for row in payload.get("regression") or ()),
        reasons=tuple(str(reason) for reason in payload.get("reasons") or ()),
    )


def snapshot_to_storage_payload(snapshot: InGamePlayerSnapshot) -> dict[str, Any]:
    return {
        "season": snapshot.season,
        "player_id": snapshot.player_id,
        "team_id": snapshot.team_id,
        "attributes": dict(snapshot.attributes),
        "tendencies": dict(snapshot.tendencies),
        "in_game_stats": dict(snapshot.in_game_stats),
        "role": dict(snapshot.role),
    }


def snapshot_from_storage_payload(payload: dict[str, Any]) -> InGamePlayerSnapshot:
    return InGamePlayerSnapshot(
        season=int(payload["season"]),
        player_id=str(payload["player_id"]),
        team_id=str(payload.get("team_id") or ""),
        attributes=dict(payload.get("attributes") or {}),
        tendencies=dict(payload.get("tendencies") or {}),
        in_game_stats=dict(payload.get("in_game_stats") or {}),
        role=dict(payload.get("role") or {}),
    )


def _three_point_adjustments(
    snapshot: InGamePlayerSnapshot,
    baseline: HistoricalPlayerBaseline,
    role_summary: dict[str, Any],
) -> tuple[list[SkillAdjustment], list[str]]:
    made = _number_from_keys(snapshot.in_game_stats, "3POINTERSMADE", "3PM", "THREEPOINTERSMADE", "three_pointers_made")
    attempted = _number_from_keys(snapshot.in_game_stats, "3POINTERSATTEMPTED", "3PA", "THREEPOINTERSATTEMPTED", "three_pointers_attempted")
    if made is None or attempted is None or attempted < 12:
        return [], ["3PT skill held: imported 3PT sample is missing or too small."]

    in_game_pct = made / max(attempted, 1.0)
    historical_pct = _number_from_keys(baseline.per_game, "x3p_percent")
    if historical_pct is None:
        historical_pct = _number_from_keys(baseline.shooting, "corner_3_point_percent")
    if historical_pct is None:
        historical_pct = 0.0

    open_quality = _bounded_float(role_summary.get("open_look_quality"), 0.0, 1.0, 0.5)
    creation_load = _bounded_float(role_summary.get("shot_creation_load"), 0.0, 1.0, 0.5)
    team_quality = _bounded_float(role_summary.get("team_quality"), 0.0, 1.0, 0.5)
    role_adjusted_expectation = historical_pct + (open_quality - 0.5) * 0.12 - creation_load * 0.08 + (team_quality - 0.5) * 0.04
    pct_signal = in_game_pct - role_adjusted_expectation
    current_three = _int_from_keys(snapshot.attributes, "Attributes/3POINT", "3POINT", "3pt Shot", "3PT")
    current_spot_up = _int_from_keys(snapshot.tendencies, "Tendencies/3POINTSPOTUPSHOT", "3POINTSPOTUPSHOT", "Spot Up Shot 3pt")
    current_pull_up = _int_from_keys(snapshot.tendencies, "Tendencies/DRIVEPULLUP3POINT", "DRIVEPULLUP3POINT", "Drive Pull Up 3pt")
    current_stepback = _int_from_keys(snapshot.tendencies, "Tendencies/STEPBACKJUMPER3POINT", "STEPBACKJUMPER3POINT", "Stepback Jumper 3pt")

    adjustments: list[SkillAdjustment] = []
    reasons: list[str] = []
    shared_evidence = {
        "in_game_stat_keys": ("3POINTERSMADE", "3POINTERSATTEMPTED"),
        "historical_link": {"player_id": baseline.link.player_id, "season": baseline.link.season, "tables": baseline.link.source_tables},
        "role_keys": ("open_look_quality", "shot_creation_load", "team_quality"),
    }

    if pct_signal >= 0.045:
        delta = 2 if creation_load >= 0.35 else 1
        adjustments.append(_adjustment("Attributes", "3POINT", current_three, delta, "progression", "3PT skill improved after role-adjusted in-game shooting beat historical expectation.", shared_evidence))
        reasons.append("3PT increase: in-game percentage beat the player-linked historical baseline after accounting for role difficulty.")
    elif pct_signal <= -0.065 and creation_load < 0.45 and open_quality >= 0.45:
        adjustments.append(_adjustment("Attributes", "3POINT", current_three, -2, "regression", "3PT skill declined because poor efficiency came from clean enough looks, not hard-shot role burden.", shared_evidence))
        reasons.append("3PT regression: poor in-game shooting came in a role that should have produced clean looks.")
    elif pct_signal <= -0.065:
        reasons.append("3PT attribute protected: efficiency fell, but shot-creation load/team context explains much of the drop.")

    if open_quality >= 0.65 and in_game_pct >= role_adjusted_expectation:
        adjustments.append(_adjustment("Tendencies", "3POINTSPOTUPSHOT", current_spot_up, 2, "progression", "Spot-up 3PT tendency rose because the player converted open catch-and-shoot chances.", shared_evidence))
    if creation_load >= 0.65 and in_game_pct < role_adjusted_expectation:
        if current_pull_up is not None:
            adjustments.append(_adjustment("Tendencies", "DRIVEPULLUP3POINT", current_pull_up, -2, "regression", "Pull-up 3PT tendency reduced because hard self-created threes hurt efficiency.", shared_evidence))
        if current_stepback is not None:
            adjustments.append(_adjustment("Tendencies", "STEPBACKJUMPER3POINT", current_stepback, -2, "regression", "Stepback 3PT tendency reduced because hard self-created threes hurt efficiency.", shared_evidence))
        reasons.append("3PT tendency correction: role indicates too many difficult self-created threes.")

    return adjustments, reasons


def _role_summary(snapshot: InGamePlayerSnapshot) -> dict[str, Any]:
    role = dict(snapshot.role)
    tendencies = snapshot.tendencies
    spot_up = _number_from_keys(role, "spot_up_share", "open_look_quality")
    creation = _number_from_keys(role, "shot_creation_load", "self_created_three_share")
    if spot_up is None:
        spot = _number_from_keys(tendencies, "3POINTSPOTUPSHOT", "Spot Up Shot 3pt") or 0.0
        pull = _number_from_keys(tendencies, "DRIVEPULLUP3POINT", "Drive Pull Up 3pt") or 0.0
        step = _number_from_keys(tendencies, "STEPBACKJUMPER3POINT", "Stepback Jumper 3pt") or 0.0
        contested = _number_from_keys(tendencies, "CONTESTEDJUMPER3POINT", "Contested Jumper 3pt") or 0.0
        total = spot + pull + step + contested
        spot_up = 0.5 if total <= 0 else spot / total
    if creation is None:
        spot = _number_from_keys(tendencies, "3POINTSPOTUPSHOT", "Spot Up Shot 3pt") or 0.0
        pull = _number_from_keys(tendencies, "DRIVEPULLUP3POINT", "Drive Pull Up 3pt") or 0.0
        step = _number_from_keys(tendencies, "STEPBACKJUMPER3POINT", "Stepback Jumper 3pt") or 0.0
        total = spot + pull + step
        creation = 0.5 if total <= 0 else (pull + step) / total
    return {
        "role_name": str(role.get("role_name") or role.get("role") or "unspecified"),
        "minutes_per_game": _number_from_keys(role, "minutes_per_game", "mpg", "MINUTES") or _number_from_keys(snapshot.in_game_stats, "MINUTESPERGAME", "MPG"),
        "usage_rate": _number_from_keys(role, "usage_rate", "usage", "USG") or _number_from_keys(snapshot.in_game_stats, "USAGE", "USG"),
        "open_look_quality": round(_bounded_float(spot_up, 0.0, 1.0, 0.5), 4),
        "shot_creation_load": round(_bounded_float(creation, 0.0, 1.0, 0.5), 4),
        "team_quality": round(_bounded_float(role.get("team_quality"), 0.0, 1.0, 0.5), 4),
    }


def _adjustment(category: str, field_name: str, current: int | None, delta: int, direction: str, reason: str, evidence: dict[str, Any]) -> SkillAdjustment:
    target = None if current is None else _bounded_int(current + delta, 0 if category == "Tendencies" else 25, 100 if category == "Tendencies" else 99)
    return SkillAdjustment(category, field_name, current, delta, target, direction, reason, dict(evidence))


def _adjustment_payload(adjustment: SkillAdjustment) -> dict[str, Any]:
    return {
        "category": adjustment.category,
        "field_name": adjustment.field_name,
        "current_value": adjustment.current_value,
        "delta": adjustment.delta,
        "target_value": adjustment.target_value,
        "direction": adjustment.direction,
        "reason": adjustment.reason,
        "evidence": dict(adjustment.evidence),
    }


def _adjustment_from_payload(payload: dict[str, Any]) -> SkillAdjustment:
    return SkillAdjustment(
        category=str(payload["category"]),
        field_name=str(payload["field_name"]),
        current_value=payload.get("current_value"),
        delta=int(payload["delta"]),
        target_value=payload.get("target_value"),
        direction=str(payload["direction"]),
        reason=str(payload["reason"]),
        evidence=dict(payload.get("evidence") or {}),
    )


def _workbook_tables(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT sheet_name, table_name FROM workbook_tables").fetchall()
    return {str(row["sheet_name"]): str(row["table_name"]) for row in rows}


def _first_player_row(connection: sqlite3.Connection, tables: dict[str, str], sheet: str, player_id: str) -> dict[str, Any]:
    table = tables[sheet]
    row = connection.execute(f'SELECT * FROM "{table}" WHERE UPPER(player_id) = ? LIMIT 1', (player_id,)).fetchone()
    if row is None:
        raise KeyError(f"missing historical {sheet} row for player_id={player_id}")
    return dict(row)


def _best_season_player_row(
    connection: sqlite3.Connection,
    tables: dict[str, str],
    sheet: str,
    player_id: str,
    season: int,
    *,
    team: str | None = None,
    required: bool = True,
) -> dict[str, Any]:
    table = tables.get(sheet)
    if table is None:
        if required:
            raise KeyError(f"missing historical sheet: {sheet}")
        return {}
    rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" WHERE UPPER(player_id) = ? AND season = ?', (player_id, int(season))).fetchall()]
    if team:
        for row in rows:
            if str(row.get("team") or row.get("tm") or "").strip().upper() == str(team).strip().upper():
                return row
    for row in rows:
        if str(row.get("team") or row.get("tm") or "").strip().upper() in {"TOT", "2TM", "3TM", "4TM", "5TM"}:
            return row
    if rows:
        return rows[0]
    if required:
        raise KeyError(f"missing historical {sheet} row for player_id={player_id} season={season}")
    return {}


def _number_from_keys(mapping: dict[str, Any], *keys: str) -> float | None:
    normalized = {_normalize_key(key): value for key, value in mapping.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        number = _number(value)
        if number is not None:
            return number
    return None


def _int_from_keys(mapping: dict[str, Any], *keys: str) -> int | None:
    number = _number_from_keys(mapping, *keys)
    return None if number is None else int(round(number))


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _normalize_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _bounded_float(value: Any, low: float, high: float, default: float) -> float:
    number = _number(value)
    if number is None:
        number = default
    return max(low, min(high, number))


def _bounded_int(value: int | float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


__all__ = [
    "HistoricalPlayerBaseline",
    "HistoricalPlayerStatLink",
    "HistoricalSQLiteStatsProvider",
    "HistoricalStatsProvider",
    "InGamePlayerSnapshot",
    "PlayerProgressionReport",
    "SkillAdjustment",
    "evaluate_player_progression",
    "report_from_storage_payload",
    "report_to_storage_payload",
    "snapshot_from_storage_payload",
    "snapshot_to_storage_payload",
]
