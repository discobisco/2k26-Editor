"""Generic shell helpers shared by the Dear PyGui app shell."""
from __future__ import annotations

import threading
from typing import Any, Callable

import dearpygui.dearpygui as dpg


class UIHostMixin:
    """Shared minimal host surface for app shells and child editor windows."""

    def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
        after(delay_ms, callback)

    def run_on_ui_thread(self, func: Callable[..., Any], delay_ms: int = 0) -> None:
        self.after(delay_ms, lambda: func())

    def _show_modal(self, title: str, message: str, level: str = "info") -> None:
        modal_tags = getattr(self, "_modal_tags", None)
        dialog_tag: int | str | None = None
        on_close: Callable[[], None] | None = None
        if isinstance(modal_tags, set):
            dialog_tag = dpg.generate_uuid()
            modal_tags.add(dialog_tag)

            def _discard() -> None:
                modal_tags.discard(dialog_tag)

            on_close = _discard
        modal_kwargs = getattr(self, "_modal_kwargs", {})
        if not isinstance(modal_kwargs, dict):
            modal_kwargs = {}
        show_modal(title, message, level=level, tag=dialog_tag, on_close=on_close, **modal_kwargs)

    def show_info(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="info")

    def show_warning(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="warn")

    def show_error(self, title: str, message: str) -> None:
        self._show_modal(title, message, level="error")


def queue_on_main(func: Callable[[], None]) -> None:
    """Queue a callback to run on the next Dear PyGui frame; fallback to direct call."""
    try:
        dpg.set_frame_callback(max(0, dpg.get_frame_count() + 1), lambda: func())
    except Exception:
        try:
            func()
        except Exception:
            pass


def after(delay_ms: int, callback: Callable[[], None]) -> None:
    """Schedule a callback on the UI thread after a delay."""
    delay_sec = max(0, delay_ms) / 1000.0
    if delay_sec <= 0:
        queue_on_main(callback)
        return
    timer = threading.Timer(delay_sec, lambda: queue_on_main(callback))
    timer.daemon = True
    timer.start()


def show_modal(
    title: str,
    message: str,
    level: str = "info",
    *,
    tag: int | str | None = None,
    on_close: Callable[[], None] | None = None,
    width: int = 420,
    height: int = 180,
    wrap: int = 380,
    button_width: int = 80,
    button_spacer_width: int = 260,
) -> int | str:
    """Lightweight modal dialog built with Dear PyGui."""
    colors = {
        "info": (224, 225, 221, 255),
        "warn": (255, 202, 126, 255),
        "error": (255, 138, 128, 255),
    }
    text_color = colors.get(level, colors["info"])
    dialog_tag = tag if tag is not None else dpg.generate_uuid()

    def _close_dialog() -> None:
        if on_close is not None:
            try:
                on_close()
            except Exception:
                pass
        if dpg.does_item_exist(dialog_tag):
            dpg.delete_item(dialog_tag)

    with dpg.window(
        label=title,
        tag=dialog_tag,
        modal=True,
        no_collapse=True,
        width=width,
        height=height,
        on_close=lambda *_: _close_dialog(),
    ):
        dpg.add_text(str(message), wrap=wrap, color=text_color)
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=button_spacer_width)
            dpg.add_button(label="OK", width=button_width, callback=lambda *_: _close_dialog())
    try:
        dpg.focus_item(dialog_tag)
    except Exception:
        pass
    return dialog_tag


def open_file_dialog(
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
                try:
                    dpg.add_file_extension(ext, parent=dialog_tag)
                except Exception:
                    pass


__all__ = ["after", "open_file_dialog", "queue_on_main", "show_modal"]
