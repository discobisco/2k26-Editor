"""Reusable Tk widgets and helpers."""
from __future__ import annotations

import tkinter as tk
from typing import Protocol, Callable, Any

_SCROLL_BINDING_INITIALIZED = False
_SCROLL_AREAS: list[tuple[tk.Misc, tk.Misc]] = []


class _YScrollable(Protocol):
    def yview_scroll(self, number: int, what: str) -> None: ...


def _is_descendant(widget: tk.Misc | None, ancestor: tk.Misc) -> bool:
    while widget is not None:
        if widget == ancestor:
            return True
        widget = widget.master  # type: ignore[attr-defined]
    return False


def _prune_dead_scroll_areas() -> None:
    alive: list[tuple[tk.Misc, tk.Misc]] = []
    for area, target in _SCROLL_AREAS:
        try:
            exists = area.winfo_exists() and target.winfo_exists()
        except Exception:
            exists = False
        if exists:
            alive.append((area, target))
    _SCROLL_AREAS[:] = alive


def _locate_scroll_target(event: tk.Event) -> tk.Misc | None:
    _prune_dead_scroll_areas()
    pointer_widget: tk.Misc | None = None
    try:
        widget = event.widget
        if widget:
            pointer_widget = widget.winfo_containing(event.x_root, event.y_root)
    except Exception:
        pointer_widget = None
    for area, target in _SCROLL_AREAS:
        if pointer_widget is not None and _is_descendant(pointer_widget, area):
            return target
    return None


def _on_global_mousewheel(event: tk.Event) -> str | None:
    target = _locate_scroll_target(event)
    if target is None or not hasattr(target, "yview_scroll"):
        return None
    scroll_target = target  # type: ignore[assignment]
    delta = getattr(event, "delta", 0)
    if delta == 0:
        return "break"
    try:
        steps = int(-1 * (delta / 120))
    except Exception:
        steps = -1 if delta > 0 else 1
    if steps == 0:
        steps = -1 if delta > 0 else 1
    try:
        cast_target: _YScrollable = scroll_target  # type: ignore[assignment]
        cast_target.yview_scroll(steps, "units")
    except tk.TclError:
        return None
    return "break"


def _on_global_linux_scroll(event: tk.Event) -> str | None:
    target = _locate_scroll_target(event)
    if target is None or not hasattr(target, "yview_scroll"):
        return None
    scroll_target = target  # type: ignore[assignment]
    direction = -1 if getattr(event, "num", 5) == 4 else 1
    try:
        cast_target: _YScrollable = scroll_target  # type: ignore[assignment]
        cast_target.yview_scroll(direction, "units")
    except tk.TclError:
        return None
    return "break"


def _ensure_global_scroll_binding(area: tk.Misc) -> None:
    global _SCROLL_BINDING_INITIALIZED
    if _SCROLL_BINDING_INITIALIZED:
        return
    try:
        root = area.winfo_toplevel()
        if root:
            root.bind_all("<MouseWheel>", _on_global_mousewheel, add="+")
            root.bind_all("<Button-4>", _on_global_linux_scroll, add="+")
            root.bind_all("<Button-5>", _on_global_linux_scroll, add="+")
            _SCROLL_BINDING_INITIALIZED = True
    except Exception:
        _SCROLL_BINDING_INITIALIZED = True


def bind_mousewheel(area: tk.Misc, target: tk.Misc | None = None) -> None:
    """
    Enable mousewheel scrolling on `target` when the pointer is over `area`.

    If `target` is omitted, the area itself is used as the scroll target.
    """
    _ensure_global_scroll_binding(area)
    _SCROLL_AREAS.append((area, target or area))


__all__ = ["bind_mousewheel"]
