"""Import/export controller helpers."""
from __future__ import annotations


def normalize_entity_key(entity_type: str | None) -> str:
    return (entity_type or "").strip().lower()


def entity_title(entity_key: str) -> str:
    return (entity_key or "").strip().title() or "Entity"

