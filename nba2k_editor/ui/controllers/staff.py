"""Staff workflow controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ..full_editor_launch import launch_full_editor_process as _launch_full_editor_process


_EMPTY_MESSAGE = "No staff found."


def current_staff_index(app: Any) -> int | None:
    sel = get_selected_staff_indices(app)
    return sel[0] if sel else None


def refresh_staff_list(app: Any) -> None:
    try:
        entries = app.model.refresh_staff()
        app.staff_status_var.set("" if entries else "No staff detected; pointers may be missing.")
    except Exception:
        entries = []
        app.staff_status_var.set("Unable to scan staff.")
    if getattr(app, "staff_status_text_tag", None):
        dpg.set_value(app.staff_status_text_tag, app.staff_status_var.get())
    app.staff_entries = entries
    filter_staff_list(app)


def filter_staff_list(app: Any, *_args) -> None:
    query = (app.staff_search_var.get() or "").strip().lower()
    app._filtered_staff_entries = [
        entry for entry in app.staff_entries if not query or query in entry[1].lower()
    ]
    items = get_staff_list_items(app) or [_EMPTY_MESSAGE]
    if app.staff_list_container and not app.staff_listbox_tag:
        with dpg.group(parent=app.staff_list_container):
            app.staff_listbox_tag = dpg.add_listbox(items=items, num_items=18, callback=app._on_staff_selected)
    elif app.staff_listbox_tag and dpg.does_item_exist(app.staff_listbox_tag):
        dpg.configure_item(app.staff_listbox_tag, items=items)
    app.staff_count_var.set(f"Staff: {len(app._filtered_staff_entries)}")
    if getattr(app, "staff_count_text_tag", None):
        dpg.set_value(app.staff_count_text_tag, app.staff_count_var.get())
    if app._filtered_staff_entries and app.staff_listbox_tag:
        dpg.set_value(app.staff_listbox_tag, items[0])
        on_staff_selected(app, app.staff_listbox_tag, items[0])
    else:
        on_staff_selected(app, app.staff_listbox_tag, _EMPTY_MESSAGE)


def on_staff_selected(app: Any, _sender=None, app_data=None) -> None:
    if app.btn_staff_full and dpg.does_item_exist(app.btn_staff_full):
        enabled = bool(app_data and isinstance(app_data, str) and app_data != _EMPTY_MESSAGE)
        dpg.configure_item(app.btn_staff_full, enabled=enabled)


def open_full_staff_editor(app: Any, staff_idx: int | None = None) -> None:
    if staff_idx is None:
        staff_idx = current_staff_index(app)
    if staff_idx is None:
        app.show_info("Staff Editor", "Select a staff member first.")
        return
    try:
        _launch_full_editor_process(editor="staff", index=staff_idx)
    except Exception as exc:
        app.show_error("Staff Editor", f"Unable to open staff editor window: {exc}")


def get_staff_list_items(app: Any) -> list[str]:
    return [name for _, name in app._filtered_staff_entries] if app._filtered_staff_entries else []


def get_selected_staff_indices(app: Any) -> list[int]:
    if not app.staff_listbox_tag or not dpg.does_item_exist(app.staff_listbox_tag):
        return []
    value = dpg.get_value(app.staff_listbox_tag)
    items = get_staff_list_items(app)
    if value in items:
        pos = items.index(value)
        if 0 <= pos < len(app._filtered_staff_entries):
            return [app._filtered_staff_entries[pos][0]]
    return []


def set_staff_selection(app: Any, positions: list[int]) -> None:
    if not positions or not app.staff_listbox_tag:
        return
    target = positions[0]
    items = get_staff_list_items(app)
    idx = next((pos for pos, entry in enumerate(app._filtered_staff_entries) if entry[0] == target), None)
    if idx is None and 0 <= target < len(items):
        idx = target
    if idx is not None and 0 <= idx < len(items):
        dpg.set_value(app.staff_listbox_tag, items[idx])
        on_staff_selected(app, app.staff_listbox_tag, items[idx])
