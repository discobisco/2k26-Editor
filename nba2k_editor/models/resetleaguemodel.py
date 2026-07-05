from __future__ import annotations

from collections.abc import Iterable as IterableABC
from typing import Any, Callable, Iterable

from nba2k_editor.models.schema import FieldEntry, RecordListItem


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
        stat_entries: list[FieldEntry] = []
        for entry in entries:
            if self.editor_model.is_player_selected_stat_detail_entry(entry):
                stat_entries.append(entry)
                continue
            value = self._player_editor_reset_value(entry, None)
            if value is not None:
                base_fields[f"{entry.section}/{entry.normalized_name}"] = {"display_value": value}

        snapshots: list[tuple[dict[str, Any], object | None]] = []
        if base_fields:
            snapshots.append(({"records": [{"index": item.index, "fields": base_fields}]}, None))

        selectors = self._player_stat_reset_selectors(item, stat_entries, stat_selector_for_entry)
        stat_fields = self._player_stat_reset_fields(stat_entries)
        for selector in selectors:
            snapshots.append(({"records": [{"index": item.index, "fields": stat_fields}]}, selector))
        return snapshots

    def _player_stat_reset_selectors(
        self,
        item: RecordListItem,
        stat_entries: list[FieldEntry],
        stat_selector_for_entry: Callable[[FieldEntry], object | None],
    ) -> tuple[object, ...]:
        if not stat_entries:
            return ()
        options_fn = getattr(self.editor_model, "player_season_stat_id_options", None)
        if callable(options_fn):
            raw_options = options_fn(item.index)
            if isinstance(raw_options, IterableABC):
                options = tuple(option for option in raw_options if str(option).strip().startswith("["))
                if options:
                    return options
        return tuple(dict.fromkeys(selector for entry in stat_entries if (selector := stat_selector_for_entry(entry)) is not None))

    def _player_stat_reset_fields(self, entries: Iterable[FieldEntry]) -> dict[str, dict[str, object]]:
        fields: dict[str, dict[str, object]] = {}
        for entry in entries:
            if str(entry.normalized_name).upper() == "ISUSED":
                continue
            fields[f"{entry.section}/{entry.normalized_name}"] = {"display_value": 0}
        return fields

    def _player_editor_reset_value(self, entry: FieldEntry, stat_selector: object | None) -> object | None:
        if entry.domain != "Players":
            return None
        normalized = str(entry.normalized_name).upper()
        if stat_selector is not None and self.editor_model.is_player_selected_stat_detail_entry(entry):
            return None if normalized == "ISUSED" else 0
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
