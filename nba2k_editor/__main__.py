"""Allow `python -m nba2k_editor` to delegate to the source launcher."""
from __future__ import annotations

from importlib import import_module


def main() -> int:
    return int(import_module("launch_editor").main())


if __name__ == "__main__":
    raise SystemExit(main())
