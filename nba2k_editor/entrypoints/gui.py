"""GUI entrypoint for the modularized editor (Dear PyGui)."""
from __future__ import annotations

import sys
from typing import Optional

from ..core import offsets
from ..core.config import HOOK_TARGET_LABELS, MODULE_NAME
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..core.perf import is_enabled as perf_enabled, summarize as perf_summarize, timed
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from ..ui.app import PlayerEditorApp
from .runtime_cleanup import cleanup_runtime_cache_dirs


def _print_offsets_status(offset_target: str, offsets_loaded: bool) -> None:
    hook_label = HOOK_TARGET_LABELS.get(
        (offset_target or MODULE_NAME).lower(), (offset_target or MODULE_NAME).replace(".exe", "").upper()
    )
    offset_file = offsets.get_offset_file_path()
    if offsets.has_active_config():
        if offset_file:
            print(f"Loaded {hook_label} offsets from {getattr(offset_file, 'name', offset_file)}")
        else:
            print(f"Loaded {hook_label} offsets from defaults")
    else:
        status = "not detected" if not offsets_loaded else "unknown"
        print(f"No offsets loaded; {hook_label} {status}.")


def _build_model() -> tuple[PlayerDataModel, str | None]:
    offset_target = MODULE_NAME
    mem = GameMemory(MODULE_NAME)
    process_open = mem.open_process()
    if process_open:
        detected_exec = mem.module_name or MODULE_NAME
        if detected_exec:
            offset_target = detected_exec
    else:
        print("NBA 2K does not appear to be running; using offsets file values.")

    startup_warning: str | None = None
    offsets_loaded = False
    try:
        with timed("gui.initialize_offsets"):
            initialize_offsets(target_executable=offset_target, force=True)
        offsets_loaded = True
    except OffsetSchemaError as exc:
        startup_warning = str(exc)

    mem.module_name = MODULE_NAME
    _print_offsets_status(offset_target, offsets_loaded)
    with timed("gui.model_init"):
        return PlayerDataModel(mem, max_players=MAX_PLAYERS), startup_warning


def _launch_with_dearpygui(app: PlayerEditorApp, startup_warning: Optional[str] = None) -> None:
    import dearpygui.dearpygui as dpg

    with timed("gui.launch"):
        dpg.create_context()
        try:
            with timed("gui.build_ui"):
                app.build_ui()
            dpg.create_viewport(
                title="Offline Player Data Editor",
                width=1280,
                height=760,
                min_width=1024,
                min_height=640,
            )
            dpg.setup_dearpygui()
            dpg.show_viewport()
            if startup_warning:
                app.show_warning("Offsets warning", startup_warning)
            dpg.start_dearpygui()
        finally:
            dpg.destroy_context()
            cleanup_runtime_cache_dirs()


def main() -> None:
    """Launch the Dear PyGui GUI and attach to the running NBA 2K process."""
    if sys.platform != "win32":
        print("This application can only run on Windows.")
        return

    with timed("gui.main"):
        model, startup_warning = _build_model()
        with timed("gui.app_init"):
            app = PlayerEditorApp(model)
        _launch_with_dearpygui(app, startup_warning=startup_warning)
    if perf_enabled():
        for metric, summary in perf_summarize().items():
            print(
                f"[perf] {metric}: count={summary.count} total={summary.total_seconds:.4f}s "
                f"avg={summary.avg_seconds:.4f}s max={summary.max_seconds:.4f}s"
            )


if __name__ == "__main__":
    main()
