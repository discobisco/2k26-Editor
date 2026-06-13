from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from nba2k_editor.entrypoints.runtime_cleanup import delete_runtime_cache_dirs
from nba2k_editor.models.data_model import EditorDataModel, verify_edits
from nba2k_editor.ui.dpg_editor import DpgEditorApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m nba2k_editor.entrypoints.gui")
    parser.add_argument("--target", default="auto")
    parser.add_argument("--verify-edits", action="store_true")
    parser.add_argument("--load-on-start", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-load-on-start", action="store_true", help="open immediately without starting the background list scan")
    parser.add_argument("--attach-on-start", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    delete_runtime_cache_dirs()
    if args.verify_edits:
        print(json.dumps(verify_edits(target_executable=args.target), sort_keys=True), flush=True)
        return 0
    DpgEditorApp(EditorDataModel(target_executable=args.target)).run(load_on_start=not args.no_load_on_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
