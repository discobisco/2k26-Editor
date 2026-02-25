"""Helpers for launching full editors in child processes."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

EDITOR_TYPES = {"player", "team", "staff", "stadium"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_indices(indices: Iterable[int] | None) -> list[int]:
    if not indices:
        return []
    out: list[int] = []
    seen: set[int] = set()
    for raw in indices:
        try:
            value = int(raw)
        except Exception:
            continue
        if value < 0 or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def build_launch_command(
    *,
    editor: str,
    index: int | None = None,
    indices: Iterable[int] | None = None,
) -> list[str]:
    """Build the process command for opening a full editor window."""
    editor_key = (editor or "").strip().lower()
    if editor_key not in EDITOR_TYPES:
        raise ValueError(f"Unsupported editor type: {editor!r}")
    cmd_args: list[str] = ["--editor", editor_key]
    normalized_indices = _normalize_indices(indices)
    if normalized_indices:
        cmd_args.extend(["--indices", ",".join(str(value) for value in normalized_indices)])
    elif index is not None:
        cmd_args.extend(["--index", str(int(index))])
    elif editor_key != "player":
        raise ValueError(f"An index is required for {editor_key} editor launches.")
    if getattr(sys, "frozen", False):
        return [sys.executable, "--child-full-editor", *cmd_args]
    return [sys.executable, "-m", "nba2k_editor.entrypoints.full_editor", *cmd_args]


def launch_full_editor_process(
    *,
    editor: str,
    index: int | None = None,
    indices: Iterable[int] | None = None,
) -> subprocess.Popen:
    """Spawn a child process hosting a dedicated full-editor viewport."""
    command = build_launch_command(editor=editor, index=index, indices=indices)
    kwargs: dict[str, object] = {"close_fds": True}
    if not getattr(sys, "frozen", False):
        kwargs["cwd"] = str(_project_root())
    return subprocess.Popen(command, **kwargs)


__all__ = [
    "build_launch_command",
    "launch_full_editor_process",
]
