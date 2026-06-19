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
    guess missing offsets. If required standings offsets are not active for the
    selected game target, it raises with the exact missing offset names.
    """
    entries = _team_entries_by_name(model)
    _require_offsets(entries, tuple(_STANDINGS_FIELDS.values()))
    teams = tuple(model.scan_records("Teams", limit=team_limit))
    standings_payload: dict[str, dict[str, int]] = {}
    team_stats_payload: dict[str, dict[str, int]] = {}
    for team in teams:
        team_key = _team_payload_key(team)
        standings_payload[team_key] = {
            payload_name: _read_int(model, entries[offset_name], team.index)
            for payload_name, offset_name in _STANDINGS_FIELDS.items()
        }
        team_stats_payload[team_key] = {
            payload_name: _read_int(model, entries[offset_name], team.index) if offset_name in entries else 0
            for payload_name, offset_name in _TEAM_STAT_FIELDS.items()
        }
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


def _require_offsets(entries: dict[str, FieldEntry], names: tuple[str, ...]) -> None:
    missing = tuple(name for name in names if _field_identity(name) not in entries)
    if missing:
        raise RuntimeError("missing active Teams offsets for Franchise import: " + ", ".join(missing))


def _read_int(model: Any, entry: FieldEntry, index: int) -> int:
    value = model.read_entry_value(entry, index=index).get("raw_value")
    if value in (None, ""):
        value = model.read_entry_value(entry, index=index).get("display_value")
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
