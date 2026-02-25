"""Right-click context menus for Dear PyGui lists."""
from __future__ import annotations

import dearpygui.dearpygui as dpg


def attach_player_context_menu(app, selectable_tag: int | str, pos: int) -> None:
    with dpg.popup(selectable_tag, mousebutton=dpg.mvMouseButton_Right):
        dpg.add_button(label="Edit Player", callback=lambda: _select_player_and(app, pos, app._open_full_editor))
        dpg.add_button(label="Copy Player", callback=lambda: _select_player_and(app, pos, app._open_copy_dialog))
        dpg.add_separator()
        dpg.add_button(label="Refresh Players", callback=lambda: app._start_scan())


def attach_team_context_menu(app, selectable_tag: int | str, pos: int, data: tuple[int, str]) -> None:
    with dpg.popup(selectable_tag, mousebutton=dpg.mvMouseButton_Right):
        dpg.add_button(label="Edit Team", callback=lambda: _select_team_and(app, pos, data, app._open_full_team_editor))
        dpg.add_button(label="Save Fields", callback=lambda: _select_team_and(app, pos, data, app._save_team))
        dpg.add_separator()
        dpg.add_button(label="Refresh Teams", callback=lambda: app._start_team_scan())


def _select_player_and(app, pos: int, action) -> None:
    try:
        _ensure_player_selected(app, pos)
        action()
    except Exception:
        pass


def _select_team_and(app, pos: int, data: tuple[int, str], action) -> None:
    try:
        _ensure_team_selected(app, pos, data)
        action()
    except Exception:
        pass


def _ensure_player_selected(app, pos: int) -> None:
    indices = set(app.get_selected_player_indices())
    indices.add(pos)
    app.set_selected_player_indices(sorted(indices))


def _ensure_team_selected(app, pos: int, data: tuple[int, str]) -> None:
    _idx, name = data
    try:
        app.team_edit_var.set(name)
        try:
            app._on_team_selected(value=name)
        except Exception:
            pass
        tag_list = getattr(app, "team_selectable_tags", None)
        if isinstance(tag_list, list) and 0 <= pos < len(tag_list):
            dpg.set_value(tag_list[pos], True)
    except Exception:
        pass


__all__ = ["attach_player_context_menu", "attach_team_context_menu"]

