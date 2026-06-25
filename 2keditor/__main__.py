"""Package command entrypoint for the rebuilt NBA 2K editor."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m nba2k_editor")
    parser.add_argument("--version", action="version", version=f"nba2k_editor {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("gui", add_help=False, help="open the Dear PyGui editor")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args, remaining = build_parser().parse_known_args(argv)
    if args.command == "gui":
        from nba2k_editor.entrypoints.gui import main as gui_main

        return gui_main(remaining)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
