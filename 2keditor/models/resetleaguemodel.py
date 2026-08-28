from __future__ import annotations

from typing import Any, Callable, Iterable

from nba2k_editor.models.schema import FieldEntry, RecordListItem


_PLAYER_EDITOR_RESET_SECTIONS: tuple[str, ...] = ("Vitals", "Attributes", "Tendencies", "Badges")


class ResetLeagueModel:
    """Build reset snapshots for editor actions without owning writes."""

    def __init__(self, editor_model: Any) -> None:
        self.editor_model = editor_model

    def player_editor_reset_snapshots(
        self,
        item: RecordListItem,
        entries: Iterable[FieldEntry],
        *,
        stat_selector_for_entry: Callable[[FieldEntry], object | None],
    ) -> list[tuple[dict[str, Any], object | None]]:
        base_fields: dict[str, dict[str, object]] = {}
        for entry in self._player_editor_reset_entries(entries):
            value = self._player_editor_reset_value(entry)
            if value is not None:
                base_fields[f"{entry.section}/{entry.normalized_name}"] = {"display_value": value}

        snapshots: list[tuple[dict[str, Any], object | None]] = []
        if base_fields:
            snapshots.append(({"records": [{"index": item.index, "fields": base_fields}]}, None))
        return snapshots

    def _player_editor_reset_entries(self, entries: Iterable[FieldEntry]) -> tuple[FieldEntry, ...]:
        return tuple(entry for entry in entries if entry.section in _PLAYER_EDITOR_RESET_SECTIONS)

    def _player_editor_reset_value(self, entry: FieldEntry) -> object | None:
        if entry.domain != "Players":
            return None
        normalized = str(entry.normalized_name).upper()
        if normalized == "FIRSTNAME":
            return "A"
        if normalized == "LASTNAME":
            return "Z"
        if normalized == "BIRTHYEAR":
            return 2006
        if entry.section == "Attributes":
            return 25
        if entry.section in {"Tendencies", "Badges"}:
            return 0
        return None
