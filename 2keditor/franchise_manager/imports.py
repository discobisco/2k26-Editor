from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nba2k_editor.models.schema import FieldEntry, RecordListItem

_STANDINGS_FIELDS: dict[str, str] = {
    "wins": "W",
    "losses": "L",
}

_TEAM_STAT_FIELDS: dict[str, str] = {
    "points": "POINTS",
    "points_allowed": "PA",
    "field_goals_made": "MADE",
    "field_goals_attempted": "ATTEMPTED",
    "three_pointers_made": "3POINTMADE",
    "three_pointers_attempted": "3POINTATTEMPTED",
    "free_throws_made": "FREETHROWMADE",
    "free_throws_attempted": "FREETHROWATTEMPTED",
    "offensive_rebounds": "OFFENSIVEREBOUNDS",
    "defensive_rebounds": "DEFENSEREBOUNDS",
    "assists": "ASSISTS",
    "steals": "STEALS",
    "blocks": "BLOCKS",
    "fouls": "FOUL",
    "turnovers": "TURNOVER",
    "possessions": "POSS",
    "pace": "PACE",
}

@dataclass(frozen=True)
class TeamOffsetImportResult:
    standings_payload: dict[str, dict[str, int]]
    team_stats_payload: dict[str, dict[str, int]]

    @property
    def standings_rows(self) -> int:
        return len(self.standings_payload)

    @property
    def team_stat_rows(self) -> int:
        return len(self.team_stats_payload)


def import_team_offsets(model: Any, *, team_limit: int | None = 30) -> TeamOffsetImportResult:
    """Read Franchise Manager import data from authored Teams offsets.

    This is a read/import bridge only. It does not simulate games and does not
    guess missing offsets. Missing fields are skipped so Franchise Manager can
    still use the live Teams data that is currently authored.
    """
    entries = _team_entries_by_name(model)
    teams = tuple(model.scan_records("Teams", limit=team_limit))
    standings_payload: dict[str, dict[str, int]] = {}
    team_stats_payload: dict[str, dict[str, int]] = {}
    for team in teams:
        team_key = _team_payload_key(team)

        standings_row: dict[str, int] = {}
        for payload_name, offset_name in _STANDINGS_FIELDS.items():
            entry = entries.get(_field_identity(offset_name))
            if entry is None:
                continue
            value = _read_optional_int(model, entry, team.index)
            if value is not None:
                standings_row[payload_name] = value
        if standings_row:
            standings_payload[team_key] = standings_row

        team_stats_row: dict[str, int] = {}
        for payload_name, offset_name in _TEAM_STAT_FIELDS.items():
            entry = entries.get(_field_identity(offset_name))
            if entry is None:
                continue
            value = _read_optional_int(model, entry, team.index)
            if value is not None:
                team_stats_row[payload_name] = value
        if team_stats_row:
            team_stats_payload[team_key] = team_stats_row
    return TeamOffsetImportResult(standings_payload=standings_payload, team_stats_payload=team_stats_payload)


def _team_entries_by_name(model: Any) -> dict[str, FieldEntry]:
    grouped = model.grouped_fields("Teams")
    entries: dict[str, FieldEntry] = {}
    for groups in grouped.values():
        for field_entries in groups.values():
            for entry in field_entries:
                entries[_field_identity(entry.normalized_name)] = entry
                entries[_field_identity(entry.display_name)] = entry
    return entries


def _read_int(model: Any, entry: FieldEntry, index: int) -> int:
    value = _read_optional_int(model, entry, index)
    if value is None:
        raise ValueError(f"Teams offset {entry.normalized_name} for row {index} is not numeric")
    return value


def _read_optional_int(model: Any, entry: FieldEntry, index: int) -> int | None:
    value = model.read_entry_value(entry, index=index).get("raw_value")
    if value in (None, ""):
        value = model.read_entry_value(entry, index=index).get("display_value")
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except Exception as exc:
        raise ValueError(f"Teams offset {entry.normalized_name} for row {index} is not numeric: {value!r}") from exc


def _team_payload_key(team: RecordListItem) -> str:
    text = str(team.label).strip()
    return text or f"Team {team.index}"


def _field_identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


__all__ = ["TeamOffsetImportResult", "import_team_offsets"]
