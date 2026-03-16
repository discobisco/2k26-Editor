"""Launcher/dialog helpers for the Dear PyGui editor app."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import MODULE_NAME
from ..core.offsets import OffsetSchemaError, initialize_offsets
from .batch_edit import BatchEditWindow
from .randomizer import RandomizerWindow
from .team_shuffle import TeamShuffleWindow
from .app_shell import set_offset_status, update_status


def _refresh_players_safely(app: Any) -> None:
    try:
        app.model.refresh_players()
    except Exception:
        pass


def open_randomizer(app: Any) -> None:
    _refresh_players_safely(app)
    RandomizerWindow(app, app.model)


def open_team_shuffle(app: Any) -> None:
    _refresh_players_safely(app)
    TeamShuffleWindow(app, app.model)


def open_batch_edit(app: Any) -> None:
    _refresh_players_safely(app)
    try:
        BatchEditWindow(app, app.model)
    except Exception as exc:
        app.show_error("Batch Edit", f"Failed to open batch edit window: {exc}")


def open_offset_file_dialog(app: Any) -> None:
    def _after_choose(path: str) -> None:
        if not path:
            return
        fname = Path(path).name
        set_offset_status(app, f"Loading offsets from {fname}...")
        target_exec = app.hook_target_var.get() or app.model.mem.module_name or MODULE_NAME
        try:
            initialize_offsets(target_executable=target_exec, force=True, filename=path)
            app.model._sync_offset_constants()
            set_offset_status(app, f"Loaded offsets from {fname}")
            app.model.invalidate_base_cache()
            update_status(app)
            app._start_scan()
            app.show_info("Offsets loaded", f"Loaded offsets from {fname}")
        except OffsetSchemaError as exc:
            set_offset_status(app, "Failed to apply offsets file.")
            app.show_error("Offsets load failed", f"Unable to apply offsets from {fname}.\n{exc}")
        except Exception as exc:
            set_offset_status(app, "Failed to apply offsets file.")
            app.show_error("Offsets load failed", f"Unable to apply offsets from {fname}.\n{exc}")

    app._open_file_dialog(
        "Select offsets file",
        file_types=[("JSON files", ".json"), ("All files", ".*")],
        callback=_after_choose,
        save=False,
    )


__all__ = [
    "open_batch_edit",
    "open_offset_file_dialog",
    "open_randomizer",
    "open_team_shuffle",
]
