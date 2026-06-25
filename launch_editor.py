from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

_RELAUNCH_ENV = "NBA2K_EDITOR_WINDOWS_RELAUNCHED"


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _running_inside_wsl() -> bool:
    if sys.platform == "win32":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def _wslpath_windows(path: Path) -> str:
    completed = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _windows_project_python(project_root: Path) -> Path:
    python_exe = project_root / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        raise FileNotFoundError(f"missing Windows project Python: {python_exe}")
    return python_exe


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launch_editor.py",
        description="Launch the rebuilt NBA2K Dear PyGui editor from the repository root.",
    )
    parser.add_argument("--target", default="auto", help="game executable to attach; default auto-detects the running NBA2K process")
    parser.add_argument("--verify-edits", action="store_true", help="perform the explicit live player/team/staff write proof")
    parser.add_argument("--no-load-on-start", action="store_true", help="test/debug hook: open the window without the default attach/list load")
    parser.add_argument("--attach-on-start", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-windows-relaunch",
        action="store_true",
        help="do not relaunch from WSL into the project Windows venv",
    )
    return parser


def _relaunch_in_windows_python(project_root: Path, argv: Sequence[str]) -> int:
    windows_python = _windows_project_python(project_root)
    windows_script = _wslpath_windows(project_root / "launch_editor.py")
    env = dict(os.environ)
    env[_RELAUNCH_ENV] = "1"
    completed = subprocess.run([str(windows_python), windows_script, *argv], env=env)
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    parsed = parser.parse_args(args_list)
    project_root = _project_root()

    if _running_inside_wsl() and not parsed.no_windows_relaunch and os.environ.get(_RELAUNCH_ENV) != "1":
        return _relaunch_in_windows_python(project_root, args_list)

    sys.path.insert(0, str(project_root))
    from nba2k_editor.entrypoints.gui import main as gui_main

    gui_args = [
        "--target",
        parsed.target,
    ]
    if parsed.verify_edits:
        gui_args.append("--verify-edits")
    if parsed.no_load_on_start:
        gui_args.append("--no-load-on-start")
    return gui_main(gui_args)


if __name__ == "__main__":
    raise SystemExit(main())
