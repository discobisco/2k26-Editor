"""Shared entity editing helpers."""
from __future__ import annotations

def coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
