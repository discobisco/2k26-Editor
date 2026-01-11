"""Main application window (ported from the monolithic editor)."""
from __future__ import annotations

import copy
import json
import os
import queue
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING, Callable, Sequence, cast

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ..ai.detection import detect_local_ai_installations, LocalAIDetectionResult
from ..ai.settings import DEFAULT_AI_SETTINGS
from ..core.config import (
    ACCENT_BG,
    AI_SETTINGS_PATH,
    APP_VERSION,
    AUTOLOAD_EXT_FILE,
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    ENTRY_ACTIVE_BG,
    ENTRY_BG,
    ENTRY_BORDER,
    ENTRY_FG,
    INPUT_TEXT_FG,
    HOOK_TARGETS,
    HOOK_TARGET_LABELS,
    INPUT_BG,
    INPUT_PLACEHOLDER_FG,
    MODULE_NAME,
    PANEL_BG,
    PRIMARY_BG,
    TEXT_BADGE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ..core.conversions import (
    format_height_inches,
    raw_height_to_inches,
    HEIGHT_MIN_INCHES,
    HEIGHT_MAX_INCHES,
)
from ..core import offsets as offsets_mod
from ..core.dynamic_bases import find_dynamic_bases
from ..core.extensions import (
    FULL_EDITOR_EXTENSIONS,
    PLAYER_PANEL_EXTENSIONS,
)
from ..core.offsets import (
    MAX_PLAYERS,
    PLAYER_PANEL_FIELDS,
    PLAYER_PANEL_OVR_FIELD,
    TEAM_FIELD_DEFS,
    OffsetSchemaError,
    initialize_offsets,
    _offset_config,
    _current_offset_target,
)
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from .batch_edit import BatchEditWindow
from .full_player_editor import FullPlayerEditor
from .full_team_editor import FullTeamEditor
from .full_staff_editor import FullStaffEditor
from .full_stadium_editor import FullStadiumEditor
from .randomizer import RandomizerWindow
from .team_shuffle import TeamShuffleWindow
from .theme import apply_base_theme
from .widgets import bind_mousewheel
from .dialogs import ImportSummaryDialog

if TYPE_CHECKING:
    from ..ai.assistant import PlayerAIAssistant

    class RawFieldInspectorExtension:  # minimal stub for type checkers
        ...
from . import extensions_ui
from .home_screen import build_home_screen
from .ai_screen import build_ai_screen
from .players_screen import build_players_screen
from .teams_screen import build_teams_screen
from .staff_screen import build_staff_screen
from .stadium_screen import build_stadium_screen
from .excel_screen import build_excel_screen
from ..ai.assistant import ensure_control_bridge
class PlayerEditorApp(tk.Tk):
    def _read_team_field_bits(self, base_addr, offset, size_bytes=1, bit_start=0, bit_length=None):
        raw = self._read_bytes(base_addr + offset, size_bytes)
        if not raw:
            return 0
        val = int.from_bytes(raw, "little")
        if bit_length is not None:
            mask = (1 << bit_length) - 1
            val = (val >> bit_start) & mask
        return val

    def _read_bytes(self, addr: int, length: int) -> bytes:
        """Safely read raw bytes from the target process."""
        try:
            return self.model.mem.read_bytes(addr, length)
        except Exception:
            return b""
    """The main Tkinter application for editing player data."""
    def __init__(self, model: PlayerDataModel):
        super().__init__()
        global app
        app = self
        self.model: PlayerDataModel = model
        self.title("2K26 Offline Player Data Editor")
        self.geometry("1280x760")
        self.minsize(1024, 640)
        self.style = ttk.Style(self)
        apply_base_theme(self)
        try:
            current_theme = self.style.theme_use()
            self.style.theme_use(current_theme)
        except Exception:
            pass
        combo_text_dark = TEXT_PRIMARY
        try:
            self.style.configure(
                "App.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=combo_text_dark,
                bordercolor=ACCENT_BG,
                arrowcolor=combo_text_dark,
            )
        except tk.TclError:
            self.style.configure(
                "App.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=combo_text_dark,
            )
        self.style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", combo_text_dark)],
            arrowcolor=[("readonly", combo_text_dark)],
        )
        # State variables
        self.selected_team: str | None = None
        self.selected_player: Player | None = None
        self.scanning = False
        self.dynamic_scan_in_progress = False
        self.offset_load_status_var: tk.StringVar = tk.StringVar(value="Using packaged offsets.")
        # Common UI element placeholders to satisfy type checkers; populated during screen builds.
        self.player_detail_fields: dict[str, tk.Variable] = {}
        self.player_listbox: tk.Listbox | None = None
        self.team_var: tk.StringVar = tk.StringVar()
        self.team_edit_var: tk.StringVar = tk.StringVar()
        self.team_name_var: tk.StringVar = tk.StringVar()
        self.var_first: tk.StringVar = tk.StringVar()
        self.var_last: tk.StringVar = tk.StringVar()
        self.var_player_team: tk.StringVar = tk.StringVar()
        self.player_name_var: tk.StringVar = tk.StringVar()
        self.player_ovr_var: tk.StringVar = tk.StringVar()
        # Maintain a list of players for the currently selected team.  This
        # list is filtered by the search bar on the players screen.
        # ``current_players`` holds the Player objects for the selected team,
        # while ``filtered_player_indices`` maps the visible listbox rows
        # back to the indices within ``current_players``.  ``player_search_var``
        # tracks the current search text.
        self.current_players: list[Player] = []
        self.filtered_player_indices: list[int] = []
        self.player_search_var = tk.StringVar()
        self.team_players_lookup: list[Player] = []
        self.team_players_listbox: tk.Listbox | None = None
        self.selected_players: list[Player] = []
        self.hook_target_var = tk.StringVar(value=self.model.mem.module_name or MODULE_NAME)
        self.player_panel_inspector: "RawFieldInspectorExtension | None" = None
        self.home_frame: tk.Frame | None = None
        self.players_frame: tk.Frame | None = None
        self.teams_frame: tk.Frame | None = None
        self.staff_frame: tk.Frame | None = None
        self.stadium_frame: tk.Frame | None = None
        self.ai_frame: tk.Frame | None = None
        self.excel_frame: tk.Frame | None = None
        # AI integration settings
        self.ai_settings: dict[str, object] = {}
        self.ai_mode_var = tk.StringVar()
        self.ai_api_base_var = tk.StringVar()
        self.ai_api_key_var = tk.StringVar()
        self.ai_model_var = tk.StringVar()
        self.ai_api_timeout_var = tk.StringVar()
        # Local process / Python backend
        self.ai_local_backend_var = tk.StringVar(value="cli")  # 'cli' or 'python'
        self.ai_local_command_var = tk.StringVar()
        self.ai_local_args_var = tk.StringVar()
        self.ai_local_workdir_var = tk.StringVar()
        # Python backend options
        self.ai_python_backend_var = tk.StringVar()  # 'llama_cpp' or 'transformers'
        self.ai_model_path_var = tk.StringVar()
        self.ai_model_max_tokens_var = tk.StringVar(value="256")
        self.ai_model_temperature_var = tk.StringVar(value="0.4")
        self.ai_test_status_var = tk.StringVar(value="")
        # Persona/profile settings
        self.ai_persona_choice_var = tk.StringVar(value="none")  # selected persona for Assistant (none/base/team:<id>)
        self.ai_base_persona_var = tk.StringVar()
        self.ai_active_team_count_var = tk.StringVar(value="12")
        self._ai_remote_inputs: list[tk.Widget] = []
        self._ai_local_inputs: list[tk.Widget] = []
        self._ai_python_inputs: list[tk.Widget] = []
        self._ai_persona_widgets: list[tk.Widget] = []
        self.ai_status_label: tk.Label | None = None
        self.ai_detected_listbox: tk.Listbox | None = None
        self.local_ai_inventory: list[LocalAIDetectionResult] = []
        self.ai_assistant: PlayerAIAssistant | None = None
        self.control_bridge = None
        self._load_ai_settings_into_vars()
        # Extension loader state
        self.extension_vars: dict[str, tk.BooleanVar] = {}
        self.extension_checkbuttons: dict[str, tk.Checkbutton] = {}
        self.loaded_extensions: set[str] = set()
        self.extension_status_var = tk.StringVar(value="")
        # Dynamic base scan results (shared with extensions)
        self.last_dynamic_base_report: dict[str, object] | None = None
        self.last_dynamic_base_overrides: dict[str, int] | None = None
        # Control bridge for external AI agents
        self._start_control_bridge()
        # Team/UI placeholders
        self.team_dropdown: ttk.Combobox | None = None
        self.player_team_listbox: tk.Listbox | None = None
        self.team_editor_field_vars: dict[str, tk.StringVar] = {}
        self.team_editor_detail_name_var: tk.StringVar = tk.StringVar()
        self.team_scan_status_var: tk.StringVar = tk.StringVar()
        self.status_var: tk.StringVar = tk.StringVar()
        self.dynamic_scan_status_var: tk.StringVar = tk.StringVar(value="Dynamic base scan not started.")
        self.scan_status_var: tk.StringVar = tk.StringVar()
        self.player_count_var: tk.StringVar = tk.StringVar(value="Players: 0")
        self.excel_status_var: tk.StringVar = tk.StringVar(value="")
        self.excel_progress_var: tk.DoubleVar = tk.DoubleVar(value=0)
        self.excel_progress: ttk.Progressbar | None = None
        self._excel_export_queue: queue.Queue[tuple] | None = None
        self._excel_export_thread: threading.Thread | None = None
        self._excel_export_polling = False
        self._excel_export_entity_label = ""
        self.btn_team_save: tk.Button | None = None
        self.btn_team_full: tk.Button | None = None
        self.btn_save: tk.Button | None = None
        self.btn_edit: tk.Button | None = None
        self.btn_copy: tk.Button | None = None
        self.player_portrait: tk.Canvas | None = None
        self.player_portrait_text: Any = None
        self.team_editor_listbox: tk.Listbox | None = None
        self.team_count_var: tk.StringVar = tk.StringVar()
        self.filtered_team_names: list[str] = []
        self.staff_search_var: tk.StringVar = tk.StringVar()
        self.staff_status_var: tk.StringVar = tk.StringVar(value="")
        self.staff_count_var: tk.StringVar = tk.StringVar(value="Staff: 0")
        self.staff_entries: list[tuple[int, str]] = []
        self._filtered_staff_entries: list[tuple[int, str]] = []
        self.staff_listbox: tk.Listbox | None = None
        self.stadium_search_var: tk.StringVar = tk.StringVar()
        self.stadium_status_var: tk.StringVar = tk.StringVar(value="")
        self.stadium_count_var: tk.StringVar = tk.StringVar(value="Stadiums: 0")
        self.stadium_entries: list[tuple[int, str]] = []
        self._filtered_stadium_entries: list[tuple[int, str]] = []
        self.stadium_listbox: tk.Listbox | None = None
        self.team_editor_field_vars: dict[str, tk.StringVar] = {}
        self.team_field_vars: dict[str, tk.StringVar] = {}
        # Pending team selection when jumping from player panel before teams are loaded
        self._pending_team_select: str | None = None
        # Build UI elements
        self._build_sidebar()
        build_home_screen(self)
        build_players_screen(self)
        self._build_teams_screen()
        build_staff_screen(self)
        build_stadium_screen(self)
        build_excel_screen(self)
        build_ai_screen(self)
        # Show home by default
        self.show_home()
        # Control bridge for external AI agents
        self._start_control_bridge()

    def _hide_frames(self, *frames: tk.Misc | None) -> None:
        """Safely hide packed frames if they exist."""
        for frame in frames:
            if frame is None:
                continue
            try:
                if hasattr(frame, "pack_forget"):
                    cast(tk.Widget, frame).pack_forget()
            except Exception:
                pass
    # ---------------------------------------------------------------------
    # AI control bridge
    # ---------------------------------------------------------------------
    def _start_control_bridge(self) -> None:
        """Start the HTTP control bridge so external AIs can drive the app."""
        try:
            self.control_bridge = ensure_control_bridge(cast(Any, self))
        except Exception:
            self.control_bridge = None
    # ---------------------------------------------------------------------
    # AI integration helpers
    # ---------------------------------------------------------------------
    def _load_ai_settings_into_vars(self) -> None:
        settings = self._load_ai_settings()
        self.ai_settings = settings
        mode = str(settings.get("mode", "none"))
        remote = settings.get("remote", {}) if isinstance(settings, dict) else {}
        local = settings.get("local", {}) if isinstance(settings, dict) else {}
        self.ai_mode_var.set(mode or "none")
        self.ai_api_base_var.set(str(remote.get("base_url", "")) if isinstance(remote, dict) else "")
        self.ai_api_key_var.set(str(remote.get("api_key", "")) if isinstance(remote, dict) else "")
        self.ai_model_var.set(str(remote.get("model", "")) if isinstance(remote, dict) else "")
        timeout_val = remote.get("timeout") if isinstance(remote, dict) else ""
        self.ai_api_timeout_var.set(str(timeout_val) if timeout_val not in (None, "") else "")
        self.ai_local_backend_var.set(str(local.get("backend", "cli")) if isinstance(local, dict) else "cli")
        self.ai_local_command_var.set(str(local.get("command", "")) if isinstance(local, dict) else "")
        self.ai_local_args_var.set(str(local.get("arguments", "")) if isinstance(local, dict) else "")
        self.ai_local_workdir_var.set(str(local.get("working_dir", "")) if isinstance(local, dict) else "")
        self.ai_python_backend_var.set(str(local.get("python_backend", "")) if isinstance(local, dict) else "")
        self.ai_model_path_var.set(str(local.get("model_path", "")) if isinstance(local, dict) else "")
        self.ai_model_max_tokens_var.set(str(local.get("max_tokens", 256)) if isinstance(local, dict) else "256")
        self.ai_model_temperature_var.set(str(local.get("temperature", 0.4)) if isinstance(local, dict) else "0.4")
        self.ai_test_status_var.set("")
        # Load persona-related vars
        profiles = settings.get("profiles") if isinstance(settings, dict) else {}
        self.ai_base_persona_var.set(str(profiles.get("base", "")) if isinstance(profiles, dict) else "")
        self.ai_active_team_count_var.set(str(profiles.get("active_count", 12)) if isinstance(profiles, dict) else "12")

    def _load_ai_settings(self) -> dict[str, object]:
        base = copy.deepcopy(DEFAULT_AI_SETTINGS)
        try:
            if AI_SETTINGS_PATH.exists():
                with AI_SETTINGS_PATH.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        self._merge_dict(base, data)
        except Exception:
            pass
        # Ensure we have sensible team profiles based on known teams (if available)
        try:
            from ..ai.personas import ensure_default_profiles
            teams = list(self.model.get_teams()) if hasattr(self, "model") and getattr(self.model, "get_teams", None) else []
            profiles_raw = base.get("profiles")
            profiles = profiles_raw if isinstance(profiles_raw, dict) else {}
            active_raw = profiles.get("active_count", 12)
            active_count = self._coerce_int(active_raw, default=12)
            ensure_default_profiles(base, teams, active_count)
        except Exception:
            pass
        return base

    def _save_ai_settings(self, settings: dict[str, object]) -> None:
        try:
            AI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AI_SETTINGS_PATH.open("w", encoding="utf-8") as fh:
                json.dump(settings, fh, indent=2)
        except Exception as exc:
            messagebox.showerror("Save Settings", f"Could not save AI settings:\n{exc}")

    @staticmethod
    def _merge_dict(target: dict[str, object], source: dict[str, object]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                PlayerEditorApp._merge_dict(target[key], value)  # type: ignore[arg-type]
            else:
                target[key] = value

    def _get_ai_profiles(self) -> dict[str, object]:
        profiles = self.ai_settings.get("profiles")
        return profiles if isinstance(profiles, dict) else {}

    def _ensure_ai_profiles(self) -> dict[str, object]:
        profiles = self.ai_settings.get("profiles")
        if isinstance(profiles, dict):
            return profiles
        profiles = {}
        self.ai_settings["profiles"] = profiles
        return profiles

    def _get_team_profiles(self) -> list[dict[str, object]]:
        profiles = self._get_ai_profiles()
        team_profiles = profiles.get("team_profiles")
        if isinstance(team_profiles, list):
            return cast(list[dict[str, object]], team_profiles)
        return []

    def _collect_ai_settings(self) -> dict[str, object]:
        mode = self.ai_mode_var.get().strip() or "none"
        team_profiles = self._get_team_profiles()
        settings: dict[str, object] = {
            "mode": mode,
            "remote": {
                "base_url": self.ai_api_base_var.get().strip(),
                "api_key": self.ai_api_key_var.get().strip(),
                "model": self.ai_model_var.get().strip(),
                "timeout": self._coerce_int(self.ai_api_timeout_var.get(), default=30),
            },
            "local": {
                "backend": self.ai_local_backend_var.get().strip() or "cli",
                "command": self.ai_local_command_var.get().strip(),
                "arguments": self.ai_local_args_var.get().strip(),
                "working_dir": self.ai_local_workdir_var.get().strip(),
                "python_backend": self.ai_python_backend_var.get().strip(),
                "model_path": self.ai_model_path_var.get().strip(),
                "max_tokens": self._coerce_int(self.ai_model_max_tokens_var.get(), default=256),
                "temperature": float(self.ai_model_temperature_var.get() or 0.4),
            },
            "profiles": {
                "base": self.ai_base_persona_var.get().strip(),
                "active_count": self._coerce_int(self.ai_active_team_count_var.get(), default=12),
                # team_profiles managed by persona helpers / UI
                "team_profiles": team_profiles,
            },
        }
        return settings

    def get_ai_settings(self) -> dict[str, object]:
        """Return a copy of the current AI integration settings."""
        return copy.deepcopy(self.ai_settings)

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        return default

    def _save_ai_settings_from_ui(self) -> None:
        settings = self._collect_ai_settings()
        self.ai_settings = settings
        self._save_ai_settings(settings)
        # Ensure persona defaults reflect active count and existing teams
        try:
            from ..ai.personas import ensure_default_profiles
            teams = list(self.model.get_teams()) if hasattr(self, "model") and getattr(self.model, "get_teams", None) else []
            profiles = self._get_ai_profiles()
            active_raw = profiles.get("active_count", 12)
            active_count = self._coerce_int(active_raw, default=12)
            ensure_default_profiles(self.ai_settings, teams, active_count)
            # persist any generated profiles
            self._save_ai_settings(self.ai_settings)
        except Exception:
            pass
        self._set_ai_status("AI settings saved.", success=True)
        self._refresh_persona_choices()

    def _on_ai_mode_change(self) -> None:
        self._update_ai_field_state()
        mode = self.ai_mode_var.get()
        if mode == "none":
            self._set_ai_status("AI integrations disabled.", success=False)
        elif mode == "remote":
            self._set_ai_status("Remote API mode selected.", success=True)
        else:
            self._set_ai_status("Local process mode selected.", success=True)

    def _update_ai_field_state(self) -> None:
        mode = self.ai_mode_var.get()
        remote_state = tk.NORMAL if mode == "remote" else tk.DISABLED
        local_state = tk.NORMAL if mode == "local" else tk.DISABLED
        python_state = tk.NORMAL if (mode == "local" and str(self.ai_local_backend_var.get()).strip().lower() == "python") else tk.DISABLED
        for widget in self._ai_remote_inputs:
            try:
                widget.configure({"state": remote_state})
            except Exception:
                pass
        for widget in self._ai_local_inputs:
            try:
                widget.configure({"state": local_state})
            except Exception:
                pass
        for widget in self._ai_python_inputs:
            try:
                widget.configure({"state": python_state})
            except Exception:
                pass

    def _test_ai_connection(self) -> None:
        mode = self.ai_mode_var.get()
        if mode == "remote":
            base = self.ai_api_base_var.get().strip()
            model_name = self.ai_model_var.get().strip()
            if not base:
                self._set_ai_status("Provide an API base URL.", success=False)
                return
            msg = f"Remote API configured at {base}"
            if model_name:
                msg += f" (model: {model_name})"
            self._set_ai_status(msg, success=True)
        elif mode == "local":
            command_text = self.ai_local_command_var.get().strip()
            if not command_text:
                self._set_ai_status("Provide a local command or executable.", success=False)
                return
            command = Path(command_text)
            if command.exists():
                self._set_ai_status(f"Local AI command found at {command}", success=True)
            else:
                self._set_ai_status(f"Command not found: {command}", success=False)
        else:
            self._set_ai_status("AI integrations are disabled.", success=False)

    def _scan_local_ai_inventory(self) -> None:
        """
        Search the filesystem for supported local AI launchers and present them.

        The scan is lightweight and only probes known install directories.
        """
        inventory = detect_local_ai_installations()
        self.local_ai_inventory = inventory
        if self.ai_detected_listbox is not None:
            self.ai_detected_listbox.delete(0, tk.END)
            for item in inventory:
                label = f"{item.name} - {item.command}"
                if item.arguments:
                    label += f" (args: {item.arguments})"
                self.ai_detected_listbox.insert(tk.END, label)
        if inventory:
            self._set_ai_status(
                f"Found {len(inventory)} local AI tool(s). Select one and click \"Apply Selected\".",
                success=True,
            )
        else:
            self._set_ai_status(
                "No known local AI tools were found automatically. Install LM Studio, Ollama, koboldcpp, etc.",
                success=False,
            )

    def _apply_selected_local_ai(self) -> None:
        """Populate the UI fields from the selected detected launcher."""
        if not self.local_ai_inventory or self.ai_detected_listbox is None:
            self._set_ai_status("Scan for local models first.", success=False)
            return
        try:
            selection = self.ai_detected_listbox.curselection()
        except Exception:
            selection = ()
        if not selection:
            self._set_ai_status("Select a detected local model before applying it.", success=False)
            return
        index = selection[0]
        try:
            detection = self.local_ai_inventory[index]
        except IndexError:
            self._set_ai_status("Selection no longer available. Scan again.", success=False)
            return
        self.ai_mode_var.set("local")
        self.ai_local_command_var.set(str(detection.command))
        self.ai_local_workdir_var.set(str(detection.command.parent))
        if detection.arguments:
            self.ai_local_args_var.set(detection.arguments)
        self._update_ai_field_state()
        self._set_ai_status(f"Applied {detection.name} located at {detection.command}", success=True)

    def _set_ai_status(self, message: str, *, success: bool) -> None:
        self.ai_test_status_var.set(message)
        if self.ai_status_label is not None:
            try:
                self.ai_status_label.configure(fg="#6FB06F" if success else "#D96C6C")
            except Exception:
                pass

    def _generate_persona_defaults(self) -> None:
        try:
            from ..ai.personas import ensure_default_profiles
            teams = list(self.model.get_teams()) if hasattr(self, "model") and getattr(self.model, "get_teams", None) else []
            active = int(self.ai_active_team_count_var.get())
            ensure_default_profiles(self.ai_settings, teams, active)
            self._save_ai_settings(self.ai_settings)
            self._set_ai_status(f"Generated {active} team persona defaults.", success=True)
            self._refresh_persona_choices()
        except Exception as exc:
            self._set_ai_status(f"Failed to generate defaults: {exc}", success=False)

    def _open_persona_editor(self) -> None:
        try:
            if hasattr(self, "_open_persona_editor_impl"):
                self._open_persona_editor_impl()
        except Exception as exc:
            self._set_ai_status(f"Failed to open persona editor: {exc}", success=False)

    def _open_edit_base_persona(self) -> None:
        win = tk.Toplevel(self)
        win.title("Edit base persona")
        win.transient(self)
        win.grab_set()
        txt = tk.Text(win, height=12, width=80)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, str(self.ai_base_persona_var.get() or ""))

        def _save_and_close() -> None:
            val = txt.get("1.0", tk.END).strip()
            self.ai_base_persona_var.set(val)
            # persist to settings immediately
            try:
                profiles = self._ensure_ai_profiles()
                profiles["base"] = val
                self._save_ai_settings(self.ai_settings)
                self._set_ai_status("Base persona saved.", success=True)
            except Exception as exc:
                messagebox.showerror("Save Persona", f"Failed to save persona: {exc}")
            finally:
                win.grab_release()
                win.destroy()

        tk.Button(win, text="Save", command=_save_and_close, bg=BUTTON_BG, fg=BUTTON_TEXT).pack(padx=8, pady=(0, 8))

    def _refresh_persona_choices(self) -> None:
        # Notify assistant UI to update its persona dropdown
        assistant = self.ai_assistant
        if assistant is None:
            return
        try:
            assistant._refresh_persona_dropdown()
        except Exception:
            pass

    def get_persona_choice_items(self) -> list[tuple[str, str]]:
        # Returns list of (label, value) tuples for persona selector
        items: list[tuple[str, str]] = [("None", "none"), ("Base", "base")]
        profiles = self._get_team_profiles()
        for t in profiles:
            label = f"Team {t.get('id')}: {t.get('name')}"
            value = f"team:{t.get('id')}"
            items.append((label, value))
        return items

    # ---------------------------------------------------------------------
    # Sidebar and navigation
    # ---------------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = tk.Frame(self, width=200, bg=PRIMARY_BG)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        # Buttons
        self.btn_home = tk.Button(
            self.sidebar,
            text="Home",
            command=self.show_home,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_home.pack(fill=tk.X, padx=10, pady=(20, 5))
        self.btn_players = tk.Button(
            self.sidebar,
            text="Players",
            command=self.show_players,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_players.pack(fill=tk.X, padx=10, pady=5)
        self.btn_ai = tk.Button(
            self.sidebar,
            text="AI Assistant",
            command=self.show_ai,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_ai.pack(fill=tk.X, padx=10, pady=5)
        # Teams button
        self.btn_teams = tk.Button(
            self.sidebar,
            text="Teams",
            command=self.show_teams,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_teams.pack(fill=tk.X, padx=10, pady=5)
        # Staff and Stadium editor entry points (scaffolds until pointers exist)
        self.btn_staff = tk.Button(
            self.sidebar,
            text="Staff",
            command=self.show_staff,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_staff.pack(fill=tk.X, padx=10, pady=5)
        self.btn_stadium = tk.Button(
            self.sidebar,
            text="Stadium",
            command=self.show_stadium,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_stadium.pack(fill=tk.X, padx=10, pady=5)
        self.btn_excel = tk.Button(
            self.sidebar,
            text="Excel",
            command=self.show_excel,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_excel.pack(fill=tk.X, padx=10, pady=5)
        # Randomizer button
        self.btn_randomizer = tk.Button(
            self.sidebar,
            text="Randomize",
            command=self._open_randomizer,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_randomizer.pack(fill=tk.X, padx=10, pady=5)
        # Team Shuffle button
        self.btn_shuffle = tk.Button(
            self.sidebar,
            text="Shuffle Teams",
            command=self._open_team_shuffle,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_shuffle.pack(fill=tk.X, padx=10, pady=5)
        # Batch Edit button
        self.btn_batch_edit = tk.Button(
            self.sidebar,
            text="Batch Edit",
            command=self._open_batch_edit,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_batch_edit.pack(fill=tk.X, padx=10, pady=5)
    # ---------------------------------------------------------------------
    # Home screen
    # ---------------------------------------------------------------------
    def _discover_extension_files(self) -> list[extensions_ui.ExtensionEntry]:
        return extensions_ui.discover_extension_files()

    def _is_extension_loaded(self, key: str) -> bool:
        return extensions_ui.is_extension_loaded(self, key)

    def _reload_with_selected_extensions(self) -> None:
        extensions_ui.reload_with_selected_extensions(self)

    def _autoload_extensions_from_file(self) -> None:
        extensions_ui.autoload_extensions_from_file(self)

    def _toggle_extension_module(self, key: str, label: str, var: tk.BooleanVar) -> None:
        extensions_ui.toggle_extension_module(self, key, label, var)

    def _load_extension_module(self, key: str) -> bool:
        return extensions_ui.load_extension_module(key)

    def _build_ai_settings_tab(self, parent: tk.Frame) -> None:
        # ---- persona editor helpers ----
        def _edit_team_profile(team_id: int) -> None:
            # Open inline editor for a single team profile
            teams = self._get_team_profiles()
            selected = next((t for t in teams if self._coerce_int(t.get("id"), default=-1) == team_id), None)
            if selected is None:
                messagebox.showerror("Edit Persona", f"Team profile {team_id} not found.")
                return
            win = tk.Toplevel(self)
            win.title(f"Edit persona — {selected.get('name', f'Team {team_id}')}")
            win.transient(self)
            win.grab_set()
            enabled_var = tk.BooleanVar(value=bool(selected.get("enabled", False)))
            tk.Checkbutton(win, text="Enabled", variable=enabled_var, bg=PANEL_BG, fg=TEXT_PRIMARY).pack(anchor="w", padx=8, pady=(8, 0))
            txt = tk.Text(win, height=10, width=60)
            txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            txt.insert(tk.END, str(selected.get("persona", "")))

            def _save_and_close() -> None:
                try:
                    selected["enabled"] = bool(enabled_var.get())
                    selected["persona"] = txt.get("1.0", tk.END).strip()
                    # write back into ai_settings and save
                    teams_list = list(teams)
                    for i, t in enumerate(teams_list):
                        if self._coerce_int(t.get("id"), default=-1) == team_id:
                            teams_list[i] = selected
                            break
                    else:
                        teams_list.append(selected)
                    profiles = self._ensure_ai_profiles()
                    profiles["team_profiles"] = teams_list
                    self._save_ai_settings(self.ai_settings)
                    self._set_ai_status("Persona saved.", success=True)
                    self._refresh_persona_choices()
                except Exception as exc:
                    messagebox.showerror("Save Persona", f"Failed to save persona: {exc}")
                finally:
                    win.grab_release()
                    win.destroy()

            tk.Button(win, text="Save", command=_save_and_close, bg=BUTTON_BG, fg=BUTTON_TEXT).pack(padx=8, pady=(0, 8))

        def _open_persona_editor_impl() -> None:
            # Main persona editor: list teams and edit selected
            win = tk.Toplevel(self)
            win.title("Team personas")
            win.transient(self)
            win.grab_set()
            frame = tk.Frame(win, bg=PANEL_BG)
            frame.pack(fill=tk.BOTH, expand=True)
            listbox = tk.Listbox(frame, width=30)
            listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), pady=8)
            details = tk.Frame(frame, bg=PANEL_BG)
            details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
            tk.Label(details, text="Team persona", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(anchor="w")
            txt = tk.Text(details, height=12)
            txt.pack(fill=tk.BOTH, expand=True)
            enabled_var = tk.BooleanVar()
            chk = tk.Checkbutton(details, text="Enabled", variable=enabled_var, bg=PANEL_BG, fg=TEXT_PRIMARY)
            chk.pack(anchor="w", pady=(4, 0))

            profiles = self._get_team_profiles()
            for t in profiles:
                label = f"{t.get('id')} - {t.get('name')} {'(disabled)' if not t.get('enabled') else ''}"
                listbox.insert(tk.END, label)

            def _on_select(evt=None) -> None:
                try:
                    idx = listbox.curselection()
                    if not idx:
                        return
                    sel = profiles[idx[0]]
                    txt.delete("1.0", tk.END)
                    txt.insert(tk.END, str(sel.get("persona", "")))
                    enabled_var.set(bool(sel.get("enabled", False)))
                except Exception:
                    pass

            def _save_selected() -> None:
                try:
                    idx = listbox.curselection()
                    if not idx:
                        return
                    sel = profiles[idx[0]]
                    sel["persona"] = txt.get("1.0", tk.END).strip()
                    sel["enabled"] = bool(enabled_var.get())
                    profiles_dict = self._ensure_ai_profiles()
                    profiles_dict["team_profiles"] = profiles
                    self._save_ai_settings(self.ai_settings)
                    self._set_ai_status("Persona saved.", success=True)
                    self._refresh_persona_choices()
                except Exception as exc:
                    messagebox.showerror("Save", f"Failed to save persona: {exc}")

            listbox.bind("<<ListboxSelect>>", _on_select)
            btns = tk.Frame(details, bg=PANEL_BG)
            btns.pack(fill=tk.X, pady=(8, 0))
            tk.Button(btns, text="Save", command=_save_selected, bg=BUTTON_BG, fg=BUTTON_TEXT).pack(side=tk.LEFT)

        # Attach the inline helpers to instance methods so other methods can call them
        self._open_persona_editor_impl = _open_persona_editor_impl
        self._edit_team_profile = _edit_team_profile

        for widget_list in (self._ai_remote_inputs, self._ai_local_inputs):
            widget_list.clear()
        tk.Label(
            parent,
            text="AI Settings",
            font=("Segoe UI", 14, "bold"),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        ).pack(anchor="w", padx=4, pady=(0, 4))
        tk.Label(
            parent,
            text="Connect a local model or remote API to power the AI Assistant.",
            font=("Segoe UI", 10),
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=4, pady=(0, 10))
        quick_frame = tk.Frame(parent, bg=PANEL_BG)
        quick_frame.pack(anchor="w", padx=4, pady=(0, 12))
        tk.Label(
            quick_frame,
            text="Quick start",
            font=("Segoe UI", 11, "bold"),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        ).pack(anchor="w")
        tk.Label(
            quick_frame,
            text="1) Choose a mode. 2) Fill in the settings below. 3) Save Settings and open the AI Assistant.",
            font=("Segoe UI", 9),
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            parent,
            text="AI integration mode",
            font=("Segoe UI", 12, "bold"),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        ).pack(anchor="w")
        mode_row = tk.Frame(parent, bg=PANEL_BG)
        mode_row.pack(anchor="w", pady=(6, 16))
        for label, value in (("Disabled", "none"), ("Remote API", "remote"), ("Local Process", "local")):
            tk.Radiobutton(
                mode_row,
                text=label,
                variable=self.ai_mode_var,
                value=value,
                command=self._on_ai_mode_change,
                bg=PANEL_BG,
                fg=TEXT_PRIMARY,
                activebackground=PANEL_BG,
                activeforeground=TEXT_PRIMARY,
                selectcolor=ACCENT_BG,
                indicatoron=False,
                relief=tk.FLAT,
                padx=12,
                pady=4,
            ).pack(side=tk.LEFT, padx=(0, 10))
        remote_frame = tk.LabelFrame(parent, text="Remote API (OpenAI-compatible)", bg=PANEL_BG, fg=TEXT_PRIMARY)
        remote_frame.configure(labelanchor="nw")
        remote_frame.pack(fill=tk.X, padx=4, pady=(0, 12))
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "Base URL", self.ai_api_base_var))
        api_key_widgets = self._build_labeled_entry(remote_frame, "API Key", self.ai_api_key_var, show="*")
        self._ai_remote_inputs.extend(api_key_widgets)
        api_key_entry = cast(tk.Entry, api_key_widgets[0]) if api_key_widgets else None
        show_key_var = tk.BooleanVar(value=False)

        def _toggle_api_key_visibility() -> None:
            if api_key_entry is None:
                return
            api_key_entry.configure(show="" if show_key_var.get() else "*")

        show_key_chk = tk.Checkbutton(
            remote_frame,
            text="Show API key",
            variable=show_key_var,
            command=_toggle_api_key_visibility,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
        )
        show_key_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._ai_remote_inputs.append(show_key_chk)
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "Model", self.ai_model_var))
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "Timeout (s)", self.ai_api_timeout_var))
        tk.Label(
            remote_frame,
            text="Base URL should point at the /v1 root for OpenAI-compatible servers.",
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9, "italic"),
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        # Persona settings
        persona_frame = tk.LabelFrame(parent, text="AI Personas", bg=PANEL_BG, fg=TEXT_PRIMARY)
        persona_frame.configure(labelanchor="nw")
        persona_frame.pack(fill=tk.X, padx=4, pady=(0, 12))
        # Inline base persona editor: opens a multi-line editor dialog
        row = tk.Frame(persona_frame, bg=PANEL_BG)
        row.pack(fill=tk.X, padx=12)
        tk.Label(row, text="Base persona", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        tk.Button(row, text="Edit…", command=self._open_edit_base_persona, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT, padx=(8, 0))
        self._ai_persona_widgets.append(row)
        # Active team count
        tk.Label(persona_frame, text="Active team profiles (12-36)", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(anchor="w", padx=12)
        spin = tk.Spinbox(persona_frame, from_=12, to=36, textvariable=self.ai_active_team_count_var, width=6)
        spin.pack(anchor="w", padx=12, pady=(0, 6))
        self._ai_persona_widgets.append(spin)
        # Buttons to generate defaults and edit team personas
        btn_row = tk.Frame(persona_frame, bg=PANEL_BG)
        btn_row.pack(anchor="w", padx=12, pady=(0, 6))
        tk.Button(btn_row, text="Generate defaults", command=self._generate_persona_defaults, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Edit team personas", command=self._open_persona_editor, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(btn_row, text="Refresh personas", command=self._refresh_persona_choices, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(
            persona_frame,
            text="Base persona is prepended to prompts when 'Base' is selected. Team personas act as role constraints when a team is selected.",
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9, "italic"),
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        local_frame = tk.LabelFrame(parent, text="Local AI Process", bg=PANEL_BG, fg=TEXT_PRIMARY)
        local_frame.configure(labelanchor="nw")
        local_frame.pack(fill=tk.X, padx=4, pady=(0, 12))
        # Backend selector (cli or python)
        backend_row = tk.Frame(local_frame, bg=PANEL_BG)
        backend_row.pack(anchor="w", pady=(6, 4))
        tk.Label(backend_row, text="Backend", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        backend_menu = ttk.Combobox(backend_row, values=["cli", "python"], textvariable=self.ai_local_backend_var, state="readonly", width=10)
        backend_menu.pack(side=tk.LEFT, padx=(8, 0))
        self._ai_local_inputs.append(backend_menu)
        # CLI fields
        command_widgets = self._build_labeled_entry(local_frame, "Command / Executable", self.ai_local_command_var)
        self._ai_local_inputs.extend(command_widgets)
        args_widgets = self._build_labeled_entry(local_frame, "Arguments", self.ai_local_args_var)
        self._ai_local_inputs.extend(args_widgets)
        workdir_widgets = self._build_labeled_entry(local_frame, "Working Directory", self.ai_local_workdir_var)
        self._ai_local_inputs.extend(workdir_widgets)
        # Python backend fields
        widgets = self._build_labeled_entry(local_frame, "Python backend (llama_cpp/transformers)", self.ai_python_backend_var)
        self._ai_local_inputs.extend(widgets)
        self._ai_python_inputs.extend(widgets)
        widgets = self._build_labeled_entry(local_frame, "Model path / HF id", self.ai_model_path_var)
        self._ai_local_inputs.extend(widgets)
        self._ai_python_inputs.extend(widgets)
        widgets = self._build_labeled_entry(local_frame, "Max tokens", self.ai_model_max_tokens_var)
        self._ai_local_inputs.extend(widgets)
        self._ai_python_inputs.extend(widgets)
        widgets = self._build_labeled_entry(local_frame, "Temperature", self.ai_model_temperature_var)
        self._ai_local_inputs.extend(widgets)
        self._ai_python_inputs.extend(widgets)
        tk.Label(
            local_frame,
            text="Local mode can either run a CLI that reads stdin, or use an in-process Python backend (llama-cpp-python or Hugging Face transformers).",
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9, "italic"),
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        detected_frame = tk.LabelFrame(parent, text="Detected Local AI Launchers", bg=PANEL_BG, fg=TEXT_PRIMARY)
        detected_frame.configure(labelanchor="nw")
        detected_frame.pack(fill=tk.BOTH, padx=4, pady=(0, 12))
        listbox_bg = "#111C2D"
        listbox_fg = "#E0E5EC"
        self.ai_detected_listbox = tk.Listbox(
            detected_frame,
            height=5,
            bg=listbox_bg,
            fg=listbox_fg,
            activestyle="dotbox",
            relief=tk.FLAT,
            selectbackground=ACCENT_BG,
            selectforeground="white",
        )
        self.ai_detected_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        self.ai_detected_listbox.bind("<Double-Button-1>", lambda _event: self._apply_selected_local_ai())
        tk.Label(
            detected_frame,
            text="Double-click or select an entry and click \"Apply Selected\" to populate the local fields.",
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9, "italic"),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 6))

        btn_row = tk.Frame(parent, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, pady=(10, 4))
        tk.Button(
            btn_row,
            text="Save Settings",
            command=self._save_ai_settings_from_ui,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            btn_row,
            text="Test Connection",
            command=self._test_ai_connection,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row,
            text="Scan for Local Models",
            command=self._scan_local_ai_inventory,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(
            btn_row,
            text="Apply Selected",
            command=self._apply_selected_local_ai,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.ai_status_label = tk.Label(
            parent,
            textvariable=self.ai_test_status_var,
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "italic"),
            wraplength=400,
            justify="left",
        )
        self.ai_status_label.pack(anchor="w", pady=(8, 0))
        self._update_ai_field_state()
        self._scan_local_ai_inventory()

    def _build_labeled_entry(
        self,
        parent: tk.Widget,
        label_text: str,
        variable: tk.StringVar,
        *,
        show: str | None = None,
    ) -> list[tk.Widget]:
        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(
            row,
            text=label_text,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11),
        ).pack(side=tk.LEFT, padx=(0, 12))
        entry = tk.Entry(
            row,
            textvariable=variable,
            width=40,
            relief=tk.FLAT,
            bg=ENTRY_BG,
            fg=ENTRY_FG,
            insertbackground=ENTRY_FG,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            disabledbackground=ENTRY_BG,
            disabledforeground=ENTRY_FG,
            show=show if show else "",
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return [entry]
    # ---------------------------------------------------------------------
    # Players screen
    # ---------------------------------------------------------------------
    def _build_players_screen(self):
        # Delegate to extracted builder
        from .players_screen import build_players_screen

        build_players_screen(self)
        return
        self.players_frame = tk.Frame(self, bg="#0F1C2E")
        controls = tk.Frame(self.players_frame, bg="#0F1C2E")
        controls.pack(fill=tk.X, padx=20, pady=15)
        tk.Label(
            controls,
            text="Search",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=0, sticky="w")
        self.player_search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            controls,
            textvariable=self.player_search_var,
            width=30,
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            fg=INPUT_PLACEHOLDER_FG,
            bg=ENTRY_BG,
            insertbackground=ENTRY_FG,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            disabledbackground=ENTRY_BG,
            disabledforeground=ENTRY_FG,
        )
        self.search_entry.grid(row=0, column=1, padx=(8, 20), sticky="w")
        self.search_entry.insert(0, "Search players.")
        def _on_search_focus_in(_event):
            if self.search_entry.get() == "Search players.":
                self.search_entry.delete(0, tk.END)
                self.search_entry.configure(fg=INPUT_TEXT_FG)
        def _on_search_focus_out(_event):
            if not self.search_entry.get():
                self.search_entry.insert(0, "Search players.")
                self.search_entry.configure(fg=INPUT_PLACEHOLDER_FG)
        self.search_entry.bind("<FocusIn>", _on_search_focus_in)
        self.search_entry.bind("<FocusOut>", _on_search_focus_out)
        refresh_btn = tk.Button(
            controls,
            text="Refresh",
            command=self._start_scan,
            bg="#778DA9",
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground="#415A77",
            activeforeground=BUTTON_TEXT,
            padx=16,
            pady=4,
        )
        refresh_btn.grid(row=0, column=2, padx=(0, 20))
        tk.Label(
            controls,
            text="Player Dataset",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=3, sticky="w")
        self.dataset_var = tk.StringVar(value="All Data")
        dataset_combo = ttk.Combobox(
            controls,
            textvariable=self.dataset_var,
            values=["All Data"],
            state="readonly",
            width=15,
            style="App.TCombobox",
        )
        dataset_combo.grid(row=0, column=4, padx=(8, 0), sticky="w")
        controls.columnconfigure(5, weight=1)
        self.player_count_var = tk.StringVar(value="Players: 0")
        tk.Label(
            controls,
            textvariable=self.player_count_var,
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=5, sticky="e")
        tk.Label(
            controls,
            text="Team",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.team_var = tk.StringVar()
        self.team_dropdown = ttk.Combobox(
            controls,
            textvariable=self.team_var,
            state="readonly",
            width=25,
            style="App.TCombobox",
        )
        self.team_dropdown.grid(row=1, column=1, padx=(8, 0), pady=(10, 0), sticky="w")
        self.team_dropdown.bind("<<ComboboxSelected>>", self._on_team_selected)
        self.scan_status_var = tk.StringVar(value="")
        self.scan_status_label = tk.Label(
            controls,
            textvariable=self.scan_status_var,
            font=("Segoe UI", 10, "italic"),
            bg="#0F1C2E",
            fg="#9BA4B5",
        )
        self.scan_status_label.grid(row=1, column=2, columnspan=3, sticky="w", pady=(10, 0))
        content = tk.Frame(self.players_frame, bg="#0F1C2E")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        list_container = tk.Frame(content, bg="#0F1C2E")
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.player_listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            exportselection=False,
            font=("Segoe UI", 11),
            bg="#0F1C2E",
            fg="#E0E1DD",
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.player_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.player_listbox.bind("<<ListboxSelect>>", self._on_player_selected)
        self.player_listbox.bind("<Double-Button-1>", lambda _e: self._open_full_editor())
        bind_mousewheel(self.player_listbox)
        list_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.player_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.player_listbox.configure(yscrollcommand=list_scroll.set)
        detail_container = tk.Frame(content, bg="#16213E", width=420)
        # Allow the player detail pane to grow with the window so labels/fields have room.
        detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(20, 0))
        detail_container.pack_propagate(False)
        self.player_portrait = tk.Canvas(detail_container, width=150, height=150, bg="#16213E", highlightthickness=0)
        self.player_portrait.pack(pady=(30, 15))
        self.player_portrait_circle = self.player_portrait.create_oval(25, 25, 125, 125, fill="#415A77", outline="")
        self.player_portrait_text = self.player_portrait.create_text(75, 75, text="", fill="#E0E1DD", font=("Segoe UI", 24, "bold"))
        self.player_name_var = tk.StringVar(value="Select a player")
        self.player_name_label = tk.Label(
            detail_container,
            textvariable=self.player_name_var,
            font=("Segoe UI", 18, "bold"),
            bg="#16213E",
            fg="#E0E1DD",
        )
        self.player_name_label.pack()
        self.player_ovr_var = tk.StringVar(value="OVR --")
        self.player_ovr_label = tk.Label(
            detail_container,
            textvariable=self.player_ovr_var,
            font=("Segoe UI", 14),
            bg="#16213E",
            fg="#E63946",
        )
        self.player_ovr_label.pack(pady=(0, 20))
        info_grid = tk.Frame(detail_container, bg="#16213E")
        info_grid.pack(padx=35, pady=10, fill=tk.X)
        self.player_detail_fields: dict[str, tk.StringVar] = {}
        detail_widgets: dict[str, tk.Widget] = {}
        detail_fields = [
            ("Position", "--"),
            ("Number", "--"),
            ("Height", "--"),
            ("Weight", "--"),
            ("Face ID", "--"),
            ("Unique ID", "--"),
        ]
        for idx, (label, default) in enumerate(detail_fields):
            row = idx // 2
            col = (idx % 2) * 2
            name_label = tk.Label(
                info_grid,
                text=label,
                bg="#16213E",
                fg="#E0E1DD",
                font=("Segoe UI", 11),
            )
            name_label.grid(row=row, column=col, sticky="w", pady=4, padx=(0, 12))
            var = tk.StringVar(value=default)
            value_label = tk.Label(
                info_grid,
                textvariable=var,
                bg="#16213E",
                fg="#9BA4B5",
                font=("Segoe UI", 11, "bold"),
            )
            value_label.grid(row=row, column=col + 1, sticky="w", pady=4, padx=(0, 20))
            self.player_detail_fields[label] = var
            detail_widgets[label] = value_label
        self.player_detail_widgets = detail_widgets
        info_grid.columnconfigure(1, weight=1)
        info_grid.columnconfigure(3, weight=1)
        form = tk.Frame(detail_container, bg="#16213E")
        form.pack(padx=35, pady=(10, 0), fill=tk.X)
        tk.Label(form, text="First Name", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=4)
        self.var_first = tk.StringVar()
        first_entry = tk.Entry(
            form,
            textvariable=self.var_first,
            relief=tk.FLAT,
            width=20,
            fg=ENTRY_FG,
            bg=ENTRY_BG,
            insertbackground=ENTRY_FG,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            disabledbackground=ENTRY_BG,
            disabledforeground=ENTRY_FG,
        )
        first_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))
        tk.Label(form, text="Last Name", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=4)
        self.var_last = tk.StringVar()
        last_entry = tk.Entry(
            form,
            textvariable=self.var_last,
            relief=tk.FLAT,
            width=20,
            fg=ENTRY_FG,
            bg=ENTRY_BG,
            insertbackground=ENTRY_FG,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            disabledbackground=ENTRY_BG,
            disabledforeground=ENTRY_FG,
        )
        last_entry.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        tk.Label(form, text="Team", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w", pady=4)
        self.var_player_team = tk.StringVar()
        team_value_label = tk.Label(
            form,
            textvariable=self.var_player_team,
            bg="#16213E",
            fg="#9BA4B5",
            font=("Segoe UI", 11, "bold"),
        )
        team_value_label.grid(row=2, column=1, sticky="w", pady=4, padx=(8, 0))
        form.columnconfigure(1, weight=1)
        panel_context = {
            "panel_parent": detail_container,
            "detail_widgets": detail_widgets,
            "detail_vars": self.player_detail_fields,
            "first_name_entry": first_entry,
            "last_name_entry": last_entry,
            "team_widget": team_value_label,
            "inspector": self.player_panel_inspector,
            "ai_settings": self.ai_settings,
        }
        for factory in PLAYER_PANEL_EXTENSIONS:
            try:
                factory(self, panel_context)
            except Exception:
                pass
        btn_row = tk.Frame(detail_container, bg="#16213E")
        btn_row.pack(pady=(20, 0))
        self.btn_edit = tk.Button(
            btn_row,
            text="Edit Player",
            command=self._open_full_editor,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            disabledforeground=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_edit.pack(side=tk.LEFT, padx=5)
        self.btn_copy = tk.Button(
            btn_row,
            text="Copy Player",
            command=self._open_copy_dialog,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            disabledforeground=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        self.current_players = []
        self.filtered_player_indices = []
        self.selected_player = None
        self.player_listbox.delete(0, tk.END)
        self.player_count_var.set("Players: 0")
        self.player_listbox.insert(tk.END, "No players available.")
        self.player_search_var.trace_add("write", lambda *_: self._filter_player_list())
    # ---------------------------------------------------------------------
    # Navigation methods
    # ---------------------------------------------------------------------
    def show_home(self):
        """
        Display the Home screen and hide any other visible panes.
        If the Teams or Stadiums panes were previously shown, they are
        explicitly hidden here.  Without forgetting those frames, their
        widgets could remain visible atop the Home screen after navigation.
        """
        self._hide_frames(
            self.players_frame,
            self.teams_frame,
            self.ai_frame,
            self.staff_frame,
            self.stadium_frame,
            self.excel_frame,
        )
        if self.home_frame is not None:
            self.home_frame.pack(fill=tk.BOTH, expand=True)
    def show_players(self):
        """
        Display the Players screen and hide other panes.
        Prior to packing the Players frame, explicitly hide the Home,
        Teams and Stadiums panes.  This prevents UI elements from
        overlapping when switching between tabs.
        """
        self._hide_frames(
            self.home_frame,
            self.teams_frame,
            self.ai_frame,
            self.staff_frame,
            self.stadium_frame,
            self.excel_frame,
        )
        if self.players_frame is not None:
            self.players_frame.pack(fill=tk.BOTH, expand=True)
        # Kick off a background scan to load players and teams
        self._start_scan()

    def show_teams(self):
        """Display the Teams screen and start scanning if necessary."""
        self._hide_frames(
            self.home_frame,
            self.players_frame,
            self.ai_frame,
            self.staff_frame,
            self.stadium_frame,
            self.excel_frame,
        )
        if self.teams_frame is not None:
            self.teams_frame.pack(fill=tk.BOTH, expand=True)
        # Kick off a scan if we don't have team names yet
        if not self.model.get_teams():
            self._start_team_scan()
        else:
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)

    def show_ai(self):
        """Display the AI Assistant screen."""
        self._hide_frames(
            self.home_frame,
            self.players_frame,
            self.teams_frame,
            self.staff_frame,
            self.stadium_frame,
            self.excel_frame,
        )
        if self.ai_frame is not None:
            self.ai_frame.pack(fill=tk.BOTH, expand=True)

    def show_staff(self):
        """Display the Staff screen."""
        self._hide_frames(
            self.home_frame,
            self.players_frame,
            self.teams_frame,
            self.ai_frame,
            self.stadium_frame,
            self.excel_frame,
        )
        if self.staff_frame is not None:
            self.staff_frame.pack(fill=tk.BOTH, expand=True)
            self._refresh_staff_list()

    def show_stadium(self):
        """Display the Stadium screen."""
        self._hide_frames(
            self.home_frame,
            self.players_frame,
            self.teams_frame,
            self.ai_frame,
            self.staff_frame,
            self.excel_frame,
        )
        if self.stadium_frame is not None:
            self.stadium_frame.pack(fill=tk.BOTH, expand=True)
            self._refresh_stadium_list()

    def show_excel(self):
        """Display the Excel import/export screen."""
        self._hide_frames(
            self.home_frame,
            self.players_frame,
            self.teams_frame,
            self.ai_frame,
            self.staff_frame,
            self.stadium_frame,
        )
        if self.excel_frame is not None:
            self.excel_frame.pack(fill=tk.BOTH, expand=True)

    def _current_staff_index(self) -> int | None:
        if self.staff_listbox is None:
            return None
        try:
            selection = self.staff_listbox.curselection()
            if not selection:
                return None
            idx = selection[0]
            if idx < 0 or idx >= len(self._filtered_staff_entries):
                return None
            return self._filtered_staff_entries[idx][0]
        except Exception:
            return None

    def _refresh_staff_list(self) -> None:
        try:
            entries = self.model.refresh_staff()
            self.staff_status_var.set("" if entries else "No staff detected; pointers may be missing.")
        except Exception:
            entries = []
            self.staff_status_var.set("Unable to scan staff.")
        self.staff_entries = entries
        self._filter_staff_list()

    def _filter_staff_list(self, *_args) -> None:
        query = (self.staff_search_var.get() or "").strip().lower()
        filtered = []
        for entry in self.staff_entries:
            name = entry[1]
            if not query or query in name.lower():
                filtered.append(entry)
        self._filtered_staff_entries = filtered
        if self.staff_listbox is None:
            return
        self.staff_listbox.delete(0, tk.END)
        if not filtered:
            self.staff_listbox.insert(tk.END, "No staff found.")
        else:
            for _, name in filtered:
                self.staff_listbox.insert(tk.END, name)
        self.staff_count_var.set(f"Staff: {len(filtered)}")
        try:
            self.staff_listbox.selection_clear(0, tk.END)
        except Exception:
            pass

    def _on_staff_selected(self) -> None:
        # Selection is handled on demand when opening the editor.
        return

    def _current_stadium_index(self) -> int | None:
        if self.stadium_listbox is None:
            return None
        try:
            selection = self.stadium_listbox.curselection()
            if not selection:
                return None
            idx = selection[0]
            if idx < 0 or idx >= len(self._filtered_stadium_entries):
                return None
            return self._filtered_stadium_entries[idx][0]
        except Exception:
            return None

    def _refresh_stadium_list(self) -> None:
        try:
            entries = self.model.refresh_stadiums()
            self.stadium_status_var.set("" if entries else "No stadiums detected; pointers may be missing.")
        except Exception:
            entries = []
            self.stadium_status_var.set("Unable to scan stadiums.")
        self.stadium_entries = entries
        self._filter_stadium_list()

    def _filter_stadium_list(self, *_args) -> None:
        query = (self.stadium_search_var.get() or "").strip().lower()
        filtered = []
        for entry in self.stadium_entries:
            name = entry[1]
            if not query or query in name.lower():
                filtered.append(entry)
        self._filtered_stadium_entries = filtered
        if self.stadium_listbox is None:
            return
        self.stadium_listbox.delete(0, tk.END)
        if not filtered:
            self.stadium_listbox.insert(tk.END, "No stadiums found.")
        else:
            for _, name in filtered:
                self.stadium_listbox.insert(tk.END, name)
        self.stadium_count_var.set(f"Stadiums: {len(filtered)}")
        try:
            self.stadium_listbox.selection_clear(0, tk.END)
        except Exception:
            pass

    def _on_stadium_selected(self) -> None:
        return
    # -----------------------------------------------------------------
    # Randomizer
    # -----------------------------------------------------------------
    def _open_randomizer(self):
        """Open the Randomizer window for mass randomizing player values."""
        try:
            # Ensure we have up-to-date player and team lists
            self.model.refresh_players()
        except Exception:
            pass
        # Launch the randomizer window.  The RandomizerWindow class is
        # defined below.  It will build its own UI and handle
        # randomization logic.
        RandomizerWindow(self, self.model)
    def _open_team_shuffle(self) -> None:
        """Open the Team Shuffle window to shuffle players across selected teams."""
        try:
            # Refresh player list to ensure team assignments are current
            self.model.refresh_players()
        except Exception:
            pass
        TeamShuffleWindow(self, self.model)
    def _open_batch_edit(self) -> None:
        """
        Open the Batch Edit window to set a specific field across
        multiple players.  The BatchEditWindow allows selection of
        one or more teams, a category (Attributes, Tendencies,
        Durability, Vitals, Body, Badges, Contract, etc.), a field
        within that category, and a new value.  When executed, the
        specified value is written to the selected field for every
        player on the chosen teams.  Only live memory editing is
        supported; if the game process is not attached the user will
        be notified and no changes will occur.
        """
        try:
            # Refresh player and team lists; ignore errors if scanning fails
            self.model.refresh_players()
        except Exception:
            pass
        # Launch the batch edit window.  Any exceptions raised during
        # creation will be reported via a messagebox.
        try:
            BatchEditWindow(self, self.model)
        except Exception as exc:
            import traceback
            messagebox.showerror("Batch Edit", f"Failed to open batch edit window: {exc}")
            traceback.print_exc()

    # -----------------------------------------------------------------
    # Excel import/export
    # -----------------------------------------------------------------
    def _open_import_dialog(self) -> None:
        """Open the Excel import screen."""
        self.show_excel()

    def _open_export_dialog(self) -> None:
        """Open the Excel export screen."""
        self.show_excel()

    def _open_load_excel(self) -> None:
        """Open the Excel screen (alias for older control bridge calls)."""
        self.show_excel()

    def _reset_excel_progress(self) -> None:
        progress = self.excel_progress
        if progress is None:
            return
        try:
            progress.stop()
        except Exception:
            pass
        progress.configure(mode="determinate", maximum=100)
        self.excel_progress_var.set(0)
        self.update_idletasks()

    def _apply_excel_progress(
        self,
        verb: str,
        entity_label: str,
        current: int,
        total: int,
        sheet_name: str | None,
    ) -> None:
        progress = self.excel_progress
        if progress is not None and total > 0:
            try:
                maximum = int(progress.cget("maximum"))
            except Exception:
                maximum = 0
            if maximum != total:
                progress.configure(maximum=total)
            self.excel_progress_var.set(current)
        status = f"{verb} {entity_label}"
        if sheet_name:
            status = f"{status} ({sheet_name})"
        if total > 0:
            status = f"{status} {current}/{total}"
        self.excel_status_var.set(status)
        self.update_idletasks()

    def _excel_progress_callback(
        self,
        verb: str,
        entity_label: str,
    ) -> Callable[[int, int, str | None], None]:
        def _callback(current: int, total: int, sheet_name: str | None) -> None:
            self._apply_excel_progress(verb, entity_label, current, total, sheet_name)

        return _callback

    def _queue_excel_export_progress(self, current: int, total: int, sheet_name: str | None) -> None:
        if self._excel_export_queue is None:
            return
        self._excel_export_queue.put(("progress", current, total, sheet_name))

    def _poll_excel_export(self) -> None:
        if self._excel_export_queue is None:
            self._excel_export_polling = False
            return
        done_seen = False
        done_result = None
        done_error = None
        try:
            while True:
                item = self._excel_export_queue.get_nowait()
                if not item:
                    continue
                kind = item[0]
                if kind == "progress":
                    current = int(item[1]) if len(item) > 1 else 0
                    total = int(item[2]) if len(item) > 2 else 0
                    sheet_name = item[3] if len(item) > 3 else None
                    self._apply_excel_progress(
                        "Exporting",
                        self._excel_export_entity_label,
                        current,
                        total,
                        sheet_name,
                    )
                elif kind == "done":
                    done_seen = True
                    done_result = item[1] if len(item) > 1 else None
                    done_error = item[2] if len(item) > 2 else None
        except queue.Empty:
            pass
        if done_seen:
            self._finish_excel_export(done_result, done_error)
            return
        if self._excel_export_thread is not None and self._excel_export_thread.is_alive():
            self._excel_export_polling = True
            self.after(100, self._poll_excel_export)
        else:
            self._excel_export_polling = False

    def _finish_excel_export(self, result: object | None, error: object | None) -> None:
        self._excel_export_thread = None
        self._excel_export_queue = None
        self._excel_export_polling = False
        self._reset_excel_progress()
        self.excel_status_var.set("")
        if error is not None:
            messagebox.showerror("Excel Export", f"Export failed: {error}")
            return
        if result is None:
            messagebox.showerror("Excel Export", "Export failed: Unknown error.")
            return
        try:
            summary = result.summary_text()  # type: ignore[union-attr]
        except Exception:
            summary = "Export completed."
        messagebox.showinfo("Excel Export", summary)

    def _import_excel(self, entity_type: str) -> None:
        try:
            from ..importing.excel_import import import_excel_workbook, template_path_for
        except Exception as exc:
            messagebox.showerror("Excel Import", f"Import helpers not available: {exc}")
            return
        if not self.model.mem.open_process():
            messagebox.showerror("Excel Import", "NBA 2K26 is not running.")
            return
        entity_key = (entity_type or "").strip().lower()
        template = template_path_for(entity_key)
        path = filedialog.askopenfilename(
            title="Select Excel workbook to import",
            initialdir=str(template.parent),
            initialfile=str(template.name),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not path:
            return
        try:
            if entity_key in ("players", "teams"):
                self.model.refresh_players()
            elif entity_key == "staff":
                self.model.refresh_staff()
            elif entity_key in ("stadiums", "stadium"):
                self.model.refresh_stadiums()
        except Exception:
            pass
        self._reset_excel_progress()
        self.excel_status_var.set(f"Importing {entity_key}...")
        progress_cb = self._excel_progress_callback("Importing", entity_key.title())
        try:
            result = import_excel_workbook(self.model, path, entity_key, progress_cb=progress_cb)
        except Exception as exc:
            self.excel_status_var.set("")
            self._reset_excel_progress()
            messagebox.showerror("Excel Import", f"Import failed: {exc}")
            return
        self.excel_status_var.set("")
        self._reset_excel_progress()
        if result.missing_names:
            roster_names: list[str]
            if entity_key == "players":
                roster_names = [p.full_name for p in self.model.players]
                missing_label = "Players not found - type to search the current roster"
            elif entity_key == "teams":
                roster_names = self.model.get_teams()
                missing_label = "Teams not found - type to search the current list"
            elif entity_key == "staff":
                roster_names = self.model.get_staff()
                missing_label = "Staff not found - type to search the current list"
            else:
                roster_names = self.model.get_stadiums()
                missing_label = "Stadiums not found - type to search the current list"

            def _apply_mapping(mapping: dict[str, str]) -> None:
                if not mapping:
                    return
                self._reset_excel_progress()
                try:
                    follow = import_excel_workbook(
                        self.model,
                        path,
                        entity_key,
                        name_overrides=mapping,
                        only_names=set(mapping.keys()),
                        progress_cb=progress_cb,
                    )
                except Exception as exc:
                    self._reset_excel_progress()
                    messagebox.showerror("Excel Import", f"Import failed: {exc}")
                    return
                self._reset_excel_progress()
                messagebox.showinfo("Excel Import", follow.summary_text())

            ImportSummaryDialog(
                self,
                f"{entity_key.title()} Import Summary",
                result.summary_text(),
                result.missing_names,
                roster_names,
                apply_callback=_apply_mapping,
                missing_label=missing_label,
            )
        else:
            messagebox.showinfo("Excel Import", result.summary_text())

    def _export_excel(self, entity_type: str) -> None:
        try:
            from ..importing.excel_import import export_excel_workbook, template_path_for
        except Exception as exc:
            messagebox.showerror("Excel Export", f"Export helpers not available: {exc}")
            return
        if self._excel_export_thread is not None and self._excel_export_thread.is_alive():
            messagebox.showinfo("Excel Export", "An export is already running.")
            return
        if not self.model.mem.open_process():
            messagebox.showerror("Excel Export", "NBA 2K26 is not running.")
            return
        entity_key = (entity_type or "").strip().lower()
        template = template_path_for(entity_key)
        default_name = template.name.replace(".xlsx", "_export.xlsx")
        path = filedialog.asksaveasfilename(
            title="Save export workbook",
            initialdir=str(template.parent),
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not path:
            return
        self._reset_excel_progress()
        use_cached = False
        if entity_key == "players":
            use_cached = bool(self.model.players)
        elif entity_key == "teams":
            use_cached = bool(self.model.team_list)
        elif entity_key == "staff":
            use_cached = bool(self.model.staff_list)
        elif entity_key in ("stadiums", "stadium"):
            use_cached = bool(self.model.stadium_list)
        status_label = f"Exporting {entity_key}..."
        if use_cached:
            status_label = f"Exporting {entity_key} (cached scan)..."
        self.excel_status_var.set(status_label)
        self._excel_export_entity_label = entity_key.title()
        self._excel_export_queue = queue.Queue()
        progress_cb = self._queue_excel_export_progress

        def _run_export() -> None:
            try:
                if entity_key == "players":
                    if not self.model.players:
                        self.model.refresh_players()
                elif entity_key == "teams":
                    if not self.model.team_list:
                        self.model.refresh_players()
                elif entity_key == "staff":
                    if not self.model.staff_list:
                        self.model.refresh_staff()
                elif entity_key in ("stadiums", "stadium"):
                    if not self.model.stadium_list:
                        self.model.refresh_stadiums()
                result = export_excel_workbook(
                    self.model,
                    path,
                    entity_key,
                    template_path=template,
                    progress_cb=progress_cb,
                )
                if self._excel_export_queue is not None:
                    self._excel_export_queue.put(("done", result, None))
            except Exception as exc:
                if self._excel_export_queue is not None:
                    self._excel_export_queue.put(("done", None, exc))

        self._excel_export_thread = threading.Thread(target=_run_export, daemon=True)
        self._excel_export_thread.start()
        if not self._excel_export_polling:
            self._poll_excel_export()
    def _build_teams_screen(self):
        """Construct the Teams editing screen."""
        self.teams_frame = tk.Frame(self, bg="#0F1C2E")
        controls = tk.Frame(self.teams_frame, bg="#0F1C2E")
        controls.pack(fill=tk.X, padx=20, pady=15)
        tk.Label(
            controls,
            text="Search",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=0, sticky="w")
        self.team_search_var = tk.StringVar()
        self.team_search_entry = tk.Entry(
            controls,
            textvariable=self.team_search_var,
            width=30,
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            fg=INPUT_PLACEHOLDER_FG,
            bg=ENTRY_BG,
            insertbackground=ENTRY_FG,
            highlightthickness=1,
            highlightbackground=ENTRY_BORDER,
            disabledbackground=ENTRY_BG,
            disabledforeground=ENTRY_FG,
        )
        self.team_search_entry.grid(row=0, column=1, padx=(8, 20), sticky="w")
        self.team_search_entry.insert(0, "Search teams.")
        def _on_team_search_focus_in(_event):
            if self.team_search_entry.get() == "Search teams.":
                self.team_search_entry.delete(0, tk.END)
                self.team_search_entry.configure(fg=INPUT_TEXT_FG)
        def _on_team_search_focus_out(_event):
            if not self.team_search_entry.get():
                self.team_search_entry.insert(0, "Search teams.")
                self.team_search_entry.configure(fg=INPUT_PLACEHOLDER_FG)
        self.team_search_entry.bind("<FocusIn>", _on_team_search_focus_in)
        self.team_search_entry.bind("<FocusOut>", _on_team_search_focus_out)
        refresh_btn = tk.Button(
            controls,
            text="Refresh",
            command=self._start_team_scan,
            bg="#778DA9",
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground="#415A77",
            activeforeground=BUTTON_TEXT,
            padx=16,
            pady=4,
        )
        refresh_btn.grid(row=0, column=2, padx=(0, 20))
        self.team_count_var = tk.StringVar(value="Teams: 0")
        tk.Label(
            controls,
            textvariable=self.team_count_var,
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=3, sticky="e")
        controls.columnconfigure(4, weight=1)
        # Scan status label for teams
        self.team_scan_status_var = tk.StringVar()
        self.team_scan_status_label = tk.Label(
            controls,
            textvariable=self.team_scan_status_var,
            font=("Segoe UI", 10, "italic"),
            bg="#0F1C2E",
            fg="#9BA4B5",
        )
        self.team_scan_status_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        content = tk.Frame(self.teams_frame, bg="#0F1C2E")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        list_container = tk.Frame(content, bg="#0F1C2E")
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.team_editor_listbox = tk.Listbox(
            list_container,
            selectmode=tk.SINGLE,
            exportselection=False,
            font=("Segoe UI", 11),
            bg="#0F1C2E",
            fg="#E0E1DD",
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.team_editor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.team_editor_listbox.bind("<<ListboxSelect>>", self._on_team_listbox_select)
        bind_mousewheel(self.team_editor_listbox)
        team_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.team_editor_listbox.yview)
        team_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.team_editor_listbox.configure(yscrollcommand=team_scroll.set)
        detail_container = tk.Frame(content, bg="#16213E", width=460)
        # Let the team detail pane expand so field inputs are not cramped.
        detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(20, 0))
        detail_container.pack_propagate(False)
        self.team_editor_detail_name_var = tk.StringVar(value="Select a team")
        tk.Label(
            detail_container,
            textvariable=self.team_editor_detail_name_var,
            font=("Segoe UI", 18, "bold"),
            bg="#16213E",
            fg="#E0E1DD",
        ).pack(pady=(25, 10))
        tk.Label(
            detail_container,
            text="Team Details",
            font=("Segoe UI", 12, "bold"),
            bg="#16213E",
            fg="#E0E1DD",
        ).pack(anchor="w", padx=30, pady=(0, 6))
        # Form for each team field
        self.team_editor_field_vars: Dict[str, tk.StringVar] = {}
        form = tk.Frame(detail_container, bg="#16213E")
        form.pack(fill=tk.X, padx=30, pady=5)
        row = 0
        if TEAM_FIELD_DEFS:
            for label in TEAM_FIELD_DEFS.keys():
                tk.Label(form, text=f"{label}:", bg="#16213E", fg="#9BA4B5").grid(row=row, column=0, sticky=tk.W, pady=2)
                var = tk.StringVar()
                entry = tk.Entry(
                    form,
                    textvariable=var,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    relief=tk.FLAT,
                    insertbackground=ENTRY_FG,
                    highlightthickness=1,
                    highlightbackground=ENTRY_BORDER,
                    highlightcolor=ENTRY_BORDER,
                    disabledbackground=ENTRY_BG,
                    disabledforeground=ENTRY_FG,
                )
                entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
                self.team_editor_field_vars[label] = var
                row += 1
            form.columnconfigure(1, weight=1)
        else:
            tk.Label(
                form,
                text="No team field offsets found. Update Offsets/offsets.json to enable editing.",
                bg="#16213E",
                fg="#B0413E",
                wraplength=360,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=4)
        # Action buttons
        btn_row = tk.Frame(detail_container, bg="#16213E")
        btn_row.pack(fill=tk.X, padx=30, pady=16)
        self.btn_team_save = tk.Button(
            btn_row,
            text="Save Fields",
            command=self._save_team,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_team_save.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_team_full = tk.Button(
            btn_row,
            text="Edit Team",
            command=self._open_full_team_editor,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_team_full.pack(side=tk.LEFT)
        # Data holders for filtering
        self.team_edit_var = tk.StringVar()
        self.all_team_names: list[str] = []
        self.filtered_team_names: list[str] = []
        self.team_editor_listbox.insert(tk.END, "No teams available.")
        self.team_search_var.trace_add("write", self._filter_team_list)
    def _start_team_scan(self) -> None:
        """Kick off a scan from the Teams screen."""
        if self.scanning:
            return
        self.scanning = True
        status_msg = "Scanning... please wait"
        self.team_scan_status_var.set(status_msg)
        self.scan_status_var.set(status_msg)
        if self.player_listbox is not None:
            self.player_listbox.delete(0, tk.END)
            self.player_listbox.insert(tk.END, "Scanning players...")
        threading.Thread(target=self._scan_teams_thread, daemon=True).start()
    def _filter_team_list(self, *_args) -> None:
        """Filter the visible teams based on the search box."""
        if not hasattr(self, "team_editor_listbox") or self.team_editor_listbox is None:
            return
        query_raw = (self.team_search_var.get() or "").strip().lower()
        placeholder = "search teams."
        teams = list(self.all_team_names or [])
        if teams and query_raw and query_raw != placeholder:
            filtered = [t for t in teams if query_raw in str(t).lower()]
        else:
            filtered = teams
        self.filtered_team_names = filtered
        self.team_editor_listbox.delete(0, tk.END)
        if not filtered:
            self.team_editor_listbox.insert(tk.END, "No teams available.")
            self.team_count_var.set("Teams: 0")
            self.team_edit_var.set("")
            self.team_editor_detail_name_var.set("Select a team")
            for var in self.team_editor_field_vars.values():
                var.set("")
            self._update_team_players(None)
            if self.btn_team_full is not None:
                self.btn_team_full.config(state=tk.DISABLED)
            if self.btn_team_save is not None:
                self.btn_team_save.config(state=tk.DISABLED)
            return
        for name in filtered:
            self.team_editor_listbox.insert(tk.END, name)
        self.team_count_var.set(f"Teams: {len(filtered)}")
        target_name = self.team_edit_var.get()
        if not target_name or target_name not in filtered:
            target_name = filtered[0]
            self.team_edit_var.set(target_name)
        self._select_team_in_listbox(target_name)
        self._on_team_edit_selected()
    def _select_team_in_listbox(self, team_name: str | None) -> None:
        """Select the given team in the list without re-triggering events."""
        if not team_name or not hasattr(self, "team_editor_listbox") or self.team_editor_listbox is None:
            if hasattr(self, "team_editor_listbox") and self.team_editor_listbox is not None:
                self.team_editor_listbox.selection_clear(0, tk.END)
            return
        try:
            idx = self.filtered_team_names.index(team_name)
        except ValueError:
            return
        self._suppress_team_list_event = True
        try:
            self.team_editor_listbox.selection_clear(0, tk.END)
            self.team_editor_listbox.selection_set(idx)
            self.team_editor_listbox.see(idx)
        finally:
            self._suppress_team_list_event = False
    def _on_team_listbox_select(self, _event=None):
        """Handle selection from the team list."""
        if getattr(self, "_suppress_team_list_event", False):
            return
        if not hasattr(self, "team_editor_listbox") or self.team_editor_listbox is None:
            return
        selection = self.team_editor_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.filtered_team_names):
            return
        team_name = self.filtered_team_names[idx]
        self.team_edit_var.set(team_name)
        self._on_team_edit_selected()
    def _scan_teams_thread(self):
        """Background thread to refresh players and teams for the Teams screen."""
        # Use the same refresh mechanism as players
        self.model.refresh_players()
        teams = self.model.get_teams()
        def update_ui():
            self.scanning = False
            self._update_team_dropdown(teams)
            self._refresh_player_list()
            status_msg = ""
            if not self.model.mem.hproc:
                status_msg = "NBA 2K26 is not running."
            elif not teams:
                status_msg = "No teams available."
            self.team_scan_status_var.set(status_msg)
            self.scan_status_var.set(status_msg)
            if getattr(self, "_pending_team_select", None) and teams:
                target = self._pending_team_select
                if target in teams:
                    self.team_edit_var.set(target)
                    self._on_team_edit_selected()
                self._pending_team_select = None
        self.after(0, update_ui)
    def _update_team_dropdown(self, teams: list[str]):
        """Helper to update both team dropdowns (players and teams screens)."""
        # Update players screen dropdown if it exists
        if self.team_dropdown is not None:
            previous_selection = self.team_var.get()
            sanitized = [name for name in teams if str(name).strip().lower() != "draft class"]
            player_list = ["All Players", "Draft Class"]
            player_list.extend(sanitized)
            self.team_dropdown['values'] = player_list
            if previous_selection in player_list:
                self.team_var.set(previous_selection)
            elif player_list:
                self.team_var.set(player_list[0])
            else:
                self.team_var.set("")
            # Keep the players screen team listbox in sync
            if hasattr(self, "player_team_listbox") and self.player_team_listbox is not None:
                self.player_team_listbox.delete(0, tk.END)
                for name in sanitized:
                    self.player_team_listbox.insert(tk.END, name)
                # Reapply selection if still valid
                if previous_selection in sanitized:
                    try:
                        idx = sanitized.index(previous_selection)
                        self.player_team_listbox.selection_set(idx)
                        self.player_team_listbox.see(idx)
                    except Exception:
                        self.player_team_listbox.selection_clear(0, tk.END)
        # Update teams screen list
        pending_team = getattr(self, "_pending_team_select", None)
        if pending_team and pending_team in (teams or []):
            self.team_edit_var.set(pending_team or "")
        self.all_team_names = list(teams or [])
        self._filter_team_list()
    def _on_team_edit_selected(self, event=None):
        """Load team field values when a team is selected."""
        team_name = self.team_edit_var.get()
        self.team_editor_detail_name_var.set(team_name if team_name else "Select a team")
        self._select_team_in_listbox(team_name)
        if not team_name:
            if self.btn_team_save is not None:
                self.btn_team_save.config(state=tk.DISABLED)
            if self.btn_team_full is not None:
                self.btn_team_full.config(state=tk.DISABLED)
            for var in self.team_editor_field_vars.values():
                var.set("")
            self._update_team_players(None)
            return
        # Find team index
        teams = self.model.get_teams()
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                if self.btn_team_save is not None:
                    self.btn_team_save.config(state=tk.DISABLED)
                self._update_team_players(None)
                return
        fields = self.model.get_team_fields(team_idx)
        if fields is None:
            # Not connected or cannot read
            for var in self.team_editor_field_vars.values():
                var.set("")
            if self.btn_team_save is not None:
                self.btn_team_save.config(state=tk.DISABLED)
            self._update_team_players(None)
            return
        # Populate fields
        for label, var in self.team_editor_field_vars.items():
            val = fields.get(label, "")
            var.set(val)
        self._update_team_players(team_idx)
        # Enable save if process open
        enable_live = bool(self.model.mem.hproc)
        if self.btn_team_save is not None:
            self.btn_team_save.config(state=tk.NORMAL if enable_live else tk.DISABLED)
        if self.btn_team_full is not None:
            self.btn_team_full.config(state=tk.NORMAL if enable_live else tk.DISABLED)
    def _save_team(self):
        """Save the edited team fields back to memory."""
        team_name = self.team_edit_var.get()
        if not team_name:
            return
        teams = self.model.get_teams()
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                return
        values = {label: var.get() for label, var in self.team_editor_field_vars.items()}
        ok = self.model.set_team_fields(team_idx, values)
        if ok:
            messagebox.showinfo("Success", f"Updated {team_name} successfully.")
            # Refresh team list to reflect potential name change
            self.model.refresh_players()
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)
            # Reselect the updated team name if changed
            new_name = values.get("Team Name")
            if new_name:
                self.team_edit_var.set(new_name)
            self._on_team_edit_selected()
            return
        else:
            messagebox.showerror("Error", "Failed to write team data. Make sure the game is running and try again.")

    def _open_full_team_editor(self) -> None:
        """Open the full team editor window for the selected team."""
        team_name = self.team_edit_var.get()
        if not team_name:
            messagebox.showinfo("Edit Team", "Please select a team first.")
            return
        teams = self.model.get_teams()
        if not teams:
            messagebox.showinfo("Edit Team", "No teams available. Refresh and try again.")
            return
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                messagebox.showerror("Edit Team", "Selected team could not be resolved.")
                return
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        if not self.model.mem.hproc:
            messagebox.showinfo("Edit Team", "NBA 2K26 is not running. Launch the game to edit team data.")
            return
        try:
            editor = FullTeamEditor(self, team_idx, team_name, self.model)
            editor.grab_set()
        except Exception as exc:
            messagebox.showerror("Edit Team", f"Unable to open team editor: {exc}")

    def _open_full_staff_editor(self, staff_idx: int | None = None) -> None:
        """Open the staff editor (requires staff pointers/stride)."""
        try:
            if staff_idx is None:
                staff_idx = self._current_staff_index() or 0
            editor = FullStaffEditor(self, self.model, staff_idx)
            editor.grab_set()
        except Exception as exc:
            messagebox.showerror("Staff Editor", f"Unable to open staff editor: {exc}")

    def _open_full_stadium_editor(self, stadium_idx: int | None = None) -> None:
        """Open the stadium editor (requires stadium pointers/stride)."""
        try:
            if stadium_idx is None:
                stadium_idx = self._current_stadium_index() or 0
            editor = FullStadiumEditor(self, self.model, stadium_idx)
            editor.grab_set()
        except Exception as exc:
            messagebox.showerror("Stadium Editor", f"Unable to open stadium editor: {exc}")

    def _open_team_editor_from_player(self) -> None:
        """Jump to the Teams screen and select the player's team."""
        team_name = (self.var_player_team.get() or "").strip()
        # Switch to teams view
        self.show_teams()
        if not team_name:
            return
        teams = self.model.get_teams()
        if not teams:
            # Defer selection until scan completes
            self._pending_team_select = team_name
            if not self.scanning:
                self._start_team_scan()
            return
        if team_name not in teams:
            return
        self._pending_team_select = None
        self.team_edit_var.set(team_name)
        self._on_team_edit_selected()

    def _update_team_players(self, team_idx: int | None) -> None:
        if not hasattr(self, 'team_players_listbox') or self.team_players_listbox is None:
            return
        self.team_players_listbox.delete(0, tk.END)
        self.team_players_lookup = []
        if team_idx is None:
            return
        players: list[Player] = []
        try:
            if self.model.mem.hproc and self.model.mem.base_addr and not self.model.external_loaded:
                players = self.model.scan_team_players(team_idx)
        except Exception:
            players = []
        if not players:
            teams = self.model.get_teams()
            if 0 <= team_idx < len(teams):
                team_name = teams[team_idx]
                players = self.model.get_players_by_team(team_name)
        self.team_players_lookup = players
        if players:
            for player in players:
                self.team_players_listbox.insert(tk.END, player.full_name)
        else:
            self.team_players_listbox.insert(tk.END, "(No players found)")

    def _open_team_player_editor(self, _event=None) -> None:
        listbox = getattr(self, 'team_players_listbox', None)
        if listbox is None:
            return
        selection = listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.team_players_lookup):
            return
        player = self.team_players_lookup[idx]
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        editor = FullPlayerEditor(self, player, self.model)
        editor.grab_set()


    # ---------------------------------------------------------------------
    # Home helpers
    # ---------------------------------------------------------------------
    def _hook_label_for(self, executable: str | None) -> str:
        """Return a friendly name for the supplied game executable."""
        exec_key = (executable or MODULE_NAME).lower()
        if exec_key in HOOK_TARGET_LABELS:
            return HOOK_TARGET_LABELS[exec_key]
        base = (executable or MODULE_NAME).replace(".exe", "")
        return base.upper()

    def _set_hook_target(self, executable: str) -> None:
        """Update the target executable used for live memory hooks."""
        target = executable or MODULE_NAME
        previous_module = (self.model.mem.module_name or MODULE_NAME).lower()
        self.hook_target_var.set(target)
        if previous_module != target.lower():
            self.model.mem.close()
        self.model.mem.module_name = target
        self._update_status()

    def _update_status(self):
        target_exec = self.hook_target_var.get() or self.model.mem.module_name or MODULE_NAME
        target_exec_lower = target_exec.lower()
        # Ensure the memory helper is aligned with the selected target.
        self.model.mem.module_name = target_exec
        target_label = self._hook_label_for(target_exec)
        if self.model.mem.open_process():
            pid = self.model.mem.pid
            actual_exec = self.model.mem.module_name or target_exec
            actual_lower = actual_exec.lower()
            if actual_lower != target_exec_lower:
                self.hook_target_var.set(actual_exec)
                target_exec = actual_exec
                target_exec_lower = actual_lower
                target_label = self._hook_label_for(actual_exec)
            if _offset_config is None or _current_offset_target != actual_lower:
                try:
                    initialize_offsets(target_executable=actual_exec, force=True)
                    self.model.invalidate_base_cache()
                except OffsetSchemaError as exc:
                    messagebox.showerror("Offset schema error", str(exc))
                    self.status_var.set(f"{target_label} detected but offsets failed to load")
                    return
            self.model.mem.module_name = target_exec
            try:
                self.model.prime_bases(open_process=False)
            except Exception:
                pass
            self.status_var.set(f"{target_label} is running (PID {pid})")
        else:
            self.status_var.set(f"{target_label} not detected - launch the game to enable editing")

    def _set_dynamic_scan_status(self, message: str) -> None:
        """Update the dynamic base scan status label safely from worker threads."""
        try:
            self.after(0, lambda: self.dynamic_scan_status_var.set(message))
        except Exception:
            self.dynamic_scan_status_var.set(message)

    def _open_offset_file_dialog(self) -> None:
        """Allow the user to load a custom offsets JSON file."""
        path = filedialog.askopenfilename(
            title="Select offsets file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        fname = Path(path).name
        self.offset_load_status_var.set(f"Loading offsets from {fname}...")
        target_exec = self.hook_target_var.get() or self.model.mem.module_name or MODULE_NAME
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:
            self.offset_load_status_var.set("Failed to read offsets file.")
            self.after(0, lambda: messagebox.showerror("Offsets load failed", f"Could not read {fname}.\n{exc}"))
            return

        def _resolve_payload(raw_obj: object) -> dict | None:
            converted = offsets_mod._convert_merged_offsets_schema(raw_obj, target_exec)
            if converted:
                return converted
            selected = offsets_mod._select_merged_offset_entry(raw_obj, target_exec)
            if selected and selected is not raw_obj:
                converted_selected = offsets_mod._convert_merged_offsets_schema(selected, target_exec)
                return converted_selected or selected
            if isinstance(raw_obj, dict):
                return raw_obj
            return None

        data = _resolve_payload(raw)
        if not isinstance(data, dict):
            self.offset_load_status_var.set("Offsets file format not recognized.")
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Offsets load failed",
                    f"{fname} does not look like a valid offsets file.",
                ),
            )
            return
        try:
            offsets_mod._offset_file_path = Path(path)
            offsets_mod._offset_config = data
            offsets_mod.MODULE_NAME = target_exec
            offsets_mod._current_offset_target = (target_exec or MODULE_NAME).lower()
            base_overrides = getattr(offsets_mod, "_base_pointer_overrides", None)
            if base_overrides:
                offsets_mod._apply_base_pointer_overrides(data, base_overrides)
            offsets_mod._apply_offset_config(data)
            self.model.categories = offsets_mod._load_categories()
            self.offset_load_status_var.set(f"Loaded offsets from {fname}")
            self.model.invalidate_base_cache()
            self._update_status()
            self._start_scan()
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Offsets loaded",
                    f"Loaded offsets from {fname}",
                ),
            )
        except Exception as exc:
            self.offset_load_status_var.set("Failed to apply offsets file.")
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Offsets load failed",
                    f"Unable to apply offsets from {fname}.\n{exc}",
                ),
            )

    def _start_dynamic_base_scan(self) -> None:
        """Start a background dynamic base discovery run."""
        if self.dynamic_scan_in_progress:
            return
        self.dynamic_scan_in_progress = True
        self._set_dynamic_scan_status("Scanning for player and team bases...")
        threading.Thread(target=self._run_dynamic_base_scan, daemon=True).start()

    def _run_dynamic_base_scan(self) -> None:
        """Worker that runs dynamic base discovery and applies overrides."""
        try:
            target_exec = self.hook_target_var.get() or self.model.mem.module_name or MODULE_NAME
            self.model.mem.module_name = target_exec
            target_label = self._hook_label_for(target_exec)
            if not self.model.mem.open_process():
                self._set_dynamic_scan_status(f"{target_label} is not running. Launch the game and try again.")
                return
            offset_target = self.model.mem.module_name or target_exec
            try:
                initialize_offsets(target_executable=offset_target, force=False)
            except OffsetSchemaError as exc:
                self._set_dynamic_scan_status("Offsets failed to load; cannot run dynamic discovery.")
                self.after(0, lambda: messagebox.showerror("Offsets not loaded", str(exc)))
                return
            base_hints: dict[str, int] = {}
            cfg: dict[str, object] | None = getattr(offsets_mod, "_offset_config", None)
            target_key = getattr(offsets_mod, "_current_offset_target", None) or (offset_target or MODULE_NAME).lower()
            base_map: dict[str, object] = {}
            versions: dict[str, object] = {}
            if isinstance(cfg, dict):
                base_raw = cfg.get("base_pointers")
                if isinstance(base_raw, dict):
                    base_map = base_raw
                versions_raw = cfg.get("versions")
                if isinstance(versions_raw, dict):
                    versions = versions_raw
                version_key = None
                try:
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
                    if not absolute and self.model.mem.base_addr:
                        addr_int = self.model.mem.base_addr + addr_int
                    return addr_int

                p_hint = _extract_addr("Player")
                t_hint = _extract_addr("Team")
                if p_hint:
                    base_hints["Player"] = p_hint
                if t_hint:
                    base_hints["Team"] = t_hint
            team_name_len = offsets_mod.TEAM_NAME_LENGTH if offsets_mod.TEAM_NAME_LENGTH > 0 else 24
            try:
                overrides, report = find_dynamic_bases(
                    process_name=offset_target,
                    player_stride=offsets_mod.PLAYER_STRIDE,
                    team_stride=offsets_mod.TEAM_STRIDE,
                    first_offset=offsets_mod.OFF_FIRST_NAME,
                    last_offset=offsets_mod.OFF_LAST_NAME,
                    team_name_offset=offsets_mod.TEAM_NAME_OFFSET,
                    team_name_length=team_name_len,
                    pid=self.model.mem.pid,
                    player_base_hint=base_hints.get("Player"),
                    team_base_hint=base_hints.get("Team"),
                    run_parallel=True,
                )
                self.last_dynamic_base_report = report or {}
                self.last_dynamic_base_overrides = overrides or {}
                try:
                    self.model.mem.last_dynamic_base_report = self.last_dynamic_base_report
                    self.model.mem.last_dynamic_base_overrides = self.last_dynamic_base_overrides
                except Exception:
                    pass
            except Exception as exc:
                self._set_dynamic_scan_status(f"Dynamic scan failed: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Dynamic base discovery",
                        f"Dynamic base scan failed; using offsets file.\n{exc}",
                    ),
                )
                return
            if overrides:
                try:
                    initialize_offsets(
                        target_executable=offset_target,
                        force=False,
                        base_pointer_overrides=overrides,
                    )
                    self.model.invalidate_base_cache()
                    addr_parts = []
                    player_addr = overrides.get("Player")
                    team_addr = overrides.get("Team")
                    if player_addr:
                        addr_parts.append(f"Player 0x{int(player_addr):X}")
                    if team_addr:
                        addr_parts.append(f"Team 0x{int(team_addr):X}")
                    summary = "Applied dynamic bases" + (f": {', '.join(addr_parts)}" if addr_parts else ".")
                    self._set_dynamic_scan_status(summary)
                    self.after(0, self._update_status)
                    self.after(0, self._start_scan)
                    self.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Dynamic base discovery",
                            summary,
                        ),
                    )
                except OffsetSchemaError as exc:
                    self._set_dynamic_scan_status(f"Dynamic bases found but failed to apply: {exc}")
                    self.after(
                        0,
                        lambda: messagebox.showwarning(
                            "Dynamic base discovery",
                            f"Dynamic bases found but failed to apply: {exc}",
                        ),
                    )
            else:
                fallback = ""
                if isinstance(report, dict) and report.get("error"):
                    fallback = str(report["error"])
                if not fallback:
                    fallback = "No dynamic bases were found; using offsets file values instead."
                self._set_dynamic_scan_status(fallback)
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Dynamic base discovery",
                        fallback,
                    ),
                )
        finally:
            self.dynamic_scan_in_progress = False
    # ---------------------------------------------------------------------
    # Scanning players
    # ---------------------------------------------------------------------
    def _start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        status_msg = "Scanning... please wait"
        if self.player_listbox is not None:
            self.player_listbox.delete(0, tk.END)
            self.player_listbox.insert(tk.END, "Scanning players...")
        self.scan_status_var.set(status_msg)
        self.team_scan_status_var.set(status_msg)
        # Launch in a separate thread to avoid blocking UI
        threading.Thread(target=self._scan_thread, daemon=True).start()
    def _scan_thread(self):
        self.model.refresh_players()
        teams = self.model.get_teams()
        def update_ui():
            self.scanning = False
            # Update both dropdowns via helper
            self._update_team_dropdown(teams)
            self._refresh_player_list()
            status_msg = ""
            if not self.model.mem.hproc:
                status_msg = "NBA 2K26 is not running."
            elif not teams:
                status_msg = "No teams available."
            self.scan_status_var.set(status_msg)
            self.team_scan_status_var.set(status_msg)
        self.after(0, update_ui)
    # ---------------------------------------------------------------------
    # UI update helpers
    # ---------------------------------------------------------------------
    def _refresh_player_list(self):
        team = (self.team_var.get() or "").strip()
        if not team:
            team = "All Players"
        # Ensure combobox reflects the current filter
        try:
            self.team_var.set(team)
        except Exception:
            pass
        if team.lower() == "all players" and not self.model.players:
            if self.scanning:
                status_msg = "Scanning... please wait"
            elif not self.model.mem.hproc:
                status_msg = "NBA 2K26 is not running."
            else:
                status_msg = "Players not loaded. Click Scan to load players."
            self.scan_status_var.set(status_msg)
            self.team_scan_status_var.set(status_msg)
        # Get the players for the selected team.  Store them in
        # ``current_players`` so the search filter can operate on
        # a stable list without hitting the model repeatedly.
        self.current_players = self.model.get_players_by_team(team) if team else []
        # Apply search filtering.  This will rebuild the listbox and
        # update ``filtered_player_indices``.  If no search term is set
        # (i.e. placeholder text), all players are displayed.
        self._filter_player_list()
        # Reset selection and detail fields
        self.selected_player = None
        self._update_detail_fields()
    def _clear_player_cards(self, message: str = "") -> None:
        if self.player_listbox is not None:
            self.player_listbox.delete(0, tk.END)
            if message:
                self.player_listbox.insert(tk.END, message)
        self.player_name_var.set("Select a player")
        self.player_ovr_var.set("OVR --")
        self.var_first.set("")
        self.var_last.set("")
        self.var_player_team.set("")
        for var in self.player_detail_fields.values():
            var.set("--")
        if self.player_portrait is not None:
            try:
                self.player_portrait.itemconfig(self.player_portrait_text, text="")
            except Exception:
                pass
        self.player_count_var.set("Players: 0")
        if self.btn_save is not None:
            self.btn_save.config(state=tk.DISABLED)
        if self.btn_edit is not None:
            self.btn_edit.config(state=tk.DISABLED)
        if self.btn_copy is not None:
            self.btn_copy.config(state=tk.DISABLED)
    def _filter_player_list(self) -> None:
        """Filter the player list based on the search entry and repopulate."""
        search = (self.player_search_var.get() or "").strip().lower()
        if search == "search players.":
            search = ""
        if self.player_listbox is None:
            return
        listbox = self.player_listbox
        listbox.delete(0, tk.END)
        self.filtered_player_indices = []
        if not self.current_players:
            if not self.model.mem.hproc:
                listbox.insert(tk.END, "NBA 2K26 is not running.")
            else:
                listbox.insert(tk.END, "No players available.")
            self.player_count_var.set("Players: 0")
            return
        visible_names: list[str] = []
        if not search:
            self.filtered_player_indices = list(range(len(self.current_players)))
            visible_names = [player.full_name for player in self.current_players]
        else:
            for idx, player in enumerate(self.current_players):
                if search in player.full_name.lower():
                    self.filtered_player_indices.append(idx)
                    visible_names.append(player.full_name)
        if not visible_names:
            if self.current_players:
                listbox.insert(tk.END, "No players match the current filter.")
            else:
                listbox.insert(tk.END, "No players available.")
        else:
            # Insert in chunks to avoid thousands of Tk calls on large rosters.
            chunk_size = 500
            for start in range(0, len(visible_names), chunk_size):
                listbox.insert(tk.END, *visible_names[start:start + chunk_size])
        self.player_count_var.set(f"Players: {len(self.filtered_player_indices)}")
    def _on_team_selected(self, event=None):
        """Handle team selection from the players screen."""
        selected_team = (self.team_var.get() or "").strip()
        if self.player_team_listbox is not None:
            selection = self.player_team_listbox.curselection()
            if selection:
                idx = selection[0]
                try:
                    selected_team = self.player_team_listbox.get(idx)
                    self.team_var.set(str(selected_team) if selected_team is not None else "")
                except Exception:
                    selected_team = self.team_var.get()
        self._refresh_player_list()
    def _on_player_selected(self, event=None):
        if self.player_listbox is None:
            return
        selection = self.player_listbox.curselection()
        selected_players: list[Player] = []
        for idx in selection:
            if idx < len(self.filtered_player_indices):
                p_idx = self.filtered_player_indices[idx]
                if p_idx < len(self.current_players):
                    selected_players.append(self.current_players[p_idx])
        self.selected_players = selected_players
        self.selected_player = selected_players[0] if selected_players else None
        self._update_detail_fields()
    def _update_detail_fields(self):
        p = self.selected_player
        selection_count = len(self.selected_players)
        if not p:
            # Clear fields
            self.player_name_var.set("Select a player")
            self.player_ovr_var.set("OVR --")
            self.var_first.set("")
            self.var_last.set("")
            self.var_player_team.set("")
            if self.btn_save is not None:
                self.btn_save.config(state=tk.DISABLED)
            if self.btn_edit is not None:
                self.btn_edit.config(state=tk.DISABLED)
            if self.btn_copy is not None:
                self.btn_copy.config(state=tk.DISABLED)
            for var in self.player_detail_fields.values():
                var.set("--")
            try:
                if self.player_portrait is not None:
                    self.player_portrait.itemconfig(self.player_portrait_text, text="")
            except Exception:
                pass
        else:
            display_name = p.full_name or f"Player {p.index}"
            if selection_count > 1:
                display_name = f"{display_name} (+{selection_count - 1} more)"
            self.player_name_var.set(display_name)
            initials = "".join(part[0].upper() for part in (p.first_name, p.last_name) if part) or "?"
            try:
                if self.player_portrait is not None:
                    self.player_portrait.itemconfig(self.player_portrait_text, text=initials[:2])
            except Exception:
                pass
            self.var_first.set(p.first_name)
            self.var_last.set(p.last_name)
            self.var_player_team.set(p.team)
            snapshot: dict[str, object] = {}
            try:
                snapshot = self.model.get_player_panel_snapshot(p)
            except Exception:
                snapshot = {}
            overall_val = snapshot.get("Overall")
            if isinstance(overall_val, (int, float)):
                self.player_ovr_var.set(f"OVR {int(overall_val)}")
            else:
                self.player_ovr_var.set("OVR --")
            def _format_detail(label: str, value: object) -> str:
                if label == "Height" and isinstance(value, (int, float)):
                    inches_val = int(value)
                    if inches_val > HEIGHT_MAX_INCHES:
                        inches_val = raw_height_to_inches(inches_val)
                    inches_val = max(HEIGHT_MIN_INCHES, min(HEIGHT_MAX_INCHES, inches_val))
                    return format_height_inches(inches_val)
                if value is None:
                    return "--"
                if isinstance(value, float):
                    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"
                return str(value)
            for label, var in self.player_detail_fields.items():
                var.set(_format_detail(label, snapshot.get(label)))
        # Save button enabled only if connected to game and not loaded from files
        enable_save = self.model.mem.hproc is not None and not self.model.external_loaded
        if self.btn_save is not None:
            self.btn_save.config(state=tk.NORMAL if enable_save else tk.DISABLED)
        if self.btn_edit is not None:
            self.btn_edit.config(state=tk.NORMAL)
        # Copy button enabled if connected and not loaded from files.  We
        # defer determining actual destination availability until the
        # copy dialog is opened.
        enable_copy = enable_save and p is not None
        if self.btn_copy is not None:
            self.btn_copy.config(state=tk.NORMAL if enable_copy else tk.DISABLED)
        inspector = getattr(self, "player_panel_inspector", None)
        if inspector:
            inspector.refresh_for_player()
    # ---------------------------------------------------------------------
    # Saving and editing
    # ---------------------------------------------------------------------
    def _save_player(self):
        p = self.selected_player
        if not p:
            return
        # Update from entry fields
        p.first_name = self.var_first.get().strip()
        p.last_name = self.var_last.get().strip()
        try:
            self.model.update_player(p)
            messagebox.showinfo("Success", "Player updated successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save changes:\n{e}")
        # Refresh list to reflect potential name changes
        self._refresh_player_list()
    def _open_full_editor(self):
        players = self.selected_players or ([self.selected_player] if self.selected_player else [])
        if not players:
            return
        editor = FullPlayerEditor(self, players, self.model)
        editor.grab_set()
    def _open_copy_dialog(self):
        """Open a dialog allowing the user to copy data from the selected player to another."""
        src = self.selected_player
        if not src:
            return
        # Prepare list of destination players (exclude source)
        dest_players: list[Player] = []
        if self.model.players:
            dest_players = [p for p in self.model.players if p.index != src.index]
        elif self.model.team_list:
            for idx, _ in self.model.team_list:
                players = self.model.scan_team_players(idx)
                for p in players:
                    if p.index != src.index:
                        dest_players.append(p)
        # Remove duplicate names (based on index) while preserving order
        seen = set()
        uniq_dest = []
        for p in dest_players:
            if p.index not in seen:
                seen.add(p.index)
                uniq_dest.append(p)
        dest_players = uniq_dest
        if not dest_players:
            messagebox.showinfo("Copy Player Data", "No other players are available to copy to.")
            return
        # Create dialog window
        win = tk.Toplevel(self)
        win.title("Copy Player Data")
        win.geometry("400x320")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        # Source label
        tk.Label(win, text=f"Copy from: {src.full_name}", font=("Segoe UI", 12, "bold")).pack(pady=(10, 5))
        # Destination dropdown
        dest_var = tk.StringVar()
        dest_names = [p.full_name for p in dest_players]
        dest_map = {p.full_name: p for p in dest_players}
        dest_frame = tk.Frame(win)
        dest_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        tk.Label(dest_frame, text="Copy to:", font=("Segoe UI", 10)).pack(side=tk.LEFT)
        dest_combo = ttk.Combobox(dest_frame, textvariable=dest_var, values=dest_names, state="readonly")
        dest_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5))
        if dest_names:
            dest_var.set(dest_names[0])
        # Category checkboxes
        chk_frame = tk.Frame(win)
        chk_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        tk.Label(chk_frame, text="Data to copy:", font=("Segoe UI", 10)).pack(anchor=tk.W)
        var_full = tk.IntVar(value=0)
        var_attributes = tk.IntVar(value=0)
        var_tendencies = tk.IntVar(value=0)
        var_badges = tk.IntVar(value=0)
        cb1 = tk.Checkbutton(chk_frame, text="Full Player", variable=var_full)
        cb3 = tk.Checkbutton(chk_frame, text="Attributes", variable=var_attributes)
        cb4 = tk.Checkbutton(chk_frame, text="Tendencies", variable=var_tendencies)
        cb5 = tk.Checkbutton(chk_frame, text="Badges", variable=var_badges)
        cb1.pack(anchor=tk.W)
        cb3.pack(anchor=tk.W)
        cb4.pack(anchor=tk.W)
        cb5.pack(anchor=tk.W)
        # Buttons for copy/cancel
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        def do_copy():
            dest_name = dest_var.get()
            dest_player = dest_map.get(dest_name)
            if not dest_player:
                messagebox.showerror("Copy Player Data", "No destination player selected.")
                return
            categories = []
            if var_full.get():
                categories = ["full"]
            else:
                if var_attributes.get():
                    categories.append("attributes")
                if var_tendencies.get():
                    categories.append("tendencies")
                if var_badges.get():
                    categories.append("badges")
            if not categories:
                messagebox.showwarning("Copy Player Data", "Please select at least one data category to copy.")
                return
            success = self.model.copy_player_data(
                src.index,
                dest_player.index,
                categories,
                src_record_ptr=getattr(src, "record_ptr", None),
                dst_record_ptr=getattr(dest_player, "record_ptr", None),
            )
            if success:
                messagebox.showinfo("Copy Player Data", "Data copied successfully.")
                # Refresh the player list to reflect any changes
                self._start_scan()
            else:
                messagebox.showerror("Copy Player Data", "Failed to copy data. Make sure the game is running and try again.")
            win.destroy()
        tk.Button(btn_frame, text="Copy", command=do_copy, bg="#84A98C", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=win.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

__all__ = ["PlayerEditorApp"]
