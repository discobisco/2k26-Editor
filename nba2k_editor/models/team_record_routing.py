from __future__ import annotations

from typing import Any

from nba2k_editor.models.data_model import target_display_label
from nba2k_editor.models.schema import _selected_record_source

TEAM_RECORD_SIDE_NAV: tuple[str, ...] = ("Single Game (Regular)", "Single Game (Playoffs)", "Season", "Career")
TEAM_RECORD_BASE_STAT_TABS: tuple[str, ...] = (
    "Points",
    "FG Made",
    "3PT Made",
    "FT Made",
    "Rebounds",
    "Assists",
    "Blocks",
    "Steals",
    "Minutes",
    "Turnovers",
)
TEAM_RECORD_EXTENDED_STAT_TABS: tuple[str, ...] = (
    *TEAM_RECORD_BASE_STAT_TABS,
    "PPG",
    "FG%",
    "3PT%",
    "FT%",
    "RPG",
    "APG",
    "BPG",
    "SPG",
    "MPG",
    "Games Played",
    "Fouls",
    "40+ Point Games",
    "50+ Point Games",
    "60+ Point Games",
    "Triple Doubles",
)
TEAM_RECORD_SECTION_STAT_TABS: dict[str, tuple[str, ...]] = {
    "Single Game (Regular)": TEAM_RECORD_BASE_STAT_TABS,
    "Single Game (Playoffs)": TEAM_RECORD_BASE_STAT_TABS,
    "Season": TEAM_RECORD_EXTENDED_STAT_TABS,
    "Career": TEAM_RECORD_EXTENDED_STAT_TABS,
}
TEAM_RECORD_SECTION_ROW_LAYOUT: dict[str, tuple[int, int]] = {
    "Single Game (Regular)": (0, 5),
    "Single Game (Playoffs)": (50, 5),
    "Season": (100, 10),
    "Career": (300, 10),
}
TEAM_RECORD_BLOCK_SIZE = 510


def team_record_row_group(section: str, stat: str) -> tuple[int, int]:
    section_start, row_count = TEAM_RECORD_SECTION_ROW_LAYOUT.get(section, TEAM_RECORD_SECTION_ROW_LAYOUT["Single Game (Regular)"])
    tabs = TEAM_RECORD_SECTION_STAT_TABS.get(section, TEAM_RECORD_BASE_STAT_TABS)
    stat_index = tabs.index(stat) if stat in tabs else 0
    return section_start + stat_index * row_count, row_count


def _selected_record_source_entry(model: Any, *, role: str, target_domain: str) -> Any | None:
    active_version = target_display_label(model.target_executable).replace("NBA ", "")
    for entry in model._layout_entries("Teams"):
        source = _selected_record_source(entry.field)
        if source is None:
            continue
        source_versions = source.get("versions")
        if isinstance(source_versions, list) and active_version not in {str(version) for version in source_versions}:
            continue
        if str(source.get("role") or "") == role and str(source.get("target_domain") or "") == target_domain:
            return entry
    return None


def _team_record_start_index(source: dict[str, Any], item: Any) -> int | None:
    if "start_index" not in source:
        return None
    row_count = int(source.get("row_count") or TEAM_RECORD_BLOCK_SIZE)
    return int(source["start_index"]) + int(item.index) * row_count


def team_record_rows(model: Any, item: Any, section: str, stat: str) -> list[dict[str, str]]:
    entry = _selected_record_source_entry(model, role="team_record_start", target_domain="NBA Records")
    if entry is None:
        return []
    source = _selected_record_source(entry.field) or {}
    row_start, row_count = team_record_row_group(section, stat)
    start_index = _team_record_start_index(source, item)
    if start_index is None:
        return []
    row_count = min(int(row_count), max(0, TEAM_RECORD_BLOCK_SIZE - int(row_start)))
    if row_count <= 0:
        return []
    return model.record_summary_rows(
        "NBA Records",
        limit=row_count,
        record_row_start=int(start_index) + int(row_start),
        record_row_count=row_count,
    )
