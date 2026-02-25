"""Dear PyGui launcher for the NBA 2K26 editor (PyInstaller-friendly)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Ensure the repo root is on sys.path when running from source or bundled.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _maybe_relaunch_with_local_venv() -> None:
    """Re-launch with `.venv` Python when the current interpreter is global."""
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("NBA2K_EDITOR_RELAUNCHED") == "1":
        return

    candidates = (
        _ROOT / ".venv" / "Scripts" / "python.exe",
        _ROOT / ".venv" / "Scripts" / "pythonw.exe",
    )
    current_exe = Path(sys.executable).resolve()
    for candidate in candidates:
        if not candidate.exists():
            continue
        candidate = candidate.resolve()
        if candidate == current_exe:
            return
        env = os.environ.copy()
        env["NBA2K_EDITOR_RELAUNCHED"] = "1"
        raise SystemExit(
            subprocess.call(
                [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
                cwd=str(_ROOT),
                env=env,
            )
        )


def _run_child_full_editor_if_requested(argv: list[str] | None = None) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--child-full-editor" not in args:
        return False
    child_args = [arg for arg in args if arg != "--child-full-editor"]
    try:
        from nba2k_editor.entrypoints.full_editor import main as child_main
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or "dependency"
        print(f"Missing dependency '{missing}'.")
        print("Try one of:")
        print("  - run_editor.bat")
        print("  - python -m pip install -e .")
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - defensive
        print("Failed to import the child full-editor entrypoint.")
        print("Ensure dependencies are installed and launch from the repo root.")
        print(f"Details: {exc}")
        raise
    child_main(child_args)
    return True


def _run_gui_main() -> None:
    try:
        from nba2k_editor.entrypoints.gui import main as gui_main
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or "dependency"
        print(f"Missing dependency '{missing}'.")
        print("Try one of:")
        print("  - run_editor.bat")
        print("  - python -m pip install -e .")
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - defensive
        print("Failed to import the Dear PyGui editor entrypoint.")
        print("Ensure dependencies are installed and launch from the repo root.")
        print(f"Details: {exc}")
        raise
    gui_main()


if __name__ == "__main__":
    _maybe_relaunch_with_local_venv()
    # Knowledge base search flag
    if "--kb-search" in sys.argv:
        idx = sys.argv.index("--kb-search")
        if idx + 1 < len(sys.argv):
            term = sys.argv[idx + 1]
            from nba2k_editor.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            results = kb.search(term)
            if results:
                for filename, excerpt in results:
                    print(f"{filename}: {excerpt}")
            else:
                print(f"No results found for '{term}'.")
        else:
            print("Usage: launch_editor.py --kb-search <term>")
        sys.exit(0)
    if not _run_child_full_editor_if_requested():
        _run_gui_main()
