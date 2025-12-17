"""GUI entrypoint for the modularized editor."""
from __future__ import annotations

import sys
from tkinter import messagebox

from ..core import offsets
from ..core.config import HOOK_TARGET_LABELS, MODULE_NAME
from ..core.dynamic_bases import find_dynamic_bases
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from ..ui.app import PlayerEditorApp


_dynamic_prompt_shown = False


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
    use_dynamic_scan = False
    global _dynamic_prompt_shown
    if process_open and not _dynamic_prompt_shown:
        try:
            use_dynamic_scan = messagebox.askyesno(
                "Dynamic base discovery",
                "Do you want to dynamically find the Player/Team/Arena/Stadium bases from the running game?\n"
                "Choose No to use the base addresses defined in the offsets file.",
            )
        except Exception:
            use_dynamic_scan = False
        _dynamic_prompt_shown = True
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
    overrides: dict[str, int] = {}
    if use_dynamic_scan and offsets_loaded:
        scan_failed = False
        try:
            print("Running dynamic base discovery (hinted around offsets.json base pointers)...")
            base_hints: dict[str, int] = {}
            cfg = getattr(offsets, "_offset_config", None)
            target_key = getattr(offsets, "_current_offset_target", None) or (offset_target or MODULE_NAME).lower()
            if isinstance(cfg, dict):
                base_map = cfg.get("base_pointers") if isinstance(cfg.get("base_pointers"), dict) else {}
                versions = cfg.get("versions") if isinstance(cfg.get("versions"), dict) else {}
                # Derive version key like "2K26" from the executable name for lookup.
                version_key = None
                try:
                    import re
                    m = re.search(r"2k(\\d{2})", target_key, re.IGNORECASE)
                    if m:
                        version_key = f"2K{m.group(1)}"
                except Exception:
                    version_key = None
                if version_key and isinstance(versions, dict):
                    vinfo = versions.get(version_key)
                    if isinstance(vinfo, dict) and isinstance(vinfo.get("base_pointers"), dict):
                        base_map = vinfo.get("base_pointers") or base_map

                def _extract_addr(label: str) -> int | None:
                    entry = base_map.get(label) or base_map.get(label.lower())
                    if not isinstance(entry, dict):
                        return None
                    addr = entry.get("address") or entry.get("rva") or entry.get("base")
                    if addr is None:
                        return None
                    try:
                        addr_int = int(addr)
                    except Exception:
                        return None
                    absolute = entry.get("absolute")
                    if absolute is None:
                        absolute = entry.get("isAbsolute")
                    if not absolute and mem.base_addr:
                        addr_int = mem.base_addr + addr_int
                    return addr_int

                p_hint = _extract_addr("Player")
                t_hint = _extract_addr("Team")
                if p_hint:
                    base_hints["Player"] = p_hint
                if t_hint:
                    base_hints["Team"] = t_hint
            team_name_len = offsets.TEAM_NAME_LENGTH if offsets.TEAM_NAME_LENGTH > 0 else 24
            overrides, _report = find_dynamic_bases(
                process_name=offset_target,
                player_stride=offsets.PLAYER_STRIDE,
                team_stride=offsets.TEAM_STRIDE,
                first_offset=offsets.OFF_FIRST_NAME,
                last_offset=offsets.OFF_LAST_NAME,
                team_name_offset=offsets.TEAM_NAME_OFFSET,
                team_name_length=team_name_len,
                pid=mem.pid,
                player_base_hint=base_hints.get("Player"),
                team_base_hint=base_hints.get("Team"),
                run_parallel=True,
            )
        except Exception as exc:
            overrides = {}
            scan_failed = True
            try:
                messagebox.showwarning(
                    "Dynamic base discovery",
                    f"Dynamic base scan failed; using offsets file.\n{exc}",
                )
            except Exception:
                print(f"Dynamic base scan failed; using offsets file. {exc}")
        if overrides:
            try:
                initialize_offsets(
                    target_executable=offset_target,
                    force=True,
                    base_pointer_overrides=overrides,
                )
                offsets_loaded = True
                addr_parts = []
                player_addr = overrides.get("Player")
                team_addr = overrides.get("Team")
                if player_addr:
                    addr_parts.append(f"Player 0x{player_addr:X}")
                if team_addr:
                    addr_parts.append(f"Team 0x{team_addr:X}")
                if addr_parts:
                    print(f"Applied dynamic bases: {', '.join(addr_parts)}")
            except OffsetSchemaError as exc:
                offsets_loaded = False
                try:
                    messagebox.showwarning(
                        "Dynamic base discovery",
                        f"Dynamic bases found but failed to apply: {exc}",
                    )
                except Exception:
                    print(f"Dynamic bases found but failed to apply: {exc}")
        elif not scan_failed:
            try:
                messagebox.showinfo(
                    "Dynamic base discovery",
                    "No dynamic bases were found; using offsets file values instead.",
                )
            except Exception:
                print("No dynamic bases were found; using offsets file values instead.")
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
