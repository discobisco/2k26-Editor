"""Main application window (ported from the monolithic editor)."""
from __future__ import annotations

import copy
import json
import queue
import random
import re
import threading
from pathlib import Path
from typing import Any, TYPE_CHECKING, Callable, cast

import dearpygui.dearpygui as dpg
class BoundVar:
    """Lightweight value holder for UI state."""

    def __init__(self, value: object | None = "") -> None:
        self._value = value

    def get(self) -> object:
        return self._value

    def set(self, value: object) -> None:
        self._value = value


class BoundDoubleVar(BoundVar):
    def get(self) -> float:
        try:
            return float(super().get())
        except Exception:
            return 0.0

    def set(self, value: object) -> None:
        try:
            value = float(value)
        except Exception:
            pass
        super().set(value)


class BoundBoolVar(BoundVar):
    def get(self) -> bool:
        return bool(super().get())

    def set(self, value: object) -> None:
        super().set(bool(value))


from ..ai.settings import DEFAULT_AI_SETTINGS
from ..core.config import (
    AI_SETTINGS_PATH,
    HOOK_TARGET_LABELS,
    MODULE_NAME,
)
from ..core.conversions import (
    format_height_inches,
    raw_height_to_inches,
    HEIGHT_MIN_INCHES,
    HEIGHT_MAX_INCHES,
)
from ..core import offsets as offsets_mod
from ..core.offsets import (
    TEAM_FIELD_DEFS,
    OffsetSchemaError,
    initialize_offsets,
)
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from .batch_edit import BatchEditWindow
from .full_player_editor import FullPlayerEditor
from .full_editor_launch import launch_full_editor_process
from .randomizer import RandomizerWindow
from .team_shuffle import TeamShuffleWindow
from .theme import apply_base_theme
from .dialogs import ImportSummaryDialog, TeamSelectionDialog

if TYPE_CHECKING:
    from ..gm_rl.adapters.base import EditorAdapter
    from ..gm_rl.adapters.editor_live import EditorLiveAdapter
    from ..gm_rl.adapters.local_mock import LocalMockAdapter
    from ..gm_rl.runtime import AgentRuntime

    class RawFieldInspectorExtension:  # minimal stub for type checkers
        ...
from .home_screen import build_home_screen
from .ai_screen import build_ai_screen
from .agent_screen import build_agent_screen
from .players_screen import build_players_screen
from .teams_screen import build_teams_screen
from .league_screen import build_nba_history_screen, build_nba_records_screen
from .staff_screen import build_staff_screen
from .stadium_screen import build_stadium_screen
from .excel_screen import build_excel_screen
from .trade_players import build_trade_players_screen
from .controllers.navigation import show_screen as nav_show_screen
from .controllers.import_export import normalize_entity_key, entity_title
from .controllers.trade import format_trade_summary
from .controllers.entity_edit import coerce_int
from .state.trade_state import TradeState
class PlayerEditorApp:
    """
    Dear PyGui implementation of the editor shell.
    """

    def __init__(self, model: PlayerDataModel):
        self.model: PlayerDataModel = model
        # Navigation + layout
        self.screen_tags: dict[str, int | str] = {}
        self.content_root: int | str | None = None
        self.sidebar_tag: int | str | None = None
        # Status + offsets
        self.status_var = BoundVar("")
        self.status_text_tag: int | str | None = None
        self.offset_load_status = BoundVar("Using packaged offsets.")
        self.offset_status_text_tag: int | str | None = None
        self.hook_target_var = BoundVar(self.model.mem.module_name or MODULE_NAME)
        # Extension loader
        self.extension_vars: dict[str, BoundBoolVar] = {}
        self.extension_checkbuttons: dict[str, int | str] = {}
        self.loaded_extensions: set[str] = set()
        self.extension_status_var = BoundVar("")
        self.extension_status_text: int | str | None = None
        # Player state
        self.selected_team: str | None = None
        self.selected_player: Player | None = None
        self.selected_players: list[Player] = []
        self.current_players: list[Player] = []
        self.filtered_player_indices: list[int] = []
        self.player_list_items: list[str] = []
        self.player_search_var = BoundVar("")
        self.player_count_var = BoundVar("Players: 0")
        self.scan_status_var = BoundVar("")
        self.player_name_var = BoundVar("Select a player")
        self.player_ovr_var = BoundVar("OVR --")
        self.var_first = BoundVar("")
        self.var_last = BoundVar("")
        self.var_player_team = BoundVar("")
        self.player_detail_fields: dict[str, BoundVar] = {
            "Position": BoundVar("--"),
            "Number": BoundVar("--"),
            "Height": BoundVar("--"),
            "Weight": BoundVar("--"),
            "Face ID": BoundVar("--"),
            "Unique ID": BoundVar("--"),
        }
        self.player_detail_widgets: dict[str, int | str] = {}
        self.player_list_container: int | str | None = None
        self.player_listbox_tag: int | str | None = None
        self.player_team_listbox: int | str | None = None
        self.team_combo_tag: int | str | None = None
        self.dataset_combo_tag: int | str | None = None
        self.btn_save: int | str | None = None
        self.btn_edit: int | str | None = None
        self.btn_copy: int | str | None = None
        self.btn_player_export: int | str | None = None
        self.btn_player_import: int | str | None = None
        self.copy_dialog_tag: int | str | None = None
        # Team state
        self.team_var = BoundVar("")
        self.team_edit_var = BoundVar("")
        self.team_name_var = BoundVar("")
        self.team_field_vars: dict[str, BoundVar] = {label: BoundVar("") for label in TEAM_FIELD_DEFS.keys()}
        self.team_field_input_tags: dict[str, int | str] = {}
        self.team_count_var = BoundVar("Teams: 0")
        self.team_search_var = BoundVar("")
        self.team_scan_status_var = BoundVar("")
        self.team_list_container: int | str | None = None
        self.team_list_items: list[str] = []
        self.team_listbox_tag: int | str | None = None
        self.btn_team_save: int | str | None = None
        self.btn_team_full: int | str | None = None
        self.team_players_lookup: list[Player] = []
        self.team_players_list_items: list[str] = []
        self.team_players_listbox_tag: int | str | None = None
        self.btn_team_player: int | str | None = None
        self.all_team_names: list[str] = []
        self.filtered_team_names: list[str] = []
        # Staff state
        self.staff_entries: list[tuple[int, str]] = []
        self._filtered_staff_entries: list[tuple[int, str]] = []
        self.staff_search_var = BoundVar("")
        self.staff_status_var = BoundVar("")
        self.staff_count_var = BoundVar("Staff: 0")
        self.staff_list_container: int | str | None = None
        self.staff_list_items: list[str] = []
        self.staff_listbox_tag: int | str | None = None
        self.btn_staff_full: int | str | None = None
        # Stadium state
        self.stadium_entries: list[tuple[int, str]] = []
        self._filtered_stadium_entries: list[tuple[int, str]] = []
        self.stadium_search_var = BoundVar("")
        self.stadium_status_var = BoundVar("")
        self.stadium_count_var = BoundVar("Stadiums: 0")
        self.stadium_list_container: int | str | None = None
        self.stadium_list_items: list[str] = []
        self.stadium_listbox_tag: int | str | None = None
        self.btn_stadium_full: int | str | None = None
        # League page state
        self.league_page_super_types: dict[str, str] = {
            "nba_history": "NBA History",
            "nba_records": "NBA Records",
        }
        self.league_states: dict[str, dict[str, object]] = {}
        for page_key in self.league_page_super_types.keys():
            self.league_states[page_key] = {
                "categories": [],
                "category_map": {},
                "selected_category": None,
                "records": [],
                "status_var": BoundVar(""),
                "count_var": BoundVar("Records: 0"),
                "category_combo_tag": None,
                "table_container": None,
                "table_tag": None,
                "status_text_tag": None,
                "count_text_tag": None,
            }
        # Trade state
        self.trade_team_options: list[str] = []
        self.trade_team_lookup: dict[str, int] = {}
        self.trade_participants: list[str] = []
        self.trade_active_team_var = BoundVar("")
        self.trade_roster_active: list[Player] = []
        self.trade_state = TradeState(slot_count=36)
        # Compatibility alias retained for existing UI references.
        self.trade_slots = self.trade_state.slots
        self.trade_selected_slot = 0
        self.trade_selected_player_obj: Player | None = None
        self.trade_selected_transaction: int | None = None
        self.trade_contract_meta: dict[str, dict[str, object]] | None = None
        self.trade_status_var = BoundVar("")
        self.trade_active_team_combo_tag: int | str | None = None
        self.trade_add_team_combo_tag: int | str | None = None
        self.trade_participants_list_tag: int | str | None = None
        self.trade_roster_list_tag: int | str | None = None
        self.trade_outgoing_container: int | str | None = None
        self.trade_incoming_container: int | str | None = None
        self.trade_slot_combo_tag: int | str | None = None
        self.trade_status_text_tag: int | str | None = None
        # Excel state
        self.excel_status_var = BoundVar("")
        self.excel_progress_var = BoundDoubleVar(0)
        self.excel_progress_bar_tag: int | str | None = None
        self.excel_status_text_tag: int | str | None = None
        self._excel_export_queue: queue.Queue | None = None
        self._excel_export_thread: threading.Thread | None = None
        self._excel_export_polling = False
        self._excel_export_entity_label = ""
        # Flags
        self.scanning = False
        self._pending_team_select: str | None = None
        # AI state
        self.ai_settings: dict[str, object] = {}
        self.ai_mode_var = BoundVar("none")
        self.ai_api_base_var = BoundVar("")
        self.ai_api_key_var = BoundVar("")
        self.ai_model_var = BoundVar("")
        self.ai_api_timeout_var = BoundVar("")
        self.ai_local_backend_var = BoundVar("cli")
        self.ai_local_command_var = BoundVar("")
        self.ai_local_args_var = BoundVar("")
        self.ai_local_workdir_var = BoundVar("")
        self.ai_python_backend_var = BoundVar("")
        self.ai_model_path_var = BoundVar("")
        self.ai_model_max_tokens_var = BoundVar("256")
        self.ai_model_temperature_var = BoundVar("0.4")
        self.ai_persona_choice_var = BoundVar("none")
        self.ai_base_persona_var = BoundVar("")
        self.ai_active_team_count_var = BoundVar("12")
        self._ai_remote_inputs: list[int | str] = []
        self._ai_local_inputs: list[int | str] = []
        self._ai_python_inputs: list[int | str] = []
        self._ai_persona_widgets: list[int | str] = []
        self.ai_status_label: int | str | None = None
        self.ai_assistant = None
        self.control_bridge = None
        # Agent / PPO state
        self.agent_adapter_var = BoundVar("mock")
        self.agent_apply_writes_var = BoundBoolVar(False)
        self.agent_status_var = BoundVar("Agent idle.")
        self.agent_checkpoint_var = BoundVar("")
        self.agent_config_var = BoundVar("")
        self.agent_team_id_var = BoundVar("1")
        self.agent_episodes_var = BoundVar("3")
        self.agent_log_lines: list[str] = []
        self.agent_runtime: AgentRuntime | None = None
        self.agent_log_tag: int | str | None = None
        self.agent_status_text_tag: int | str | None = None
        self.agent_checkpoint_input: int | str | None = None
        self.agent_config_input: int | str | None = None
        self.agent_team_input: int | str | None = None
        self.agent_episode_input: int | str | None = None
        self.agent_apply_writes_checkbox: int | str | None = None
        self.agent_adapter_combo: int | str | None = None
        self.agent_polling = False
        # Misc
        self._lazy_screen_builders: dict[str, Callable[[Any], None]] = {
            "players": build_players_screen,
            "teams": build_teams_screen,
            "nba_history": build_nba_history_screen,
            "nba_records": build_nba_records_screen,
            "staff": build_staff_screen,
            "stadium": build_stadium_screen,
            "excel": build_excel_screen,
            "trade": build_trade_players_screen,
            "ai": build_ai_screen,
            "agent": build_agent_screen,
        }
        # Preload AI settings only. Control bridge starts lazily on first AI usage.
        self._load_ai_settings_into_vars()

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------
    def _queue_on_main(self, func: Callable[[], None]) -> None:
        """Queue a callback to run on the next Dear PyGui frame; fallback to direct call."""
        try:
            dpg.set_frame_callback(max(0, dpg.get_frame_count() + 1), lambda: func())
        except Exception:
            try:
                func()
            except Exception:
                pass

    def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Schedule a callback on the UI thread after a delay."""
        delay_sec = max(0, delay_ms) / 1000.0
        if delay_sec <= 0:
            self._queue_on_main(callback)
            return
        t = threading.Timer(delay_sec, lambda: self._queue_on_main(callback))
        t.daemon = True
        t.start()

    def run_on_ui_thread(self, func: Callable, delay_ms: int = 0) -> None:
        self.after(delay_ms, lambda: func())

    def enqueue_ui_update(self, func: Callable) -> None:
        self.run_on_ui_thread(func)

    def destroy(self) -> None:
        try:
            dpg.destroy_context()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build_ui(self) -> None:
        apply_base_theme()
        with dpg.window(
            tag="main_window",
            label="2K26 Offline Player Data Editor",
            width=1280,
            height=760,
            no_title_bar=False,
        ):
            with dpg.group(horizontal=True):
                self._build_sidebar()
                self.content_root = dpg.add_child_window(tag="content_root", autosize_x=True, autosize_y=True, border=False)
        dpg.set_primary_window("main_window", True)
        # Build home screen eagerly; all others are lazy-built on first navigation.
        build_home_screen(self)
        # Start on Home
        self.show_home()
        self._update_status()

    def _build_sidebar(self) -> None:
        with dpg.child_window(width=200, autosize_y=True, tag="sidebar", border=False) as sidebar:
            self.sidebar_tag = sidebar
            def nav(label: str, cb: Callable[[], None]) -> int | str:
                return dpg.add_button(label=label, width=-1, callback=lambda *_: cb())
            self.nav_home = nav("Home", self.show_home)
            self.nav_players = nav("Players", self.show_players)
            self.nav_ai = nav("AI Assistant", self.show_ai)
            self.nav_agent = nav("GM Agent", self.show_agent)
            self.nav_teams = nav("Teams", self.show_teams)
            self.nav_nba_history = nav("NBA History", self.show_nba_history)
            self.nav_nba_records = nav("NBA Records", self.show_nba_records)
            # Compatibility alias for legacy references.
            self.nav_league = self.nav_nba_history
            self.nav_staff = nav("Staff", self.show_staff)
            self.nav_stadium = nav("Stadium", self.show_stadium)
            self.nav_excel = nav("Excel", self.show_excel)
            self.nav_trade = nav("Trade Players", self.show_trade_players)
            dpg.add_separator()
            nav("Randomize", self._open_randomizer)
            nav("Shuffle Teams", self._open_team_shuffle)
            nav("Batch Edit", self._open_batch_edit)

    def _show_screen(self, key: str) -> None:
        nav_show_screen(self, key)

    def _ensure_screen_built(self, key: str) -> None:
        existing = self.screen_tags.get(key)
        if existing is not None:
            # In tests and pre-build flows, tags may be placeholders before Dear PyGui context exists.
            if self.content_root is None:
                return
            try:
                if dpg.does_item_exist(existing):
                    return
            except Exception:
                return
        builder = self._lazy_screen_builders.get(key)
        if builder is not None:
            builder(self)

    def show_home(self) -> None:
        self._show_screen("home")

    def show_players(self) -> None:
        self._ensure_screen_built("players")
        self._show_screen("players")
        self._ensure_roster_loaded(apply_pending_team_select=False)

    def show_teams(self) -> None:
        self._ensure_screen_built("teams")
        self._show_screen("teams")
        self._ensure_roster_loaded(apply_pending_team_select=True)

    def show_nba_history(self) -> None:
        self._ensure_screen_built("nba_history")
        self._show_screen("nba_history")
        self._refresh_league_records("nba_history")

    def show_nba_records(self) -> None:
        self._ensure_screen_built("nba_records")
        self._show_screen("nba_records")
        self._refresh_league_records("nba_records")

    def show_league(self) -> None:
        # Backward-compatible alias.
        self.show_nba_history()

    def _ensure_control_bridge_started(self) -> None:
        if self.control_bridge is None:
            self._start_control_bridge()

    def show_ai(self) -> None:
        self._ensure_screen_built("ai")
        self._ensure_control_bridge_started()
        self._show_screen("ai")

    def show_agent(self) -> None:
        self._ensure_screen_built("agent")
        self._show_screen("agent")
        self._start_agent_polling()

    def show_trade_players(self) -> None:
        self._ensure_screen_built("trade")
        self._show_screen("trade")
        self._refresh_trade_data()

    def show_staff(self) -> None:
        self._ensure_screen_built("staff")
        self._show_screen("staff")
        self._refresh_staff_list()

    def show_stadium(self) -> None:
        self._ensure_screen_built("stadium")
        self._show_screen("stadium")
        self._refresh_stadium_list()

    def show_excel(self) -> None:
        self._ensure_screen_built("excel")
        self._show_screen("excel")

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        """Refresh status text based on current memory attachment."""
        if self.model.mem.hproc:
            status = f"Attached to {self.model.mem.module_name or MODULE_NAME}"
        else:
            status = "NBA 2K26 is not running."
        self.status_var.set(status)
        if self.status_text_tag and dpg.does_item_exist(self.status_text_tag):
            dpg.set_value(self.status_text_tag, status)

    def _set_offset_status(self, message: str) -> None:
        self.offset_load_status.set(message)
        if self.offset_status_text_tag and dpg.does_item_exist(self.offset_status_text_tag):
            dpg.set_value(self.offset_status_text_tag, message)

    # ------------------------------------------------------------------
    # Clipboard helper
    # ------------------------------------------------------------------
    @staticmethod
    def copy_to_clipboard(text: str) -> None:
        dpg.set_clipboard_text(text or "")

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _show_modal(self, title: str, message: str, level: str = "info") -> None:
        """Lightweight modal dialog built with Dear PyGui."""
        colors = {
            "info": (224, 225, 221, 255),
            "warn": (255, 202, 126, 255),
            "error": (255, 138, 128, 255),
        }
        text_color = colors.get(level, colors["info"])
        dialog_tag = dpg.generate_uuid()

        def _close_dialog() -> None:
            if dpg.does_item_exist(dialog_tag):
                dpg.delete_item(dialog_tag)

        with dpg.window(
            label=title,
            tag=dialog_tag,
            modal=True,
            no_collapse=True,
            width=420,
            height=180,
        ):
            dpg.add_text(str(message), wrap=380, color=text_color)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=260)
                dpg.add_button(label="OK", width=80, callback=lambda *_: _close_dialog())
        try:
            dpg.focus_item(dialog_tag)
        except Exception:
            pass

    def show_info(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="info")

    def show_warning(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="warn")

    def show_error(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="error")

    def show_message(self, title: str, message: str) -> None:
        self.show_info(title, message)

    def _open_file_dialog(
        self,
        title: str,
        *,
        default_path: str | None = None,
        default_filename: str | None = None,
        file_types: list[tuple[str, str]] | None = None,
        callback: Callable[[str], None] | None = None,
        save: bool = False,
    ) -> None:
        """Open a Dear PyGui file dialog and invoke callback with the chosen path."""
        dialog_tag = dpg.generate_uuid()

        def _close() -> None:
            if dpg.does_item_exist(dialog_tag):
                dpg.delete_item(dialog_tag)

        def _on_select(_sender, app_data) -> None:
            path = ""
            if isinstance(app_data, dict):
                path = str(app_data.get("file_path_name") or "")
            _close()
            if path and callback:
                callback(path)

        dialog_kwargs: dict[str, object] = {
            "label": title,
            "tag": dialog_tag,
            "width": 700,
            "height": 400,
            "show": True,
            "modal": True,
            "callback": _on_select,
            "cancel_callback": lambda *_: _close(),
            "default_path": default_path or "",
            "default_filename": default_filename or "",
        }
        if save:
            dialog_kwargs["directory_selector"] = False
        dpg.add_file_dialog(**dialog_kwargs)
        if file_types:
            for label, pattern in file_types:
                ext = str(pattern or "").strip()
                if not ext:
                    continue
                ext_kwargs: dict[str, object] = {"parent": dialog_tag}
                if label:
                    ext_kwargs["custom_text"] = str(label)
                try:
                    dpg.add_file_extension(ext, **ext_kwargs)
                except Exception:
                    # Keep dialog usable even if custom label rendering isn't supported.
                    try:
                        dpg.add_file_extension(ext, parent=dialog_tag)
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # AI settings + control bridge
    # ------------------------------------------------------------------
    def _start_control_bridge(self) -> None:
        """Start the HTTP control bridge so external AIs can drive the app."""
        if self.control_bridge is not None:
            return
        try:
            from ..ai.assistant import ensure_control_bridge

            self.control_bridge = ensure_control_bridge(cast(Any, self))
        except Exception:
            self.control_bridge = None

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
        try:
            from ..ai.personas import ensure_default_profiles
            teams = list(self.model.get_teams()) if hasattr(self.model, "get_teams") else []
            profiles_raw = base.get("profiles")
            profiles = profiles_raw if isinstance(profiles_raw, dict) else {}
            active_raw = profiles.get("active_count", 12)
            active_count = self._coerce_int(active_raw, default=12)
            ensure_default_profiles(base, teams, active_count)
        except Exception:
            pass
        return base

    def _merge_dict(self, target: dict[str, object], source: dict[str, object]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge_dict(cast(dict[str, object], target[key]), value)  # type: ignore[arg-type]
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
        mode = str(self.ai_mode_var.get()).strip() or "none"
        team_profiles = self._get_team_profiles()
        settings: dict[str, object] = {
            "mode": mode,
            "remote": {
                "base_url": str(self.ai_api_base_var.get()).strip(),
                "api_key": str(self.ai_api_key_var.get()).strip(),
                "model": str(self.ai_model_var.get()).strip(),
                "timeout": self._coerce_int(self.ai_api_timeout_var.get(), default=30),
            },
            "local": {
                "backend": str(self.ai_local_backend_var.get()).strip() or "cli",
                "command": str(self.ai_local_command_var.get()).strip(),
                "arguments": str(self.ai_local_args_var.get()).strip(),
                "working_dir": str(self.ai_local_workdir_var.get()).strip(),
                "python_backend": str(self.ai_python_backend_var.get()).strip(),
                "model_path": str(self.ai_model_path_var.get()).strip(),
                "max_tokens": self._coerce_int(self.ai_model_max_tokens_var.get(), default=256),
                "temperature": float(self.ai_model_temperature_var.get() or 0.4),
            },
            "profiles": {
                "base": str(self.ai_base_persona_var.get()).strip(),
                "active_count": self._coerce_int(self.ai_active_team_count_var.get(), default=12),
                "team_profiles": team_profiles,
            },
        }
        return settings

    def get_ai_settings(self) -> dict[str, object]:
        settings = self._collect_ai_settings()
        try:
            self._save_ai_settings(settings)
        except Exception:
            pass
        return settings

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        try:
            return int(value) if value not in (None, "") else default
        except Exception:
            return default

    def _save_ai_settings(self, settings: dict[str, object]) -> None:
        try:
            AI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AI_SETTINGS_PATH.open("w", encoding="utf-8") as fh:
                json.dump(settings, fh, indent=2)
        except Exception:
            pass

    def get_persona_choice_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [("None", "none"), ("Base Persona", "base")]
        try:
            for idx, team in enumerate(self.model.get_teams()):
                items.append((f"Team: {team}", f"team:{idx}"))
        except Exception:
            pass
        return items

    # ------------------------------------------------------------------
    # Player scanning + list management
    # ------------------------------------------------------------------
    def _render_player_list(self, items: list[str] | None = None, message: str | None = None) -> None:
        if self.player_list_container is None or not dpg.does_item_exist(self.player_list_container):
            return
        if items is None:
            items = []
        if message:
            items = [message]
        if not self.player_listbox_tag or not dpg.does_item_exist(self.player_listbox_tag):
            with dpg.group(parent=self.player_list_container):
                self.player_listbox_tag = dpg.add_listbox(
                    items=items,
                    num_items=28,
                    callback=self._on_player_selected,
                )
        else:
            dpg.configure_item(self.player_listbox_tag, items=items)
            if items:
                dpg.set_value(self.player_listbox_tag, items[0])

    def _start_scan(self) -> None:
        PlayerEditorApp._start_roster_scan(self, apply_pending_team_select=False)

    def _scan_thread(self) -> None:
        PlayerEditorApp._run_roster_scan(self, apply_pending_team_select=False)

    def _start_roster_scan(self, *, apply_pending_team_select: bool) -> None:
        if self.scanning:
            return
        self.scanning = True
        status_msg = "Scanning... please wait"
        self.scan_status_var.set(status_msg)
        self.team_scan_status_var.set(status_msg)
        self._render_player_list(message="Scanning players...")
        PlayerEditorApp._run_roster_scan(self, apply_pending_team_select=apply_pending_team_select)

    def _run_roster_scan(self, *, apply_pending_team_select: bool) -> None:
        teams: list[str] = []
        error_msg = ""
        try:
            self.model.refresh_players()
            teams = self.model.get_teams()
        except Exception as exc:
            error_msg = str(exc) or exc.__class__.__name__

        def update_ui() -> None:
            self.scanning = False
            self._update_team_dropdown(teams)
            self._refresh_player_list()
            status_msg = ""
            if error_msg:
                status_msg = f"Scan failed: {error_msg}"
            elif not self.model.mem.hproc:
                status_msg = "NBA 2K26 is not running."
            elif not teams:
                status_msg = "No teams available."
            self.scan_status_var.set(status_msg)
            self.team_scan_status_var.set(status_msg)
            if apply_pending_team_select and not error_msg and self._pending_team_select and self._pending_team_select in teams:
                self.team_edit_var.set(self._pending_team_select)
                self._on_team_edit_selected()
                self._pending_team_select = None

        update_ui()

    def _refresh_player_list(self) -> None:
        team = (self.team_var.get() or "").strip()
        if not team:
            team = "All Players"
        try:
            self.team_var.set(team)
        except Exception:
            pass
        if team.lower() == "all players" and not self.model.players:
            status_msg = "Players not loaded. Click Scan to load players."
            if self.scanning:
                status_msg = "Scanning... please wait"
            elif not self.model.mem.hproc:
                status_msg = "NBA 2K26 is not running."
            self.scan_status_var.set(status_msg)
            self.team_scan_status_var.set(status_msg)
        team_lower = team.lower()
        if team_lower == "draft prospects":
            self.current_players = self.model.get_draft_prospects()
        elif team_lower == "free agents":
            self.current_players = self.model.get_free_agents_by_flags()
        else:
            self.current_players = self.model.get_players_by_team(team) if team else []
        self.selected_player = None
        self.selected_players = []
        self._filter_player_list()
        if self.filtered_player_indices:
            self.set_selected_player_indices([0])
        else:
            self._update_detail_fields()

    def _filter_player_list(self) -> None:
        search = (self.player_search_var.get() or "").strip().lower()
        if search == "search players.":
            search = ""
        self.filtered_player_indices = []
        self.player_list_items = []
        if not self.current_players:
            self._render_player_list(message="No players available." if self.model.mem.hproc else "NBA 2K26 is not running.")
            self.player_count_var.set("Players: 0")
            if hasattr(self, "player_count_text_tag") and self.player_count_text_tag:
                dpg.set_value(self.player_count_text_tag, self.player_count_var.get())
            return
        visible_names: list[str] = []
        if not search:
            self.filtered_player_indices = list(range(len(self.current_players)))
            visible_names = [p.full_name for p in self.current_players]
        else:
            for idx, player in enumerate(self.current_players):
                if search in player.full_name.lower():
                    self.filtered_player_indices.append(idx)
                    visible_names.append(player.full_name)
        if not visible_names:
            self._render_player_list(message="No players match the current filter.")
        else:
            self.player_list_items = visible_names
            self._render_player_list(items=visible_names)
        self.player_count_var.set(f"Players: {len(self.filtered_player_indices)}")
        if getattr(self, "player_count_text_tag", None):
            dpg.set_value(self.player_count_text_tag, self.player_count_var.get())

    def _on_team_selected(self, _sender=None, value: str | None = None) -> None:
        selected_team = value or (self.team_var.get() or "").strip()
        self.team_var.set(selected_team)
        self._refresh_player_list()

    def _on_player_selected(self, _sender, app_data) -> None:
        name = str(app_data) if app_data is not None else ""
        idx = self.player_list_items.index(name) if name in self.player_list_items else -1
        selected_players: list[Player] = []
        if 0 <= idx < len(self.filtered_player_indices):
            p_idx = self.filtered_player_indices[idx]
            if 0 <= p_idx < len(self.current_players):
                selected_players.append(self.current_players[p_idx])
        self.selected_players = selected_players
        self.selected_player = selected_players[0] if selected_players else None
        self._update_detail_fields()

    def _update_detail_fields(self) -> None:
        p = self.selected_player
        selection_count = len(self.selected_players)
        if not p:
            self.player_name_var.set("Select a player")
            self.player_ovr_var.set("OVR --")
            self.var_first.set("")
            self.var_last.set("")
            self.var_player_team.set("")
            for var in self.player_detail_fields.values():
                var.set("--")
            if self.btn_save:
                dpg.configure_item(self.btn_save, enabled=False)
            if self.btn_edit:
                dpg.configure_item(self.btn_edit, enabled=False)
            if self.btn_copy:
                dpg.configure_item(self.btn_copy, enabled=False)
            if self.btn_player_export:
                dpg.configure_item(self.btn_player_export, enabled=False)
            if self.btn_player_import:
                dpg.configure_item(self.btn_player_import, enabled=False)
        else:
            display_name = p.full_name or f"Player {p.index}"
            if selection_count > 1:
                display_name = f"{display_name} (+{selection_count - 1} more)"
            self.player_name_var.set(display_name)
            self.var_first.set(p.first_name)
            self.var_last.set(p.last_name)
            team_display = p.team
            try:
                if self.model.is_player_free_agent_group(p):
                    team_display = ""
            except Exception:
                team_display = p.team
            self.var_player_team.set(team_display)
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
                widget = self.player_detail_widgets.get(label)
                if widget and dpg.does_item_exist(widget):
                    dpg.set_value(widget, var.get())
        # Update UI widgets
        if getattr(self, "player_name_text", None):
            dpg.set_value(self.player_name_text, self.player_name_var.get())
        if getattr(self, "player_ovr_text", None):
            dpg.set_value(self.player_ovr_text, self.player_ovr_var.get())
        enable_save = self.model.mem.hproc is not None and not getattr(self.model, "external_loaded", False)
        if self.btn_save:
            dpg.configure_item(self.btn_save, enabled=enable_save)
        if self.btn_edit:
            dpg.configure_item(self.btn_edit, enabled=bool(p))
        enable_copy = enable_save and p is not None
        if self.btn_copy:
            dpg.configure_item(self.btn_copy, enabled=enable_copy)
        enable_io = self.model.mem.hproc is not None and p is not None
        if self.btn_player_export:
            dpg.configure_item(self.btn_player_export, enabled=enable_io)
        if self.btn_player_import:
            dpg.configure_item(self.btn_player_import, enabled=enable_io)
        inspector = getattr(self, "player_panel_inspector", None)
        if inspector:
            try:
                inspector.refresh_for_player()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Player actions
    # ------------------------------------------------------------------
    def _save_player(self) -> None:
        p = self.selected_player
        if not p:
            return
        p.first_name = str(self.var_first.get()).strip()
        p.last_name = str(self.var_last.get()).strip()
        try:
            self.model.update_player(p)
            self.show_info("Success", "Player updated successfully")
        except Exception as exc:
            self.show_error("Error", f"Failed to save changes:\n{exc}")
        self._refresh_player_list()

    def _open_full_editor(self) -> None:
        selected = self.selected_players or ([self.selected_player] if self.selected_player else [])
        if not selected:
            return
        if not self.model.mem.open_process():
            self.show_error("Player Editor", "NBA 2K26 is not running. Launch the game and try again.")
            return
        try:
            self.model.refresh_players()
        except Exception:
            pass
        player_indices: list[int] = []
        seen: set[int] = set()
        for player in selected:
            try:
                idx = int(getattr(player, "index", -1))
            except Exception:
                continue
            if idx < 0 or idx in seen:
                continue
            seen.add(idx)
            player_indices.append(idx)
        if not player_indices:
            self.show_error("Player Editor", "Selected players could not be resolved.")
            return
        try:
            launch_full_editor_process(editor="player", indices=player_indices)
        except Exception as exc:
            self.show_error("Player Editor", f"Unable to open player editor window: {exc}")

    def _open_copy_dialog(self) -> None:
        src = self.selected_player
        if not src:
            self.show_info("Copy Player Data", "Select a player to copy from.")
            return
        dest_players: list[Player] = []
        if self.model.players:
            dest_players = [p for p in self.model.players if p.index != src.index]
        elif self.model.team_list:
            for idx, _name in self.model.team_list:
                try:
                    for p in self.model.scan_team_players(idx):
                        if p.index != src.index:
                            dest_players.append(p)
                except Exception:
                    continue
        seen: set[int] = set()
        uniq_dest: list[Player] = []
        for p in dest_players:
            if p.index in seen:
                continue
            seen.add(p.index)
            uniq_dest.append(p)
        dest_players = uniq_dest
        if not dest_players:
            self.show_info("Copy Player Data", "No other players are available to copy to.")
            return
        if self.copy_dialog_tag and dpg.does_item_exist(self.copy_dialog_tag):
            dpg.delete_item(self.copy_dialog_tag)
        self.copy_dialog_tag = dpg.generate_uuid()
        dest_names = [p.full_name for p in dest_players]
        dest_map = {p.full_name: p for p in dest_players}
        with dpg.window(
            label="Copy Player Data",
            tag=self.copy_dialog_tag,
            modal=True,
            no_collapse=True,
            width=440,
            height=340,
        ):
            dpg.add_text(f"Copy from: {src.full_name}")
            dpg.add_spacer(height=6)
            combo_tag = dpg.add_combo(items=dest_names, default_value=dest_names[0], width=260, label="Copy to")
            dpg.add_spacer(height=8)
            chk_full = dpg.add_checkbox(label="Full Player", default_value=False)
            chk_attr = dpg.add_checkbox(label="Attributes", default_value=False)
            chk_tend = dpg.add_checkbox(label="Tendencies", default_value=False)
            chk_badges = dpg.add_checkbox(label="Badges", default_value=False)
            dpg.add_spacer(height=10)

            def _close_dialog() -> None:
                if self.copy_dialog_tag and dpg.does_item_exist(self.copy_dialog_tag):
                    dpg.delete_item(self.copy_dialog_tag)
                self.copy_dialog_tag = None

            def _do_copy() -> None:
                dest_name = str(dpg.get_value(combo_tag) or "").strip()
                dest_player = dest_map.get(dest_name)
                if not dest_player:
                    self.show_error("Copy Player Data", "No destination player selected.")
                    return
                categories: list[str] = []
                if dpg.get_value(chk_full):
                    categories = ["full"]
                else:
                    if dpg.get_value(chk_attr):
                        categories.append("attributes")
                    if dpg.get_value(chk_tend):
                        categories.append("tendencies")
                    if dpg.get_value(chk_badges):
                        categories.append("badges")
                if not categories:
                    self.show_warning("Copy Player Data", "Please select at least one data category to copy.")
                    return
                success = self.model.copy_player_data(
                    src.index,
                    dest_player.index,
                    categories,
                    src_record_ptr=getattr(src, "record_ptr", None),
                    dst_record_ptr=getattr(dest_player, "record_ptr", None),
                )
                if success:
                    self.show_info("Copy Player Data", "Data copied successfully.")
                    self._start_scan()
                else:
                    self.show_error("Copy Player Data", "Failed to copy data. Make sure the game is running and try again.")
                _close_dialog()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Copy", width=80, callback=lambda *_: _do_copy())
                dpg.add_button(label="Cancel", width=80, callback=lambda *_: _close_dialog())

    def _export_selected_player(self) -> None:
        try:
            from ..importing.excel_import import export_excel_workbook, template_path_for
        except Exception as exc:
            self.show_error("Excel Export", f"Export helpers not available: {exc}")
            return
        if self._excel_export_thread is not None and self._excel_export_thread.is_alive():
            self.show_info("Excel Export", "An export is already running.")
            return
        player = self.selected_player
        if not player:
            self.show_info("Excel Export", "Select a player to export.")
            return
        if not self.model.mem.open_process():
            self.show_error("Excel Export", "NBA 2K26 is not running.")
            return
        template = template_path_for("players")
        safe_name = re.sub(r'[<>:"/\\\\|?*]', "_", player.full_name or f"Player_{player.index}")
        safe_name = re.sub(r"\\s+", "_", safe_name).strip("_")
        if not safe_name:
            safe_name = f"Player_{player.index}"
        default_name = f"{safe_name}_export.xlsx"
        def _after_choose(path: str) -> None:
            if not path:
                return
            self._reset_excel_progress()
            status = f"Exporting {player.full_name}..."
            self.excel_status_var.set(status)
            if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
                dpg.set_value(self.excel_status_text_tag, status)
            self._excel_export_entity_label = "Player"
            self._excel_export_queue = queue.Queue()
            progress_cb = self._queue_excel_export_progress

            def _run_export() -> None:
                try:
                    result = export_excel_workbook(
                        self.model,
                        path,
                        "players",
                        template_path=template,
                        progress_cb=progress_cb,
                        players=[player],
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

        self._open_file_dialog(
            "Save player workbook",
            default_path=str(template.parent),
            default_filename=default_name,
            file_types=[("Excel files", ".xlsx")],
            callback=_after_choose,
            save=True,
        )

    def _import_selected_player(self) -> None:
        try:
            from ..importing.excel_import import import_excel_workbook, template_path_for
        except Exception as exc:
            self.show_error("Excel Import", f"Import helpers not available: {exc}")
            return
        player = self.selected_player
        if not player:
            self.show_info("Excel Import", "Select a player to import.")
            return
        if not self.model.mem.open_process():
            self.show_error("Excel Import", "NBA 2K26 is not running.")
            return
        template = template_path_for("players")
        def _after_choose(path: str) -> None:
            if not path:
                return
            try:
                if not self.model.players:
                    self.model.refresh_players()
            except Exception:
                pass
            self._reset_excel_progress()
            status = f"Importing {player.full_name}..."
            self.excel_status_var.set(status)
            if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
                dpg.set_value(self.excel_status_text_tag, status)
            progress_cb = self._excel_progress_callback("Importing", "Player")
            try:
                result = import_excel_workbook(
                    self.model,
                    path,
                    "players",
                    only_names={player.full_name},
                    progress_cb=progress_cb,
                )
            except Exception as exc:
                self.excel_status_var.set("")
                if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
                    dpg.set_value(self.excel_status_text_tag, "")
                self._reset_excel_progress()
                self.show_error("Excel Import", f"Import failed: {exc}")
                return
            self.excel_status_var.set("")
            if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
                dpg.set_value(self.excel_status_text_tag, "")
            self._reset_excel_progress()
            if result.rows_applied:
                self.show_info("Excel Import", result.summary_text())
                self._start_scan()
                return
            if result.missing_names:
                self.show_warning(
                    "Excel Import",
                    f"No rows matched {player.full_name}. Use the Excel screen to map names.",
                )
                return
            self.show_info("Excel Import", result.summary_text())

        self._open_file_dialog(
            "Select player workbook to import",
            default_path=str(template.parent),
            default_filename=str(template.name),
            file_types=[("Excel files", ".xlsx")],
            callback=_after_choose,
            save=False,
        )

    # ------------------------------------------------------------------
    # Selection helpers for AI bridge
    # ------------------------------------------------------------------
    def get_player_list_items(self) -> list[str]:
        return list(self.player_list_items)

    def get_selected_player_indices(self) -> list[int]:
        if not self.player_listbox_tag or not dpg.does_item_exist(self.player_listbox_tag):
            return []
        val = dpg.get_value(self.player_listbox_tag)
        if val is None:
            return []
        try:
            idx = self.player_list_items.index(val)
        except ValueError:
            return []
        return [idx]

    def set_selected_player_indices(self, indices: list[int]) -> None:
        if not indices:
            return
        idx = indices[0]
        if 0 <= idx < len(self.player_list_items) and self.player_listbox_tag and dpg.does_item_exist(self.player_listbox_tag):
            dpg.set_value(self.player_listbox_tag, self.player_list_items[idx])
            self._on_player_selected(self.player_listbox_tag, self.player_list_items[idx])

    def clear_player_selection(self) -> None:
        if self.player_listbox_tag and dpg.does_item_exist(self.player_listbox_tag):
            try:
                dpg.set_value(self.player_listbox_tag, None)
            except Exception:
                pass
        self.selected_player = None
        self.selected_players = []
        self._update_detail_fields()

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------
    def _ensure_team_listbox(self) -> None:
        if self.team_list_container is None or not dpg.does_item_exist(self.team_list_container):
            return
        if not self.team_listbox_tag or not dpg.does_item_exist(self.team_listbox_tag):
            with dpg.group(parent=self.team_list_container):
                self.team_listbox_tag = dpg.add_listbox(
                    items=self.team_list_items,
                    num_items=20,
                    callback=self._on_team_listbox_select,
                )

    def _start_team_scan(self) -> None:
        PlayerEditorApp._start_roster_scan(self, apply_pending_team_select=True)

    def _scan_teams_thread(self) -> None:
        PlayerEditorApp._run_roster_scan(self, apply_pending_team_select=True)

    def _roster_needs_refresh(self) -> bool:
        try:
            players_dirty = bool(self.model.is_dirty("players"))
            teams_dirty = bool(self.model.is_dirty("teams"))
            if players_dirty or teams_dirty:
                return True
        except Exception:
            pass
        if not getattr(self.model, "players", None):
            return True
        if not getattr(self.model, "team_list", None):
            return True
        return False

    def _ensure_roster_loaded(self, *, apply_pending_team_select: bool, force: bool = False) -> None:
        if force or self._roster_needs_refresh():
            PlayerEditorApp._start_roster_scan(self, apply_pending_team_select=apply_pending_team_select)
            return
        try:
            teams = self.model.get_teams()
        except Exception:
            teams = []
        self._update_team_dropdown(teams)
        self._refresh_player_list()
        status_msg = ""
        if not self.model.mem.hproc:
            status_msg = "NBA 2K26 is not running."
        elif not teams:
            status_msg = "No teams available."
        self.scan_status_var.set(status_msg)
        self.team_scan_status_var.set(status_msg)
        if apply_pending_team_select and self._pending_team_select and self._pending_team_select in teams:
            self.team_edit_var.set(self._pending_team_select)
            self._on_team_edit_selected()
            self._pending_team_select = None

    def _update_team_dropdown(self, teams: list[str]) -> None:
        special_filters = ["Free Agents", "Draft Prospects"]

        def _append_unique(values: list[str], name: str) -> None:
            if not name:
                return
            if any(existing.lower() == name.lower() for existing in values):
                return
            values.append(name)

        self.all_team_names = list(teams or [])
        if self.team_combo_tag and dpg.does_item_exist(self.team_combo_tag):
            previous_selection = self.team_var.get()
            player_list = ["All Players"]
            for name in special_filters:
                _append_unique(player_list, name)
            for name in teams or []:
                _append_unique(player_list, name)
            dpg.configure_item(self.team_combo_tag, items=player_list)
            if previous_selection in player_list:
                self.team_var.set(previous_selection)
                dpg.set_value(self.team_combo_tag, previous_selection)
            elif player_list:
                self.team_var.set(player_list[0])
                dpg.set_value(self.team_combo_tag, player_list[0])
        # Teams screen list
        self.team_list_items = list(teams or [])
        self._filter_team_list()

    def _filter_team_list(self, *_args) -> None:
        if not self.team_list_container:
            return
        query_raw = (self.team_search_var.get() or "").strip().lower()
        placeholder = "search teams."
        teams = list(self.all_team_names or [])
        if teams and query_raw and query_raw != placeholder:
            filtered = [t for t in teams if query_raw in str(t).lower()]
        else:
            filtered = teams
        self.filtered_team_names = filtered
        self.team_list_items = filtered
        self._ensure_team_listbox()
        if not self.team_listbox_tag or not dpg.does_item_exist(self.team_listbox_tag):
            return
        dpg.configure_item(self.team_listbox_tag, items=filtered or ["No teams available."])
        target_name = self.team_edit_var.get()
        if not target_name or target_name not in filtered:
            target_name = filtered[0] if filtered else ""
            self.team_edit_var.set(target_name)
        if target_name:
            try:
                dpg.set_value(self.team_listbox_tag, target_name)
            except Exception:
                pass
        self.team_count_var.set(f"Teams: {len(filtered)}")
        if getattr(self, "team_count_text_tag", None):
            dpg.set_value(self.team_count_text_tag, self.team_count_var.get())
        self._on_team_edit_selected()

    def _on_team_listbox_select(self, _sender, app_data) -> None:
        name = str(app_data) if app_data is not None else ""
        self.team_edit_var.set(name)
        self._on_team_edit_selected()

    def _on_team_edit_selected(self) -> None:
        team_name = self.team_edit_var.get()
        if getattr(self, "team_editor_detail_name_tag", None):
            dpg.set_value(self.team_editor_detail_name_tag, team_name if team_name else "Select a team")
        if not team_name:
            if self.btn_team_save:
                dpg.configure_item(self.btn_team_save, enabled=False)
            if self.btn_team_full:
                dpg.configure_item(self.btn_team_full, enabled=False)
            for var in self.team_field_vars.values():
                var.set("")
            for tag in self.team_field_input_tags.values():
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, "")
            self._update_team_players(None)
            return
        teams = self.model.get_teams()
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                if self.btn_team_save:
                    dpg.configure_item(self.btn_team_save, enabled=False)
                if self.btn_team_full:
                    dpg.configure_item(self.btn_team_full, enabled=False)
                self._update_team_players(None)
                return
        fields = self.model.get_team_fields(team_idx)
        if not isinstance(fields, dict):
            for var in self.team_field_vars.values():
                var.set("")
            if self.btn_team_save:
                dpg.configure_item(self.btn_team_save, enabled=False)
            self._update_team_players(None)
            return
        for label, var in self.team_field_vars.items():
            val = fields.get(label, "")
            var.set(val)
            tag = self.team_field_input_tags.get(label)
            if tag and dpg.does_item_exist(tag):
                dpg.set_value(tag, str(val))
        enable_live = bool(self.model.mem.hproc)
        if self.btn_team_save:
            dpg.configure_item(self.btn_team_save, enabled=enable_live)
        if self.btn_team_full:
            dpg.configure_item(self.btn_team_full, enabled=enable_live)
        self._update_team_players(team_idx)

    def _on_team_field_changed(self, label: str) -> None:
        tag = self.team_field_input_tags.get(label)
        if not tag or not dpg.does_item_exist(tag):
            return
        value = dpg.get_value(tag)
        self.team_field_vars[label].set(value)

    def _save_team(self) -> None:
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
        values = {label: var.get() for label, var in self.team_field_vars.items()}
        ok = self.model.set_team_fields(team_idx, values)
        if ok:
            self.show_info("Success", f"Updated {team_name} successfully.")
            self.model.refresh_players()
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)
            new_name = values.get("Team Name")
            if new_name:
                self.team_edit_var.set(str(new_name))
            self._on_team_edit_selected()
        else:
            self.show_error("Error", "Failed to write team data. Make sure the game is running and try again.")

    def _open_full_team_editor(self) -> None:
        team_name = self.team_edit_var.get()
        if not team_name:
            self.show_info("Edit Team", "Please select a team first.")
            return
        teams = self.model.get_teams()
        if not teams:
            self.show_info("Edit Team", "No teams available. Refresh and try again.")
            return
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                self.show_error("Edit Team", "Selected team could not be resolved.")
                return
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        if not self.model.mem.hproc:
            self.show_info("Edit Team", "NBA 2K26 is not running. Launch the game to edit team data.")
            return
        try:
            launch_full_editor_process(editor="team", index=team_idx)
        except Exception as exc:
            self.show_error("Edit Team", f"Unable to open team editor window: {exc}")

    # ------------------------------------------------------------------
    # League
    # ------------------------------------------------------------------
    def _league_state(self, page_key: str) -> dict[str, object]:
        state = self.league_states.get(page_key)
        if state is None:
            state = self.league_states["nba_history"]
        return state

    @staticmethod
    def _is_nba_records_category(category_name: str) -> bool:
        cat_lower = (category_name or "").strip().lower()
        if not cat_lower:
            return False
        return (
            "record" in cat_lower
            or cat_lower.startswith("career/")
            or cat_lower.startswith("season/")
            or "single game" in cat_lower
        )

    def _filter_league_page_categories(
        self,
        page_key: str,
        categories: dict[str, list[dict]],
    ) -> dict[str, list[dict]]:
        if page_key == "nba_records":
            return {name: fields for name, fields in categories.items() if self._is_nba_records_category(name)}
        if page_key == "nba_history":
            return {name: fields for name, fields in categories.items() if not self._is_nba_records_category(name)}
        return dict(categories)

    def _register_league_widgets(
        self,
        page_key: str,
        *,
        status_text_tag: int | str | None = None,
        category_combo_tag: int | str | None = None,
        count_text_tag: int | str | None = None,
        table_container: int | str | None = None,
    ) -> None:
        state = self._league_state(page_key)
        state["status_text_tag"] = status_text_tag
        state["category_combo_tag"] = category_combo_tag
        state["count_text_tag"] = count_text_tag
        state["table_container"] = table_container

    def _on_league_category_selected(self, page_key: str, value: str) -> None:
        state = self._league_state(page_key)
        state["selected_category"] = value
        self._refresh_league_records(page_key)

    def _ensure_league_categories(self, page_key: str = "nba_history") -> None:
        state = self._league_state(page_key)
        categories: dict[str, list[dict]] = {}
        target_super = self.league_page_super_types.get(page_key, "League")
        getter = getattr(self.model, "get_categories_for_super", None)
        if callable(getter):
            try:
                resolved = getter(target_super)
                if isinstance(resolved, dict):
                    categories = resolved
            except Exception:
                categories = {}
        if not categories and callable(getter):
            try:
                league_categories = getter("League")
                if isinstance(league_categories, dict):
                    categories = self._filter_league_page_categories(page_key, league_categories)
            except Exception:
                categories = {}
        if not categories:
            legacy_getter = getattr(self.model, "get_league_categories", None)
            if callable(legacy_getter):
                try:
                    legacy_categories = legacy_getter()
                    if isinstance(legacy_categories, dict):
                        categories = self._filter_league_page_categories(page_key, legacy_categories)
                except Exception:
                    categories = {}
        state["category_map"] = categories or {}
        names = sorted((state.get("category_map") or {}).keys())
        state["categories"] = names
        selected = state.get("selected_category")
        if names:
            if not selected or selected not in names:
                selected = names[0]
        else:
            selected = None
        state["selected_category"] = selected
        category_combo_tag = state.get("category_combo_tag")
        if category_combo_tag and dpg.does_item_exist(category_combo_tag):
            dpg.configure_item(category_combo_tag, items=names)
            if selected:
                try:
                    dpg.set_value(category_combo_tag, selected)
                except Exception:
                    pass

    def _update_league_status(self, page_key: str = "nba_history") -> None:
        state = self._league_state(page_key)
        status_var = cast(BoundVar, state.get("status_var"))
        count_var = cast(BoundVar, state.get("count_var"))
        status_text_tag = state.get("status_text_tag")
        count_text_tag = state.get("count_text_tag")
        if status_text_tag and dpg.does_item_exist(status_text_tag):
            dpg.set_value(status_text_tag, status_var.get())
        if count_text_tag and dpg.does_item_exist(count_text_tag):
            dpg.set_value(count_text_tag, count_var.get())

    def _clear_league_table(self, page_key: str = "nba_history", placeholder: str = "No league data loaded.") -> None:
        state = self._league_state(page_key)
        table_container = state.get("table_container")
        if not table_container or not dpg.does_item_exist(table_container):
            return
        children = dpg.get_item_children(table_container, 1) or []
        for child in children:
            dpg.delete_item(child)
        dpg.add_text(placeholder, parent=table_container)
        state["table_tag"] = None

    def _render_league_table(
        self,
        page_key: str,
        category_name: str,
        records: list[dict[str, object]],
    ) -> None:
        state = self._league_state(page_key)
        table_container = state.get("table_container")
        if not table_container or not dpg.does_item_exist(table_container):
            return
        children = dpg.get_item_children(table_container, 1) or []
        for child in children:
            dpg.delete_item(child)
        category_map = cast(dict[str, list[dict]], state.get("category_map") or {})
        fields = [f for f in category_map.get(category_name, []) if isinstance(f, dict)]
        columns = [str(f.get("name", "")) or f"Field {idx + 1}" for idx, f in enumerate(fields)]
        if not columns and records:
            sample = records[0]
            columns = [key for key in sample.keys() if key != "_index"]
        if not records:
            dpg.add_text("No league data found.", parent=table_container)
            state["table_tag"] = None
            return
        with dpg.table(
            parent=table_container,
            header_row=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
        ) as table:
            state["table_tag"] = table
            dpg.add_table_column(label="#")
            for col in columns:
                dpg.add_table_column(label=col)
            for row in records:
                with dpg.table_row():
                    dpg.add_text(str(row.get("_index", len(records))))
                    for col in columns:
                        val = row.get(col, "")
                        if isinstance(val, float):
                            text_val = f"{val:.3f}".rstrip("0").rstrip(".")
                        elif val is None:
                            text_val = ""
                        else:
                            text_val = str(val)
                        dpg.add_text(text_val)

    def _refresh_league_records(self, page_key: str = "nba_history", *_args) -> None:
        state = self._league_state(page_key)
        status_var = cast(BoundVar, state.get("status_var"))
        count_var = cast(BoundVar, state.get("count_var"))
        self._ensure_league_categories(page_key)
        categories = cast(list[str], state.get("categories") or [])
        category = state.get("selected_category") or (categories[0] if categories else None)
        if not category:
            status_var.set("No league offsets available.")
            self._update_league_status(page_key)
            self._clear_league_table(page_key, "No league offsets found in the active schema.")
            return
        state["selected_category"] = category
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        if not self.model.mem.hproc:
            status_var.set("NBA 2K26 is not running; league data unavailable.")
            self._update_league_status(page_key)
            self._clear_league_table(page_key, "Start the game to view league data.")
            return
        status_var.set(f"Loading {category}...")
        self._update_league_status(page_key)
        try:
            records = self.model.get_league_records(str(category))
        except Exception as exc:
            status_var.set(f"Failed to load league data: {exc}")
            self._update_league_status(page_key)
            return
        state["records"] = records
        count_var.set(f"Records: {len(records)}")
        if records:
            status_var.set(f"Loaded {len(records)} records from {category}.")
        else:
            status_var.set(f"No data found for {category}.")
        self._update_league_status(page_key)
        self._render_league_table(page_key, str(category), records)

    # ------------------------------------------------------------------
    # Staff
    # ------------------------------------------------------------------
    def _current_staff_index(self) -> int | None:
        sel = self.get_selected_staff_indices()
        return sel[0] if sel else None

    def _refresh_staff_list(self) -> None:
        try:
            entries = self.model.refresh_staff()
            self.staff_status_var.set("" if entries else "No staff detected; pointers may be missing.")
        except Exception:
            entries = []
            self.staff_status_var.set("Unable to scan staff.")
        if getattr(self, "staff_status_text_tag", None):
            dpg.set_value(self.staff_status_text_tag, self.staff_status_var.get())
        self.staff_entries = entries
        self._filter_staff_list()

    def _filter_staff_list(self, *_args) -> None:
        query = (self.staff_search_var.get() or "").strip().lower()
        filtered: list[tuple[int, str]] = []
        for entry in self.staff_entries:
            name = entry[1]
            if not query or query in name.lower():
                filtered.append(entry)
        self._filtered_staff_entries = filtered
        items = [name for _, name in filtered] if filtered else ["No staff found."]
        if self.staff_list_container and not self.staff_listbox_tag:
            with dpg.group(parent=self.staff_list_container):
                self.staff_listbox_tag = dpg.add_listbox(items=items, num_items=18, callback=self._on_staff_selected)
        elif self.staff_listbox_tag and dpg.does_item_exist(self.staff_listbox_tag):
            dpg.configure_item(self.staff_listbox_tag, items=items)
        self.staff_count_var.set(f"Staff: {len(filtered)}")
        if getattr(self, "staff_count_text_tag", None):
            dpg.set_value(self.staff_count_text_tag, self.staff_count_var.get())
        if filtered and self.staff_listbox_tag:
            dpg.set_value(self.staff_listbox_tag, items[0])

    def _on_staff_selected(self, _sender=None, app_data=None) -> None:
        # Enable the open editor button when a valid staff member is selected.
        enable = False
        if app_data and isinstance(app_data, str) and self.btn_staff_full:
            enable = app_data != "No staff found."
            dpg.configure_item(self.btn_staff_full, enabled=enable)

    def _open_full_staff_editor(self, staff_idx: int | None = None) -> None:
        if staff_idx is None:
            sel = self.get_selected_staff_indices()
            staff_idx = sel[0] if sel else None
        if staff_idx is None:
            self.show_info("Staff Editor", "Select a staff member first.")
            return
        try:
            launch_full_editor_process(editor="staff", index=staff_idx)
        except Exception as exc:
            self.show_error("Staff Editor", f"Unable to open staff editor window: {exc}")

    def get_staff_list_items(self) -> list[str]:
        return [name for _, name in self._filtered_staff_entries] if self._filtered_staff_entries else []

    def get_selected_staff_indices(self) -> list[int]:
        if not self.staff_listbox_tag or not dpg.does_item_exist(self.staff_listbox_tag):
            return []
        val = dpg.get_value(self.staff_listbox_tag)
        items = self.get_staff_list_items()
        if val in items:
            pos = items.index(val)
            if 0 <= pos < len(self._filtered_staff_entries):
                return [self._filtered_staff_entries[pos][0]]
        return []

    def set_staff_selection(self, positions: list[int]) -> None:
        if not positions or not self.staff_listbox_tag:
            return
        target = positions[0]
        items = self.get_staff_list_items()
        idx: int | None = None
        for pos, entry in enumerate(self._filtered_staff_entries):
            if entry[0] == target:
                idx = pos
                break
        if idx is None and 0 <= target < len(items):
            idx = target
        if idx is not None and 0 <= idx < len(items):
            dpg.set_value(self.staff_listbox_tag, items[idx])
            self._on_staff_selected(self.staff_listbox_tag, items[idx])

    # ------------------------------------------------------------------
    # Stadiums
    # ------------------------------------------------------------------
    def _current_stadium_index(self) -> int | None:
        sel = self.get_selected_stadium_indices()
        return sel[0] if sel else None

    def _refresh_stadium_list(self) -> None:
        try:
            entries = self.model.refresh_stadiums()
            self.stadium_status_var.set("" if entries else "No stadiums detected; pointers may be missing.")
        except Exception:
            entries = []
            self.stadium_status_var.set("Unable to scan stadiums.")
        if getattr(self, "stadium_status_text_tag", None):
            dpg.set_value(self.stadium_status_text_tag, self.stadium_status_var.get())
        self.stadium_entries = entries
        self._filter_stadium_list()

    def _filter_stadium_list(self, *_args) -> None:
        query = (self.stadium_search_var.get() or "").strip().lower()
        filtered: list[tuple[int, str]] = []
        for entry in self.stadium_entries:
            name = entry[1]
            if not query or query in name.lower():
                filtered.append(entry)
        self._filtered_stadium_entries = filtered
        items = [name for _, name in filtered] if filtered else ["No stadiums found."]
        if self.stadium_list_container and not self.stadium_listbox_tag:
            with dpg.group(parent=self.stadium_list_container):
                self.stadium_listbox_tag = dpg.add_listbox(items=items, num_items=18, callback=self._on_stadium_selected)
        elif self.stadium_listbox_tag and dpg.does_item_exist(self.stadium_listbox_tag):
            dpg.configure_item(self.stadium_listbox_tag, items=items)
        self.stadium_count_var.set(f"Stadiums: {len(filtered)}")
        if getattr(self, "stadium_count_text_tag", None):
            dpg.set_value(self.stadium_count_text_tag, self.stadium_count_var.get())
        if filtered and self.stadium_listbox_tag:
            dpg.set_value(self.stadium_listbox_tag, items[0])

    def _on_stadium_selected(self, _sender=None, app_data=None) -> None:
        if self.btn_stadium_full:
            enable = bool(app_data and app_data != "No stadiums found.")
            dpg.configure_item(self.btn_stadium_full, enabled=enable)

    def _open_full_stadium_editor(self, stadium_idx: int | None = None) -> None:
        if stadium_idx is None:
            sel = self.get_selected_stadium_indices()
            stadium_idx = sel[0] if sel else None
        if stadium_idx is None:
            self.show_info("Stadium Editor", "Select a stadium first.")
            return
        try:
            launch_full_editor_process(editor="stadium", index=stadium_idx)
        except Exception as exc:
            self.show_error("Stadium Editor", f"Unable to open stadium editor window: {exc}")

    def get_stadium_list_items(self) -> list[str]:
        return [name for _, name in self._filtered_stadium_entries] if self._filtered_stadium_entries else []

    def get_selected_stadium_indices(self) -> list[int]:
        if not self.stadium_listbox_tag or not dpg.does_item_exist(self.stadium_listbox_tag):
            return []
        val = dpg.get_value(self.stadium_listbox_tag)
        items = self.get_stadium_list_items()
        if val in items:
            pos = items.index(val)
            if 0 <= pos < len(self._filtered_stadium_entries):
                return [self._filtered_stadium_entries[pos][0]]
        return []

    def set_stadium_selection(self, positions: list[int]) -> None:
        if not positions or not self.stadium_listbox_tag:
            return
        target = positions[0]
        items = self.get_stadium_list_items()
        idx: int | None = None
        for pos, entry in enumerate(self._filtered_stadium_entries):
            if entry[0] == target:
                idx = pos
                break
        if idx is None and 0 <= target < len(items):
            idx = target
        if idx is not None and 0 <= idx < len(items):
            dpg.set_value(self.stadium_listbox_tag, items[idx])
            self._on_stadium_selected(self.stadium_listbox_tag, items[idx])

    # ------------------------------------------------------------------
    # Randomizer / Shuffle / Batch
    # ------------------------------------------------------------------
    def _open_randomizer(self) -> None:
        try:
            self.model.refresh_players()
        except Exception:
            pass
        RandomizerWindow(self, self.model)

    def _open_team_shuffle(self) -> None:
        try:
            self.model.refresh_players()
        except Exception:
            pass
        TeamShuffleWindow(self, self.model)

    def _open_batch_edit(self) -> None:
        try:
            self.model.refresh_players()
        except Exception:
            pass
        try:
            BatchEditWindow(self, self.model)
        except Exception as exc:
            self.show_error("Batch Edit", f"Failed to open batch edit window: {exc}")

    def _open_team_player_editor(self) -> None:
        if not self.team_players_listbox_tag or not dpg.does_item_exist(self.team_players_listbox_tag):
            self.show_info("Team Player Editor", "No team player list is available.")
            return
        value = dpg.get_value(self.team_players_listbox_tag)
        name = str(value) if value else ""
        if not name or name == "(No players found)":
            self.show_info("Team Player Editor", "Select a player slot first.")
            return
        try:
            idx = self.team_players_list_items.index(name)
        except ValueError:
            idx = -1
        if idx < 0 or idx >= len(self.team_players_lookup):
            self.show_info("Team Player Editor", "Selected player could not be resolved.")
            return
        player = self.team_players_lookup[idx]
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        if not self.model.mem.hproc:
            self.show_info("Team Player Editor", "NBA 2K26 is not running. Launch the game to edit team players.")
            return
        try:
            FullPlayerEditor(self, player, self.model)
        except Exception as exc:
            self.show_error("Team Player Editor", f"Unable to open player editor: {exc}")

    def _on_team_player_selected(self, _sender=None, app_data=None) -> None:
        has_selection = bool(app_data) and app_data != "(No players found)"
        if self.btn_team_player and dpg.does_item_exist(self.btn_team_player):
            dpg.configure_item(self.btn_team_player, enabled=has_selection)

    def _update_team_players(self, team_idx: int | None) -> None:
        items = ["(No players found)"]
        self.team_players_lookup = []
        if team_idx is not None:
            players: list[Player] = []
            try:
                if self.model.mem.hproc and self.model.mem.base_addr and not getattr(self.model, "external_loaded", False):
                    players = self.model.scan_team_players(team_idx)
            except Exception:
                players = []
            if not players:
                try:
                    teams = self.model.get_teams()
                    if 0 <= team_idx < len(teams):
                        team_name = teams[team_idx]
                        players = self.model.get_players_by_team(team_name)
                except Exception:
                    players = []
            self.team_players_lookup = players
            if players:
                items = [p.full_name for p in players]
        self.team_players_list_items = items
        if self.team_players_listbox_tag and dpg.does_item_exist(self.team_players_listbox_tag):
            dpg.configure_item(self.team_players_listbox_tag, items=items)
            if items:
                try:
                    dpg.set_value(self.team_players_listbox_tag, items[0])
                except Exception:
                    pass
        if self.btn_team_player and dpg.does_item_exist(self.btn_team_player):
            dpg.configure_item(self.btn_team_player, enabled=bool(self.team_players_lookup))

    # ------------------------------------------------------------------
    # Excel import/export
    # ------------------------------------------------------------------
    def _set_excel_status(self, message: str) -> None:
        self.excel_status_var.set(message)
        if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
            dpg.set_value(self.excel_status_text_tag, message)

    def _reset_excel_progress(self) -> None:
        self.excel_progress_var.set(0)
        if self.excel_progress_bar_tag and dpg.does_item_exist(self.excel_progress_bar_tag):
            dpg.set_value(self.excel_progress_bar_tag, 0)

    def _apply_excel_progress(
        self,
        verb: str,
        entity_label: str,
        current: int,
        total: int,
        sheet_name: str | None,
    ) -> None:
        self.excel_progress_var.set(current if total else 0)
        status = f"{verb} {entity_label}"
        if sheet_name:
            status = f"{status} ({sheet_name})"
        if total > 0:
            status = f"{status} {current}/{total}"
        self.excel_status_var.set(status)
        if self.excel_status_text_tag and dpg.does_item_exist(self.excel_status_text_tag):
            dpg.set_value(self.excel_status_text_tag, status)
        if self.excel_progress_bar_tag and dpg.does_item_exist(self.excel_progress_bar_tag):
            dpg.set_value(self.excel_progress_bar_tag, current / total if total else 0)

    def _excel_progress_callback(
        self,
        verb: str,
        entity_label: str,
    ) -> Callable[[int, int, str | None], None]:
        def _callback(current: int, total: int, sheet_name: str | None) -> None:
            self.run_on_ui_thread(lambda: self._apply_excel_progress(verb, entity_label, current, total, sheet_name))

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

    def _finish_excel_export(self, result: object, error: Exception | None) -> None:
        self._excel_export_thread = None
        self._excel_export_queue = None
        self._excel_export_polling = False
        if error is not None:
            self._reset_excel_progress()
            self._set_excel_status("")
            self.show_error("Excel Export", f"Export failed: {error}")
            return
        if result is None:
            self._reset_excel_progress()
            self._set_excel_status("")
            self.show_error("Excel Export", "Export failed: Unknown error.")
            return
        # Keep completion state visible; it will reset when the next operation starts.
        self.excel_progress_var.set(1.0)
        if self.excel_progress_bar_tag and dpg.does_item_exist(self.excel_progress_bar_tag):
            dpg.set_value(self.excel_progress_bar_tag, 1.0)
        if self._excel_export_entity_label:
            self._set_excel_status(f"{self._excel_export_entity_label} export complete.")
        else:
            self._set_excel_status("Export complete.")
        try:
            summary = result.summary_text()  # type: ignore[union-attr]
        except Exception:
            summary = "Export completed."
        self.show_info("Excel Export", summary)

    def _import_excel(self, entity_type: str) -> None:
        try:
            from ..importing.excel_import import import_excel_workbook, template_path_for
        except Exception as exc:
            self.show_error("Excel Import", f"Import helpers not available: {exc}")
            return
        if not self.model.mem.open_process():
            self.show_error("Excel Import", "NBA 2K26 is not running.")
            return
        entity_key = normalize_entity_key(entity_type)
        if not entity_key:
            self.show_error("Excel Import", "Unknown entity type.")
            return
        try:
            template = template_path_for(entity_key)
        except ValueError as exc:
            self.show_error("Excel Import", str(exc))
            return
        def _after_choose(path: str) -> None:
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
            self._set_excel_status(f"Importing {entity_key}...")
            progress_cb = self._excel_progress_callback("Importing", entity_title(entity_key))
            try:
                result = import_excel_workbook(self.model, path, entity_key, progress_cb=progress_cb)
            except Exception as exc:
                self._set_excel_status("")
                self._reset_excel_progress()
                self.show_error("Excel Import", f"Import failed: {exc}")
                return
            self._set_excel_status("")
            self._reset_excel_progress()
            if result.missing_names:
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
                    self._set_excel_status(f"Importing {entity_key}...")
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
                        self._set_excel_status("")
                        self.show_error("Excel Import", f"Import failed: {exc}")
                        return
                    self._reset_excel_progress()
                    self._set_excel_status("")
                    self.show_info("Excel Import", follow.summary_text())

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
                self.show_info("Excel Import", result.summary_text())

        self._open_file_dialog(
            "Select Excel workbook to import",
            default_path=str(template.parent),
            default_filename=str(template.name),
            file_types=[("Excel files", ".xlsx")],
            callback=_after_choose,
            save=False,
        )

    def _export_excel(self, entity_type: str) -> None:
        try:
            from ..importing.excel_import import export_excel_workbook, template_path_for
        except Exception as exc:
            self.show_error("Excel Export", f"Export helpers not available: {exc}")
            return
        if self._excel_export_thread is not None and self._excel_export_thread.is_alive():
            self.show_info("Excel Export", "An export is already running.")
            return
        if not self.model.mem.open_process():
            self.show_error("Excel Export", "NBA 2K26 is not running.")
            return
        entity_key = normalize_entity_key(entity_type)
        if not entity_key:
            self.show_error("Excel Export", "Unknown entity type.")
            return
        try:
            template = template_path_for(entity_key)
        except ValueError as exc:
            self.show_error("Excel Export", str(exc))
            return

        def _start_export(team_filter: set[str] | None = None) -> None:
            default_name = template.name.replace(".xlsx", "_export.xlsx")
            def _after_choose(path: str) -> None:
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
                self._set_excel_status(status_label)
                self._excel_export_entity_label = entity_title(entity_key)
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
                            team_filter=team_filter,
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

            self._open_file_dialog(
                "Save export workbook",
                default_path=str(template.parent),
                default_filename=default_name,
                file_types=[("Excel files", ".xlsx")],
                callback=_after_choose,
                save=True,
            )

        if entity_key == "players":
            if not self.model.players or not self.model.team_list:
                try:
                    self.model.refresh_players()
                except Exception:
                    pass
            teams_ordered = self.model.get_teams()
            if not teams_ordered:
                self.show_error("Excel Export", "No teams available to export.")
                return
            team_id_map = {name: idx for idx, name in self.model.team_list}
            teams = [(team_id_map.get(name), name) for name in teams_ordered]

            def _after_team_choice(selected: list[str] | None, all_teams: bool) -> None:
                if selected is None:
                    return
                team_filter = None
                if not all_teams:
                    team_filter = {str(name).lower() for name in selected}
                _start_export(team_filter)

            TeamSelectionDialog(
                self,
                teams,
                title="Export Players",
                message="Select teams to include in the export:",
                select_all=True,
                callback=_after_team_choice,
            )
            return

        _start_export()

    def _open_import_dialog(self) -> None:
        self.show_excel()

    def _open_export_dialog(self) -> None:
        self.show_excel()

    def _open_load_excel(self) -> None:
        self.show_excel()

    # ------------------------------------------------------------------
    # Offsets
    # ------------------------------------------------------------------
    def _hook_label_for(self, target: str | None) -> str:
        if not target:
            return MODULE_NAME
        key = str(target).lower()
        return HOOK_TARGET_LABELS.get(key, target.replace(".exe", "").upper())

    def _set_hook_target(self, exe_name: str) -> None:
        self.hook_target_var.set(exe_name)
        self._update_status()

    def _open_offset_file_dialog(self) -> None:
        def _after_choose(path: str) -> None:
            if not path:
                return
            fname = Path(path).name
            self._set_offset_status(f"Loading offsets from {fname}...")
            target_exec = self.hook_target_var.get() or self.model.mem.module_name or MODULE_NAME
            try:
                initialize_offsets(target_executable=target_exec, force=True, filename=path)
                self.model._sync_offset_constants()
                self.model.categories = offsets_mod._load_categories()
                self._set_offset_status(f"Loaded offsets from {fname}")
                self.model.invalidate_base_cache()
                self._update_status()
                self._start_scan()
                self.show_info("Offsets loaded", f"Loaded offsets from {fname}")
            except OffsetSchemaError as exc:
                self._set_offset_status("Failed to apply offsets file.")
                self.show_error("Offsets load failed", f"Unable to apply offsets from {fname}.\n{exc}")
            except Exception as exc:
                self._set_offset_status("Failed to apply offsets file.")
                self.show_error("Offsets load failed", f"Unable to apply offsets from {fname}.\n{exc}")

        self._open_file_dialog(
            "Select offsets file",
            file_types=[("JSON files", ".json"), ("All files", ".*")],
            callback=_after_choose,
            save=False,
        )
    # ------------------------------------------------------------------
    # Trade helpers
    # ------------------------------------------------------------------
    def _refresh_trade_data(self) -> None:
        """Refresh team options, rosters, and staged packages for the trade screen."""
        self._trade_refresh_team_options()
        self._trade_refresh_rosters()
        self._trade_refresh_package_lists()
        self._trade_update_status("")
        if self.trade_slot_combo_tag and dpg.does_item_exist(self.trade_slot_combo_tag):
            dpg.configure_item(self.trade_slot_combo_tag, items=[f"Slot {i+1}" for i in range(36)])
            dpg.set_value(self.trade_slot_combo_tag, f"Slot {self.trade_selected_slot+1}")
        if self.trade_participants_list_tag and dpg.does_item_exist(self.trade_participants_list_tag):
            dpg.configure_item(self.trade_participants_list_tag, items=self.trade_participants)
        if self.trade_active_team_combo_tag and dpg.does_item_exist(self.trade_active_team_combo_tag):
            dpg.configure_item(self.trade_active_team_combo_tag, items=self.trade_participants)
            if self.trade_active_team_var.get():
                dpg.set_value(self.trade_active_team_combo_tag, self.trade_active_team_var.get())

    def _trade_refresh_team_options(self) -> None:
        """Populate global team list and ensure participants list is initialized."""
        try:
            if PlayerEditorApp._roster_needs_refresh(self):
                self.model.refresh_players()
        except Exception:
            pass
        sorted_teams = sorted(
            self.model.team_list,
            key=lambda pair: pair[0] if isinstance(pair, tuple) and pair and pair[0] is not None else 10**9,
        )
        self.trade_team_options = [name for tid, name in sorted_teams]
        self.trade_team_lookup = {name: tid for tid, name in sorted_teams}
        # Seed participants with first two teams if empty.
        if not self.trade_participants and self.trade_team_options:
            self.trade_participants.append(self.trade_team_options[0])
            if len(self.trade_team_options) > 1:
                self.trade_participants.append(self.trade_team_options[1])
            self.trade_active_team_var.set(self.trade_participants[0])
        # Ensure current slot has entries for all participants
        self._trade_ensure_slot_entries()
        # Sync dropdowns
        if self.trade_add_team_combo_tag and dpg.does_item_exist(self.trade_add_team_combo_tag):
            remaining = [t for t in self.trade_team_options if t not in self.trade_participants]
            dpg.configure_item(self.trade_add_team_combo_tag, items=remaining)
        if self.trade_participants_list_tag and dpg.does_item_exist(self.trade_participants_list_tag):
            dpg.configure_item(self.trade_participants_list_tag, items=self.trade_participants)
        if self.trade_active_team_combo_tag and dpg.does_item_exist(self.trade_active_team_combo_tag):
            dpg.configure_item(self.trade_active_team_combo_tag, items=self.trade_participants)
            if self.trade_active_team_var.get():
                dpg.set_value(self.trade_active_team_combo_tag, self.trade_active_team_var.get())
        self._trade_render_team_lists()

    def _trade_get_roster(self, team_name: str | None) -> list[Player]:
        if not team_name:
            return []
        players = getattr(self.model, "players", []) or []
        if PlayerEditorApp._roster_needs_refresh(self):
            try:
                self.model.refresh_players()
                players = getattr(self.model, "players", [])
            except Exception:
                return []
        team_id = self.trade_team_lookup.get(team_name)
        roster: list[Player] = []
        for p in players:
            if team_id is not None and p.team_id == team_id:
                roster.append(p)
            elif team_id is None and p.team == team_name:
                roster.append(p)
        self._trade_load_contracts(roster)
        return roster

    def _trade_load_contracts(self, players: list[Player]) -> None:
        """Attach contract info to players if contract offsets are available."""
        if self.trade_contract_meta is None:
            contract_fields = self.model.categories.get("Contract", []) or []
            meta_map: dict[str, dict[str, object]] = {}
            for field in contract_fields:
                name = field.get("name") or field.get("display_name") or field.get("normalized_name")
                if not name:
                    continue
                meta_map[str(name)] = field
            self.trade_contract_meta = meta_map
        meta_map = self.trade_contract_meta or {}
        salary_fields = [f"Year {i}" for i in range(1, 7)]
        extra_fields = [
            "Years Left",
            "Original Contract Length",
            "Extension Length",
            "Option",
            "Extension Option",
            "Free Agency Type",
            "Type",
            "Two-Way NBA Days Left",
        ]
        for p in players:
            contract: dict[str, object] = {}
            record_ptr = getattr(p, "record_ptr", None)
            salaries: list[object] = []
            for label in salary_fields:
                meta = meta_map.get(label)
                if not meta:
                    continue
                try:
                    val = self.model.decode_field_value(
                        entity_type="player",
                        entity_index=p.index,
                        category="Contract",
                        field_name=label,
                        meta=meta,
                        record_ptr=record_ptr,
                    )
                except Exception:
                    val = None
                if val is not None:
                    salaries.append(val)
            if salaries:
                contract["salaries"] = salaries
            for label in extra_fields:
                meta = meta_map.get(label)
                if not meta:
                    continue
                try:
                    val = self.model.decode_field_value(
                        entity_type="player",
                        entity_index=p.index,
                        category="Contract",
                        field_name=label,
                        meta=meta,
                        record_ptr=record_ptr,
                    )
                except Exception:
                    val = None
                if val is not None:
                    contract[label] = val
            setattr(p, "contract_info", contract)

    def _trade_player_label(self, player: Player) -> str:
        contract = getattr(player, "contract_info", {}) or {}
        salaries = contract.get("salaries") or []
        salary_str = ""
        if isinstance(salaries, (list, tuple)) and salaries:
            salary_str = f" | Y1 {salaries[0]}"
        return f"{player.index}: {player.full_name}{salary_str}"

    def _trade_y1_salary(self, player: Player) -> int:
        contract = getattr(player, "contract_info", {}) or {}
        salaries = contract.get("salaries") or []
        if isinstance(salaries, (list, tuple)) and salaries:
            try:
                return int(salaries[0])
            except Exception:
                return 0
        return 0

    def _trade_refresh_rosters(self) -> None:
        """Load roster for the active team and update list widget."""
        self.trade_roster_active = self._trade_get_roster(self.trade_active_team_var.get())
        if self.trade_roster_list_tag and dpg.does_item_exist(self.trade_roster_list_tag):
            dpg.configure_item(
                self.trade_roster_list_tag,
                items=[self._trade_player_label(p) for p in self.trade_roster_active],
            )

    def _trade_set_active_team(self, _sender, value) -> None:
        self.trade_active_team_var.set(value or "")
        self.trade_selected_player_obj = None
        self._trade_refresh_rosters()

    def _trade_set_active_team_from_list(self, _sender, value) -> None:
        self._trade_set_active_team(_sender, value)
        if self.trade_active_team_combo_tag and dpg.does_item_exist(self.trade_active_team_combo_tag):
            try:
                dpg.set_value(self.trade_active_team_combo_tag, value)
            except Exception:
                pass

    def _trade_add_participant(self, team_name: str | None) -> None:
        if not team_name:
            return
        if team_name not in self.trade_participants and len(self.trade_participants) < 36:
            self.trade_participants.append(team_name)
            self._trade_ensure_slot_entries()
            if self.trade_participants_list_tag and dpg.does_item_exist(self.trade_participants_list_tag):
                dpg.configure_item(self.trade_participants_list_tag, items=self.trade_participants)
            if self.trade_active_team_combo_tag and dpg.does_item_exist(self.trade_active_team_combo_tag):
                dpg.configure_item(self.trade_active_team_combo_tag, items=self.trade_participants)
            if not self.trade_active_team_var.get():
                self.trade_active_team_var.set(team_name)
            self._trade_refresh_rosters()
            self._trade_render_team_lists()
        # Update add-team dropdown to exclude already-selected teams
        if self.trade_add_team_combo_tag and dpg.does_item_exist(self.trade_add_team_combo_tag):
            remaining = [t for t in self.trade_team_options if t not in self.trade_participants]
            dpg.configure_item(self.trade_add_team_combo_tag, items=remaining)

    def _trade_select_active_player(self, _sender, value) -> None:
        self.trade_selected_player_obj = None
        if not value:
            return
        label = str(value)
        try:
            idx = int(label.split(":", 1)[0].strip())
        except Exception:
            return
        for p in self.trade_roster_active:
            if p.index == idx:
                self.trade_selected_player_obj = p
                break

    def _trade_open_player_modal(self) -> None:
        """Open modal to select players and direction for the active team."""
        team = self.trade_active_team_var.get()
        if not team:
            self._trade_update_status("Select a team first.")
            return
        roster = self.trade_roster_active or []
        if not roster:
            self._trade_update_status("No roster loaded for selected team.")
            return
        modal = dpg.generate_uuid()
        player_list = dpg.generate_uuid()
        direction_radio = dpg.generate_uuid()
        dest_combo = dpg.generate_uuid()
        roster_labels = [self._trade_player_label(p) for p in roster]

        def _confirm(_s, _a):
            sel = dpg.get_value(player_list)
            direction = dpg.get_value(direction_radio)
            dest = dpg.get_value(dest_combo)
            idx = None
            if isinstance(sel, int):
                idx = sel
            elif isinstance(sel, str):
                try:
                    idx = roster_labels.index(sel)
                except ValueError:
                    idx = None
            if idx is None or idx < 0 or idx >= len(roster):
                self._trade_update_status("Select a player.")
                return
            if not dest:
                self._trade_update_status("Select a destination team.")
                return
            player = roster[idx]
            if direction == "send":
                self._trade_add_transaction(player, team, dest, outgoing=True)
            else:
                self._trade_add_transaction(player, dest, team, outgoing=False)
            dpg.delete_item(modal)

        with dpg.window(modal=True, popup=True, tag=modal, width=360, height=360, label=f"Trade Players - {team}"):
            dpg.add_text(f"Players on {team}")
            dpg.add_listbox(tag=player_list, items=roster_labels, num_items=10)
            dpg.add_text("Direction")
            dpg.add_radio_button(items=["send", "receive"], default_value="send", tag=direction_radio, horizontal=True)
            dpg.add_text("Other team")
            choices = [t for t in self.trade_participants if t != team]
            dpg.add_combo(items=choices, default_value=choices[0] if choices else "", tag=dest_combo)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Confirm", width=100, callback=_confirm)
                dpg.add_button(label="Cancel", width=100, callback=lambda *_: dpg.delete_item(modal))

    def _trade_add_transaction(self, player: Player, from_team: str | None, to_team: str | None, outgoing: bool) -> None:
        if not from_team or not to_team or from_team == to_team:
            self._trade_update_status("Pick distinct source and destination teams.")
            return
        source = from_team if outgoing else to_team
        dest = to_team if outgoing else from_team
        if not self.trade_state.add_transaction(player, source, dest):
            self._trade_update_status("Transaction already exists in this slot.")
            return
        self._trade_refresh_package_lists()
        self._trade_update_status(f"Staged {player.full_name} ({from_team} ↔ {to_team}) in Slot {self.trade_selected_slot+1}")

    def _trade_clear(self) -> None:
        self.trade_state.clear_slot(self.trade_selected_slot)
        self.trade_slots = self.trade_state.slots
        self._trade_refresh_package_lists()
        self._trade_update_status("")

    def _trade_swap_teams(self) -> None:
        a = self.trade_team_a_var.get()
        b = self.trade_team_b_var.get()
        self.trade_team_a_var.set(b)
        self.trade_team_b_var.set(a)
        self.trade_selected_player_obj = None
        self.trade_selected_transaction = None
        self._trade_refresh_rosters()
        self._trade_refresh_package_lists()

    def _trade_refresh_package_lists(self) -> None:
        self._trade_render_team_lists()

    def _trade_update_status(self, text: str) -> None:
        self.trade_status_var.set(text)
        if self.trade_status_text_tag and dpg.does_item_exist(self.trade_status_text_tag):
            dpg.set_value(self.trade_status_text_tag, text)

    def _trade_select_transaction(self, _sender, value) -> None:
        try:
            idx = int(value) if isinstance(value, int) else None
        except Exception:
            idx = None
        self.trade_selected_transaction = idx

    def _trade_remove_transaction(self) -> None:
        if self.trade_selected_transaction is None:
            return
        self.trade_state.remove_transaction(self.trade_selected_transaction)
        self.trade_selected_transaction = None
        self._trade_refresh_package_lists()

    def _trade_select_slot(self, value: str) -> None:
        """Switch the active trade package slot (1-36)."""
        idx = coerce_int(str(value).replace("Slot", "").strip(), 1) - 1
        idx = max(0, min(35, idx))
        self.trade_selected_slot = idx
        self.trade_state.select_slot(idx)
        self._trade_refresh_package_lists()
        self._trade_update_status(f"Switched to Slot {idx+1}")

    def _trade_clear_slot(self) -> None:
        """Clear only the current slot packages."""
        self.trade_state.clear_slot(self.trade_selected_slot)
        self.trade_slots = self.trade_state.slots
        self.trade_selected_transaction = None
        self._trade_refresh_package_lists()
        self._trade_update_status(f"Cleared Slot {self.trade_selected_slot+1}")

    def _trade_propose(self) -> None:
        slot = self.trade_state.current_slot()
        if not slot.transactions:
            self._trade_update_status("Add players to the package before proposing a trade.")
            return
        summary = (
            format_trade_summary(self.trade_selected_slot + 1, len(slot.transactions))
        )
        self._trade_update_status(summary)

    def _trade_render_team_lists(self) -> None:
        """Render outgoing/incoming lists per team for the current slot."""
        slot = self.trade_state.current_slot()
        packages = slot.packages(self.trade_participants)
        # Ensure containers exist
        if not (self.trade_outgoing_container and self.trade_incoming_container):
            return
        # Clear children
        for container in (self.trade_outgoing_container, self.trade_incoming_container):
            try:
                for child in list(dpg.get_item_children(container, 1) or []):
                    dpg.delete_item(child)
            except Exception:
                pass
        # Build per-team blocks
        for team in self.trade_participants:
            pkg = packages.get(team)
            outgoing = list(pkg.outgoing) if pkg else []
            incoming = list(pkg.incoming) if pkg else []
            out_salary = sum(self._trade_y1_salary(p) for p in outgoing)
            in_salary = sum(self._trade_y1_salary(p) for p in incoming)
            with dpg.group(parent=self.trade_outgoing_container):
                dpg.add_text(f"{team} (outgoing) — Y1 total: {out_salary:,}")
                dpg.add_listbox(items=[self._trade_player_label(p) for p in outgoing] or ["(none)"], num_items=4, width=320)
                dpg.add_spacer(height=4)
            with dpg.group(parent=self.trade_incoming_container):
                dpg.add_text(f"{team} (incoming) — Y1 total: {in_salary:,}")
                dpg.add_listbox(items=[self._trade_player_label(p) for p in incoming] or ["(none)"], num_items=4, width=320)
                dpg.add_spacer(height=4)

    def _trade_ensure_slot_entries(self) -> None:
        """Retained for backward compatibility; package entries are derived at render time."""
        self.trade_state.select_slot(self.trade_selected_slot)

    # ------------------------------------------------------------------
    # Agent runtime (PPO)
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_agent_runtime_class() -> type["AgentRuntime"]:
        from ..gm_rl.runtime import AgentRuntime

        return AgentRuntime

    @staticmethod
    def _resolve_agent_adapter_classes() -> tuple[type["EditorLiveAdapter"], type["LocalMockAdapter"]]:
        from ..gm_rl.adapters.editor_live import EditorLiveAdapter
        from ..gm_rl.adapters.local_mock import LocalMockAdapter

        return EditorLiveAdapter, LocalMockAdapter

    def _ensure_agent_runtime(self) -> "AgentRuntime":
        if self.agent_runtime is None:
            try:
                runtime_class = self._resolve_agent_runtime_class()
            except Exception as exc:
                error_msg = f"Agent runtime unavailable: {exc}"
                self._append_agent_log(f"Error: {error_msg}")
                self._set_agent_status(error_msg)
                raise
            self.agent_runtime = runtime_class(lambda name, writes: self._build_agent_adapter(name, writes))
        return self.agent_runtime

    def _build_agent_adapter(self, name: str, apply_writes: bool) -> "EditorAdapter":
        try:
            editor_live_adapter_cls, local_mock_adapter_cls = self._resolve_agent_adapter_classes()
        except Exception as exc:
            error_msg = f"Agent adapters unavailable: {exc}"
            self._append_agent_log(f"Error: {error_msg}")
            self._set_agent_status(error_msg)
            raise
        adapter_name = (name or "mock").strip().lower()
        if adapter_name == "live":
            return editor_live_adapter_cls(model=self.model, dry_run=not apply_writes, seed=random.randint(1, 10_000))
        return local_mock_adapter_cls(seed=random.randint(1, 10_000))

    def _agent_refresh_snapshot(self) -> None:
        adapter = self._build_agent_adapter(self.agent_adapter_var.get(), self.agent_apply_writes_var.get())
        try:
            state = adapter.load_roster_state(seed=random.randint(1, 10_000))
            msg = f"Snapshot loaded ({len(state.players)} players / {len(state.teams)} teams) using {self.agent_adapter_var.get()} adapter."
        except Exception as exc:  # noqa: BLE001
            msg = f"Agent snapshot failed: {exc}"
        self._set_agent_status(msg)

    def _agent_start_evaluate(self) -> None:
        runtime = self._ensure_agent_runtime()
        try:
            team_id = int(self.agent_team_id_var.get() or 1)
        except Exception:
            team_id = 1
        try:
            episodes = int(self.agent_episodes_var.get() or 3)
        except Exception:
            episodes = 3
        runtime.start_evaluate(
            adapter=self.agent_adapter_var.get(),
            config_path=self.agent_config_var.get() or None,
            checkpoint=self.agent_checkpoint_var.get() or None,
            episodes=max(1, episodes),
            team_id=team_id,
            apply_writes=self.agent_apply_writes_var.get(),
        )
        self._set_agent_status("Evaluation started ...")

    def _agent_start_live_assist(self) -> None:
        runtime = self._ensure_agent_runtime()
        try:
            team_id = int(self.agent_team_id_var.get() or 1)
        except Exception:
            team_id = 1
        runtime.start_live_assist(
            adapter=self.agent_adapter_var.get(),
            config_path=self.agent_config_var.get() or None,
            checkpoint=self.agent_checkpoint_var.get() or None,
            team_id=team_id,
            apply_writes=self.agent_apply_writes_var.get(),
        )
        self._set_agent_status("Live assist started ...")

    def _agent_start_training(self) -> None:
        runtime = self._ensure_agent_runtime()
        runtime.start_training(config_path=self.agent_config_var.get() or None)
        self._set_agent_status("Training started ...")

    def _agent_stop_runtime(self) -> None:
        if self.agent_runtime:
            self.agent_runtime.stop()
            self._set_agent_status("Agent stopped.")

    def _agent_pick_checkpoint(self) -> None:
        self._open_file_dialog("Select checkpoint", callback=lambda path: self._set_agent_checkpoint(path))

    def _agent_pick_config(self) -> None:
        self._open_file_dialog("Select config", callback=lambda path: self._set_agent_config(path))

    def _set_agent_checkpoint(self, path: str | None) -> None:
        if path:
            self.agent_checkpoint_var.set(str(path))
            if self.agent_checkpoint_input and dpg.does_item_exist(self.agent_checkpoint_input):
                dpg.set_value(self.agent_checkpoint_input, str(path))

    def _set_agent_config(self, path: str | None) -> None:
        if path:
            self.agent_config_var.set(str(path))
            if self.agent_config_input and dpg.does_item_exist(self.agent_config_input):
                dpg.set_value(self.agent_config_input, str(path))

    def _set_agent_status(self, text: str) -> None:
        self.agent_status_var.set(text)
        if self.agent_status_text_tag and dpg.does_item_exist(self.agent_status_text_tag):
            dpg.set_value(self.agent_status_text_tag, text)

    def _append_agent_log(self, text: str) -> None:
        if not text:
            return
        self.agent_log_lines.append(text)
        # keep last 200 lines to avoid oversized widget
        self.agent_log_lines = self.agent_log_lines[-200:]
        if self.agent_log_tag and dpg.does_item_exist(self.agent_log_tag):
            dpg.set_value(self.agent_log_tag, "\n".join(self.agent_log_lines))

    def _start_agent_polling(self) -> None:
        if self.agent_polling:
            return
        self.agent_polling = True
        self.after(250, self._poll_agent_events)

    def _poll_agent_events(self) -> None:
        runtime = self.agent_runtime
        if runtime is not None:
            try:
                while not runtime.events.empty():
                    evt = runtime.events.get_nowait()
                    etype = evt.get("type")
                    if etype == "metrics":
                        metrics = evt.get("metrics", {})
                        msg = (
                            f"Mean reward {metrics.get('mean_reward', 0):.3f} "
                            f"(episodes={metrics.get('episodes', 0)})"
                        )
                        self._set_agent_status(msg)
                        self._append_agent_log(msg)
                    elif etype == "step":
                        reward_val = evt.get("reward", 0.0)
                        meta = evt.get("metadata", {})
                        self._append_agent_log(f"Step reward {reward_val:.3f} | meta {meta}")
                    elif etype == "log":
                        self._append_agent_log(str(evt.get("message", "")))
                    elif etype == "error":
                        self._append_agent_log(f"Error: {evt.get('message')}")
                        self._set_agent_status(f"Error: {evt.get('message')}")
                    elif etype == "done":
                        mode = evt.get("mode", "")
                        self._append_agent_log(f"{mode or 'run'} finished.")
                        self._set_agent_status(f"{mode or 'Agent'} finished.")
            except Exception:
                pass
        if self.agent_polling:
            self.after(300, self._poll_agent_events)


__all__ = ["PlayerEditorApp"]
