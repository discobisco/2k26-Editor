"""Main application window (ported from the monolithic editor)."""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING, Callable, Sequence, cast
import difflib

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
    COY_SHEET_ID,
    COY_SHEET_TABS,
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
from ..importing import csv_import, excel_import
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from .batch_edit import BatchEditWindow
from .dialogs import CategorySelectionDialog, ImportSummaryDialog
from .full_player_editor import FullPlayerEditor
from .full_team_editor import FullTeamEditor
from .full_staff_editor import FullStaffEditor
from .full_stadium_editor import FullStadiumEditor
from .randomizer import RandomizerWindow
from .team_shuffle import TeamShuffleWindow
from .theme import apply_base_theme
from .widgets import bind_mousewheel

if TYPE_CHECKING:
    class RawFieldInspectorExtension:  # minimal stub for type checkers
        ...
from . import import_flows, extensions_ui
from .home_screen import build_home_screen
from .ai_screen import build_ai_screen
from .players_screen import build_players_screen
from .teams_screen import build_teams_screen
from .staff_screen import build_staff_screen
from .stadium_screen import build_stadium_screen
from ..ai.assistant import ensure_control_bridge

_EXTENSION_LOGGER = __import__('logging').getLogger('nba2k26.extensions')
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
        self.ai_local_command_var = tk.StringVar()
        self.ai_local_args_var = tk.StringVar()
        self.ai_local_workdir_var = tk.StringVar()
        self.ai_test_status_var = tk.StringVar(value="")
        self._ai_remote_inputs: list[tk.Widget] = []
        self._ai_local_inputs: list[tk.Widget] = []
        self.ai_status_label: tk.Label | None = None
        self.ai_detected_listbox: tk.Listbox | None = None
        self.local_ai_inventory: list[LocalAIDetectionResult] = []
        self.ai_assistant = None
        self.control_bridge = None
        self._load_ai_settings_into_vars()
        # Extension loader state
        self.extension_vars: dict[str, tk.BooleanVar] = {}
        self.extension_checkbuttons: dict[str, tk.Checkbutton] = {}
        self.loaded_extensions: set[str] = set()
        self.extension_status_var = tk.StringVar(value="")
        # Control bridge for external AI agents
        self._start_control_bridge()
        # Team/UI placeholders
        self.team_dropdown: ttk.Combobox | None = None
        self.player_team_listbox: tk.Listbox | None = None
        self.team_editor_field_vars: dict[str, tk.StringVar] = {}
        self.team_editor_detail_name_var: tk.StringVar = tk.StringVar()
        self.team_scan_status_var: tk.StringVar = tk.StringVar()
        self.status_var: tk.StringVar = tk.StringVar()
        self.scan_status_var: tk.StringVar = tk.StringVar()
        self.player_count_var: tk.StringVar = tk.StringVar(value="Players: 0")
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
        build_ai_screen(self)
        self._build_excel_screen()
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
        self.ai_local_command_var.set(str(local.get("command", "")) if isinstance(local, dict) else "")
        self.ai_local_args_var.set(str(local.get("arguments", "")) if isinstance(local, dict) else "")
        self.ai_local_workdir_var.set(str(local.get("working_dir", "")) if isinstance(local, dict) else "")
        self.ai_test_status_var.set("")

    def _load_ai_settings(self) -> dict[str, object]:
        base = copy.deepcopy(DEFAULT_AI_SETTINGS)
        try:
            if AI_SETTINGS_PATH.exists():
                with AI_SETTINGS_PATH.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        self._merge_dict(base, data)
        except Exception:
            _EXTENSION_LOGGER.exception("Failed to load AI settings; using defaults.")
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

    def _collect_ai_settings(self) -> dict[str, object]:
        mode = self.ai_mode_var.get().strip() or "none"
        settings: dict[str, object] = {
            "mode": mode,
            "remote": {
                "base_url": self.ai_api_base_var.get().strip(),
                "api_key": self.ai_api_key_var.get().strip(),
                "model": self.ai_model_var.get().strip(),
                "timeout": self._coerce_int(self.ai_api_timeout_var.get(), default=30),
            },
            "local": {
                "command": self.ai_local_command_var.get().strip(),
                "arguments": self.ai_local_args_var.get().strip(),
                "working_dir": self.ai_local_workdir_var.get().strip(),
            },
        }
        return settings

    def get_ai_settings(self) -> dict[str, object]:
        """Return a copy of the current AI integration settings."""
        return copy.deepcopy(self.ai_settings)

    @staticmethod
    def _coerce_int(value: str, default: int = 0) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _save_ai_settings_from_ui(self) -> None:
        settings = self._collect_ai_settings()
        self.ai_settings = settings
        self._save_ai_settings(settings)
        self._set_ai_status("AI settings saved.", success=True)

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
            text="Staff (preview)",
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
            text="Stadium (preview)",
            command=self.show_stadium,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_stadium.pack(fill=tk.X, padx=10, pady=5)
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
        # 2K COY button
        # This button imports player data from external tables (e.g. Google
        # Sheets export) and applies it to the roster.  It expects the
        # import files to follow the same column ordering as the batch
        # import functionality already implemented.  When complete it
        # displays a summary of how many players were updated and
        # lists any players that could not be found.  See
        # ``_open_2kcoy`` for details.
        self.btn_coy = tk.Button(
            self.sidebar,
            text="2K COY",
            command=self._open_2kcoy,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_coy.pack(fill=tk.X, padx=10, pady=5)
        # Excel I/O hub button (import/export templates)
        self.btn_excel_hub = tk.Button(
            self.sidebar,
            text="Excel Import / Export",
            command=self.show_excel,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_excel_hub.pack(fill=tk.X, padx=10, pady=5)
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
    def _discover_extension_files(self) -> list[Path]:
        return extensions_ui.discover_extension_files()

    def _is_extension_loaded(self, path: Path) -> bool:
        return extensions_ui.is_extension_loaded(self, path)

    def _reload_with_selected_extensions(self) -> None:
        extensions_ui.reload_with_selected_extensions(self)

    def _autoload_extensions_from_file(self) -> None:
        extensions_ui.autoload_extensions_from_file(self)

    def _toggle_extension_module(self, path: Path, var: tk.BooleanVar) -> None:
        extensions_ui.toggle_extension_module(self, path, var)

    def _load_extension_module(self, path: Path) -> bool:
        return extensions_ui.load_extension_module(path)

    def _build_ai_settings_tab(self, parent: tk.Frame) -> None:
        for widget_list in (self._ai_remote_inputs, self._ai_local_inputs):
            widget_list.clear()
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
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "API Key", self.ai_api_key_var, show="*"))
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "Model", self.ai_model_var))
        self._ai_remote_inputs.extend(self._build_labeled_entry(remote_frame, "Timeout (s)", self.ai_api_timeout_var))

        local_frame = tk.LabelFrame(parent, text="Local AI Process", bg=PANEL_BG, fg=TEXT_PRIMARY)
        local_frame.configure(labelanchor="nw")
        local_frame.pack(fill=tk.X, padx=4, pady=(0, 12))
        command_widgets = self._build_labeled_entry(local_frame, "Command / Executable", self.ai_local_command_var)
        self._ai_local_inputs.extend(command_widgets)
        args_widgets = self._build_labeled_entry(local_frame, "Arguments", self.ai_local_args_var)
        self._ai_local_inputs.extend(args_widgets)
        workdir_widgets = self._build_labeled_entry(local_frame, "Working Directory", self.ai_local_workdir_var)
        self._ai_local_inputs.extend(workdir_widgets)

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
        detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(20, 0))
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
        edit_team_btn = tk.Button(
            form,
            text="Edit Team",
            command=self._open_team_editor_from_player,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            padx=10,
            pady=4,
        )
        edit_team_btn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
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
            except Exception as exc:
                _EXTENSION_LOGGER.exception("Player panel extension failed: %s", exc)
        btn_row = tk.Frame(detail_container, bg="#16213E")
        btn_row.pack(pady=(20, 0))
        self.btn_save = tk.Button(
            btn_row,
            text="Save",
            command=self._save_player,
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
        self.btn_save.pack(side=tk.LEFT, padx=5)
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
        self.btn_import = tk.Button(
            btn_row,
            text="Import Data",
            command=self._open_import_dialog,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            padx=16,
            pady=6,
        )
        self.btn_import.pack(side=tk.LEFT, padx=5)
        self.btn_export = tk.Button(
            btn_row,
            text="Export CSV",
            command=self._open_export_dialog,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            padx=16,
            pady=6,
        )
        self.btn_export.pack(side=tk.LEFT, padx=5)
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
        self._hide_frames(self.players_frame, self.teams_frame, self.ai_frame, self.staff_frame, self.stadium_frame, self.excel_frame)
        if self.home_frame is not None:
            self.home_frame.pack(fill=tk.BOTH, expand=True)
        self._update_status()

    def show_players(self):
        """
        Display the Players screen and hide other panes.
        Prior to packing the Players frame, explicitly hide the Home,
        Teams and Stadiums panes.  This prevents UI elements from
        overlapping when switching between tabs.
        """
        self._hide_frames(self.home_frame, self.teams_frame, self.ai_frame, self.staff_frame, self.stadium_frame, self.excel_frame)
        if self.players_frame is not None:
            self.players_frame.pack(fill=tk.BOTH, expand=True)
        # Kick off a background scan to load players and teams
        self._start_scan()

    def show_teams(self):
        """Display the Teams screen and start scanning if necessary."""
        self._hide_frames(self.home_frame, self.players_frame, self.ai_frame, self.staff_frame, self.stadium_frame, self.excel_frame)
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
        self._hide_frames(self.home_frame, self.players_frame, self.teams_frame, self.staff_frame, self.stadium_frame, self.excel_frame)
        if self.ai_frame is not None:
            self.ai_frame.pack(fill=tk.BOTH, expand=True)

    def show_staff(self):
        """Display the Staff screen."""
        self._hide_frames(self.home_frame, self.players_frame, self.teams_frame, self.ai_frame, self.stadium_frame, self.excel_frame)
        if self.staff_frame is not None:
            self.staff_frame.pack(fill=tk.BOTH, expand=True)

    def show_stadium(self):
        """Display the Stadium screen."""
        self._hide_frames(self.home_frame, self.players_frame, self.teams_frame, self.ai_frame, self.staff_frame, self.excel_frame)
        if self.stadium_frame is not None:
            self.stadium_frame.pack(fill=tk.BOTH, expand=True)

    def show_excel(self):
        """Display the Excel import/export screen."""
        self._hide_frames(self.home_frame, self.players_frame, self.teams_frame, self.ai_frame, self.staff_frame, self.stadium_frame)
        if self.excel_frame is not None:
            self.excel_frame.pack(fill=tk.BOTH, expand=True)
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
    def _open_2kcoy(self) -> None:
        import_flows.open_2kcoy(self)

    def _open_load_excel(self) -> None:
        """
        Prompt the user to import player updates from a single Excel workbook.
        Uses the bundled Excel import logic to read the workbook and apply
        matching tabs directly (Attributes/Tendencies/etc). Avoids the COY flow.
        """
        # Refresh players to ensure we have up-to-date indices
        try:
            self.model.refresh_players()
        except Exception:
            pass
        # Require the game to be running
        if not self.model.mem.hproc:
            messagebox.showinfo(
                "Excel Import",
                "NBA 2K26 does not appear to be running. Please launch the game and "
                "load a roster before importing."
            )
            return
        # Prompt for the Excel workbook first
        workbook_path = filedialog.askopenfilename(
            title="Select Excel or CSV File",
            filetypes=[("Excel/CSV files", "*.xlsx *.xls *.csv *.tsv"), ("All files", "*.*")],
        )
        if not workbook_path:
            return
        match_response = messagebox.askyesnocancel(
            "Excel Import",
            "Match players by name?\n\nYes = match each row to a roster player by name.\n"
            "No = overwrite players in current roster order.\nCancel = abort import.",
        )
        if match_response is None:
            return
        match_by_name = bool(match_response)
        try:
            loading_win = tk.Toplevel(self)
            loading_win.title("Loading")
            loading_win.geometry("350x120")
            loading_win.resizable(False, False)
            tk.Label(
                loading_win,
                text="Loading data... Please wait and do not click the updater.",
                wraplength=320,
                justify="left",
            ).pack(padx=20, pady=20)
            loading_win.update_idletasks()
            results = excel_import.import_excel_workbook(self.model, workbook_path, match_by_name=match_by_name)
        except Exception as exc:
            messagebox.showerror("Excel Import", f"Failed to import workbook:\n{exc}")
            try:
                loading_win.destroy()
            except Exception:
                pass
            return
        finally:
            try:
                loading_win.destroy()
            except Exception:
                pass
        try:
            self.model.refresh_players()
        except Exception:
            pass
        missing_bucket = getattr(self.model, "import_partial_matches", {}).get("excel_missing", {}) or {}
        not_found = list(missing_bucket.keys())
        msg_lines = ["Excel import completed."]
        if not match_by_name:
            msg_lines.append("\nImport applied using roster order (names were not matched).")
        if results:
            msg_lines.append("\nPlayers updated:")
            for cat, cnt in results.items():
                msg_lines.append(f"  {cat}: {cnt}")
        if not_found:
            msg_lines.append(f"\nPlayers not found: {len(not_found)}")
        summary = "\n".join(msg_lines)
        self._show_import_summary(
            title="Excel Import",
            summary_lines=msg_lines,
            missing_players=sorted(not_found),
            apply_callback=None,
            context="excel",
        )
    def _show_import_summary(
        self,
        title: str,
        summary_lines: list[str],
        missing_players: list[str],
        apply_callback: Callable[[dict[str, str]], None] | None = None,
        *,
        context: str = "default",
    ) -> None:
        """Display an import summary with optional lookup helpers for missing players."""
        summary_text = "\n".join(summary_lines)
        roster_names = [p.full_name for p in self.model.players if (p.first_name or p.last_name)]
        if not missing_players or not roster_names:
            messagebox.showinfo(title, summary_text)
            return
        partial_matches = getattr(self.model, "import_partial_matches", {}) or {}
        suggestions: dict[str, str] = {}
        suggestion_scores: dict[str, float] = {}
        score_threshold = 0.92 if context != "coy" else 0.0
        for mapping in partial_matches.values():
            if not mapping:
                continue
            for raw_name, candidates in mapping.items():
                if not candidates:
                    continue
                first = candidates[0]
                candidate_name = ""
                candidate_score: float | None = None
                if isinstance(first, dict):
                    candidate_name = str(first.get("name", "")).strip()
                    raw_score = first.get("score")
                    if isinstance(raw_score, (int, float)):
                        candidate_score = float(raw_score)
                elif isinstance(first, (tuple, list)) and first:
                    candidate_name = str(first[0]).strip()
                    if len(first) > 1 and isinstance(first[1], (int, float)):
                        candidate_score = float(first[1])
                else:
                    candidate_name = str(first).strip()
                key = str(raw_name or "").strip()
                if not key or not candidate_name:
                    continue
                if candidate_score is None:
                    if score_threshold <= 0.0 and context == "coy":
                        suggestions.setdefault(key, candidate_name)
                elif candidate_score >= score_threshold:
                    if key not in suggestions:
                        suggestions[key] = candidate_name
                    suggestion_scores.setdefault(key, candidate_score)
        if context == "coy":
            roster_lookup = {name.lower(): name for name in roster_names}
            for raw_name in missing_players:
                key = str(raw_name or "").strip()
                if not key or key in suggestions:
                    continue
                best_candidate = roster_lookup.get(key.lower())
                best_score = 1.0 if best_candidate else 0.0
                if not best_candidate:
                    matches = difflib.get_close_matches(key, roster_names, n=1, cutoff=0.0)
                    if matches:
                        candidate = matches[0]
                        best_candidate = candidate
                        best_score = difflib.SequenceMatcher(
                            None, key.lower(), candidate.lower()
                        ).ratio()
                    else:
                        lower_matches = difflib.get_close_matches(
                            key.lower(), list(roster_lookup.keys()), n=1, cutoff=0.0
                        )
                        if lower_matches:
                            candidate = roster_lookup.get(lower_matches[0])
                            if candidate:
                                best_candidate = candidate
                                best_score = difflib.SequenceMatcher(
                                    None, key.lower(), candidate.lower()
                                ).ratio()
                    if best_candidate:
                        suggestions[key] = best_candidate
                        suggestion_scores.setdefault(key, best_score)
        ImportSummaryDialog(
            self,
            title,
            summary_text,
            missing_players,
            roster_names,
            apply_callback=apply_callback,
            suggestions=suggestions if suggestions else None,
            suggestion_scores=suggestion_scores if suggestion_scores else None,
            require_confirmation=context == "coy",
        )

    def _open_excel_hub(self) -> None:
        """Unified Excel import/export window with per-category controls."""
        try:
            self.model.refresh_players()
        except Exception:
            pass
        if self._excel_hub_win and tk.Toplevel.winfo_exists(self._excel_hub_win):
            try:
                self._excel_hub_win.lift()
                return
            except Exception:
                self._excel_hub_win = None
        hub = tk.Toplevel(self)
        self._excel_hub_win = hub
        hub.title("Excel Import / Export")
        hub.geometry("780x520")
        hub.resizable(True, True)
        hub.configure(bg=PANEL_BG)
        main = tk.Frame(hub, bg=PANEL_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Import section
        import_frame = tk.LabelFrame(main, text="Import Excel", bg=PANEL_BG, fg=TEXT_PRIMARY)
        import_frame.configure(labelanchor="nw")
        import_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=4)
        import_path_var = tk.StringVar()
        tk.Label(import_frame, text="Workbook", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        tk.Entry(import_frame, textvariable=import_path_var, width=38, bg=INPUT_BG, fg=INPUT_TEXT_FG, relief=tk.FLAT).grid(
            row=0, column=1, sticky="we", padx=(0, 6), pady=(8, 2)
        )

        def _browse_import():
            path = filedialog.askopenfilename(
                parent=hub,
                title="Select Excel or CSV File",
                filetypes=[("Excel/CSV files", "*.xlsx *.xls *.csv *.tsv"), ("All files", "*.*")],
            )
            if path:
                import_path_var.set(path)

        tk.Button(import_frame, text="Browse", command=_browse_import, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).grid(
            row=0, column=2, padx=(0, 6), pady=(8, 2)
        )
        match_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            import_frame,
            text="Match players by name",
            variable=match_var,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
        ).grid(row=1, column=1, sticky="w", padx=(0, 6), pady=(2, 6))
        import_status = tk.StringVar(value="")
        tk.Label(import_frame, textvariable=import_status, bg=PANEL_BG, fg=TEXT_SECONDARY, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 2)
        )
        import_frame.columnconfigure(1, weight=1)

        def _run_import():
            path = import_path_var.get().strip()
            if not path:
                messagebox.showinfo("Excel Import", "Choose a workbook to import.")
                return
            if not self.model.mem.hproc:
                messagebox.showinfo(
                    "Excel Import",
                    "NBA 2K26 does not appear to be running. Please launch the game and load a roster before importing.",
                )
                return
            try:
                loading = tk.Toplevel(hub)
                loading.title("Importing...")
                loading.geometry("300x110")
                loading.resizable(False, False)
                tk.Label(loading, text="Importing workbook...\nPlease wait.", justify="center").pack(padx=20, pady=20)
                loading.update_idletasks()
            except Exception:
                loading = None
            try:
                results = excel_import.import_excel_workbook(self.model, path, match_by_name=bool(match_var.get()))
                try:
                    self.model.refresh_players()
                except Exception:
                    pass
            except Exception as exc:
                import_status.set(f"Import failed: {exc}")
                if loading:
                    loading.destroy()
                return
            finally:
                if loading:
                    try:
                        loading.destroy()
                    except Exception:
                        pass
            missing_bucket = getattr(self.model, "import_partial_matches", {}).get("excel_missing", {}) or {}
            not_found = len(missing_bucket)
            lines = [f"Imported {sum(results.values()) if results else 0} players."]
            if results:
                for cat, cnt in results.items():
                    lines.append(f"  {cat}: {cnt}")
            if not_found:
                lines.append(f"Players not found: {not_found}")
            import_status.set("\n".join(lines))

        tk.Button(import_frame, text="Import Workbook", command=_run_import, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).grid(
            row=3, column=1, sticky="w", padx=(0, 6), pady=(6, 10)
        )
        # Export section
        export_frame = tk.LabelFrame(main, text="Export Excel", bg=PANEL_BG, fg=TEXT_PRIMARY)
        export_frame.configure(labelanchor="nw")
        export_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0), pady=4)
        categories = self.model.categories or {}
        super_map = getattr(offsets_mod, "CATEGORY_SUPER_TYPES", {}) or {}
        super_map_lower = {str(k).lower(): str(v) for k, v in super_map.items()}
        grouped: dict[str, list[str]] = {}
        allowed_supers = {"players", "teams", "staff", "stadiums"}
        for cat in categories:
            sup = super_map.get(cat) or super_map_lower.get(cat.lower())
            if not sup or str(sup).lower() not in allowed_supers:
                continue
            grouped.setdefault(str(sup), []).append(cat)
        export_vars: dict[str, tk.BooleanVar] = {}
        group_container = tk.Frame(export_frame, bg=PANEL_BG)
        group_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        for sup, cats in sorted(grouped.items(), key=lambda kv: kv[0]):
            lf = tk.LabelFrame(group_container, text=sup.title(), bg=PANEL_BG, fg=TEXT_PRIMARY)
            lf.configure(labelanchor="nw")
            lf.pack(fill=tk.X, padx=4, pady=4)
            cols = 2
            for idx, cat in enumerate(sorted(cats)):
                var = tk.BooleanVar(value=(sup.lower() == "players"))
                export_vars[cat] = var
                chk = tk.Checkbutton(
                    lf,
                    text=cat,
                    variable=var,
                    bg=PANEL_BG,
                    fg=TEXT_PRIMARY,
                    activebackground=PANEL_BG,
                    activeforeground=TEXT_PRIMARY,
                    selectcolor=ACCENT_BG,
                )
                chk.grid(row=idx // cols, column=idx % cols, sticky="w", padx=4, pady=2)
            lf.columnconfigure(0, weight=1)
            lf.columnconfigure(1, weight=1)
        tk.Label(export_frame, text="Output Folder", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(anchor="w", padx=6, pady=(6, 0))
        export_dir_var = tk.StringVar()
        dir_row = tk.Frame(export_frame, bg=PANEL_BG)
        dir_row.pack(fill=tk.X, padx=6, pady=(0, 6))
        tk.Entry(dir_row, textvariable=export_dir_var, width=42, bg=INPUT_BG, fg=INPUT_TEXT_FG, relief=tk.FLAT).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )

        def _browse_export():
            path = filedialog.askdirectory(parent=hub, title="Select export folder")
            if path:
                export_dir_var.set(path)

        tk.Button(dir_row, text="Browse", command=_browse_export, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT)
        raw_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            export_frame,
            text="Also export raw player records",
            variable=raw_var,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
        ).pack(anchor="w", padx=6, pady=(0, 4))
        prog_frame = tk.Frame(export_frame, bg=PANEL_BG)
        prog_frame.pack(fill=tk.X, padx=6, pady=(4, 6))
        prog_var = tk.IntVar(value=0)
        prog_max = tk.IntVar(value=100)
        prog_bar = ttk.Progressbar(
            prog_frame, orient=tk.HORIZONTAL, mode="determinate", variable=prog_var, maximum=prog_max.get(), length=300
        )
        prog_bar.pack(fill=tk.X, expand=True)
        exp_status = tk.StringVar(value="")
        tk.Label(export_frame, textvariable=exp_status, bg=PANEL_BG, fg=TEXT_SECONDARY, justify="left").pack(
            anchor="w", padx=6, pady=(2, 8)
        )

        def _export_progress(done: int, total: int, label: str) -> None:
            try:
                if total > 0:
                    prog_max.set(total)
                    prog_bar.configure(maximum=total)
                prog_var.set(done)
                exp_status.set(f"{label}: {done}/{total if total else '?'}")
                prog_frame.update_idletasks()
            except Exception:
                pass

        def _run_export():
            selected = [cat for cat, var in export_vars.items() if var.get()]
            if not selected:
                messagebox.showinfo("Export Excel", "Select at least one category to export.")
                return
            export_dir = export_dir_var.get().strip()
            if not export_dir:
                messagebox.showinfo("Export Excel", "Choose an output folder.")
                return
            _export_progress(0, 100, "Starting")
            try:
                results = self.model.export_to_excel_templates(selected, export_dir, progress_cb=_export_progress)
                if raw_var.get():
                    _export_progress(prog_var.get(), prog_max.get(), "Raw Player Records")
                    raw_path, raw_count = self.model.export_player_raw_records(export_dir)
                    if raw_count > 0:
                        results["Raw Player Records"] = (raw_path, raw_count)
            except Exception as exc:
                exp_status.set(f"Export failed: {exc}")
                return
            if not results:
                exp_status.set("No Excel files were created.")
                return
            lines = []
            for cat in selected:
                if cat in results:
                    path, cnt = results[cat]
                    lines.append(f"{cat}: {cnt} rows -> {os.path.basename(path)}")
            if "Raw Player Records" in results:
                path, cnt = results["Raw Player Records"]
                lines.append(f"Raw Player Records: {cnt} -> {os.path.basename(path)}")
            exp_status.set("\n".join(lines))

        tk.Button(export_frame, text="Export Selected", command=_run_export, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(
            anchor="w", padx=6, pady=(2, 8)
        )
    def _apply_manual_import(
        self,
        mapping: dict[str, str],
        category_tables: dict[str, dict[str, object]],
        title: str,
        *,
        context: str | None = None,
    ) -> None:
        if not mapping:
            messagebox.showinfo(title, "No player matches were selected.")
            return
        import csv as _csv
        map_lookup = {str(k or "").strip().lower(): v for k, v in mapping.items() if v}
        if not map_lookup:
            messagebox.showinfo(title, "No valid player matches were provided.")
            return
        temp_files: dict[str, str] = {}
        try:
            for cat, table in category_tables.items():
                rows_obj = table.get("rows")
                if not isinstance(rows_obj, list) or len(rows_obj) < 2:
                    continue
                rows = [list(row) for row in rows_obj]
                header = rows[0]
                filtered = [header]
                for row in rows[1:]:
                    if not row:
                        continue
                    sheet_name = str(row[0]).strip()
                    mapped = map_lookup.get(sheet_name.lower())
                    if not mapped:
                        continue
                    new_row = list(row)
                    new_row[0] = mapped
                    filtered.append(new_row)
                if len(filtered) <= 1:
                    continue
                delimiter_obj = table.get("delimiter")
                delimiter = delimiter_obj if isinstance(delimiter_obj, str) else ","
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline='', encoding='utf-8')
                writer = _csv.writer(tmp, delimiter=delimiter)
                writer.writerows(filtered)
                tmp.close()
                temp_files[cat] = tmp.name
            if not temp_files:
                messagebox.showinfo(title, "No matching rows were found for the selected players.")
                return
            if context == "coy":
                results = self.model.import_coy_tables(temp_files)
            elif context == "excel":
                results = self.model.import_excel_tables(temp_files)
            else:
                results = self.model.import_all(temp_files)
            try:
                self.model.refresh_players()
            except Exception:
                pass
            msg_lines = [f"{title} completed."]
            if results:
                msg_lines.append("\nPlayers updated:")
                for cat, cnt in results.items():
                    msg_lines.append(f"  {cat}: {cnt}")
            messagebox.showinfo(title, "\n".join(msg_lines))
        finally:
            for path in temp_files.values():
                try:
                    os.remove(path)
                except Exception:
                    pass
    # ---------------------------------------------------------------------
    # Teams screen
    # ---------------------------------------------------------------------
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
        detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(20, 0))
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
            text="Full Editor",
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
            messagebox.showinfo("Full Editor", "Please select a team first.")
            return
        teams = self.model.get_teams()
        if not teams:
            messagebox.showinfo("Full Editor", "No teams available. Refresh and try again.")
            return
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                messagebox.showerror("Full Editor", "Selected team could not be resolved.")
                return
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        if not self.model.mem.hproc:
            messagebox.showinfo("Full Editor", "NBA 2K26 is not running. Launch the game to edit team data.")
            return
        try:
            editor = FullTeamEditor(self, team_idx, team_name, self.model)
            editor.grab_set()
        except Exception as exc:
            messagebox.showerror("Full Editor", f"Unable to open team editor: {exc}")

    def _open_full_staff_editor(self) -> None:
        """Open the staff editor scaffold (activates when staff pointers exist)."""
        try:
            editor = FullStaffEditor(self, self.model)
            editor.grab_set()
        except Exception as exc:
            messagebox.showerror("Staff Editor", f"Unable to open staff editor: {exc}")

    def _open_full_stadium_editor(self) -> None:
        """Open the stadium editor scaffold (activates when stadium pointers exist)."""
        try:
            editor = FullStadiumEditor(self, self.model)
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
                except OffsetSchemaError as exc:
                    messagebox.showerror("Offset schema error", str(exc))
                    self.status_var.set(f"{target_label} detected but offsets failed to load")
                    return
            self.model.mem.module_name = target_exec
            self.status_var.set(f"{target_label} is running (PID {pid})")
        else:
            self.status_var.set(f"{target_label} not detected - launch the game to enable editing")
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
        self.player_listbox.delete(0, tk.END)
        self.filtered_player_indices = []
        if not self.current_players:
            if not self.model.mem.hproc:
                self.player_listbox.insert(tk.END, "NBA 2K26 is not running.")
            else:
                self.player_listbox.insert(tk.END, "No players available.")
            self.player_count_var.set("Players: 0")
            return
        for idx, player in enumerate(self.current_players):
            name = (player.full_name or "").lower()
            if not search or search in name:
                self.filtered_player_indices.append(idx)
                self.player_listbox.insert(tk.END, player.full_name)
        if not self.filtered_player_indices:
            if self.current_players:
                self.player_listbox.insert(tk.END, "No players match the current filter.")
            else:
                self.player_listbox.insert(tk.END, "No players available.")
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
                    inches_val = raw_height_to_inches(int(value))
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

    def _build_excel_screen(self) -> None:
        """Build the inline Excel import/export screen."""
        self.excel_frame = tk.Frame(self, bg=PANEL_BG)
        main = tk.Frame(self.excel_frame, bg=PANEL_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Import pane
        import_frame = tk.LabelFrame(main, text="Import Excel", bg=PANEL_BG, fg=TEXT_PRIMARY)
        import_frame.configure(labelanchor="nw")
        import_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=4)
        import_path_var = tk.StringVar()
        tk.Label(import_frame, text="Workbook", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        tk.Entry(import_frame, textvariable=import_path_var, width=38, bg=INPUT_BG, fg=INPUT_TEXT_FG, relief=tk.FLAT).grid(
            row=0, column=1, sticky="we", padx=(0, 6), pady=(8, 2)
        )

        def _browse_import() -> None:
            path = filedialog.askopenfilename(
                parent=self,
                title="Select Excel or CSV File",
                filetypes=[("Excel/CSV files", "*.xlsx *.xls *.csv *.tsv"), ("All files", "*.*")],
            )
            if path:
                import_path_var.set(path)

        tk.Button(import_frame, text="Browse", command=_browse_import, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).grid(
            row=0, column=2, padx=(0, 6), pady=(8, 2)
        )
        match_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            import_frame,
            text="Match players by name",
            variable=match_var,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
        ).grid(row=1, column=1, sticky="w", padx=(0, 6), pady=(2, 6))
        import_status = tk.StringVar(value="")
        tk.Label(import_frame, textvariable=import_status, bg=PANEL_BG, fg=TEXT_SECONDARY, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 2)
        )
        import_frame.columnconfigure(1, weight=1)

        def _run_import() -> None:
            path = import_path_var.get().strip()
            if not path:
                messagebox.showinfo("Excel Import", "Choose a workbook to import.")
                return
            if not self.model.mem.hproc:
                messagebox.showinfo(
                    "Excel Import",
                    "NBA 2K26 does not appear to be running. Please launch the game and load a roster before importing.",
                )
                return
            loading = None
            try:
                loading = tk.Toplevel(self)
                loading.title("Importing...")
                loading.geometry("300x110")
                loading.resizable(False, False)
                tk.Label(loading, text="Importing workbook...\nPlease wait.", justify="center").pack(padx=20, pady=20)
                loading.update_idletasks()
            except Exception:
                loading = None
            try:
                results = excel_import.import_excel_workbook(self.model, path, match_by_name=bool(match_var.get()))
                try:
                    self.model.refresh_players()
                except Exception:
                    pass
            except Exception as exc:
                import_status.set(f"Import failed: {exc}")
                if loading:
                    loading.destroy()
                return
            finally:
                if loading:
                    try:
                        loading.destroy()
                    except Exception:
                        pass
            missing_bucket = getattr(self.model, "import_partial_matches", {}).get("excel_missing", {}) or {}
            not_found = len(missing_bucket)
            lines = [f"Imported {sum(results.values()) if results else 0} players."]
            if results:
                for cat, cnt in results.items():
                    lines.append(f"  {cat}: {cnt}")
            if not_found:
                lines.append(f"Players not found: {not_found}")
            import_status.set("\n".join(lines))

        tk.Button(import_frame, text="Import Workbook", command=_run_import, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).grid(
            row=3, column=1, sticky="w", padx=(0, 6), pady=(6, 10)
        )
        # Export pane
        export_frame = tk.LabelFrame(main, text="Export Excel", bg=PANEL_BG, fg=TEXT_PRIMARY)
        export_frame.configure(labelanchor="nw")
        export_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0), pady=4)
        categories = self.model.categories or {}
        super_map = getattr(offsets_mod, "CATEGORY_SUPER_TYPES", {}) or {}
        super_map_lower = {str(k).lower(): str(v) for k, v in super_map.items()}
        grouped: dict[str, list[str]] = {}
        allowed_supers = {"players", "teams", "staff", "stadiums"}
        for cat in categories:
            sup = super_map.get(cat) or super_map_lower.get(cat.lower())
            if not sup or str(sup).lower() not in allowed_supers:
                continue
            grouped.setdefault(str(sup), []).append(cat)
        export_vars: dict[str, tk.BooleanVar] = {}
        group_container = tk.Frame(export_frame, bg=PANEL_BG)
        group_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        for sup, cats in sorted(grouped.items(), key=lambda kv: kv[0]):
            lf = tk.LabelFrame(group_container, text=sup.title(), bg=PANEL_BG, fg=TEXT_PRIMARY)
            lf.configure(labelanchor="nw")
            lf.pack(fill=tk.X, padx=4, pady=4)
            cols = 2
            for idx, cat in enumerate(sorted(cats)):
                var = tk.BooleanVar(value=(sup.lower() == "players"))
                export_vars[cat] = var
                chk = tk.Checkbutton(
                    lf,
                    text=cat,
                    variable=var,
                    bg=PANEL_BG,
                    fg=TEXT_PRIMARY,
                    activebackground=PANEL_BG,
                    activeforeground=TEXT_PRIMARY,
                    selectcolor=ACCENT_BG,
                )
                chk.grid(row=idx // cols, column=idx % cols, sticky="w", padx=4, pady=2)
            lf.columnconfigure(0, weight=1)
            lf.columnconfigure(1, weight=1)
        tk.Label(export_frame, text="Output Folder", bg=PANEL_BG, fg=TEXT_PRIMARY).pack(anchor="w", padx=6, pady=(6, 0))
        export_dir_var = tk.StringVar()
        dir_row = tk.Frame(export_frame, bg=PANEL_BG)
        dir_row.pack(fill=tk.X, padx=6, pady=(0, 6))
        tk.Entry(dir_row, textvariable=export_dir_var, width=42, bg=INPUT_BG, fg=INPUT_TEXT_FG, relief=tk.FLAT).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )

        def _browse_export() -> None:
            path = filedialog.askdirectory(parent=self, title="Select export folder")
            if path:
                export_dir_var.set(path)

        tk.Button(dir_row, text="Browse", command=_browse_export, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(side=tk.LEFT)
        raw_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            export_frame,
            text="Also export raw player records",
            variable=raw_var,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
        ).pack(anchor="w", padx=6, pady=(0, 4))
        prog_frame = tk.Frame(export_frame, bg=PANEL_BG)
        prog_frame.pack(fill=tk.X, padx=6, pady=(4, 6))
        prog_var = tk.IntVar(value=0)
        prog_max = tk.IntVar(value=100)
        prog_bar = ttk.Progressbar(
            prog_frame, orient=tk.HORIZONTAL, mode="determinate", variable=prog_var, maximum=prog_max.get(), length=300
        )
        prog_bar.pack(fill=tk.X, expand=True)
        exp_status = tk.StringVar(value="")
        tk.Label(export_frame, textvariable=exp_status, bg=PANEL_BG, fg=TEXT_SECONDARY, justify="left").pack(
            anchor="w", padx=6, pady=(2, 8)
        )

        def _export_progress(done: int, total: int, label: str) -> None:
            try:
                if total > 0:
                    prog_max.set(total)
                    prog_bar.configure(maximum=total)
                prog_var.set(done)
                exp_status.set(f"{label}: {done}/{total if total else '?'}")
                prog_frame.update_idletasks()
            except Exception:
                pass

        def _run_export() -> None:
            selected = [cat for cat, var in export_vars.items() if var.get()]
            if not selected:
                messagebox.showinfo("Export Excel", "Select at least one category to export.")
                return
            export_dir = export_dir_var.get().strip()
            if not export_dir:
                messagebox.showinfo("Export Excel", "Choose an output folder.")
                return
            _export_progress(0, 100, "Starting")
            try:
                results = self.model.export_to_excel_templates(selected, export_dir, progress_cb=_export_progress)
                if raw_var.get():
                    _export_progress(prog_var.get(), prog_max.get(), "Raw Player Records")
                    raw_path, raw_count = self.model.export_player_raw_records(export_dir)
                    if raw_count > 0:
                        results["Raw Player Records"] = (raw_path, raw_count)
            except Exception as exc:
                exp_status.set(f"Export failed: {exc}")
                return
            if not results:
                exp_status.set("No Excel files were created.")
                return
            lines = []
            for cat in selected:
                if cat in results:
                    path, cnt = results[cat]
                    lines.append(f"{cat}: {cnt} rows -> {os.path.basename(path)}")
            if "Raw Player Records" in results:
                path, cnt = results["Raw Player Records"]
                lines.append(f"Raw Player Records: {cnt} -> {os.path.basename(path)}")
            exp_status.set("\n".join(lines))

        tk.Button(export_frame, text="Export Selected", command=_run_export, bg=BUTTON_BG, fg=BUTTON_TEXT, relief=tk.FLAT).pack(
            anchor="w", padx=6, pady=(2, 8)
        )

    def _open_export_dialog(self) -> None:
        """Prompt the user to export selected roster categories to CSV files."""
        try:
            if not self.model.mem.open_process():
                messagebox.showerror("Export Data", "Unable to connect to NBA 2K. Launch the game and try again.")
                return
        except Exception:
            messagebox.showerror("Export Data", "Failed to access the game process. Make sure NBA 2K is running.")
            return
        # Ensure we have an up-to-date player list before exporting
        try:
            self.model.refresh_players()
        except Exception:
            pass
        if not self.model.players:
            messagebox.showerror("Export Data", "No players were detected. Refresh the roster and try again.")
            return
        player_categories = [
            cat
            for cat, super_type in (getattr(offsets_mod, "CATEGORY_SUPER_TYPES", {}) or {}).items()
            if str(super_type).lower() == "players" and cat in self.model.categories
        ]
        available_categories = player_categories or [cat for cat in ("Attributes", "Tendencies", "Durability", "Potential") if cat in self.model.categories]
        if not available_categories:
            messagebox.showerror("Export Data", "No exportable categories were found in the current offsets configuration.")
            return
        dlg = CategorySelectionDialog(
            self,
            available_categories,
            title="Select categories to export",
            message="Export the following categories:",
        )
        self.wait_window(dlg)
        export_raw = bool(getattr(dlg, "export_full_records", False))
        selected_categories = dlg.selected or []
        if not selected_categories and not export_raw:
            return
        export_dir = filedialog.askdirectory(parent=self, title="Select export folder")
        if not export_dir:
            return
        # Progress dialog
        progress_win = tk.Toplevel(self)
        progress_win.title("Exporting...")
        progress_win.geometry("360x140")
        progress_win.resizable(False, False)
        tk.Label(progress_win, text="Exporting players...", justify="left").pack(padx=12, pady=(14, 6), anchor="w")
        progress_var = tk.IntVar(value=0)
        progress_max = tk.IntVar(value=100)
        progress_label_var = tk.StringVar(value="")
        bar = ttk.Progressbar(progress_win, orient=tk.HORIZONTAL, length=320, mode="determinate", variable=progress_var, maximum=progress_max.get())
        bar.pack(padx=12, pady=6)
        tk.Label(progress_win, textvariable=progress_label_var, justify="left").pack(padx=12, pady=(0, 10), anchor="w")

        def progress_cb(done: int, total: int, label: str) -> None:
            try:
                if total > 0:
                    progress_max.set(total)
                    bar.configure(maximum=total)
                progress_var.set(done)
                progress_label_var.set(f"{label}: {done}/{total if total else '?'}")
                progress_win.update_idletasks()
            except Exception:
                pass

        try:
            results = self.model.export_to_excel_templates(selected_categories, export_dir, progress_cb=progress_cb)
            if export_raw:
                progress_cb(progress_var.get(), progress_max.get(), "Raw Player Records")
                raw_path, raw_count = self.model.export_player_raw_records(export_dir)
                if raw_count > 0:
                    results["Raw Player Records"] = (raw_path, raw_count)
        except RuntimeError as exc:
            messagebox.showerror("Export Data", str(exc))
            try:
                progress_win.destroy()
            except Exception:
                pass
            return
        except Exception as exc:  # Safety net
            messagebox.showerror("Export Data", f"Failed to export roster data:\n{exc}")
            try:
                progress_win.destroy()
            except Exception:
                pass
            return
        try:
            progress_win.destroy()
        except Exception:
            pass
        if not results:
            messagebox.showinfo(
                "Export Data",
                "No Excel files were created. Ensure the selected categories have templates in the Offsets folder.",
            )
            return
        lines: list[str] = []
        for cat in selected_categories:
            info = results.get(cat)
            if info:
                path, count = info
                lines.append(f"{cat}: exported {count} players to {os.path.basename(path)}")
        for key in ("All Offsets", "Raw Player Records"):
            info = results.get(key)
            if not info:
                continue
            path, count = info
            basename = os.path.basename(path) or path
            lines.append(f"{key}: exported {count} entries to {basename}")
        summary = "\n".join(lines) if lines else "Export completed."
        messagebox.showinfo("Export Data", summary)

    def _open_import_dialog(self):
        import_flows.open_import_dialog(self)


__all__ = ["PlayerEditorApp"]
