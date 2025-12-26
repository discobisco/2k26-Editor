"""GUI entrypoint for the modularized editor."""
from __future__ import annotations

import sys
from tkinter import messagebox

from ..core import offsets
from ..core.config import HOOK_TARGET_LABELS, MODULE_NAME
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from ..ui.app import PlayerEditorApp


def main() -> None:
    """Launch the Tk GUI and attach to the running NBA 2K process."""
    if sys.platform != "win32":
        try:
            messagebox.showerror("Unsupported platform", "This application can only run on Windows.")
        except Exception:
            print("This application can only run on Windows.")
        return
    mem = GameMemory(MODULE_NAME)
    offset_target = MODULE_NAME
    process_open = mem.open_process()
    if process_open:
        detected_exec = mem.module_name or MODULE_NAME
        if detected_exec:
            offset_target = detected_exec
    else:
        print("NBA 2K does not appear to be running; using offsets file values.")
    offsets_loaded = False
    try:
        initialize_offsets(target_executable=offset_target, force=True)
        offsets_loaded = True
    except OffsetSchemaError as exc:
        try:
            messagebox.showwarning("Offsets not fully loaded", str(exc))
        except Exception:
            print(f"Offsets not fully loaded: {exc}")
    mem.module_name = MODULE_NAME
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
        print(f"No offsets loaded; {hook_label} not detected.")
    model = PlayerDataModel(mem, max_players=MAX_PLAYERS)
    app = PlayerEditorApp(model)
    app.mainloop()


if __name__ == "__main__":
    main()
