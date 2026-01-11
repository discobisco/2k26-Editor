"""
Built-in LM Studio / local AI integration for the modular editor.

This module adds an "AI Assistant" panel to the player detail view. When the
user selects a player and clicks "Ask AI", the assistant gathers the visible
player metadata and sends a prompt to the AI backend configured inside the
editor's AI Settings tab. The backend can be either a remote OpenAI-compatible
endpoint (such as the LM Studio local server) or a local command that accepts a
prompt on stdin and writes a response to stdout.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import urllib.error
import urllib.request
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, TYPE_CHECKING

from ..core.config import (
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    INPUT_TEXT_FG,
    PANEL_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from . import nba_data
if TYPE_CHECKING:
    from typing import Protocol

    class _PlayerProto(Protocol):
        record_index: int
        player_id: int

    class PlayerEditorApp(Protocol):
        selected_player: _PlayerProto | None
        player_detail_fields: Mapping[str, tk.Variable]
        filtered_player_indices: list[int]
        current_players: list[Any] | None
        player_listbox: tk.Listbox
        staff_listbox: tk.Listbox
        stadium_listbox: tk.Listbox
        team_var: tk.Variable
        team_edit_var: tk.Variable
        team_field_vars: Mapping[str, tk.Variable]
        ai_mode_var: tk.Variable
        player_search_var: tk.Variable
        player_name_var: tk.Variable
        player_ovr_var: tk.Variable
        var_first: tk.Variable
        var_last: tk.Variable
        var_player_team: tk.Variable
        model: Any
        home_frame: tk.Misc
        players_frame: tk.Misc
        teams_frame: tk.Misc | None
        staff_frame: tk.Misc | None
        stadium_frame: tk.Misc | None

        def after(self, delay_ms: int, callback: Callable, *args: Any) -> Any: ...

        def _refresh_player_list(self) -> Any: ...

        def _filter_player_list(self) -> Any: ...

        def _refresh_staff_list(self) -> Any: ...

        def _refresh_stadium_list(self) -> Any: ...

        def _save_player(self) -> Any: ...

        def _save_team(self) -> Any: ...

        def _on_team_edit_selected(self) -> Any: ...

        def show_home(self) -> Any: ...

        def show_players(self) -> Any: ...

        def show_teams(self) -> Any: ...

        def show_staff(self) -> Any: ...

        def show_stadium(self) -> Any: ...

        def show_excel(self) -> Any: ...

        def get_ai_settings(self) -> dict[str, Any]: ...

        def _open_full_editor(self) -> Any: ...

        def _open_full_staff_editor(self, staff_idx: int | None = None) -> Any: ...

        def _open_full_stadium_editor(self, stadium_idx: int | None = None) -> Any: ...

        def _open_copy_dialog(self) -> Any: ...

        def _open_randomizer(self) -> Any: ...

        def _open_team_shuffle(self) -> Any: ...

        def _open_batch_edit(self) -> Any: ...

        def _open_import_dialog(self) -> Any: ...

        def _open_export_dialog(self) -> Any: ...

        def _open_load_excel(self) -> Any: ...

        def _open_team_player_editor(self) -> Any: ...

        def winfo_children(self) -> list[tk.Misc]: ...

else:
    PlayerEditorApp = Any

class LLMControlBridge:
    """
    Lightweight HTTP bridge that lets an external LLM issue editor commands.

    Endpoints:
        * GET /state      -> snapshot of current UI state.
        * POST /command   -> execute an action. Payload: {"action": "...", ...}
    """

    def __init__(self, app: PlayerEditorApp, host: str = "127.0.0.1", port: int = 18711) -> None:
        self._app_ref = weakref.ref(app)
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._start_server()

    @property
    def app(self) -> PlayerEditorApp:
        app = self._app_ref()
        if app is None:
            raise RuntimeError("Editor instance is no longer available.")
        return app

    def _start_server(self) -> None:
        def handler_factory() -> type[BaseHTTPRequestHandler]:
            bridge = self

            class ControlHandler(BaseHTTPRequestHandler):
                def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                    body = json.dumps(payload).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)

                def do_OPTIONS(self) -> None:  # noqa: N802
                    self.send_response(204)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                    self.end_headers()

                def do_GET(self) -> None:  # noqa: N802
                    try:
                        if self.path.rstrip("/") == "/state":
                            data = bridge.describe_state()
                            self._send_json(200, {"success": True, "state": data})
                        elif self.path.rstrip("/") == "/players":
                            data = bridge.list_players()
                            self._send_json(200, {"success": True, "players": data})
                        else:
                            self._send_json(404, {"success": False, "error": "Unknown endpoint"})
                    except Exception as exc:  # noqa: BLE001
                        self._send_json(500, {"success": False, "error": str(exc)})

                def do_POST(self) -> None:  # noqa: N802
                    if self.path.rstrip("/") != "/command":
                        self._send_json(404, {"success": False, "error": "Unknown endpoint"})
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "0") or 0)
                    except ValueError:
                        length = 0
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8") or "{}")
                    except json.JSONDecodeError as exc:
                        self._send_json(400, {"success": False, "error": f"Invalid JSON: {exc}"})
                        return
                    try:
                        result = bridge.handle_command(payload)
                        self._send_json(200, {"success": True, "result": result})
                    except Exception as exc:  # noqa: BLE001
                        self._send_json(400, {"success": False, "error": str(exc)})

                def log_message(self, format: str, *args: Any) -> None:
                    return

            return ControlHandler

        Handler = handler_factory()
        try:
            server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            raise RuntimeError(f"Could not bind control bridge to {self.host}:{self.port} ({exc})") from exc
        self._server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="LLMControlBridge")
        self._thread = thread
        thread.start()

    def describe_state(self) -> dict[str, Any]:
        def gather() -> dict[str, Any]:
            app = self.app
            player = app.selected_player
            detail = {}
            for label, var in app.player_detail_fields.items():
                try:
                    detail[label] = var.get()
                except Exception:
                    detail[label] = ""
            state = {
                "team": app.team_var.get(),
                "selected_index": None,
                "selected_player": None,
                "detail_fields": detail,
                "ai_mode": app.ai_mode_var.get(),
                "search_term": app.player_search_var.get(),
                "players_count": len(app.current_players or []),
                "screen": self._detect_screen(),
            }
            selection = app.player_listbox.curselection()
            if selection:
                state["selected_index"] = int(selection[0])
            if player:
                state["selected_player"] = {
                    "name": app.player_name_var.get(),
                    "overall": app.player_ovr_var.get(),
                    "first_name": app.var_first.get(),
                    "last_name": app.var_last.get(),
                    "team": app.var_player_team.get(),
                    "record_index": getattr(player, "record_index", getattr(player, "index", None)),
                    "player_id": getattr(player, "player_id", getattr(player, "index", None)),
                }
            state["teams"] = list(app.model.get_teams())
            state["available_actions"] = self.available_actions()
            return state

        return self._run_on_ui_thread(gather)

    def list_players(self) -> list[dict[str, Any]]:
        def gather() -> list[dict[str, Any]]:
            app = self.app
            players: list[dict[str, Any]] = []
            if not hasattr(app, "player_listbox"):
                return players
            for idx in range(app.player_listbox.size()):
                name = app.player_listbox.get(idx)
                players.append(
                    {
                        "index": idx,
                        "name": name,
                        "filtered_index": app.filtered_player_indices[idx] if idx < len(app.filtered_player_indices) else None,
                    }
                )
            return players

        return self._run_on_ui_thread(gather)

    def handle_command(self, payload: dict[str, Any]) -> Any:
        action = str(payload.get("action", "")).strip().lower()
        if not action:
            raise ValueError("Missing 'action' value.")
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "describe_state": lambda _p: self.describe_state(),
            "list_players": lambda _p: self.list_players(),
            "list_teams": lambda _p: self.list_teams(),
            "get_team_state": self._cmd_get_team_state,
            "set_team_field": self._cmd_set_team_field,
            "set_team_fields": self._cmd_set_team_fields,
            "save_team": self._cmd_save_team,
            "list_actions": lambda _p: self.available_actions(),
            "select_player": self._cmd_select_player,
            "select_team": self._cmd_select_team,
            "select_staff": self._cmd_select_staff,
            "select_stadium": self._cmd_select_stadium,
            "set_name_fields": self._cmd_set_name_fields,
            "set_search_filter": self._cmd_set_search_filter,
            "save_player": self._cmd_save_player,
            "refresh_players": self._cmd_refresh_players,
            "show_screen": self._cmd_show_screen,
            "invoke_feature": self._cmd_invoke_feature,
            "open_full_editor": self._cmd_open_full_editor,
            "open_full_staff_editor": self._cmd_open_full_staff_editor,
            "open_full_stadium_editor": self._cmd_open_full_stadium_editor,
            "set_detail_field": self._cmd_set_detail_field,
            "list_full_fields": self._cmd_list_full_fields,
            "set_full_field": self._cmd_set_full_field,
            "save_full_editor": self._cmd_save_full_editor,
            "set_full_fields": self._cmd_set_full_fields,
            "get_full_editor_state": self._cmd_get_full_editor_state,
            "list_staff": lambda _p: self.list_staff(),
            "list_stadiums": lambda _p: self.list_stadiums(),
            "list_staff_fields": self._cmd_list_staff_fields,
            "list_stadium_fields": self._cmd_list_stadium_fields,
            "set_staff_field": self._cmd_set_staff_field,
            "set_staff_fields": self._cmd_set_staff_fields,
            "save_staff_editor": self._cmd_save_staff_editor,
            "get_staff_editor_state": self._cmd_get_staff_editor_state,
            "set_stadium_field": self._cmd_set_stadium_field,
            "set_stadium_fields": self._cmd_set_stadium_fields,
            "save_stadium_editor": self._cmd_save_stadium_editor,
            "get_stadium_editor_state": self._cmd_get_stadium_editor_state,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported action: {action}")
        return handler(payload)

    @staticmethod
    def feature_actions() -> dict[str, str]:
        return {
            "open_full_editor": "_open_full_editor",
            "open_full_staff_editor": "_open_full_staff_editor",
            "open_full_stadium_editor": "_open_full_stadium_editor",
            "open_copy_dialog": "_open_copy_dialog",
            "open_randomizer": "_open_randomizer",
            "open_team_shuffle": "_open_team_shuffle",
            "open_batch_edit": "_open_batch_edit",
            "open_import_dialog": "_open_import_dialog",
            "open_export_dialog": "_open_export_dialog",
            "open_load_excel": "_open_load_excel",
            "open_team_player_editor": "_open_team_player_editor",
        }

    def available_actions(self) -> dict[str, Any]:
        return {
            "commands": sorted(
                [
                    "describe_state",
                    "list_players",
                    "list_teams",
                    "list_staff",
                    "list_stadiums",
                    "get_team_state",
                    "list_actions",
                    "select_player",
                    "select_team",
                    "select_staff",
                    "select_stadium",
                    "set_name_fields",
                    "set_detail_field",
                    "set_search_filter",
                    "set_team_field",
                    "set_team_fields",
                    "save_team",
                    "list_full_fields",
                    "get_full_editor_state",
                    "set_full_field",
                    "set_full_fields",
                    "save_full_editor",
                    "list_staff_fields",
                    "set_staff_field",
                    "set_staff_fields",
                    "save_staff_editor",
                    "get_staff_editor_state",
                    "list_stadium_fields",
                    "set_stadium_field",
                    "set_stadium_fields",
                    "save_stadium_editor",
                    "get_stadium_editor_state",
                    "refresh_players",
                    "save_player",
                    "show_screen",
                    "invoke_feature",
                ]
            ),
            "features": sorted(self.feature_actions().keys()),
        }

    def _cmd_select_player(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "index" in payload:
            index = int(payload["index"])
            return self._run_on_ui_thread(lambda: self._select_player_index(index))
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Provide 'index' or 'name' to select a player.")
        return self._run_on_ui_thread(lambda: self._select_player_name(name))

    def _cmd_select_staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "index" not in payload:
            raise ValueError("Provide 'index' to select a staff member.")
        index = int(payload["index"])
        return self._run_on_ui_thread(lambda: self._select_staff_index(index))

    def _cmd_select_stadium(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "index" not in payload:
            raise ValueError("Provide 'index' to select a stadium.")
        index = int(payload["index"])
        return self._run_on_ui_thread(lambda: self._select_stadium_index(index))

    def _select_player_index(self, index: int) -> dict[str, Any]:
        app = self.app
        size = app.player_listbox.size()
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        app.player_listbox.selection_clear(0, tk.END)
        app.player_listbox.selection_set(index)
        app.player_listbox.activate(index)
        app.player_listbox.see(index)
        app.player_listbox.event_generate("<<ListboxSelect>>")
        return self._gather_selection_summary()

    def _select_staff_index(self, index: int) -> dict[str, Any]:
        app = self.app
        app.show_staff()
        app._refresh_staff_list()
        size = app.staff_listbox.size() if app.staff_listbox else 0
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        lb = app.staff_listbox
        if lb is None:
            raise RuntimeError("Staff listbox not initialized.")
        lb.selection_clear(0, tk.END)
        lb.selection_set(index)
        lb.activate(index)
        lb.see(index)
        lb.event_generate("<<ListboxSelect>>")
        return {"selected_index": index, "name": lb.get(index)}

    def _select_stadium_index(self, index: int) -> dict[str, Any]:
        app = self.app
        app.show_stadium()
        app._refresh_stadium_list()
        size = app.stadium_listbox.size() if app.stadium_listbox else 0
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        lb = app.stadium_listbox
        if lb is None:
            raise RuntimeError("Stadium listbox not initialized.")
        lb.selection_clear(0, tk.END)
        lb.selection_set(index)
        lb.activate(index)
        lb.see(index)
        lb.event_generate("<<ListboxSelect>>")
        return {"selected_index": index, "name": lb.get(index)}

    def _select_player_name(self, name: str) -> dict[str, Any]:
        app = self.app
        normalized = name.strip().lower()
        for idx in range(app.player_listbox.size()):
            if app.player_listbox.get(idx).strip().lower() == normalized:
                return self._select_player_index(idx)
        raise ValueError(f"Player named '{name}' not found in the current list.")

    def _cmd_set_name_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        first = payload.get("first_name")
        last = payload.get("last_name")
        if first is None and last is None:
            raise ValueError("Provide 'first_name' and/or 'last_name'.")

        def apply() -> dict[str, Any]:
            if first is not None:
                self.app.var_first.set(str(first))
            if last is not None:
                self.app.var_last.set(str(last))
            return self._gather_selection_summary()

        return self._run_on_ui_thread(apply)

    def _cmd_save_player(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_on_ui_thread(self._save_player_and_refresh)

    def _cmd_select_team(self, payload: dict[str, Any]) -> dict[str, Any]:
        team = str(payload.get("team", "")).strip()
        if not team:
            raise ValueError("Provide 'team' to select.")

        def apply() -> dict[str, Any]:
            if team not in self.app.model.get_teams():
                raise ValueError(f"Team '{team}' not found.")
            self.app.team_var.set(team)
            self.app._refresh_player_list()
            return {"team": self.app.team_var.get()}

        return self._run_on_ui_thread(apply)

    def _cmd_set_search_filter(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = str(payload.get("term", "")).strip()

        def apply() -> dict[str, Any]:
            self.app.player_search_var.set(term)
            self.app._filter_player_list()
            return {"term": self.app.player_search_var.get()}

        return self._run_on_ui_thread(apply)

    def _cmd_get_team_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def gather() -> dict[str, Any]:
            team_name = getattr(self.app, "team_edit_var", None)
            selected = team_name.get() if team_name is not None else None
            fields: dict[str, Any] = {}
            for label, var in getattr(self.app, "team_field_vars", {}).items():
                try:
                    fields[label] = var.get()
                except Exception:
                    fields[label] = ""
            return {
                "selected_team": selected,
                "fields": fields,
                "teams": list(self.app.model.get_teams()),
            }

        return self._run_on_ui_thread(gather)

    def _cmd_set_team_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        field = str(payload.get("field", "")).strip()
        if not field:
            raise ValueError("Provide 'field'.")
        value = payload.get("value", "")
        team_name = payload.get("team")

        def apply() -> dict[str, Any]:
            if team_name:
                try:
                    self.app.team_edit_var.set(str(team_name))
                    self.app._on_team_edit_selected()
                except Exception:
                    pass
            mapping = getattr(self.app, "team_field_vars", {})
            key = None
            for label in mapping.keys():
                if label.lower() == field.lower():
                    key = label
                    break
            if key is None:
                raise ValueError(f"Unknown team field '{field}'.")
            mapping[key].set(str(value))
            return {"team": self.app.team_edit_var.get(), "field": key, "value": mapping[key].get()}

        return self._run_on_ui_thread(apply)

    def _cmd_set_team_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates = payload.get("fields")
        if not isinstance(updates, list):
            raise ValueError("Provide 'fields' as a list of {field, value}.")
        team_name = payload.get("team")

        def apply() -> dict[str, Any]:
            if team_name:
                try:
                    self.app.team_edit_var.set(str(team_name))
                    self.app._on_team_edit_selected()
                except Exception:
                    pass
            mapping = getattr(self.app, "team_field_vars", {})
            changed = []
            errors = []
            for entry in updates:
                fname = str(entry.get("field", "")).strip()
                value = entry.get("value", "")
                key = None
                for label in mapping.keys():
                    if label.lower() == fname.lower():
                        key = label
                        break
                if key is None:
                    errors.append({"field": fname, "error": "Unknown field"})
                    continue
                try:
                    mapping[key].set(str(value))
                    changed.append({"field": key, "value": mapping[key].get()})
                except Exception as exc:  # noqa: BLE001
                    errors.append({"field": key, "error": str(exc)})
            return {"team": self.app.team_edit_var.get(), "updated": changed, "errors": errors}

        return self._run_on_ui_thread(apply)

    def _cmd_save_team(self, payload: dict[str, Any]) -> dict[str, Any]:
        team_name = payload.get("team")

        def save() -> dict[str, Any]:
            if team_name:
                try:
                    self.app.team_edit_var.set(str(team_name))
                    self.app._on_team_edit_selected()
                except Exception:
                    pass
            try:
                self.app._save_team()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Saving team failed: {exc}")
            return {"saved": True, "team": self.app.team_edit_var.get()}

        return self._run_on_ui_thread(save)

    def _cmd_refresh_players(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_on_ui_thread(
            lambda: (
                self.app._refresh_player_list(),
                {"players": len(self.app.current_players or [])},
            )[1]
        )

    def _cmd_show_screen(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = str(payload.get("screen", "")).strip().lower()
        if not target:
            raise ValueError("Provide 'screen': home, players, teams, staff, stadium, or excel.")

        def apply() -> dict[str, Any]:
            if target == "home":
                self.app.show_home()
            elif target == "players":
                self.app.show_players()
            elif target == "teams":
                self.app.show_teams()
            elif target == "staff":
                self.app.show_staff()
            elif target == "stadium":
                self.app.show_stadium()
            elif target == "excel":
                self.app.show_excel()
            else:
                raise ValueError(f"Unknown screen '{target}'.")
            return {"screen": target}

        return self._run_on_ui_thread(apply)

    def _cmd_invoke_feature(self, payload: dict[str, Any]) -> dict[str, Any]:
        feature = str(payload.get("feature", "")).strip().lower()
        if not feature:
            raise ValueError("Provide 'feature' to invoke.")
        mapping = {name: method for name, method in self.feature_actions().items()}
        method_name = mapping.get(feature)
        if not method_name:
            raise ValueError(f"Unsupported feature '{feature}'.")
        return self._run_on_ui_thread(lambda: self._invoke_app_method(method_name))

    def _cmd_open_full_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Open the full editor for the currently selected player or a provided index/name."""
        idx = payload.get("index")
        name = payload.get("name")

        def open_it() -> dict[str, Any]:
            if idx is not None:
                try:
                    self._select_player_index(int(idx))
                except Exception:
                    pass
            elif isinstance(name, str) and name.strip():
                try:
                    self._select_player_name(name)
                except Exception:
                    pass
            # Open the full editor for the current selection
            try:
                self.app._open_full_editor()
            except Exception as exc:
                raise RuntimeError(f"Failed to open full editor: {exc}")
            return {"opened": True}

        return self._run_on_ui_thread(open_it)

    def _cmd_open_full_staff_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        idx = payload.get("index")

        def open_it() -> dict[str, Any]:
            if idx is not None:
                try:
                    self._select_staff_index(int(idx))
                except Exception:
                    pass
            try:
                self.app._open_full_staff_editor(idx if idx is not None else None)
            except Exception as exc:
                raise RuntimeError(f"Failed to open staff editor: {exc}")
            return {"opened": True}

        return self._run_on_ui_thread(open_it)

    def _cmd_open_full_stadium_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        idx = payload.get("index")

        def open_it() -> dict[str, Any]:
            if idx is not None:
                try:
                    self._select_stadium_index(int(idx))
                except Exception:
                    pass
            try:
                self.app._open_full_stadium_editor(idx if idx is not None else None)
            except Exception as exc:
                raise RuntimeError(f"Failed to open stadium editor: {exc}")
            return {"opened": True}

        return self._run_on_ui_thread(open_it)

    def _invoke_app_method(self, method_name: str) -> dict[str, Any]:
        method = getattr(self.app, method_name, None)
        if method is None:
            raise ValueError(f"Method '{method_name}' not found on editor.")
        result = method()
        return {"invoked": method_name, "result": result}

    def _cmd_set_detail_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        field = str(payload.get("field", "")).strip()
        if not field:
            raise ValueError("Provide 'field' name.")
        value = payload.get("value", "")

        def apply() -> dict[str, Any]:
            vars_map = self.app.player_detail_fields
            key = None
            for label in vars_map.keys():
                if label.lower() == field.lower():
                    key = label
                    break
            if key is None:
                raise ValueError(f"Unknown detail field '{field}'.")
            vars_map[key].set(str(value))
            return {key: vars_map[key].get()}

        return self._run_on_ui_thread(apply)

    def list_teams(self) -> list[str]:
        return self._run_on_ui_thread(lambda: list(self.app.model.get_teams()))

    def list_staff(self) -> list[str]:
        return self._run_on_ui_thread(lambda: list(self.app.model.get_staff()))

    def list_stadiums(self) -> list[str]:
        return self._run_on_ui_thread(lambda: list(self.app.model.get_stadiums()))

    def _save_player_and_refresh(self) -> dict[str, Any]:
        app = self.app
        app._save_player()
        return self._gather_selection_summary()

    def _gather_selection_summary(self) -> dict[str, Any]:
        app = self.app
        player = app.selected_player
        info: dict[str, Any] = {
            "selected_index": None,
            "player": None,
        }
        selection = app.player_listbox.curselection()
        if selection:
            info["selected_index"] = int(selection[0])
        if player:
            info["player"] = {
                "name": app.player_name_var.get(),
                "first_name": app.var_first.get(),
                "last_name": app.var_last.get(),
                "overall": app.player_ovr_var.get(),
                "team": app.var_player_team.get(),
                "player_id": getattr(player, "player_id", getattr(player, "index", None)),
                "record_index": getattr(player, "record_index", getattr(player, "index", None)),
            }
        return info

    # ------------------------------------------------------------------ #
    # Full Player Editor helpers
    # ------------------------------------------------------------------ #
    def _find_open_full_editor(self) -> Any:
        """Return the first open FullPlayerEditor-like Toplevel or None.
        Implemented as a direct scan of `self.app.winfo_children()` and **must be
        called from the UI thread** (e.g. from inside `_run_on_ui_thread`).
        """
        app = self.app
        for child in app.winfo_children():
            try:
                if hasattr(child, "player") and hasattr(child, "_save_all"):
                    return child
            except Exception:
                continue
        return None

    def _find_open_staff_editor(self) -> Any:
        app = self.app
        for child in app.winfo_children():
            try:
                if getattr(child, "_editor_type", "") == "staff" and hasattr(child, "_save_all"):
                    return child
            except Exception:
                continue
        return None

    def _find_open_stadium_editor(self) -> Any:
        app = self.app
        for child in app.winfo_children():
            try:
                if getattr(child, "_editor_type", "") == "stadium" and hasattr(child, "_save_all"):
                    return child
            except Exception:
                continue
        return None

    def _cmd_list_full_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def list_fields() -> dict[str, Any]:
            editor = self._find_open_full_editor()
            if editor is None:
                return {"open": False, "fields": {}}
            p = getattr(editor, "player", None)
            player_info = {"index": getattr(p, "index", None), "full_name": getattr(p, "full_name", None)} if p is not None else None
            result = {"open": True, "player": player_info, "fields": {}}
            for cat, mapping in editor.field_vars.items():
                fields = []
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    fields.append({
                        "name": fname,
                        "value": (var.get() if hasattr(var, "get") else None),
                        "offset": getattr(meta, "offset", None) if meta else None,
                        "length": getattr(meta, "length", None) if meta else None,
                        "values": getattr(meta, "values", None) if meta else None,
                    })
                result["fields"][cat] = fields
            return result

        return self._run_on_ui_thread(list_fields)

    def _cmd_set_full_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category", "")).strip()
        field = str(payload.get("field", "")).strip()
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_full_field")
        value = payload.get("value")

        player_index = payload.get("player_index")

        def set_field() -> dict[str, Any]:
            return self._set_full_field_on_ui(category, field, value, player_index)

        return self._run_on_ui_thread(set_field)

    def _set_full_field_on_ui(
        self,
        category: str,
        field: str,
        value: Any,
        player_index: int | None = None,
    ) -> dict[str, Any]:
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_full_field")
        # If a player index was provided, ensure the right player is selected
        if player_index is not None:
            try:
                self._select_player_index(int(player_index))
            except Exception:
                pass
        editor = self._find_open_full_editor()
        if editor is None:
            # Try opening one (current selection)
            try:
                self.app._open_full_editor()
            except Exception:
                pass
            editor = self._find_open_full_editor()
            if editor is None:
                raise RuntimeError("No open full editor found and unable to open one.")
        # find category
        cat_key = None
        for cat in editor.field_vars.keys():
            if cat.strip().lower() == category.lower():
                cat_key = cat
                break
        if cat_key is None:
            raise ValueError(f"Unknown category '{category}'")
        # find field
        fname_key = None
        for fname in editor.field_vars[cat_key].keys():
            if fname.strip().lower() == field.lower():
                fname_key = fname
                break
        if fname_key is None:
            raise ValueError(f"Unknown field '{field}' in category '{cat_key}'")
        var = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        # Enumerations
        if meta and getattr(meta, "values", None):
            vals = list(meta.values)
            if isinstance(value, str):
                idx = None
                for i, v in enumerate(vals):
                    if str(v).strip().lower() == value.strip().lower():
                        idx = i
                        break
                if idx is None:
                    raise ValueError(f"Unknown enumerated value '{value}' for field '{fname_key}'")
            else:
                if value is None:
                    raise ValueError(f"Value for '{fname_key}' is required.")
                idx = int(value)
            try:
                var.set(int(idx))
            except Exception:
                pass
            widget = getattr(meta, "widget", None)
            if widget is not None and hasattr(widget, "set"):
                try:
                    widget.set(vals[idx])
                except Exception:
                    pass
        else:
            try:
                if hasattr(var, "set"):
                    var.set(value)
                else:
                    setattr(editor, fname_key, value)
            except Exception as exc:
                raise RuntimeError(f"Failed to set field: {exc}")
        return {"category": cat_key, "field": fname_key, "value": (var.get() if hasattr(var, "get") else None)}

    def _cmd_save_full_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        close_after = bool(payload.get("close_after", False))

        player_index = payload.get("player_index")

        def save() -> dict[str, Any]:
            if player_index is not None:
                try:
                    self._select_player_index(int(player_index))
                except Exception:
                    pass
            editor = self._find_open_full_editor()
            if editor is None:
                raise RuntimeError("No open FullPlayerEditor to save.")
            try:
                editor._save_all()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Saving failed: {exc}")
            if close_after:
                try:
                    editor.destroy()
                except Exception:
                    pass
            return {"saved": True}

        return self._run_on_ui_thread(save)

    def _cmd_set_full_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Set multiple fields at once. Payload contains: fields: [{category, field, value}] and optional player_index."""
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise ValueError("Provide 'fields' as a list of {category, field, value} dicts.")
        player_index = payload.get("player_index")

        def set_many() -> dict[str, Any]:
            if player_index is not None:
                try:
                    self._select_player_index(int(player_index))
                except Exception:
                    pass
            updated = []
            errors = []
            for entry in fields:
                try:
                    cat = str(entry.get("category", "")).strip()
                    fname = str(entry.get("field", "")).strip()
                    self._set_full_field_on_ui(cat, fname, entry.get("value"))
                    updated.append({"category": entry.get("category"), "field": entry.get("field")})
                except Exception as exc:  # noqa: BLE001
                    errors.append({"field": entry.get("field"), "error": str(exc)})
            return {"updated": updated, "errors": errors}

        return self._run_on_ui_thread(set_many)

    def _cmd_get_full_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def state() -> dict[str, Any]:
            editor = self._find_open_full_editor()
            if editor is None:
                return {"open": False, "categories": {}}
            p = getattr(editor, "player", None)
            player_info = {"index": getattr(p, "index", None), "full_name": getattr(p, "full_name", None)} if p is not None else None
            data = {"open": True, "player": player_info, "categories": {}}
            for cat, mapping in editor.field_vars.items():
                data["categories"][cat] = {}
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    data["categories"][cat][fname] = {
                        "value": (var.get() if hasattr(var, "get") else None),
                        "offset": getattr(meta, "offset", None) if meta is not None else None,
                        "length": getattr(meta, "length", None) if meta is not None else None,
                        "values": getattr(meta, "values", None) if meta is not None else None,
                    }
            return data

        return self._run_on_ui_thread(state)

    # ---------------- Staff editor helpers ---------------- #
    def _cmd_list_staff_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def list_fields() -> dict[str, Any]:
            editor = self._find_open_staff_editor()
            if editor is None:
                return {"open": False, "fields": {}}
            result = {"open": True, "fields": {}}
            for cat, mapping in editor.field_vars.items():
                fields = []
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    fields.append(
                        {
                            "name": fname,
                            "value": (var.get() if hasattr(var, "get") else None),
                            "offset": getattr(meta, "offset", None) if meta else None,
                            "length": getattr(meta, "length", None) if meta else None,
                            "values": getattr(meta, "values", None) if meta else None,
                        }
                    )
                result["fields"][cat] = fields
            return result

        return self._run_on_ui_thread(list_fields)

    def _cmd_set_staff_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category", "")).strip()
        field = str(payload.get("field", "")).strip()
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_staff_field")
        value = payload.get("value")
        staff_index = payload.get("staff_index")

        def set_field() -> dict[str, Any]:
            return self._set_staff_field_on_ui(category, field, value, staff_index)

        return self._run_on_ui_thread(set_field)

    def _set_staff_field_on_ui(
        self,
        category: str,
        field: str,
        value: Any,
        staff_index: int | None = None,
    ) -> dict[str, Any]:
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_staff_field")
        if staff_index is not None:
            try:
                self._select_staff_index(int(staff_index))
            except Exception:
                pass
        editor = self._find_open_staff_editor()
        if editor is None:
            try:
                self.app._open_full_staff_editor(staff_index if staff_index is not None else None)
            except Exception:
                pass
            editor = self._find_open_staff_editor()
            if editor is None:
                raise RuntimeError("No open staff editor found and unable to open one.")
        cat_key = None
        for cat in editor.field_vars.keys():
            if cat.strip().lower() == category.lower():
                cat_key = cat
                break
        if cat_key is None:
            raise ValueError(f"Unknown category '{category}'")
        fname_key = None
        for fname in editor.field_vars[cat_key].keys():
            if fname.strip().lower() == field.lower():
                fname_key = fname
                break
        if fname_key is None:
            raise ValueError(f"Unknown field '{field}' in category '{cat_key}'")
        var = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        if meta and getattr(meta, "values", None):
            vals = list(meta.values)
            if isinstance(value, str):
                idx = None
                for i, v in enumerate(vals):
                    if str(v).strip().lower() == value.strip().lower():
                        idx = i
                        break
                if idx is None:
                    raise ValueError(f"Unknown enumerated value '{value}' for field '{fname_key}'")
            else:
                if value is None:
                    raise ValueError(f"Value for '{fname_key}' is required.")
                idx = int(value)
            try:
                var.set(int(idx))
            except Exception:
                pass
            widget = getattr(meta, "widget", None)
            if widget is not None and hasattr(widget, "set"):
                try:
                    widget.set(vals[idx])
                except Exception:
                    pass
        else:
            try:
                if hasattr(var, "set"):
                    var.set(value)
                else:
                    setattr(editor, fname_key, value)
            except Exception as exc:
                raise RuntimeError(f"Failed to set field: {exc}")
        return {"category": cat_key, "field": fname_key, "value": (var.get() if hasattr(var, "get") else None)}

    def _cmd_set_staff_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise ValueError("Provide 'fields' as a list of {category, field, value} dicts.")
        staff_index = payload.get("staff_index")

        def set_many() -> dict[str, Any]:
            if staff_index is not None:
                try:
                    self._select_staff_index(int(staff_index))
                except Exception:
                    pass
            editor = self._find_open_staff_editor()
            if editor is None:
                try:
                    self.app._open_full_staff_editor(staff_index if staff_index is not None else None)
                except Exception:
                    pass
                editor = self._find_open_staff_editor()
                if editor is None:
                    raise RuntimeError("No open staff editor found and unable to open one.")
            updated = []
            errors = []
            for entry in fields:
                try:
                    cat = str(entry.get("category", "")).strip()
                    fname = str(entry.get("field", "")).strip()
                    self._set_staff_field_on_ui(cat, fname, entry.get("value"))
                    updated.append({"category": entry.get("category"), "field": entry.get("field")})
                except Exception as exc:
                    errors.append({"field": entry.get("field"), "error": str(exc)})
            return {"updated": updated, "errors": errors}

        return self._run_on_ui_thread(set_many)

    def _cmd_save_staff_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        close_after = bool(payload.get("close_after", False))

        def save() -> dict[str, Any]:
            editor = self._find_open_staff_editor()
            if editor is None:
                raise RuntimeError("No open Staff editor to save.")
            try:
                editor._save_all()
            except Exception as exc:
                raise RuntimeError(f"Saving failed: {exc}")
            if close_after:
                try:
                    editor.destroy()
                except Exception:
                    pass
            return {"saved": True}

        return self._run_on_ui_thread(save)

    def _cmd_get_staff_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def state() -> dict[str, Any]:
            editor = self._find_open_staff_editor()
            if editor is None:
                return {"open": False, "categories": {}}
            data = {"open": True, "categories": {}}
            for cat, mapping in editor.field_vars.items():
                data["categories"][cat] = {}
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    data["categories"][cat][fname] = {
                        "value": (var.get() if hasattr(var, "get") else None),
                        "offset": getattr(meta, "offset", None) if meta is not None else None,
                        "length": getattr(meta, "length", None) if meta is not None else None,
                        "values": getattr(meta, "values", None) if meta is not None else None,
                    }
            return data

        return self._run_on_ui_thread(state)

    # ---------------- Stadium editor helpers ---------------- #
    def _cmd_list_stadium_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def list_fields() -> dict[str, Any]:
            editor = self._find_open_stadium_editor()
            if editor is None:
                return {"open": False, "fields": {}}
            result = {"open": True, "fields": {}}
            for cat, mapping in editor.field_vars.items():
                fields = []
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    fields.append(
                        {
                            "name": fname,
                            "value": (var.get() if hasattr(var, "get") else None),
                            "offset": getattr(meta, "offset", None) if meta else None,
                            "length": getattr(meta, "length", None) if meta else None,
                            "values": getattr(meta, "values", None) if meta else None,
                        }
                    )
                result["fields"][cat] = fields
            return result

        return self._run_on_ui_thread(list_fields)

    def _cmd_set_stadium_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category", "")).strip()
        field = str(payload.get("field", "")).strip()
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_stadium_field")
        value = payload.get("value")
        stadium_index = payload.get("stadium_index")

        def set_field() -> dict[str, Any]:
            return self._set_stadium_field_on_ui(category, field, value, stadium_index)

        return self._run_on_ui_thread(set_field)

    def _set_stadium_field_on_ui(
        self,
        category: str,
        field: str,
        value: Any,
        stadium_index: int | None = None,
    ) -> dict[str, Any]:
        if not category or not field:
            raise ValueError("Provide 'category' and 'field' for set_stadium_field")
        if stadium_index is not None:
            try:
                self._select_stadium_index(int(stadium_index))
            except Exception:
                pass
        editor = self._find_open_stadium_editor()
        if editor is None:
            try:
                self.app._open_full_stadium_editor(stadium_index if stadium_index is not None else None)
            except Exception:
                pass
            editor = self._find_open_stadium_editor()
            if editor is None:
                raise RuntimeError("No open stadium editor found and unable to open one.")
        cat_key = None
        for cat in editor.field_vars.keys():
            if cat.strip().lower() == category.lower():
                cat_key = cat
                break
        if cat_key is None:
            raise ValueError(f"Unknown category '{category}'")
        fname_key = None
        for fname in editor.field_vars[cat_key].keys():
            if fname.strip().lower() == field.lower():
                fname_key = fname
                break
        if fname_key is None:
            raise ValueError(f"Unknown field '{field}' in category '{cat_key}'")
        var = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        if meta and getattr(meta, "values", None):
            vals = list(meta.values)
            if isinstance(value, str):
                idx = None
                for i, v in enumerate(vals):
                    if str(v).strip().lower() == value.strip().lower():
                        idx = i
                        break
                if idx is None:
                    raise ValueError(f"Unknown enumerated value '{value}' for field '{fname_key}'")
            else:
                if value is None:
                    raise ValueError(f"Value for '{fname_key}' is required.")
                idx = int(value)
            try:
                var.set(int(idx))
            except Exception:
                pass
            widget = getattr(meta, "widget", None)
            if widget is not None and hasattr(widget, "set"):
                try:
                    widget.set(vals[idx])
                except Exception:
                    pass
        else:
            try:
                if hasattr(var, "set"):
                    var.set(value)
                else:
                    setattr(editor, fname_key, value)
            except Exception as exc:
                raise RuntimeError(f"Failed to set field: {exc}")
        return {"category": cat_key, "field": fname_key, "value": (var.get() if hasattr(var, "get") else None)}

    def _cmd_set_stadium_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise ValueError("Provide 'fields' as a list of {category, field, value} dicts.")
        stadium_index = payload.get("stadium_index")

        def set_many() -> dict[str, Any]:
            if stadium_index is not None:
                try:
                    self._select_stadium_index(int(stadium_index))
                except Exception:
                    pass
            editor = self._find_open_stadium_editor()
            if editor is None:
                try:
                    self.app._open_full_stadium_editor(stadium_index if stadium_index is not None else None)
                except Exception:
                    pass
                editor = self._find_open_stadium_editor()
                if editor is None:
                    raise RuntimeError("No open stadium editor found and unable to open one.")
            updated = []
            errors = []
            for entry in fields:
                try:
                    cat = str(entry.get("category", "")).strip()
                    fname = str(entry.get("field", "")).strip()
                    self._set_stadium_field_on_ui(cat, fname, entry.get("value"))
                    updated.append({"category": entry.get("category"), "field": entry.get("field")})
                except Exception as exc:
                    errors.append({"field": entry.get("field"), "error": str(exc)})
            return {"updated": updated, "errors": errors}

        return self._run_on_ui_thread(set_many)

    def _cmd_save_stadium_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        close_after = bool(payload.get("close_after", False))

        def save() -> dict[str, Any]:
            editor = self._find_open_stadium_editor()
            if editor is None:
                raise RuntimeError("No open Stadium editor to save.")
            try:
                editor._save_all()
            except Exception as exc:
                raise RuntimeError(f"Saving failed: {exc}")
            if close_after:
                try:
                    editor.destroy()
                except Exception:
                    pass
            return {"saved": True}

        return self._run_on_ui_thread(save)

    def _cmd_get_stadium_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def state() -> dict[str, Any]:
            editor = self._find_open_stadium_editor()
            if editor is None:
                return {"open": False, "categories": {}}
            data = {"open": True, "categories": {}}
            for cat, mapping in editor.field_vars.items():
                data["categories"][cat] = {}
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    data["categories"][cat][fname] = {
                        "value": (var.get() if hasattr(var, "get") else None),
                        "offset": getattr(meta, "offset", None) if meta is not None else None,
                        "length": getattr(meta, "length", None) if meta is not None else None,
                        "values": getattr(meta, "values", None) if meta is not None else None,
                    }
            return data

        return self._run_on_ui_thread(state)

    def _run_on_ui_thread(self, func: Callable[[], Any], timeout: float = 5.0) -> Any:
        result: dict[str, Any] = {}
        event = threading.Event()

        def wrapper() -> None:
            try:
                result["value"] = func()
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc
            finally:
                event.set()

        self.app.after(0, wrapper)
        if not event.wait(timeout):
            raise RuntimeError("Timed out waiting for editor UI thread.")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def server_address(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _detect_screen(self) -> str:
        app = self.app
        try:
            if app.home_frame.winfo_ismapped():
                return "home"
            if app.players_frame.winfo_ismapped():
                return "players"
            teams_frame = getattr(app, "teams_frame", None)
            if teams_frame is not None and teams_frame.winfo_ismapped():
                return "teams"
        except Exception:
            pass
        return "unknown"


CONTROL_BRIDGE: LLMControlBridge | None = None


def ensure_control_bridge(app: PlayerEditorApp) -> LLMControlBridge:
    """Instantiate the HTTP bridge once."""
    global CONTROL_BRIDGE
    if CONTROL_BRIDGE is not None:
        return CONTROL_BRIDGE
    host = os.environ.get("NBA2K26_AI_HOST", "127.0.0.1")
    port_text = os.environ.get("NBA2K26_AI_PORT", "18711")
    try:
        port = int(port_text)
    except ValueError:
        port = 18711
    bridge = LLMControlBridge(app, host=host, port=port)
    CONTROL_BRIDGE = bridge
    return bridge

class PlayerAIAssistant:
    """UI helper that wires player data into an AI backend."""

    def __init__(self, app: PlayerEditorApp, context: dict[str, Any]) -> None:
        self.app = app
        self.context = context
        parent_obj = context.get("panel_parent")
        parent: tk.Widget | None = parent_obj if isinstance(parent_obj, tk.Widget) else None
        if parent is None:
            return
        self.prompt_var = tk.StringVar(
            value="Provide scouting notes and suggested attribute tweaks."
        )
        self.status_var = tk.StringVar(value="Select a player and click Ask AI.")
        nba_data.warm_cache_async()
        self._worker: threading.Thread | None = None
        self._build_panel(parent)
        try:
            bridge = ensure_control_bridge(app)
            self.status_var.set(f"AI Assistant ready. Control bridge at {bridge.server_address()}")
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Control bridge unavailable: {exc}")

    def _build_panel(self, parent: tk.Widget) -> None:
        frame = tk.LabelFrame(
            parent,
            text="AI Assistant",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            labelanchor="n",
        )
        frame.pack(fill=tk.BOTH, expand=False, padx=24, pady=(10, 0))
        self.frame = frame
        # Persona selector (optional)
        persona_row = tk.Frame(frame, bg=PANEL_BG)
        persona_row.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Label(
            persona_row,
            text="Persona",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        # Combobox shows human-friendly labels; we map them to internal values
        self._persona_display_map: dict[str, str] = {}
        self.persona_combobox = ttk.Combobox(persona_row, values=[], state="readonly")
        self.persona_combobox.pack(fill=tk.X, pady=(2, 0))

        def _on_persona_select(evt=None) -> None:
            try:
                sel_display = self.persona_combobox.get()
                sel_val = self._persona_display_map.get(sel_display, "none")
                try:
                    self.app.ai_persona_choice_var.set(sel_val)
                except Exception:
                    pass
            except Exception:
                pass

        self.persona_combobox.bind("<<ComboboxSelected>>", _on_persona_select)
        # Initialize available choices
        try:
            items = self.app.get_persona_choice_items()
            displays = [lab for lab, val in items]
            self._persona_display_map = {lab: val for lab, val in items}
            self.persona_combobox.configure(values=displays)
            # Set initial selection display from the current ai_persona_choice_var
            try:
                cur = self.app.ai_persona_choice_var.get() or "none"
                inv_map = {v: k for k, v in self._persona_display_map.items()}
                if cur in inv_map:
                    self.persona_combobox.set(inv_map[cur])
            except Exception:
                pass
        except Exception:
            pass

        prompt_row = tk.Frame(frame, bg=PANEL_BG)
        prompt_row.pack(fill=tk.X, padx=8, pady=(4, 4))
        tk.Label(
            prompt_row,
            text="Request",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        self.prompt_entry = tk.Entry(
            prompt_row,
            textvariable=self.prompt_var,
            bg="white",
            fg="#0B0B0B",
            relief=tk.FLAT,
        )
        self.prompt_entry.pack(fill=tk.X, pady=(2, 0))
        btn_bar = tk.Frame(frame, bg=PANEL_BG)
        btn_bar.pack(fill=tk.X, padx=8, pady=(6, 4))
        self.ask_button = tk.Button(
            btn_bar,
            text="Ask AI",
            command=self._on_request,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.ask_button.pack(side=tk.LEFT)
        tk.Button(
            btn_bar,
            text="Copy Response",
            command=self._copy_response,
            bg="#3C6E71",
            fg="white",
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.status_label = tk.Label(
            frame,
            textvariable=self.status_var,
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            wraplength=340,
            justify="left",
            font=("Segoe UI", 9, "italic"),
        )
        self.status_label.pack(fill=tk.X, padx=8, pady=(0, 6))
        # Progress indicator for long-running requests
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=200)
        self.progress.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.progress.stop()
        self.progress.configure(mode="indeterminate")

    def _refresh_persona_dropdown(self) -> None:
        try:
            items = self.app.get_persona_choice_items()
            displays = [lab for lab, val in items]
            self._persona_display_map = {lab: val for lab, val in items}
            self.persona_combobox.configure(values=displays)
            # attempt to keep current selection if still present
            try:
                cur = self.app.ai_persona_choice_var.get() or "none"
                inv_map = {v: k for k, v in self._persona_display_map.items()}
                if cur in inv_map:
                    self.persona_combobox.set(inv_map[cur])
                else:
                    # reset to 'None'
                    self.persona_combobox.set("None")
                    self.app.ai_persona_choice_var.set("none")
            except Exception:
                pass
        except Exception:
            pass

        self.output_text = tk.Text(
            frame,
            height=8,
            bg="white",
            fg="#0B0B0B",
            wrap="word",
            relief=tk.FLAT,
            state="disabled",
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 10))

    def _copy_response(self) -> None:
        try:
            text = self.output_text.get("1.0", tk.END).strip()
        except Exception:
            text = ""
        if not text:
            self.status_var.set("No response to copy yet.")
            return
        self.output_text.clipboard_clear()
        self.output_text.clipboard_append(text)
        self.status_var.set("Copied response to clipboard.")

    def _on_request(self) -> None:
        if self._worker and self._worker.is_alive():
            self.status_var.set("Hold on, the AI is still processing.")
            return
        prompt = self._build_prompt()
        if not prompt:
            self.status_var.set("Select a player first.")
            return
        self.status_var.set("Contacting AI backend ...")
        self._set_output("Thinking ...")
        self._start_progress()
        self._worker = threading.Thread(target=self._run_ai, args=(prompt,), daemon=True)
        self._worker.start()

    def _run_ai(self, prompt: str) -> None:
        settings = self.app.get_ai_settings()
        # Determine persona selection from the app and resolve to persona text
        selection = None
        try:
            selection = getattr(self.app, "ai_persona_choice_var", tk.StringVar()).get()
        except Exception:
            selection = None
        try:
            from .personas import get_persona_text
        except Exception:
            persona_text = ""
        else:
            persona_text = get_persona_text(settings, selection)

        mode = str(settings.get("mode", "none"))
        # If using local python backend, prefix persona into the prompt and stream
        if mode == "local" and str(settings.get("local", {}).get("backend", "cli")).strip().lower() == "python":
            local = settings.get("local") or {}
            backend = str(local.get("python_backend", "")).strip().lower()
            model_path = str(local.get("model_path", "")).strip()
            max_tokens = int(local.get("max_tokens", 256))
            temperature = float(local.get("temperature", 0.4))

            def _on_update(text: str, done: bool, error: Exception | None) -> None:
                if error:
                    self.frame.after(0, lambda: self._finalize_request(f"AI error: {error}", False))
                    return
                if done:
                    self.frame.after(0, lambda: self._finalize_request(text or "(AI backend returned no content.)", True))
                else:
                    self.frame.after(0, lambda t=text: self._append_output(t))

            try:
                from .backend_helpers import generate_text_async
            except Exception:
                # Fallback to existing sync path
                full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
                try:
                    response = invoke_ai_backend(settings, full_prompt)
                except Exception as exc:  # noqa: BLE001
                    self.frame.after(0, lambda: self._finalize_request(f"AI error: {exc}", False))
                    return
                self.frame.after(0, lambda: self._finalize_request(response or "(AI backend returned no content.)", True))
                return

            # Kick off async generator (persona prefixed to prompt)
            full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
            generate_text_async(backend, model_path, full_prompt, max_tokens=max_tokens, temperature=temperature, on_update=_on_update)
            return

        # Remote mode needs persona passed to remote API as system message
        if mode == "remote":
            try:
                response = invoke_ai_backend(settings, prompt, persona=(persona_text or None))
            except Exception as exc:  # noqa: BLE001
                message = f"AI error: {exc}"
                success = False
            else:
                message = response or "(AI backend returned no content.)"
                success = True
            self.frame.after(0, lambda: self._finalize_request(message, success))
            return

        # CLI/local (non-python) backends: prefix persona into prompt and call
        full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
        try:
            response = invoke_ai_backend(settings, full_prompt)
        except Exception as exc:  # noqa: BLE001
            message = f"AI error: {exc}"
            success = False
        else:
            message = response or "(AI backend returned no content.)"
            success = True
        self.frame.after(0, lambda: self._finalize_request(message, success))

    def _finalize_request(self, message: str, success: bool) -> None:
        self._stop_progress()
        self._set_output(message)
        if success:
            self.status_var.set("AI response received.")
        else:
            self.status_var.set(message)

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text.strip())
        self.output_text.configure(state="disabled")

    def _start_progress(self) -> None:
        try:
            self.progress.start(50)
            self.status_var.set("AI thinking...")
        except Exception:
            pass

    def _stop_progress(self) -> None:
        try:
            self.progress.stop()
        except Exception:
            pass
    def _append_output(self, text: str, *, replace_placeholder: bool = True) -> None:
        """Append incremental text to the output box.

        If the current content equals the placeholder text "Thinking ...", it will
        be replaced on the first append so we don't show the placeholder and the
        first token together.
        """
        try:
            self.output_text.configure(state="normal")
            current = self.output_text.get("1.0", tk.END)
            if replace_placeholder and current.strip() == "Thinking ...":
                self.output_text.delete("1.0", tk.END)
            self.output_text.insert(tk.END, text)
            self.output_text.configure(state="disabled")
        except Exception:
            try:
                self.output_text.configure(state="disabled")
            except Exception:
                pass

    def _build_prompt(self) -> str:
        first_entry_obj = self.context.get("first_name_entry")
        last_entry_obj = self.context.get("last_name_entry")
        first_entry: tk.Entry | None = first_entry_obj if isinstance(first_entry_obj, tk.Entry) else None
        last_entry: tk.Entry | None = last_entry_obj if isinstance(last_entry_obj, tk.Entry) else None
        detail_vars_obj = self.context.get("detail_vars", {})
        detail_vars: dict[str, tk.StringVar] = detail_vars_obj if isinstance(detail_vars_obj, dict) else {}
        name = self.app.player_name_var.get().strip()
        ovr = self.app.player_ovr_var.get().strip()
        first = first_entry.get().strip() if first_entry is not None else ""
        last = last_entry.get().strip() if last_entry is not None else ""
        team = ""
        try:
            team = self.app.var_player_team.get().strip()
        except Exception:
            team = ""
        pieces = [
            f"Displayed name: {name}",
            f"First name entry: {first or 'N/A'}",
            f"Last name entry: {last or 'N/A'}",
            f"Team: {team or 'N/A'}",
            f"Overall rating label: {ovr}",
        ]
        for label, var in detail_vars.items():
            try:
                pieces.append(f"{label}: {var.get()}")
            except Exception:
                continue
        lookup_names = [f"{first} {last}".strip(), name]
        summary = nba_data.get_player_summary([n for n in lookup_names if n])
        if summary:
            pieces.append(f"NBA reference: {summary}")
        else:
            error = nba_data.last_error()
            if error:
                pass
        request_text = self.prompt_var.get().strip() or "Provide a scouting report."
        return (
            "You are assisting with NBA 2K roster editing. "
            "Use the provided player data to answer the user's request. "
            "Keep responses concise and actionable.\n\n"
            "Player data:\n- "
            + "\n- ".join(pieces)
            + "\n\nUser request:\n"
            + request_text
        )


def build_local_command(local_settings: dict[str, Any]) -> tuple[list[str], Path | None]:
    """Return the command list and working directory for a local AI invocation."""
    command = str(local_settings.get("command", "")).strip()
    if not command:
        raise RuntimeError("Local AI command is not configured.")
    cmd: list[str] = [command]
    args_text = str(local_settings.get("arguments", "")).strip()
    if args_text:
        cmd.extend(shlex.split(args_text, posix=False))
    workdir_text = str(local_settings.get("working_dir", "")).strip()
    workdir = Path(workdir_text).expanduser() if workdir_text else None
    return cmd, workdir


def call_local_process(local_settings: dict[str, Any], prompt: str) -> str:
    """Invoke a local CLI that reads the prompt from stdin."""
    cmd, workdir = build_local_command(local_settings)
    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            cwd=workdir,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(stderr or f"Local AI process exited with {completed.returncode}.")
    output = (completed.stdout or "").strip()
    if not output:
        raise RuntimeError("Local AI process returned no output.")
    return output


# In-process Python backend instances cache
_PYTHON_BACKEND_INSTANCES: dict[str, Any] = {}


def call_python_backend(local_settings: dict[str, Any], prompt: str) -> str:
    """Run an in-process Python backend (llama_cpp or transformers).

    Expects local_settings to include:
    - python_backend: 'llama_cpp' or 'transformers'
    - model_path: path or model identifier
    - max_tokens: int
    - temperature: float
    """
    backend = str(local_settings.get("python_backend", "")).strip().lower()
    if not backend:
        raise RuntimeError("Local python backend is not configured.")
    model_path = str(local_settings.get("model_path", "")).strip()
    max_tokens = int(local_settings.get("max_tokens", 256))
    temperature = float(local_settings.get("temperature", 0.4))

    if backend == "llama_cpp":
        try:
            from llama_cpp import Llama
        except Exception as exc:
            raise RuntimeError("Install 'llama-cpp-python' (pip install llama-cpp-python) to use the llama_cpp backend.") from exc
        key = f"llama_cpp::{model_path}"
        inst = _PYTHON_BACKEND_INSTANCES.get(key)
        if inst is None:
            if not model_path:
                raise RuntimeError("Provide 'model_path' for llama_cpp backend.")
            inst = Llama(model_path=model_path)
            _PYTHON_BACKEND_INSTANCES[key] = inst
        resp = inst.create(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        choices = resp.get("choices") if isinstance(resp, dict) else None
        if choices and choices[0] and "text" in choices[0]:
            return str(choices[0]["text"]).strip()
        return str(resp)

    elif backend == "transformers":
        try:
            from transformers import pipeline
        except Exception as exc:
            raise RuntimeError("Install 'transformers' to use the transformers backend.") from exc
        key = f"transformers::{model_path}"
        inst = _PYTHON_BACKEND_INSTANCES.get(key)
        if inst is None:
            if not model_path:
                raise RuntimeError("Provide 'model_path' for transformers backend.")
            inst = pipeline("text-generation", model=model_path, device_map="auto")
            _PYTHON_BACKEND_INSTANCES[key] = inst
        out = inst(prompt, max_length=max_tokens, do_sample=True, temperature=temperature)
        if isinstance(out, list) and out:
            return str(out[0].get("generated_text", "")).strip()
        return str(out).strip()

    else:
        raise RuntimeError(f"Unsupported python backend: {backend}")


def call_remote_api(remote_settings: dict[str, Any], prompt: str, persona: str | None = None) -> str:
    """Send the prompt to an OpenAI-compatible /chat/completions endpoint.

    If `persona` is provided, it will be prepended as a system message so the
    remote model receives the GM persona as system-level instruction.
    """
    base = str(remote_settings.get("base_url", "")).strip()
    if not base:
        raise RuntimeError("Remote API base URL is not configured.")
    url = base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    model = str(remote_settings.get("model", "")).strip() or "lmstudio"
    system_intro = "You are a helpful basketball analyst assisting with NBA 2K roster edits."
    system_content = (str(persona).strip() + "\n\n" if persona else "") + system_intro
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    api_key = str(remote_settings.get("api_key", "")).strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(payload).encode("utf-8")
    timeout = int(remote_settings.get("timeout") or 30)
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Remote API error: {exc.reason}") from exc
    parsed = json.loads(raw)
    choices = parsed.get("choices")
    if not choices:
        raise RuntimeError("Remote API returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content")
    if not content:
        raise RuntimeError("Remote API choice did not include content.")
    return str(content).strip()


def invoke_ai_backend(settings: dict[str, Any], prompt: str, persona: str | None = None) -> str:
    """Route the prompt to whichever backend the user configured.

    When `persona` is provided and mode == 'remote', the persona is passed as a
    system message. For local backends, the caller should prepend the persona
    text to the prompt if it should influence the model.
    """
    mode = str(settings.get("mode", "none"))
    if mode == "remote":
        remote = settings.get("remote") or {}
        return call_remote_api(remote, prompt, persona)
    if mode == "local":
        local = settings.get("local") or {}
        backend = str(local.get("backend", "cli")).strip().lower()
        if backend == "python":
            return call_python_backend(local, prompt)
        return call_local_process(local, prompt)
    raise RuntimeError("Enable the AI integration in Home > AI Settings first.")


__all__ = [
    "LLMControlBridge",
    "ensure_control_bridge",
    "PlayerAIAssistant",
    "build_local_command",
    "call_local_process",
    "call_python_backend",
    "call_remote_api",
    "invoke_ai_backend",
]
