"""Shell-frame helpers for the Dear PyGui editor app."""
from __future__ import annotations

from typing import Any, Callable

import dearpygui.dearpygui as dpg

from ..core.config import MODULE_NAME
from .controllers.navigation import show_screen_key as nav_show_screen_key
from .theme import apply_base_theme


_NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("Home", "home"),
    ("Players", "players"),
    ("Teams", "teams"),
    ("NBA History", "nba_history"),
    ("NBA Records", "nba_records"),
    ("Staff", "staff"),
    ("Stadium", "stadium"),
    ("Excel", "excel"),
    ("Trade Players", "trade"),
)


def build_ui(app: Any) -> None:
    apply_base_theme()
    with dpg.window(
        tag="main_window",
        label="2K26 Offline Player Data Editor",
        width=1280,
        height=760,
        no_title_bar=False,
    ):
        with dpg.group(horizontal=True):
            build_sidebar(app)
            app.content_root = dpg.add_child_window(tag="content_root", autosize_x=True, autosize_y=True, border=False)
    dpg.set_primary_window("main_window", True)
    from . import app as app_module

    app_module.build_home_screen(app)
    nav_show_screen_key(app, "home")
    update_status(app)


def build_sidebar(app: Any) -> None:
    with dpg.child_window(width=200, autosize_y=True, tag="sidebar", border=False) as sidebar:
        app.sidebar_tag = sidebar

        def nav(label: str, cb: Callable[[], None]) -> int | str:
            return dpg.add_button(label=label, width=-1, callback=lambda *_: cb())

        for label, key in _NAV_ITEMS:
            setattr(app, f"nav_{key}", nav(label, lambda key=key: nav_show_screen_key(app, key)))
        dpg.add_separator()
        nav("Randomize", app._open_randomizer)
        nav("Shuffle Teams", app._open_team_shuffle)
        nav("Batch Edit", app._open_batch_edit)


def update_status(app: Any) -> None:
    if app.model.mem.hproc:
        status = f"Attached to {app.model.mem.module_name or MODULE_NAME}"
    else:
        status = "NBA 2K26 is not running."
    app.status_var.set(status)
    if app.status_text_tag and dpg.does_item_exist(app.status_text_tag):
        dpg.set_value(app.status_text_tag, status)


def set_offset_status(app: Any, message: str) -> None:
    app.offset_load_status.set(message)
    if app.offset_status_text_tag and dpg.does_item_exist(app.offset_status_text_tag):
        dpg.set_value(app.offset_status_text_tag, message)


def copy_to_clipboard(text: str) -> None:
    dpg.set_clipboard_text(text or "")


def set_hook_target(app: Any, exe_name: str) -> None:
    app.hook_target_var.set(exe_name)
    update_status(app)


__all__ = [
    "build_sidebar",
    "build_ui",
    "copy_to_clipboard",
    "set_hook_target",
    "set_offset_status",
    "update_status",
]
