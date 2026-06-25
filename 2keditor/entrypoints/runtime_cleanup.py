"""Shared runtime cleanup helpers for entrypoints."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_CLEANUP_SKIP_DIRS = {".venv", ".git", "build", "dist"}


def delete_runtime_cache_dirs(root: Path | None = None) -> tuple[int, int]:
    target_root = root or PROJECT_ROOT
    removed = 0
    failed = 0
    for current, dirnames, _ in os.walk(target_root):
        dirnames[:] = [name for name in dirnames if name not in CACHE_CLEANUP_SKIP_DIRS]
        for name in list(dirnames):
            if name != "__pycache__":
                continue
            cache_dir = Path(current) / name
            try:
                shutil.rmtree(cache_dir)
                removed += 1
                dirnames.remove(name)
            except OSError:
                failed += 1
    return removed, failed


__all__ = [
    "PROJECT_ROOT",
    "CACHE_CLEANUP_SKIP_DIRS",
    "delete_runtime_cache_dirs",
]
