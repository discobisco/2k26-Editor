"""Screen registry helpers for the editor shell."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ScreenRegistration:
    key: str
    builder: Callable[[Any], None] | None = None
    post_show: str | None = None


def ensure_screen_built(app: Any, registration: ScreenRegistration) -> None:
    existing = app.screen_tags.get(registration.key)
    if existing is not None:
        if app.content_root is None:
            return
        try:
            import dearpygui.dearpygui as dpg

            if dpg.does_item_exist(existing):
                return
        except Exception:
            return
    if registration.builder is not None:
        registration.builder(app)


def run_post_show(app: Any, registration: ScreenRegistration) -> None:
    callback_name = registration.post_show
    if not callback_name:
        return
    callback = getattr(app, callback_name, None)
    if callable(callback):
        callback()
