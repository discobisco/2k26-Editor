"""Reusable Dear PyGui helpers.

Retained for extension/plugin compatibility; currently not imported by core UI modules.
"""
from __future__ import annotations

import dearpygui.dearpygui as dpg


def add_scroll_area(**kwargs) -> int | str:
    """
    Create a scrollable child window and return its tag.
    Common kwargs: width, height, autosize_x, autosize_y.
    """
    kwargs.setdefault("border", False)
    kwargs.setdefault("menubar", False)
    kwargs.setdefault("no_scrollbar", False)
    with dpg.child_window(**kwargs) as tag:
        pass
    return tag


def set_scroll_y(tag: int | str, value: float) -> None:
    """Set vertical scroll position for a child window."""
    try:
        dpg.set_y_scroll(tag, value)
    except Exception:
        # ignore if tag is missing; keeps helper no-op safe
        pass


__all__ = ["add_scroll_area", "set_scroll_y"]
