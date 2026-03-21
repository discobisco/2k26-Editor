"""Staff workflow controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ..full_editor_launch import launch_full_editor_process as _launch_full_editor_process


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
    items = get_staff_list_items(app)
    empty_text_tag = getattr(app, "staff_empty_text_tag", None)
    has_items = bool(items)
    if empty_text_tag and dpg.does_item_exist(empty_text_tag):
        dpg.configure_item(empty_text_tag, show=not has_items)
    if app.staff_list_container and not app.staff_listbox_tag:
        with dpg.group(parent=app.staff_list_container):
            app.staff_listbox_tag = dpg.add_listbox(items=items, num_items=18, callback=app._on_staff_selected)
    elif app.staff_listbox_tag and dpg.does_item_exist(app.staff_listbox_tag):
        dpg.configure_item(app.staff_listbox_tag, items=items)
    app.staff_count_var.set(f"Staff: {len(app._filtered_staff_entries)}")
    if getattr(app, "staff_count_text_tag", None):
        dpg.set_value(app.staff_count_text_tag, app.staff_count_var.get())
    if app._filtered_staff_entries:
        selected_index = app.selected_staff_index
        if selected_index is None or all(entry[0] != selected_index for entry in app._filtered_staff_entries):
            selected_index = app._filtered_staff_entries[0][0]
        set_staff_selection(app, [selected_index])
    else:
        app.selected_staff_index = None
        on_staff_selected(app, app.staff_listbox_tag, None)


def on_staff_selected(app: Any, _sender=None, app_data=None) -> None:
    selected_index = None
    if isinstance(app_data, str):
        selected_index = next(
            (entry_index for entry_index, label in app._filtered_staff_entries if label == app_data),
            None,
        )
    app.selected_staff_index = selected_index
    if app.btn_staff_full and dpg.does_item_exist(app.btn_staff_full):
        dpg.configure_item(app.btn_staff_full, enabled=selected_index is not None)


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
    selected_index = app.selected_staff_index
    if selected_index is None:
        return []
    return [selected_index]


def set_staff_selection(app: Any, positions: list[int]) -> None:
    if not positions:
        app.selected_staff_index = None
        on_staff_selected(app, app.staff_listbox_tag, None)
        return
    target = positions[0]
    idx = next((pos for pos, entry in enumerate(app._filtered_staff_entries) if entry[0] == target), None)
    if idx is None:
        return
    app.selected_staff_index = target
    items = get_staff_list_items(app)
    if app.staff_listbox_tag and dpg.does_item_exist(app.staff_listbox_tag):
        dpg.set_value(app.staff_listbox_tag, items[idx])
    on_staff_selected(app, app.staff_listbox_tag, items[idx])
