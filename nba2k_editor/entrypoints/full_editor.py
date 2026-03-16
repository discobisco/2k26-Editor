"""Dedicated child-process entrypoint for full editor windows."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable

from ..core.config import MODULE_NAME
from ..core.offsets import MAX_PLAYERS, OffsetSchemaError, initialize_offsets
from ..memory.game_memory import GameMemory
from ..models.data_model import PlayerDataModel
from .runtime_cleanup import cleanup_runtime_cache_dirs
from ..ui.full_player_editor import FullPlayerEditor
from ..ui.full_staff_editor import FullStaffEditor
from ..ui.full_stadium_editor import FullStadiumEditor
from ..ui.full_team_editor import FullTeamEditor
from ..ui.shell_utils import UIHostMixin


@dataclass(frozen=True)
class EditorRequest:
    editor: str
    index: int | None = None
    indices: tuple[int, ...] = ()


EditorOpener = Callable[['_ChildEditorHost', EditorRequest], bool]


def _dpg() -> Any:
    import dearpygui.dearpygui as dpg

    return dpg


def _parse_indices_csv(raw_value: str) -> tuple[int, ...]:
    values: list[int] = []
    seen: set[int] = set()
    for chunk in (raw_value or "").split(","):
        token = chunk.strip()
        if not token:
            raise ValueError("Empty index token in --indices list")
        try:
            value = int(token)
        except ValueError as exc:
            raise ValueError(f"Non-numeric index token in --indices: {token!r}") from exc
        if value < 0:
            raise ValueError("Negative indices are not allowed in --indices")
        if value in seen:
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
    indices = ()
    if parsed.indices != "" or (args is not None and "--indices" in args):
        try:
            indices = _parse_indices_csv(parsed.indices)
        except ValueError as exc:
            parser.error(str(exc))

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


class _ChildEditorHost(UIHostMixin):
    """Minimal app surface required by the full editor classes."""

    def __init__(self, model: PlayerDataModel) -> None:
        self.model = model
        self.full_editors: list[object] = []
        self._modal_tags: set[int | str] = set()
        self._modal_kwargs = {
            "width": 460,
            "height": 190,
            "wrap": 420,
            "button_width": 90,
            "button_spacer_width": 0,
        }

    def can_stop(self) -> bool:
        return not self.full_editors and not self._modal_tags


def _build_model() -> tuple[PlayerDataModel, str | None]:
    offset_target = GameMemory.detect_running_module_name(MODULE_NAME) or MODULE_NAME
    mem = GameMemory(offset_target)
    if mem.open_process():
        detected_exec = mem.module_name or MODULE_NAME
        if detected_exec:
            offset_target = detected_exec
    startup_warning: str | None = None
    try:
        initialize_offsets(target_executable=offset_target, force=True)
    except OffsetSchemaError as exc:
        startup_warning = str(exc)
    mem.module_name = offset_target
    return PlayerDataModel(mem, max_players=MAX_PLAYERS), startup_warning


def _open_process_or_show_error(host: _ChildEditorHost, title: str, message: str) -> bool:
    if host.model.mem.open_process():
        return True
    host.show_error(title, message)
    return False



def _open_indexed_editor(host: _ChildEditorHost, request: EditorRequest, editor_ctor: Callable[[Any, Any, int | None], object]) -> bool:
    """Open editors that consume a host+model+index signature."""
    editor_ctor(host, host.model, request.index)
    return True


def _resolve_team_name(model: PlayerDataModel, team_idx: int) -> str:
    try:
        model.refresh_players()
    except Exception:
        pass
    for idx, name in getattr(model, "team_list", []):
        if idx == team_idx:
            return name
    return f"Team {team_idx}"


def _open_player_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    model = host.model
    if not _open_process_or_show_error(
        host,
        "Player Editor",
        "NBA 2K is not running. Launch the game and try again.",
    ):
        return False
    try:
        model.refresh_players()
    except Exception:
        pass
    player_map = {player.index: player for player in getattr(model, "players", [])}
    selected_players = [player_map[idx] for idx in request.indices if idx in player_map]
    if not selected_players:
        host.show_error("Player Editor", "Selected players could not be resolved in the current roster scan.")
        return False
    FullPlayerEditor(host, selected_players, model)
    return True


def _open_team_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    if not _open_process_or_show_error(
        host,
        "Edit Team",
        "NBA 2K is not running. Launch the game to edit team data.",
    ):
        return False
    team_idx = int(request.index or 0)
    FullTeamEditor(host, team_idx, _resolve_team_name(host.model, team_idx), host.model)
    return True


def _open_staff_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    if not _open_process_or_show_error(
        host,
        "Staff Editor",
        "NBA 2K is not running. Launch the game and try again.",
    ):
        return False
    return _open_indexed_editor(host, request, FullStaffEditor)


def _open_stadium_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    if not _open_process_or_show_error(
        host,
        "Stadium Editor",
        "NBA 2K is not running. Launch the game and try again.",
    ):
        return False
    return _open_indexed_editor(host, request, FullStadiumEditor)


_EDITOR_OPENERS: dict[str, EditorOpener] = {
    "player": _open_player_editor,
    "team": _open_team_editor,
    "staff": _open_staff_editor,
    "stadium": _open_stadium_editor,
}


def _open_requested_editor(host: _ChildEditorHost, request: EditorRequest) -> bool:
    opener = _EDITOR_OPENERS.get(request.editor)
    if opener is None:
        host.show_error("Full Editor", f"Unsupported editor type: {request.editor}")
        return False
    return opener(host, request)


def _viewport_title(request: EditorRequest) -> str:
    base = {
        "player": "Player",
        "team": "Team",
        "staff": "Staff",
        "stadium": "Stadium",
    }.get(request.editor, "Full")
    return f"{base} Editor"


def main(args: list[str] | None = None) -> None:
    dpg = _dpg()
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
        cleanup_runtime_cache_dirs()


if __name__ == "__main__":
    main()
