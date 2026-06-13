from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class FieldEntry:
    domain: str
    section: str
    group: str
    ordinal: int
    field: dict[str, Any]

    @property
    def normalized_name(self) -> str:
        return str(self.field.get("normalized_name") or self.field.get("display_name") or self.ordinal)

    @property
    def display_name(self) -> str:
        return str(self.field.get("display_name") or self.normalized_name)


@dataclass(frozen=True)
class RecordListItem:
    domain: str
    index: int
    address: int
    label: str

    @property
    def display_label(self) -> str:
        return f"[{self.index}] {self.label}"


def _field_identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _field_display_or_name(field: dict[str, Any]) -> str:
    return str(field.get("display_name") or field.get("normalized_name") or "")


def _iter_layout_fields(domain: str, layout: dict[str, Any]) -> Iterable[FieldEntry]:
    ordinal = 0
    for section, groups in layout.items():
        if not isinstance(groups, dict):
            raise TypeError(f"layout section {domain}/{section} must contain groups")
        for group, fields in groups.items():
            if not isinstance(fields, list):
                raise TypeError(f"layout group {domain}/{section}/{group} must contain fields")
            for field in fields:
                if not isinstance(field, dict):
                    raise TypeError(f"layout field {domain}/{section}/{group}/{ordinal} must be an object")
                yield FieldEntry(domain=domain, section=str(section), group=str(group), ordinal=ordinal, field=field)
                ordinal += 1


_STAT_ROLE_SELECTOR = "season_id_selector"
_STAT_ROLE_DETAIL = "season_id_detail"


def _stat_role(field: dict[str, Any]) -> str:
    return str(field.get("stat_role") or "").strip()


def _selected_record_source(field: dict[str, Any]) -> dict[str, Any] | None:
    source = field.get("selected_record_source")
    return source if isinstance(source, dict) else None


def _is_player_season_id_selector_entry(entry: FieldEntry) -> bool:
    return _stat_role(entry.field) == _STAT_ROLE_SELECTOR


def _is_player_selected_stat_detail_entry(entry: FieldEntry) -> bool:
    return _stat_role(entry.field) == _STAT_ROLE_DETAIL and _selected_record_source(entry.field) is not None


def _player_season_id_option_label(entry: FieldEntry) -> str:
    return entry.display_name.replace("_", " ").strip()


def _player_season_id_identity_from_option(option: object) -> str:
    text = str(option or "").strip()
    text = re.sub(r"^\[\s*-?\d+\s*\]\s*", "", text)
    text = re.sub(r"^--\s*", "", text)
    text = re.sub(r"\s+\((?:unavailable|-?\d+)\)\s*$", "", text)
    return _field_identity(text)
