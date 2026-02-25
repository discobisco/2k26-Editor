"""Stadium entity service."""
from __future__ import annotations

from typing import Any

from .base_entity_service import EntityServiceBase
from .io_codec import FieldSpec, IOCodec


class StadiumService(EntityServiceBase):
    def __init__(self, model: Any, codec: IOCodec | None = None) -> None:
        super().__init__(model=model, dirty_key="stadiums", codec=codec)

    def refresh(self) -> list[tuple[int, str]]:
        return self.model.refresh_stadiums()

    def get_field(self, stadium_index: int, spec: FieldSpec) -> object | None:
        return self.codec.get_stadium(stadium_index, spec)

    def set_field(
        self,
        stadium_index: int,
        spec: FieldSpec,
        value: object,
        *,
        deref_cache: dict[int, int] | None = None,
    ) -> bool:
        ok = self.codec.set_stadium(stadium_index, spec, value, deref_cache=deref_cache)
        if ok:
            self._mark_dirty()
        return ok
