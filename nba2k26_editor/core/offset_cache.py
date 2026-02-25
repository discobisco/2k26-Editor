"""Shared offsets cache with explicit invalidation."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedOffsetPayload:
    path: Path
    target_key: str
    data: dict[str, Any]


class OffsetCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_target: dict[str, CachedOffsetPayload] = {}
        self._json_by_path: dict[Path, dict[str, Any]] = {}
        self._dropdowns_by_path: dict[Path, dict[str, dict[str, list[str]]]] = {}

    def get_target(self, target_key: str) -> CachedOffsetPayload | None:
        with self._lock:
            return self._by_target.get(target_key)

    def set_target(self, payload: CachedOffsetPayload) -> None:
        with self._lock:
            self._by_target[payload.target_key] = payload

    def get_json(self, path: Path) -> dict[str, Any] | None:
        with self._lock:
            return self._json_by_path.get(path)

    def set_json(self, path: Path, data: dict[str, Any]) -> None:
        with self._lock:
            self._json_by_path[path] = data

    def get_dropdowns(self, path: Path) -> dict[str, dict[str, list[str]]] | None:
        with self._lock:
            return self._dropdowns_by_path.get(path)

    def set_dropdowns(self, path: Path, data: dict[str, dict[str, list[str]]]) -> None:
        with self._lock:
            self._dropdowns_by_path[path] = data

    def invalidate_target(self, target_key: str) -> None:
        with self._lock:
            self._by_target.pop(target_key, None)

    def clear(self) -> None:
        with self._lock:
            self._by_target.clear()
            self._json_by_path.clear()
            self._dropdowns_by_path.clear()

