"""Player entity service."""
from __future__ import annotations

from typing import Any

from .base_entity_service import EntityServiceBase
from .io_codec import FieldSpec, IOCodec


class PlayerService(EntityServiceBase):
    def __init__(self, model: Any, codec: IOCodec | None = None) -> None:
        super().__init__(model=model, dirty_key="players", codec=codec)

    def refresh(self) -> None:
        self.model.refresh_players()

    def get_field(self, player_index: int, spec: FieldSpec) -> object | None:
        return self.codec.get_player(player_index, spec)

    def set_field(self, player_index: int, spec: FieldSpec, value: object, *, deref_cache: dict[int, int] | None = None) -> bool:
        ok = self.codec.set_player(player_index, spec, value, deref_cache=deref_cache)
        if ok:
            self._mark_dirty()
        return ok
