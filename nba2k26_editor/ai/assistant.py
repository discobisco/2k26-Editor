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
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, TYPE_CHECKING

import dearpygui.dearpygui as dpg

from . import nba_data
from .backends.http_backend import call_chat_completions
from .backends.python_backend import generate_sync as generate_python_sync, load_instance as load_python_instance
from .cba_context import build_cba_guidance
if TYPE_CHECKING:
    from typing import Protocol

    class _PlayerProto(Protocol):
        record_index: int
        player_id: int

    class PlayerEditorApp(Protocol):
        selected_player: _PlayerProto | None
        selected_players: list[Any]
        player_detail_fields: Mapping[str, Any]
        filtered_player_indices: list[int]
        current_players: list[Any] | None
        team_var: Any
        team_edit_var: Any
        team_field_vars: Mapping[str, Any]
        ai_mode_var: Any
        player_search_var: Any
        player_name_var: Any
        player_ovr_var: Any
        var_first: Any
        var_last: Any
        var_player_team: Any
        ai_persona_choice_var: Any
        ai_settings: dict[str, Any]
        screen_tags: Mapping[str, Any]
        full_editors: list[Any]
        model: Any

        def run_on_ui_thread(self, func: Callable, delay_ms: int = 0) -> None: ...
        def enqueue_ui_update(self, func: Callable) -> None: ...

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

        def show_ai(self) -> Any: ...

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

        def get_persona_choice_items(self) -> list[tuple[str, str]]: ...

        def copy_to_clipboard(self, text: str) -> None: ...

        def get_player_list_items(self) -> list[str]: ...

        def get_selected_player_indices(self) -> list[int]: ...

        def set_selected_player_indices(self, indices: list[int]) -> None: ...

        def clear_player_selection(self) -> None: ...

        def get_staff_list_items(self) -> list[str]: ...

        def get_selected_staff_indices(self) -> list[int]: ...

        def set_staff_selection(self, positions: list[int]) -> None: ...

        def get_stadium_list_items(self) -> list[str]: ...

        def get_selected_stadium_indices(self) -> list[int]: ...

        def set_stadium_selection(self, positions: list[int]) -> None: ...

else:
    PlayerEditorApp = Any


class EditorCommandAdapter:
    """Entity-parameterized adapter for full/staff/stadium editor commands."""

    def __init__(
        self,
        *,
        bridge: "LLMControlBridge",
        entity_label: str,
        index_key: str | None,
        find_editor: Callable[[], Any],
        select_index: Callable[[int], Any] | None,
        set_field_on_ui: Callable[[str, str, Any, int | None], dict[str, Any]],
        subject_builder: Callable[[Any], dict[str, Any] | None] | None = None,
        subject_key: str | None = None,
    ) -> None:
        self._bridge = bridge
        self._entity_label = entity_label
        self._index_key = index_key
        self._find_editor = find_editor
        self._select_index = select_index
        self._set_field_on_ui = set_field_on_ui
        self._subject_builder = subject_builder
        self._subject_key = subject_key

    def _resolve_index(self, payload: dict[str, Any]) -> int | None:
        if not self._index_key:
            return None
        raw = payload.get(self._index_key)
        if raw is None:
            return None
        return int(raw)

    def _maybe_select(self, index_value: int | None) -> None:
        if index_value is None or self._select_index is None:
            return
        try:
            self._select_index(index_value)
        except Exception:
            return

    def _subject_payload(self, editor: Any) -> dict[str, Any]:
        if self._subject_key is None:
            return {}
        subject = self._subject_builder(editor) if self._subject_builder is not None else None
        return {self._subject_key: subject}

    def list_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def list_impl() -> dict[str, Any]:
            editor = self._find_editor()
            if editor is None:
                return {"open": False, "fields": {}}
            result: dict[str, Any] = {"open": True, "fields": {}}
            result.update(self._subject_payload(editor))
            for cat, mapping in editor.field_vars.items():
                fields = []
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    fields.append(
                        {
                            "name": fname,
                            "value": self._bridge._get_control_value(var),
                            "offset": getattr(meta, "offset", None) if meta else None,
                            "length": getattr(meta, "length", None) if meta else None,
                            "values": getattr(meta, "values", None) if meta else None,
                        }
                    )
                result["fields"][cat] = fields
            return result

        return self._bridge._run_on_ui_thread(list_impl)

    def set_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category", "")).strip()
        field = str(payload.get("field", "")).strip()
        if not category or not field:
            raise ValueError(f"Provide 'category' and 'field' for set_{self._entity_label}_field")
        value = payload.get("value")
        index_value = self._resolve_index(payload)

        def set_impl() -> dict[str, Any]:
            return self._set_field_on_ui(category, field, value, index_value)

        return self._bridge._run_on_ui_thread(set_impl)

    def set_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise ValueError("Provide 'fields' as a list of {category, field, value} dicts.")
        index_value = self._resolve_index(payload)

        def set_many_impl() -> dict[str, Any]:
            self._maybe_select(index_value)
            updated = []
            errors = []
            for entry in fields:
                try:
                    cat = str(entry.get("category", "")).strip()
                    fname = str(entry.get("field", "")).strip()
                    self._set_field_on_ui(cat, fname, entry.get("value"), index_value)
                    updated.append({"category": entry.get("category"), "field": entry.get("field")})
                except Exception as exc:  # noqa: BLE001
                    errors.append({"field": entry.get("field"), "error": str(exc)})
            return {"updated": updated, "errors": errors}

        return self._bridge._run_on_ui_thread(set_many_impl)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        close_after = bool(payload.get("close_after", False))
        index_value = self._resolve_index(payload)

        def save_impl() -> dict[str, Any]:
            self._maybe_select(index_value)
            editor = self._find_editor()
            if editor is None:
                raise RuntimeError(f"No open {self._entity_label.title()} editor to save.")
            try:
                editor._save_all()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Saving failed: {exc}") from exc
            if close_after:
                try:
                    if hasattr(editor, "_on_close"):
                        editor._on_close()
                except Exception:
                    pass
            return {"saved": True}

        return self._bridge._run_on_ui_thread(save_impl)

    def get_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        def state_impl() -> dict[str, Any]:
            editor = self._find_editor()
            if editor is None:
                return {"open": False, "categories": {}}
            result: dict[str, Any] = {"open": True, "categories": {}}
            result.update(self._subject_payload(editor))
            for cat, mapping in editor.field_vars.items():
                result["categories"][cat] = {}
                for fname, var in mapping.items():
                    meta = editor.field_meta.get((cat, fname))
                    result["categories"][cat][fname] = {
                        "value": self._bridge._get_control_value(var),
                        "offset": getattr(meta, "offset", None) if meta is not None else None,
                        "length": getattr(meta, "length", None) if meta is not None else None,
                        "values": getattr(meta, "values", None) if meta is not None else None,
                    }
            return result

        return self._bridge._run_on_ui_thread(state_impl)


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
        self._editor_adapters = self._build_editor_adapters()

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
                    try:
                        detail[label] = dpg.get_value(var)
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
            selection = app.get_selected_player_indices()
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
            items = []
            try:
                items = app.get_player_list_items()
            except Exception:
                items = []
            for idx, name in enumerate(items):
                filtered_index = app.filtered_player_indices[idx] if idx < len(app.filtered_player_indices) else None
                players.append({"index": idx, "name": name, "filtered_index": filtered_index})
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

    def _build_editor_adapters(self) -> dict[str, EditorCommandAdapter]:
        def _full_subject(editor: Any) -> dict[str, Any] | None:
            player = getattr(editor, "player", None)
            if player is None:
                return None
            return {
                "index": getattr(player, "index", None),
                "full_name": getattr(player, "full_name", None),
            }

        return {
            "full": EditorCommandAdapter(
                bridge=self,
                entity_label="full",
                index_key="player_index",
                find_editor=self._find_open_full_editor,
                select_index=lambda idx: self._select_player_index(idx),
                set_field_on_ui=self._set_full_field_on_ui,
                subject_builder=_full_subject,
                subject_key="player",
            ),
            "staff": EditorCommandAdapter(
                bridge=self,
                entity_label="staff",
                index_key="staff_index",
                find_editor=self._find_open_staff_editor,
                select_index=lambda idx: self._select_staff_index(idx),
                set_field_on_ui=self._set_staff_field_on_ui,
            ),
            "stadium": EditorCommandAdapter(
                bridge=self,
                entity_label="stadium",
                index_key="stadium_index",
                find_editor=self._find_open_stadium_editor,
                select_index=lambda idx: self._select_stadium_index(idx),
                set_field_on_ui=self._set_stadium_field_on_ui,
            ),
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
        items = app.get_player_list_items()
        size = len(items)
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        app.set_selected_player_indices([index])
        return self._gather_selection_summary()

    def _select_staff_index(self, index: int) -> dict[str, Any]:
        app = self.app
        app.show_staff()
        items = app.get_staff_list_items()
        size = len(items)
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        app.set_staff_selection([index])
        return {"selected_index": index, "name": items[index]}

    def _select_stadium_index(self, index: int) -> dict[str, Any]:
        app = self.app
        app.show_stadium()
        items = app.get_stadium_list_items()
        size = len(items)
        if index < 0 or index >= size:
            raise ValueError(f"Index {index} out of bounds (0-{size - 1}).")
        app.set_stadium_selection([index])
        return {"selected_index": index, "name": items[index]}

    def _select_player_name(self, name: str) -> dict[str, Any]:
        app = self.app
        normalized = name.strip().lower()
        items = app.get_player_list_items()
        for idx, label in enumerate(items):
            if label.strip().lower() == normalized:
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
        selection = []
        try:
            selection = app.get_selected_player_indices()
        except Exception:
            selection = []
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
        Implemented as a scan of `self.app.full_editors` and **must be called
        from the UI thread** (e.g. from inside `_run_on_ui_thread`).
        """
        app = self.app
        editors = getattr(app, "full_editors", None)
        if isinstance(editors, list):
            for editor in editors:
                try:
                    if hasattr(editor, "player") and hasattr(editor, "_save_all"):
                        return editor
                except Exception:
                    continue
        return None

    def _find_open_staff_editor(self) -> Any:
        app = self.app
        editors = getattr(app, "full_editors", None)
        if isinstance(editors, list):
            for editor in editors:
                try:
                    if getattr(editor, "_editor_type", "") == "staff" and hasattr(editor, "_save_all"):
                        return editor
                except Exception:
                    continue
        return None

    def _find_open_stadium_editor(self) -> Any:
        app = self.app
        editors = getattr(app, "full_editors", None)
        if isinstance(editors, list):
            for editor in editors:
                try:
                    if getattr(editor, "_editor_type", "") == "stadium" and hasattr(editor, "_save_all"):
                        return editor
                except Exception:
                    continue
        return None

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _get_control_value(control: Any) -> Any:
        try:
            return dpg.get_value(control)
        except Exception:
            try:
                return control.get()
            except Exception:
                return None

    def _set_control_value(self, control: Any, meta: Any, value: Any) -> Any:
        """Set a DPG control value using metadata; returns the applied value."""
        if meta and getattr(meta, "values", None):
            vals = list(meta.values)
            target = vals[0] if vals else value
            if isinstance(value, str):
                for v in vals:
                    if str(v).strip().lower() == value.strip().lower():
                        target = v
                        break
            elif value is not None and vals:
                idx = self._coerce_int(value, 0)
                if 0 <= idx < len(vals):
                    target = vals[idx]
            try:
                dpg.set_value(control, target)
            except Exception:
                pass
            return target

        data_type = (getattr(meta, "data_type", "") or "").lower() if meta else ""
        if "float" in data_type:
            applied = float(value) if value is not None else 0.0
        elif any(tag in data_type for tag in ("string", "text", "char", "pointer", "wide")):
            applied = "" if value is None else str(value)
        else:
            applied = self._coerce_int(value, 0)
        try:
            dpg.set_value(control, applied)
        except Exception:
            pass
        return applied

    def _cmd_list_full_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["full"].list_fields(_payload)

    def _cmd_set_full_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["full"].set_field(payload)

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
        control = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        self._set_control_value(control, meta, value)
        return {"category": cat_key, "field": fname_key, "value": self._get_control_value(control)}

    def _cmd_save_full_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["full"].save(payload)

    def _cmd_set_full_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["full"].set_fields(payload)

    def _cmd_get_full_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["full"].get_state(_payload)

    # ---------------- Staff editor helpers ---------------- #
    def _cmd_list_staff_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["staff"].list_fields(_payload)

    def _cmd_set_staff_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["staff"].set_field(payload)

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
        control = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        self._set_control_value(control, meta, value)
        return {"category": cat_key, "field": fname_key, "value": self._get_control_value(control)}

    def _cmd_set_staff_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["staff"].set_fields(payload)

    def _cmd_save_staff_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["staff"].save(payload)

    def _cmd_get_staff_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["staff"].get_state(_payload)

    # ---------------- Stadium editor helpers ---------------- #
    def _cmd_list_stadium_fields(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["stadium"].list_fields(_payload)

    def _cmd_set_stadium_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["stadium"].set_field(payload)

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
        control = editor.field_vars[cat_key][fname_key]
        meta = editor.field_meta.get((cat_key, fname_key))
        self._set_control_value(control, meta, value)
        return {"category": cat_key, "field": fname_key, "value": self._get_control_value(control)}

    def _cmd_set_stadium_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["stadium"].set_fields(payload)

    def _cmd_save_stadium_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["stadium"].save(payload)

    def _cmd_get_stadium_editor_state(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self._editor_adapters["stadium"].get_state(_payload)

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

        try:
            self.app.run_on_ui_thread(wrapper)
        except Exception:
            # Fallback: execute immediately if scheduling fails
            wrapper()
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
            for name, tag in getattr(app, "screen_tags", {}).items():
                if dpg.does_item_exist(tag) and dpg.is_item_shown(tag):
                    return name
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
    """UI helper that wires player data into an AI backend (Dear PyGui)."""

    def __init__(self, app: PlayerEditorApp, context: dict[str, Any]) -> None:
        self.app = app
        self.context = context
        self._worker: threading.Thread | None = None
        self._persona_display_map: dict[str, str] = {}
        self.prompt_tag: int | str | None = None
        self.status_tag: int | str | None = None
        self.output_tag: int | str | None = None
        self.progress_tag: int | str | None = None
        self.persona_combo_tag: int | str | None = None
        self.ask_button_tag: int | str | None = None
        self.copy_button_tag: int | str | None = None
        self.prompt_placeholder = (
            "Provide direct 2K26 roster edits with target values, or general roster guidance if no player is selected."
        )
        self.status_text = "Enter a request. Player selection is optional."
        nba_data.warm_cache_async()
        parent_tag = context.get("panel_parent")
        if parent_tag is None or not dpg.does_item_exist(parent_tag):
            return
        self._build_panel(parent_tag)
        try:
            bridge = ensure_control_bridge(app)
            self._set_status(f"AI Assistant ready. Control bridge at {bridge.server_address()}")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Control bridge unavailable: {exc}")

    def _build_panel(self, parent_tag: int | str) -> None:
        dpg.add_text("AI Assistant", parent=parent_tag, color=(224, 225, 221, 255))
        dpg.add_spacer(parent=parent_tag, height=4)
        self.persona_combo_tag = dpg.add_combo(
            parent=parent_tag,
            items=[],
            width=260,
            callback=self._on_persona_select,
        )
        self._refresh_persona_dropdown()
        dpg.add_spacer(parent=parent_tag, height=4)
        self.prompt_tag = dpg.add_input_text(
            parent=parent_tag,
            hint="Ask for roster edits or guidance...",
            width=-1,
            height=80,
            multiline=True,
            default_value=self.prompt_placeholder,
        )
        with dpg.group(horizontal=True, parent=parent_tag):
            self.ask_button_tag = dpg.add_button(label="Ask AI", width=120, callback=self._on_request)
            self.copy_button_tag = dpg.add_button(label="Copy Response", width=140, callback=self._copy_response)
        self.status_tag = dpg.add_text(self.status_text, parent=parent_tag, wrap=520, color=(155, 164, 181, 255))
        self.progress_tag = dpg.add_loading_indicator(parent=parent_tag, radius=8, style=1)
        dpg.configure_item(self.progress_tag, show=False)
        self.output_tag = dpg.add_input_text(
            parent=parent_tag,
            multiline=True,
            readonly=True,
            width=-1,
            height=220,
            default_value="",
        )

    def _refresh_persona_dropdown(self) -> None:
        items: list[tuple[str, str]] = []
        try:
            items = self.app.get_persona_choice_items()
        except Exception:
            items = [("None", "none")]
        self._persona_display_map = {label: value for label, value in items}
        displays = list(self._persona_display_map.keys())
        if self.persona_combo_tag and dpg.does_item_exist(self.persona_combo_tag):
            dpg.configure_item(self.persona_combo_tag, items=displays)
            current_val = None
            try:
                current_val = self.app.ai_persona_choice_var.get()
            except Exception:
                current_val = "none"
            inv_map = {v: k for k, v in self._persona_display_map.items()}
            display = inv_map.get(current_val, displays[0] if displays else "")
            if display:
                dpg.set_value(self.persona_combo_tag, display)

    def _on_persona_select(self, _sender, value) -> None:
        try:
            sel_val = self._persona_display_map.get(value, "none")
            self.app.ai_persona_choice_var.set(sel_val)
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.status_text = text
        if self.status_tag and dpg.does_item_exist(self.status_tag):
            dpg.set_value(self.status_tag, text)

    def _set_output(self, text: str) -> None:
        if self.output_tag and dpg.does_item_exist(self.output_tag):
            dpg.set_value(self.output_tag, text or "")

    def _append_output(self, text: str, *, replace_placeholder: bool = True) -> None:
        if not (self.output_tag and dpg.does_item_exist(self.output_tag)):
            return
        current = str(dpg.get_value(self.output_tag) or "")
        if replace_placeholder and current.strip() == "Thinking ...":
            current = ""
        dpg.set_value(self.output_tag, current + (text or ""))

    def _start_progress(self) -> None:
        if self.progress_tag and dpg.does_item_exist(self.progress_tag):
            dpg.configure_item(self.progress_tag, show=True)
        if self.ask_button_tag and dpg.does_item_exist(self.ask_button_tag):
            dpg.disable_item(self.ask_button_tag)

    def _stop_progress(self) -> None:
        if self.progress_tag and dpg.does_item_exist(self.progress_tag):
            dpg.configure_item(self.progress_tag, show=False)
        if self.ask_button_tag and dpg.does_item_exist(self.ask_button_tag):
            dpg.enable_item(self.ask_button_tag)

    def _copy_response(self) -> None:
        text = ""
        if self.output_tag and dpg.does_item_exist(self.output_tag):
            try:
                text = str(dpg.get_value(self.output_tag) or "").strip()
            except Exception:
                text = ""
        if not text:
            self._set_status("No response to copy yet.")
            return
        try:
            self.app.copy_to_clipboard(text)
            self._set_status("Copied response to clipboard.")
        except Exception:
            self._set_status("Could not copy response.")

    def _get_settings_for_request(self) -> tuple[dict[str, Any] | None, str | None]:
        try:
            settings = self.app.get_ai_settings()
        except Exception as exc:  # noqa: BLE001
            return None, f"Could not read AI settings: {exc}"
        if not isinstance(settings, dict):
            return None, "AI settings are invalid."
        mode = str(settings.get("mode", "none")).strip().lower()
        if mode in ("", "none"):
            return None, "AI is disabled. Enable it in AI Settings."
        if mode == "remote":
            remote = settings.get("remote") or {}
            base = str(remote.get("base_url", "")).strip()
            if not base:
                return None, "Remote API base URL is missing."
        elif mode == "local":
            local = settings.get("local") or {}
            backend = str(local.get("backend", "cli")).strip().lower() or "cli"
            if backend == "python":
                backend_name = str(local.get("python_backend", "")).strip()
                model_path = str(local.get("model_path", "")).strip()
                if not backend_name:
                    return None, "Select a python backend (llama_cpp or transformers)."
                if not model_path:
                    return None, "Provide a model path or Hugging Face model id."
            else:
                command = str(local.get("command", "")).strip()
                if not command:
                    return None, "Provide a local command or executable."
        else:
            return None, f"Unknown AI mode: {mode}"
        return settings, None

    def _on_request(self) -> None:
        if self._worker and self._worker.is_alive():
            self._set_status("Hold on, the AI is still processing.")
            return
        settings, error = self._get_settings_for_request()
        if error:
            self._set_status(error)
            self._set_output(error)
            return
        prompt = self._build_prompt()
        if not prompt:
            message = "Enter a request to send to the AI."
            self._set_status(message)
            self._set_output(message)
            return
        self._set_status("Contacting AI backend ...")
        self._set_output("Thinking ...")
        self._start_progress()
        self._worker = threading.Thread(target=self._run_ai, args=(prompt, settings), daemon=True)
        self._worker.start()

    def _run_ai(self, prompt: str, settings: dict[str, Any]) -> None:
        selection = None
        persona_var = getattr(self.app, "ai_persona_choice_var", None)
        if persona_var is not None and hasattr(persona_var, "get"):
            try:
                selection = persona_var.get()
            except Exception:
                selection = None
        try:
            from .personas import get_persona_text
            persona_text = get_persona_text(settings, selection)
        except Exception:
            persona_text = ""

        mode = str(settings.get("mode", "none"))
        if mode == "local" and str(settings.get("local", {}).get("backend", "cli")).strip().lower() == "python":
            local = settings.get("local") or {}
            backend = str(local.get("python_backend", "")).strip().lower()
            model_path = str(local.get("model_path", "")).strip()
            max_tokens = int(local.get("max_tokens", 256))
            temperature = float(local.get("temperature", 0.4))

            def _on_update(text: str, done: bool, error: Exception | None) -> None:
                if error:
                    self.app.run_on_ui_thread(lambda: self._finalize_request(f"AI error: {error}", False))
                    return
                if done:
                    self.app.run_on_ui_thread(
                        lambda: self._finalize_request(text or "(AI backend returned no content.)", True)
                    )
                else:
                    self.app.run_on_ui_thread(lambda t=text: self._append_output(t))

            try:
                from .backend_helpers import generate_text_async
            except Exception:
                full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
                try:
                    response = invoke_ai_backend(settings, full_prompt)
                except Exception as exc:  # noqa: BLE001
                    error_message = f"AI error: {exc}"
                    self.app.run_on_ui_thread(lambda msg=error_message: self._finalize_request(msg, False))
                    return
                self.app.run_on_ui_thread(
                    lambda: self._finalize_request(response or "(AI backend returned no content.)", True)
                )
                return

            full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
            generate_text_async(
                backend,
                model_path,
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                on_update=_on_update,
            )
            return

        if mode == "remote":
            try:
                response = invoke_ai_backend(settings, prompt, persona=(persona_text or None))
            except Exception as exc:  # noqa: BLE001
                message = f"AI error: {exc}"
                success = False
            else:
                message = response or "(AI backend returned no content.)"
                success = True
            self.app.run_on_ui_thread(lambda: self._finalize_request(message, success))
            return

        full_prompt = (persona_text + "\n\n" if persona_text else "") + prompt
        try:
            response = invoke_ai_backend(settings, full_prompt)
        except Exception as exc:  # noqa: BLE001
            message = f"AI error: {exc}"
            success = False
        else:
            message = response or "(AI backend returned no content.)"
            success = True
        self.app.run_on_ui_thread(lambda: self._finalize_request(message, success))

    def _finalize_request(self, message: str, success: bool) -> None:
        self._stop_progress()
        self._set_output(message)
        self._worker = None
        if success:
            self._set_status("AI response received.")
        else:
            self._set_status(message)

    def _build_prompt(self) -> str:
        has_player = getattr(self.app, "selected_player", None) is not None
        detail_vars_obj = self.context.get("detail_vars", {})
        detail_vars: dict[str, Any] = detail_vars_obj if isinstance(detail_vars_obj, dict) else {}
        name = str(self.app.player_name_var.get() or "").strip() if has_player else ""
        ovr = str(self.app.player_ovr_var.get() or "").strip() if has_player else ""
        first = str(self.app.var_first.get() or "").strip() if has_player else ""
        last = str(self.app.var_last.get() or "").strip() if has_player else ""
        team = str(self.app.var_player_team.get() or "").strip() if has_player else ""
        pieces: list[str] = []
        if has_player:
            if name and name.lower() != "select a player":
                pieces.append(f"Displayed name: {name}")
            pieces.append(f"First name entry: {first or 'N/A'}")
            pieces.append(f"Last name entry: {last or 'N/A'}")
            pieces.append(f"Team: {team or 'N/A'}")
            if ovr:
                pieces.append(f"Overall rating label: {ovr}")
            for label, var in detail_vars.items():
                try:
                    val = str(var.get()).strip()
                except Exception:
                    try:
                        val = str(dpg.get_value(var)).strip()
                    except Exception:
                        val = ""
                if val and val != "--":
                    pieces.append(f"{label}: {val}")
            lookup_names = [f"{first} {last}".strip(), name]
            summary = nba_data.get_player_summary([n for n in lookup_names if n])
            if summary:
                pieces.append(f"NBA reference: {summary}")
        else:
            pieces.append("No player selected.")
        request_text = ""
        try:
            prompt_tag = self.prompt_tag
            if prompt_tag is not None and dpg.does_item_exist(prompt_tag):
                request_text = str(dpg.get_value(prompt_tag) or "").strip()
        except Exception:
            request_text = ""
        if not request_text:
            request_text = self.prompt_placeholder
        cba_guidance = build_cba_guidance(season="2025-26")
        cba_block = f"\n\nCBA guidance:\n{cba_guidance}" if cba_guidance else ""
        return (
            "You are assisting with NBA 2K roster editing. "
            "Provide specific, actionable field/value edits the editor can apply. "
            "If no player is selected, answer generally or ask which player to edit. "
            "Keep responses concise and actionable.\n\n"
            "Context:\n- "
            + "\n- ".join(pieces)
            + cba_block
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
    timeout = float(local_settings.get("timeout", 60) or 60)
    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            cwd=workdir,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Local AI process timed out after {timeout:g}s.") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(stderr or f"Local AI process exited with {completed.returncode}.")
    output = (completed.stdout or "").strip()
    if not output:
        raise RuntimeError("Local AI process returned no output.")
    return output


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
    inst = load_python_instance(backend, model_path)
    return generate_python_sync(
        backend,
        inst,
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def call_remote_api(remote_settings: dict[str, Any], prompt: str, persona: str | None = None) -> str:
    """Send the prompt to an OpenAI-compatible /chat/completions endpoint.

    If `persona` is provided, it will be prepended as a system message so the
    remote model receives the GM persona as system-level instruction.
    """
    return call_chat_completions(
        base_url=str(remote_settings.get("base_url", "")).strip(),
        model=str(remote_settings.get("model", "")).strip() or "lmstudio",
        prompt=prompt,
        api_key=str(remote_settings.get("api_key", "")).strip(),
        timeout=int(remote_settings.get("timeout") or 30),
        persona=persona,
    )


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


# Backward-compatible alias for older imports/tests.
AIAssistantPanel = PlayerAIAssistant


__all__ = [
    "AIAssistantPanel",
    "LLMControlBridge",
    "ensure_control_bridge",
    "PlayerAIAssistant",
    "build_local_command",
    "call_local_process",
    "call_python_backend",
    "call_remote_api",
    "invoke_ai_backend",
]
