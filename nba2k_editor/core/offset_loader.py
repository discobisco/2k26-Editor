"""Offsets repository for loading offsets/dropdown bundles from disk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .offset_cache import CachedOffsetPayload, OffsetCache
from .offset_resolver import OffsetResolver


class OffsetRepository:
    def __init__(self, cache: OffsetCache | None = None) -> None:
        self.cache = cache or OffsetCache()

    def load_offsets(
        self,
        *,
        target_executable: str | None,
        search_dirs: Iterable[Path],
        candidates: Iterable[str],
        resolver: OffsetResolver,
    ) -> tuple[Path | None, dict[str, Any] | None]:
        target_key = (target_executable or "").lower()
        if target_key:
            cached = self.cache.get_target(target_key)
            if cached is not None:
                return cached.path, dict(cached.data)
        for folder in search_dirs:
            for fname in candidates:
                path = folder / fname
                if not path.is_file():
                    continue
                raw = self._load_raw_json(path)
                if raw is None:
                    continue
                resolved = resolver.resolve(raw, target_executable)
                if isinstance(resolved, dict):
                    payload = dict(resolved)
                    if target_key:
                        self.cache.set_target(
                            CachedOffsetPayload(path=path, target_key=target_key, data=payload),
                        )
                    return path, payload
        return None, None

    def load_dropdowns(self, *, search_dirs: Iterable[Path]) -> dict[str, dict[str, list[str]]]:
        for folder in search_dirs:
            path = folder / "dropdowns.json"
            if not path.is_file():
                continue
            cached = self.cache.get_dropdowns(path)
            if cached is not None:
                return cached
            raw = self._load_raw_json(path)
            parsed = self._parse_dropdowns(raw)
            if parsed:
                self.cache.set_dropdowns(path, parsed)
                return parsed
        return {}

    def _load_raw_json(self, path: Path) -> dict[str, Any] | None:
        cached = self.cache.get_json(path)
        if cached is not None:
            return cached
        try:
            with path.open("r", encoding="utf-8") as handle:
                parsed = json.load(handle)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        self.cache.set_json(path, parsed)
        return parsed

    @staticmethod
    def _parse_dropdowns(raw: dict[str, Any] | None) -> dict[str, dict[str, list[str]]]:
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, list[str]]] = {}
        for category, value in raw.items():
            if not isinstance(value, dict):
                continue
            cat_key = str(category).strip().lower()
            inner: dict[str, list[str]] = {}
            for field_name, field_values in value.items():
                if not isinstance(field_values, list):
                    continue
                inner[str(field_name).strip().lower()] = [str(v) for v in field_values]
            if inner:
                out[cat_key] = inner
        return out

