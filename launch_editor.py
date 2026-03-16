"""Source launcher for the NBA 2K26 editor."""
from __future__ import annotations

import sys

from nba2k_editor.entrypoints.bootstrap import (
    ensure_project_root_on_path,
    load_entrypoint_main,
    maybe_relaunch_with_local_venv,
)

ensure_project_root_on_path()


def _run_child_full_editor_if_requested(argv: list[str] | None = None) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--child-full-editor" not in args:
        return False
    child_args = [arg for arg in args if arg != "--child-full-editor"]
    load_entrypoint_main("nba2k_editor.entrypoints.full_editor", "child full-editor")(child_args)
    return True


def main(argv: list[str] | None = None) -> int:
    maybe_relaunch_with_local_venv(__file__, argv)
    if _run_child_full_editor_if_requested(argv):
        return 0
    load_entrypoint_main("nba2k_editor.entrypoints.gui", "GUI editor")()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
