"""Shared runtime cleanup helpers for entrypoints."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_CLEANUP_SKIP_DIRS = {".venv", ".git", "build", "dist"}
SKIP_CLEAN_CACHE_ENV = "NBA2K_EDITOR_SKIP_CACHE_CLEANUP"


def cleanup_enabled() -> bool:
    return os.getenv(SKIP_CLEAN_CACHE_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


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


def cleanup_runtime_cache_dirs(root: Path | None = None) -> tuple[int, int]:
    if not cleanup_enabled():
        return 0, 0
    return delete_runtime_cache_dirs(root)


__all__ = [
    "PROJECT_ROOT",
    "CACHE_CLEANUP_SKIP_DIRS",
    "SKIP_CLEAN_CACHE_ENV",
    "cleanup_enabled",
    "delete_runtime_cache_dirs",
    "cleanup_runtime_cache_dirs",
]
