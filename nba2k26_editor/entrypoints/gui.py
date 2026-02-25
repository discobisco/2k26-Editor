"""GUI entrypoint for the modularized editor (Dear PyGui)."""
from __future__ import annotations

import shutil
import sys
import os
from pathlib import Path
from typing import Optional

import dearpygui.dearpygui as dpg

from ..core import offsets
from ..core.config import HOOK_TARGET_LABELS, MODULE_NAME
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..core.perf import is_enabled as perf_enabled, summarize as perf_summarize, timed
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from ..ui.app import PlayerEditorApp

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_CLEANUP_SKIP_DIRS = {".venv", ".git", "build", "dist"}
_CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache"}
_SKIP_CLEAN_CACHE_ENV = "NBA2K_EDITOR_SKIP_CACHE_CLEANUP"


def _cleanup_enabled() -> bool:
    skip = os.getenv(_SKIP_CLEAN_CACHE_ENV, "")
    return skip.strip().lower() not in {"1", "true", "yes", "on"}


def _delete_runtime_cache_dirs(root: Path) -> tuple[int, int]:
    removed = 0
    failed = 0
    for current, dirnames, _ in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _CACHE_CLEANUP_SKIP_DIRS]
        for name in list(dirnames):
            if name not in _CACHE_DIR_NAMES:
                continue
            cache_dir = Path(current) / name
            try:
                shutil.rmtree(cache_dir)
                removed += 1
                dirnames.remove(name)
            except OSError as exc:
                failed += 1
                print(f"Failed to remove {cache_dir}: {exc}")
    return removed, failed


def _print_offsets_status(offset_target: str, offsets_loaded: bool) -> None:
    hook_label = HOOK_TARGET_LABELS.get(
        (offset_target or MODULE_NAME).lower(), (offset_target or MODULE_NAME).replace(".exe", "").upper()
    )
    offset_file = getattr(offsets, "_offset_file_path", None)
    if getattr(offsets, "_offset_config", None):
        if offset_file:
            print(f"Loaded {hook_label} offsets from {getattr(offset_file, 'name', offset_file)}")
        else:
            print(f"Loaded {hook_label} offsets from defaults")
    else:
        status = "not detected" if not offsets_loaded else "unknown"
        print(f"No offsets loaded; {hook_label} {status}.")


def _launch_with_dearpygui(app: PlayerEditorApp, startup_warning: Optional[str] = None) -> None:
    with timed("gui.launch"):
        dpg.create_context()
        try:
            with timed("gui.build_ui"):
                app.build_ui()
            dpg.create_viewport(
                title="2K26 Offline Player Data Editor",
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
            if _cleanup_enabled():
                removed, failed = _delete_runtime_cache_dirs(_PROJECT_ROOT)
                if removed:
                    print(f"Removed {removed} cache folder(s) ({', '.join(sorted(_CACHE_DIR_NAMES))}).")
                if failed:
                    print(f"Failed to remove {failed} cache folder(s).")


def main() -> None:
    """Launch the Dear PyGui GUI and attach to the running NBA 2K process."""
    if sys.platform != "win32":
        print("This application can only run on Windows.")
        return

    with timed("gui.main"):
        mem = GameMemory(MODULE_NAME)
        offset_target = MODULE_NAME
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
            model = PlayerDataModel(mem, max_players=MAX_PLAYERS)
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
