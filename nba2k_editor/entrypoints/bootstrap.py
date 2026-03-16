"""Shared startup helpers for source and module entrypoints."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELAUNCHED_ENV = "NBA2K_EDITOR_RELAUNCHED"


def ensure_project_root_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def maybe_relaunch_with_local_venv(script_path: str | Path, argv: list[str] | None = None) -> None:
    """Re-launch with the repo-local `.venv` when available and not already active."""
    if getattr(sys, "frozen", False):
        return
    if os.environ.get(RELAUNCHED_ENV) == "1":
        return

    current_exe = Path(sys.executable).resolve()
    for candidate in (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe",
    ):
        if not candidate.exists():
            continue
        candidate = candidate.resolve()
        if candidate == current_exe:
            return
        env = os.environ.copy()
        env[RELAUNCHED_ENV] = "1"
        args = [str(candidate), str(Path(script_path).resolve()), *(argv or sys.argv[1:])]
        raise SystemExit(subprocess.call(args, cwd=str(PROJECT_ROOT), env=env))


def load_entrypoint_main(module_path: str, failure_label: str) -> Callable:
    try:
        module = __import__(module_path, fromlist=["main"])
        return module.main
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or "dependency"
        print(f"Missing dependency '{missing}' while loading {failure_label}.")
        print("Use the repo-local launcher/runtime:")
        print("  - run_editor.bat")
        print("  - .\\.venv\\Scripts\\python.exe launch_editor.py")
        print("This repo does not currently support 'python -m pip install -e .'")
        raise SystemExit(1) from exc
