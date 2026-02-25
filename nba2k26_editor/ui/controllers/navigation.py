"""Navigation controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg


def show_screen(app: Any, key: str) -> None:
    for name, tag in app.screen_tags.items():
        try:
            dpg.configure_item(tag, show=(name == key))
        except Exception:
            pass

