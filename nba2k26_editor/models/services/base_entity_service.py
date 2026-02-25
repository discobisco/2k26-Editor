"""Shared service helpers for entity model wrappers."""
from __future__ import annotations

from typing import Any

from .io_codec import IOCodec


class EntityServiceBase:
    def __init__(self, model: Any, dirty_key: str, codec: IOCodec | None = None) -> None:
        self.model = model
        self.codec = codec or IOCodec(model)
        self._dirty_key = dirty_key

    def _mark_dirty(self) -> None:
        if hasattr(self.model, "mark_dirty"):
            self.model.mark_dirty(self._dirty_key)

