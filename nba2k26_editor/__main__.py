"""Allow `python -m nba2k26_editor` to launch the GUI entrypoint."""
from __future__ import annotations

from .entrypoints.gui import main


if __name__ == "__main__":
    main()
