"""Lightweight bound variable helpers for Dear PyGui shell state."""
from __future__ import annotations


class BoundVar:
    """Lightweight value holder for UI state."""

    def __init__(self, value: object | None = "") -> None:
        self._value = value

    def get(self) -> object:
        return self._value

    def set(self, value: object) -> None:
        self._value = value


class BoundDoubleVar(BoundVar):
    def get(self) -> float:
        try:
            return float(super().get())
        except Exception:
            return 0.0

    def set(self, value: object) -> None:
        try:
            value = float(value)
        except Exception:
            pass
        super().set(value)


class BoundBoolVar(BoundVar):
    def get(self) -> bool:
        return bool(super().get())

    def set(self, value: object) -> None:
        super().set(bool(value))


__all__ = ["BoundVar", "BoundDoubleVar", "BoundBoolVar"]
