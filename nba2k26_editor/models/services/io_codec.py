"""Typed I/O codec wrappers around PlayerDataModel field APIs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    offset: int
    start_bit: int
    length: int
    requires_deref: bool = False
    deref_offset: int = 0
    field_type: str | None = None
    byte_length: int = 0


class IOCodec:
    """Centralized typed read/write adapter used by entity services."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def get_player(self, player_index: int, spec: FieldSpec) -> object | None:
        return self.model.get_field_value_typed(
            player_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
        )

    def set_player(self, player_index: int, spec: FieldSpec, value: object, *, deref_cache: dict[int, int] | None = None) -> bool:
        return self.model.set_field_value_typed(
            player_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            value,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
            deref_cache=deref_cache,
        )

    def get_team(self, team_index: int, spec: FieldSpec) -> object | None:
        return self.model.get_team_field_value_typed(
            team_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
        )

    def set_team(self, team_index: int, spec: FieldSpec, value: object, *, deref_cache: dict[int, int] | None = None) -> bool:
        return self.model.set_team_field_value_typed(
            team_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            value,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
            deref_cache=deref_cache,
        )

    def get_staff(self, staff_index: int, spec: FieldSpec) -> object | None:
        return self.model.get_staff_field_value_typed(
            staff_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
        )

    def set_staff(self, staff_index: int, spec: FieldSpec, value: object, *, deref_cache: dict[int, int] | None = None) -> bool:
        return self.model.set_staff_field_value_typed(
            staff_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            value,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
            deref_cache=deref_cache,
        )

    def get_stadium(self, stadium_index: int, spec: FieldSpec) -> object | None:
        return self.model.get_stadium_field_value_typed(
            stadium_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
        )

    def set_stadium(
        self,
        stadium_index: int,
        spec: FieldSpec,
        value: object,
        *,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        return self.model.set_stadium_field_value_typed(
            stadium_index,
            spec.offset,
            spec.start_bit,
            spec.length,
            value,
            requires_deref=spec.requires_deref,
            deref_offset=spec.deref_offset,
            field_type=spec.field_type,
            byte_length=spec.byte_length,
            deref_cache=deref_cache,
        )

