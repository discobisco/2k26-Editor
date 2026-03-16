"""Lightweight process-local performance instrumentation helpers."""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")

_LOCK = threading.Lock()
_MEASUREMENTS: dict[str, list[float]] = {}
_ENABLE_ENV = "NBA2K_EDITOR_PROFILE"


def is_enabled() -> bool:
    raw = os.getenv(_ENABLE_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def record_duration(name: str, seconds: float) -> None:
    if not name:
        return
    with _LOCK:
        _MEASUREMENTS.setdefault(name, []).append(max(0.0, float(seconds)))


@contextmanager
def timed(name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        if is_enabled():
            record_duration(name, time.perf_counter() - start)


def time_call(name: str, fn: Callable[[], T]) -> T:
    start = time.perf_counter()
    try:
        return fn()
    finally:
        if is_enabled():
            record_duration(name, time.perf_counter() - start)


def clear() -> None:
    with _LOCK:
        _MEASUREMENTS.clear()


def snapshot() -> dict[str, list[float]]:
    with _LOCK:
        return {k: list(v) for k, v in _MEASUREMENTS.items()}


@dataclass(frozen=True)
class PerfSummary:
    count: int
    total_seconds: float
    avg_seconds: float
    max_seconds: float


def summarize() -> dict[str, PerfSummary]:
    data = snapshot()
    out: dict[str, PerfSummary] = {}
    for key, values in data.items():
        if not values:
            continue
        total = sum(values)
        out[key] = PerfSummary(
            count=len(values),
            total_seconds=total,
            avg_seconds=total / len(values),
            max_seconds=max(values),
        )
    return out

