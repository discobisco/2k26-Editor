"""Navigation controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from .screen_registry import ScreenRegistration, run_post_show


def show_screen(app: Any, key: str) -> None:
    for name, tag in app.screen_tags.items():
        try:
            dpg.configure_item(tag, show=(name == key))
        except Exception:
            pass


def show_registered_screen(app: Any, registration: ScreenRegistration) -> None:
    app._ensure_screen_built(registration.key)
    show_screen(app, registration.key)
    run_post_show(app, registration)


def show_screen_key(app: Any, key: str) -> None:
    if key == "home":
        show_screen(app, key)
        return
    registration = app._screen_registry.get(key)
    if registration is None:
        show_screen(app, key)
        return
    show_registered_screen(app, registration)
