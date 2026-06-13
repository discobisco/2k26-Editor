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

    roster_rows = tuple(row for row in read_sqlite_sheet_rows_for_season(validated.source_root, _PLAYER_SEASON_INFO_SHEET, int(validated.season)) if _same(row.get("team"), selected_team))
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


def _same(left: Any, right: str) -> bool:
    return str(left or "").strip().upper() == str(right or "").strip().upper()


__all__ = ["TeamRosterEvidence", "build_team_roster_evidence"]
