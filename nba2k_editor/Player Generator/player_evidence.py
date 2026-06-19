from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from contracts import GeneratorInputContract
from workbook_sqlite import ensure_workbook_sqlite_database, iter_workbook_sqlite_sheet_rows, workbook_sqlite_sheet_names

_PLAYER_IDENTITY_SHEET = "Player Info"
_PLAYER_SEASON_INFO_SHEET = "Player Season Info"
_PLAYER_PER_GAME_SHEET = "Player Per Game"
_PLAYER_TOTALS_SHEET = "Player Totals"
_PLAYER_PER_36_SHEET = "Player Per 36 min"
_PLAYER_PER_100_SHEET = "Player Per 100 Poss"
_PLAYER_ADVANCED_SHEET = "Advanced"
_PLAYER_SHOOTING_SHEET = "Player Shooting"
_PLAYER_PLAY_BY_PLAY_SHEET = "Player Play by Play"
_TEAM_STATS_PER_GAME_SHEET = "Team Stats Per Game"
_TEAM_STATS_PER_100_SHEET = "Team Stats Per 100 Pos"
_TEAM_SUMMARY_SHEET = "Team Summaries"
_OPPONENT_STATS_PER_GAME_SHEET = "Opponent Stats Per Game"
_OPPONENT_STATS_PER_100_SHEET = "Opponent Stats Per 100 Poss"
_PLAYER_CAREER_CONTEXT_SHEETS = {
    "Draft Picks",
    _PLAYER_IDENTITY_SHEET,
    "All Star Selections",
    "All Teams",
    "Player Award Shares",
    "All team Voting",
}
_SEASON_SCOPED_PLAYER_CONTEXT_SHEETS = {
    "All Star Selections",
    "All Teams",
    "Player Award Shares",
    "All team Voting",
}


@dataclass(frozen=True)
class PlayerEvidence:
    player_id: str
    season: int
    team: str
    identity: dict[str, Any]
    season_info: dict[str, Any]
    per_game: dict[str, Any]
    totals: dict[str, Any]
    per_36: dict[str, Any]
    per_100: dict[str, Any]
    advanced: dict[str, Any]
    shooting: dict[str, Any]
    play_by_play: dict[str, Any]
    team_roster: tuple[dict[str, Any], ...]
    team_stats_per_game: dict[str, Any]
    team_stats_per_100: dict[str, Any]
    team_summary: dict[str, Any]
    opponent_stats_per_game: dict[str, Any]
    opponent_stats_per_100: dict[str, Any]
    source_context: dict[str, Any]
    missing_sources: tuple[str, ...]


def build_player_evidence(contract: GeneratorInputContract, *, player_id: str, team: str) -> PlayerEvidence:
    validated = contract.validate()
    requested_player_id = str(player_id).strip()
    requested_team = str(team).strip()
    if not requested_player_id:
        raise ValueError("player_id is required")
    if not requested_team:
        raise ValueError("team is required")

    database_path = ensure_workbook_sqlite_database(validated.source_root)
    missing: list[str] = []

    identity = _find_player_identity(database_path, requested_player_id)
    season_info = _required_player_row(validated, _PLAYER_SEASON_INFO_SHEET, requested_player_id, requested_team)
    per_game = _required_player_row(validated, _PLAYER_PER_GAME_SHEET, requested_player_id, requested_team)
    totals = _optional_player_row(validated, _PLAYER_TOTALS_SHEET, requested_player_id, requested_team, missing)
    per_36 = _optional_player_row(validated, _PLAYER_PER_36_SHEET, requested_player_id, requested_team, missing)
    per_100 = _optional_player_row(validated, _PLAYER_PER_100_SHEET, requested_player_id, requested_team, missing)
    advanced = _optional_player_row(validated, _PLAYER_ADVANCED_SHEET, requested_player_id, requested_team, missing)
    shooting = _optional_player_row(validated, _PLAYER_SHOOTING_SHEET, requested_player_id, requested_team, missing)
    play_by_play = _optional_player_row(validated, _PLAYER_PLAY_BY_PLAY_SHEET, requested_player_id, requested_team, missing)
    team_roster = _team_roster(validated, requested_team)

    team_stats_per_game = _optional_team_row(validated, _TEAM_STATS_PER_GAME_SHEET, requested_team, missing)
    team_stats_per_100 = _optional_team_row(validated, _TEAM_STATS_PER_100_SHEET, requested_team, missing)
    team_summary = _optional_team_row(validated, _TEAM_SUMMARY_SHEET, requested_team, missing)
    opponent_stats_per_game = _optional_team_row(validated, _OPPONENT_STATS_PER_GAME_SHEET, requested_team, missing)
    opponent_stats_per_100 = _optional_team_row(validated, _OPPONENT_STATS_PER_100_SHEET, requested_team, missing)

    return PlayerEvidence(
        player_id=requested_player_id,
        season=int(validated.season),
        team=requested_team,
        identity=identity,
        season_info=season_info,
        per_game=per_game,
        totals=totals,
        per_36=per_36,
        per_100=per_100,
        advanced=advanced,
        shooting=shooting,
        play_by_play=play_by_play,
        team_roster=team_roster,
        team_stats_per_game=team_stats_per_game,
        team_stats_per_100=team_stats_per_100,
        team_summary=team_summary,
        opponent_stats_per_game=opponent_stats_per_game,
        opponent_stats_per_100=opponent_stats_per_100,
        source_context=_source_context(validated, requested_player_id, requested_team),
        missing_sources=tuple(dict.fromkeys(missing)),
    )


def _find_player_identity(database_path: str | object, player_id: str) -> dict[str, Any]:
    row = _identity_rows(str(database_path)).get(str(player_id).strip().upper())
    if row:
        return row
    raise KeyError(f"missing player identity row: {player_id}")


def _required_player_row(contract: GeneratorInputContract, sheet: str, player_id: str, team: str) -> dict[str, Any]:
    row = _find_player_row(contract, sheet, player_id, team)
    if row:
        return row
    raise KeyError(f"missing required {sheet} row for player_id={player_id} team={team} season={contract.season}")


def _optional_player_row(
    contract: GeneratorInputContract,
    sheet: str,
    player_id: str,
    team: str,
    missing_sources: list[str],
) -> dict[str, Any]:
    row = _find_player_row(contract, sheet, player_id, team)
    if row:
        return row
    missing_sources.append(sheet)
    return {}


def _find_player_row(contract: GeneratorInputContract, sheet: str, player_id: str, team: str) -> dict[str, Any]:
    database_path = ensure_workbook_sqlite_database(contract.source_root)
    key = (str(player_id).strip().upper(), str(team).strip().upper())
    return _player_rows_by_key(str(database_path), int(contract.season), sheet).get(key, {})


def _team_roster(contract: GeneratorInputContract, team: str) -> tuple[dict[str, Any], ...]:
    database_path = ensure_workbook_sqlite_database(contract.source_root)
    rows = _team_rosters(str(database_path), int(contract.season)).get(str(team).strip().upper(), ())
    if not rows:
        raise KeyError(f"missing team roster rows for team={team} season={contract.season}")
    return rows


def _optional_team_row(
    contract: GeneratorInputContract,
    sheet: str,
    team: str,
    missing_sources: list[str],
) -> dict[str, Any]:
    database_path = ensure_workbook_sqlite_database(contract.source_root)
    row = _team_rows_by_abbreviation(str(database_path), int(contract.season), sheet).get(str(team).strip().upper())
    if row:
        return row
    missing_sources.append(sheet)
    return {}


@lru_cache(maxsize=1)
def _identity_rows(database_path: str) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("player_id") or "").strip().upper(): row
        for row in iter_workbook_sqlite_sheet_rows(database_path, _PLAYER_IDENTITY_SHEET)
        if row.get("player_id")
    }


@lru_cache(maxsize=None)
def _player_rows_by_key(database_path: str, season: int, sheet: str) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in iter_workbook_sqlite_sheet_rows(database_path, sheet):
        if row.get("season") != int(season):
            continue
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if player_id and team:
            rows.setdefault((player_id, team), row)
    return rows


@lru_cache(maxsize=None)
def _team_rosters(database_path: str, season: int) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in iter_workbook_sqlite_sheet_rows(database_path, _PLAYER_SEASON_INFO_SHEET):
        if row.get("season") != int(season):
            continue
        team = str(row.get("team") or "").strip().upper()
        if team:
            grouped.setdefault(team, []).append(row)
    return {team: tuple(rows) for team, rows in grouped.items()}


@lru_cache(maxsize=None)
def _team_rows_by_abbreviation(database_path: str, season: int, sheet: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in iter_workbook_sqlite_sheet_rows(database_path, sheet):
        if row.get("season") != int(season):
            continue
        abbreviation = str(row.get("abbreviation") or "").strip().upper()
        if abbreviation:
            rows.setdefault(abbreviation, row)
    return rows


def _same(left: Any, right: str) -> bool:
    return str(left or "").strip().upper() == str(right).strip().upper()


def _source_context(contract: GeneratorInputContract, player_id: str, team: str) -> dict[str, Any]:
    database_path = ensure_workbook_sqlite_database(contract.source_root)
    selected_player = str(player_id).strip().upper()
    selected_team = str(team).strip().upper()
    context: dict[str, Any] = {"player_id": selected_player, "team": selected_team, "season": int(contract.season)}
    for sheet in workbook_sqlite_sheet_names(database_path):
        prefix = sheet.lower().replace(" ", "_")
        for row in iter_workbook_sqlite_sheet_rows(database_path, sheet):
            row_season = row.get("season")
            if row_season is not None and row_season != int(contract.season):
                if sheet not in _PLAYER_CAREER_CONTEXT_SHEETS or sheet in _SEASON_SCOPED_PLAYER_CONTEXT_SHEETS:
                    continue
            row_player = str(row.get("player_id") or "").strip().upper()
            row_team = str(row.get("team") or row.get("tm") or "").strip().upper()
            row_abbreviation = str(row.get("abbreviation") or "").strip().upper()
            applies_to_player = row_player == selected_player and (sheet in _PLAYER_CAREER_CONTEXT_SHEETS or not row_team or row_team == selected_team)
            applies_to_team = not row_player and row_abbreviation == selected_team
            if applies_to_player or applies_to_team:
                _merge_source_row(context, prefix, row, include_bare=applies_to_player)
    return context


def _merge_source_row(target: dict[str, Any], prefix: str, row: dict[str, Any], *, include_bare: bool) -> None:
    for column, value in row.items():
        if value is None:
            continue
        target.setdefault(f"{prefix}.{column}", value)
        if include_bare and column not in target:
            target[column] = value


__all__ = ["PlayerEvidence", "build_player_evidence"]
