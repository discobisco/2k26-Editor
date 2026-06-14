from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contracts import GeneratorInputContract
from workbook_sqlite import read_sqlite_sheet_rows_for_season

_PLAYER_SEASON_INFO_SHEET = "Player Season Info"
_OPTIONAL_PLAYER_SHEETS: tuple[str, ...] = (
    "Player Per 100 Poss",
    "Advanced",
    "Player Shooting",
    "Player Play by Play",
)
_OPTIONAL_TEAM_CONTEXT_SHEETS: tuple[str, ...] = (
    "Team Stats Per Game",
    "Team Stats Per 100 Pos",
    "Team Summaries",
    "Opponent Stats Per Game",
    "Opponent Stats Per 100 Poss",
)


@dataclass(frozen=True)
class TeamRosterEvidence:
    season: int
    team: str
    roster_rows: tuple[dict[str, Any], ...]
    player_ids: tuple[str, ...]
    player_count: int
    missing_sources: tuple[str, ...]


def build_team_roster_evidence(contract: GeneratorInputContract, *, team: str) -> TeamRosterEvidence:
    validated = contract.validate()
    selected_team = str(team).strip()
    if not selected_team:
        raise ValueError("team is required")

    season_rows = tuple(read_sqlite_sheet_rows_for_season(validated.source_root, _PLAYER_SEASON_INFO_SHEET, int(validated.season)))
    roster_rows = tuple(row for row in _canonical_roster_rows(season_rows) if _same(row.get("team"), selected_team))
    if not roster_rows:
        raise KeyError(f"missing roster rows for team={selected_team} season={validated.season}")

    player_ids = tuple(str(row.get("player_id") or "").strip() for row in roster_rows if str(row.get("player_id") or "").strip())
    missing_sources = _missing_sources_for_roster(validated, selected_team, set(player_ids))

    return TeamRosterEvidence(
        season=int(validated.season),
        team=selected_team,
        roster_rows=roster_rows,
        player_ids=player_ids,
        player_count=len(roster_rows),
        missing_sources=missing_sources,
    )


def _missing_sources_for_roster(contract: GeneratorInputContract, team: str, player_ids: set[str]) -> tuple[str, ...]:
    missing: list[str] = []
    for sheet in _OPTIONAL_PLAYER_SHEETS:
        rows = tuple(row for row in read_sqlite_sheet_rows_for_season(contract.source_root, sheet, int(contract.season)) if _same(row.get("team"), team))
        present_ids = {str(row.get("player_id") or "").strip() for row in rows if str(row.get("player_id") or "").strip()}
        if not rows or not player_ids.intersection(present_ids):
            missing.append(sheet)
    for sheet in _OPTIONAL_TEAM_CONTEXT_SHEETS:
        rows = tuple(row for row in read_sqlite_sheet_rows_for_season(contract.source_root, sheet, int(contract.season)) if _same(row.get("abbreviation"), team))
        if not rows:
            missing.append(sheet)
    return tuple(dict.fromkeys(missing))


def _canonical_roster_rows(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    primary_by_player = _multi_team_primary_teams(rows)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if _is_multi_team_marker(team):
            continue
        primary = primary_by_player.get(player_id)
        if primary and team != primary:
            continue
        filtered.append(row)
    return tuple(filtered)


def _multi_team_primary_teams(rows: tuple[dict[str, Any], ...]) -> dict[str, str]:
    saw_multi: set[str] = set()
    primary: dict[str, str] = {}
    for row in rows:
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if not player_id or not team:
            continue
        if _is_multi_team_marker(team):
            saw_multi.add(player_id)
            continue
        if player_id in saw_multi:
            primary.setdefault(player_id, team)
    return primary


def _is_multi_team_marker(team: object) -> bool:
    text = str(team or "").strip().upper()
    return len(text) == 3 and text[0].isdigit() and text[1:] == "TM"


def _same(left: Any, right: str) -> bool:
    return str(left or "").strip().upper() == str(right or "").strip().upper()


__all__ = ["TeamRosterEvidence", "build_team_roster_evidence"]
