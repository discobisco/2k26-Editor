"""Dedicated child-process entrypoint for full editor windows."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from ..core.config import MODULE_NAME
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from ..ui.full_player_editor import FullPlayerEditor
from ..ui.full_staff_editor import FullStaffEditor
from ..ui.full_stadium_editor import FullStadiumEditor
from ..ui.full_team_editor import FullTeamEditor


@dataclass(frozen=True)
class EditorRequest:
    editor: str
    index: int | None = None
    indices: tuple[int, ...] = ()


def _parse_indices_csv(raw_value: str) -> tuple[int, ...]:
    values: list[int] = []
    seen: set[int] = set()
    for chunk in (raw_value or "").split(","):
        token = chunk.strip()
        if not token:
            continue
        value = int(token)
        if value < 0 or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def parse_editor_request(args: list[str] | None = None) -> EditorRequest:
    parser = argparse.ArgumentParser(description="Open one full editor in a dedicated viewport window.")
    parser.add_argument("--editor", choices=("player", "team", "staff", "stadium"), required=True)
    parser.add_argument("--index", type=int, default=None, help="Single entity index (team/staff/stadium).")
    parser.add_argument(
        "--indices",
        type=str,
        default="",
        help="Comma-separated entity indices (player multi-select).",
    )
    parsed = parser.parse_args(args=args)
    editor = str(parsed.editor).strip().lower()
    index = parsed.index
    if index is not None and index < 0:
        parser.error("--index must be non-negative.")
    indices = _parse_indices_csv(parsed.indices)
    if editor == "player":
        if not indices:
            if index is not None:
                indices = (index,)
            else:
                parser.error("--indices (or --index) is required for player editor.")
    else:
        if index is None:
            parser.error(f"--index is required for {editor} editor.")
        if parsed.indices:
            parser.error("--indices is only valid with --editor player.")
    return EditorRequest(editor=editor, index=index, indices=indices)


class _ChildEditorHost:
    """Minimal app surface required by the full editor classes."""

    def __init__(self, model: PlayerDataModel) -> None:
        self.model = model
        self.full_editors: list[object] = []
        self._modal_tags: set[int | str] = set()

    def run_on_ui_thread(self, func: Callable, delay_ms: int = 0) -> None:
        if delay_ms <= 0:
            self._queue_on_main(func)
            return
        # Keep implementation simple for child windows; defer timing via frame callback.
        self._queue_on_main(func)

    def _queue_on_main(self, func: Callable[[], None]) -> None:
        try:
            dpg.set_frame_callback(max(0, dpg.get_frame_count() + 1), lambda: func())
        except Exception:
            try:
                func()
            except Exception:
                pass

    def _show_modal(self, title: str, message: str, level: str = "info") -> None:
        colors = {
            "info": (224, 225, 221, 255),
            "warn": (255, 202, 126, 255),
            "error": (255, 138, 128, 255),
        }
        text_color = colors.get(level, colors["info"])
        tag = dpg.generate_uuid()
        self._modal_tags.add(tag)

        def _close() -> None:
            self._modal_tags.discard(tag)
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        with dpg.window(
            label=title,
            tag=tag,
            modal=True,
            no_collapse=True,
            width=460,
            height=190,
            on_close=lambda *_: _close(),
        ):
            dpg.add_text(str(message), wrap=420, color=text_color)
            dpg.add_spacer(height=10)
            dpg.add_button(label="OK", width=90, callback=lambda *_: _close())
        try:
            dpg.focus_item(tag)
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

    def can_stop(self) -> bool:
        return not self.full_editors and not self._modal_tags


def _build_model() -> tuple[PlayerDataModel, str | None]:
    mem = GameMemory(MODULE_NAME)
    offset_target = MODULE_NAME
    process_open = mem.open_process()
    if process_open:
        detected_exec = mem.module_name or MODULE_NAME
        if detected_exec:
            offset_target = detected_exec
    startup_warning: str | None = None
    try:
        initialize_offsets(target_executable=offset_target, force=True)
    except OffsetSchemaError as exc:
        startup_warning = str(exc)
    mem.module_name = MODULE_NAME
    model = PlayerDataModel(mem, max_players=MAX_PLAYERS)
    return model, startup_warning


def _resolve_team_name(model: PlayerDataModel, team_idx: int) -> str:
    try:
        model.refresh_players()
    except Exception:
        pass
    for idx, name in getattr(model, "team_list", []):
        if idx == team_idx:
            return name
    return f"Team {team_idx}"


def _open_requested_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    model = host.model
    editor = request.editor
    if editor == "player":
        if not model.mem.open_process():
            host.show_error("Player Editor", "NBA 2K26 is not running. Launch the game and try again.")
            return False
        try:
            model.refresh_players()
        except Exception:
            pass
        player_map = {p.index: p for p in getattr(model, "players", [])}
        selected_players = [player_map[idx] for idx in request.indices if idx in player_map]
        if not selected_players:
            host.show_error("Player Editor", "Selected players could not be resolved in the current roster scan.")
            return False
        FullPlayerEditor(host, selected_players, model)
        return True
    if editor == "team":
        team_idx = int(request.index or 0)
        if not model.mem.open_process():
            host.show_error("Edit Team", "NBA 2K26 is not running. Launch the game to edit team data.")
            return False
        team_name = _resolve_team_name(model, team_idx)
        FullTeamEditor(host, team_idx, team_name, model)
        return True
    if editor == "staff":
        staff_idx = int(request.index or 0)
        FullStaffEditor(host, model, staff_idx)
        return True
    if editor == "stadium":
        stadium_idx = int(request.index or 0)
        FullStadiumEditor(host, model, stadium_idx)
        return True
    host.show_error("Full Editor", f"Unsupported editor type: {editor}")
    return False


def _viewport_title(request: EditorRequest) -> str:
    base = {
        "player": "Player",
        "team": "Team",
        "staff": "Staff",
        "stadium": "Stadium",
    }.get(request.editor, "Full")
    return f"2K26 {base} Editor"


def main(args: list[str] | None = None) -> None:
    request = parse_editor_request(args)
    model, startup_warning = _build_model()
    host = _ChildEditorHost(model)
    dpg.create_context()
    try:
        dpg.create_viewport(
            title=_viewport_title(request),
            width=980,
            height=760,
            min_width=760,
            min_height=560,
        )
        dpg.setup_dearpygui()
        dpg.show_viewport()
        if startup_warning:
            host.show_warning("Offsets warning", startup_warning)
        _open_requested_editor(host, request)
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()
            if host.can_stop():
                dpg.stop_dearpygui()
    finally:
        dpg.destroy_context()


if __name__ == "__main__":
    main()
