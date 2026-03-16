"""Shared scan helpers used by dynamic memory scanners."""
from __future__ import annotations

from typing import Iterable


def encode_wstring(text: str) -> bytes:
    return (text + "\x00").encode("utf-16le", errors="ignore")


def find_all(data: bytes, pattern: bytes, *, step: int = 1) -> Iterable[int]:
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        yield idx
        start = idx + max(1, step)

