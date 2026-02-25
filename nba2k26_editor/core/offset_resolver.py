"""Resolution helpers for merged offsets payloads."""
from __future__ import annotations

from typing import Any, Callable


class OffsetResolveError(RuntimeError):
    """Raised when an offsets payload cannot be resolved."""


class OffsetResolver:
    def __init__(
        self,
        convert_schema: Callable[[object, str | None], dict[str, Any] | None],
    ) -> None:
        self._convert_schema = convert_schema

    def resolve(self, raw: object, target_executable: str | None = None) -> dict[str, Any] | None:
        return self._convert_schema(raw, target_executable)

    def require_dict(self, raw: object, target_executable: str | None = None) -> dict[str, Any]:
        resolved = self.resolve(raw, target_executable)
        if not isinstance(resolved, dict):
            target = target_executable or "unknown target"
            raise OffsetResolveError(f"Could not resolve offsets payload for {target}.")
        return resolved
