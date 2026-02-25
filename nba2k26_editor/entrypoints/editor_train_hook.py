from __future__ import annotations

from pathlib import Path
from ..gm_rl.train import main


def run_training_from_editor(config_path: str | None = None) -> None:
    """Entry used by the editor to launch RL training from the UI."""
    args = []
    if config_path:
        args.extend(["--config", str(Path(config_path))])
    main(args)


if __name__ == "__main__":
    run_training_from_editor()
