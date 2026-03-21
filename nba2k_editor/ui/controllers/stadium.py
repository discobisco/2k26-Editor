"""Stadium workflow controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ..full_editor_launch import launch_full_editor_process as _launch_full_editor_process


def current_stadium_index(app: Any) -> int | None:
    sel = get_selected_stadium_indices(app)
    return sel[0] if sel else None


def refresh_stadium_list(app: Any) -> None:
    try:
        entries = app.model.refresh_stadiums()
        app.stadium_status_var.set("" if entries else "No stadiums detected; pointers may be missing.")
    except Exception:
        entries = []
        app.stadium_status_var.set("Unable to scan stadiums.")
    if getattr(app, "stadium_status_text_tag", None):
        dpg.set_value(app.stadium_status_text_tag, app.stadium_status_var.get())
    app.stadium_entries = entries
    filter_stadium_list(app)


def filter_stadium_list(app: Any, *_args) -> None:
    query = (app.stadium_search_var.get() or "").strip().lower()
    app._filtered_stadium_entries = [
        entry for entry in app.stadium_entries if not query or query in entry[1].lower()
    ]
    items = get_stadium_list_items(app)
    empty_text_tag = getattr(app, "stadium_empty_text_tag", None)
    has_items = bool(items)
    if empty_text_tag and dpg.does_item_exist(empty_text_tag):
        dpg.configure_item(empty_text_tag, show=not has_items)
    if app.stadium_list_container and not app.stadium_listbox_tag:
        with dpg.group(parent=app.stadium_list_container):
            app.stadium_listbox_tag = dpg.add_listbox(items=items, num_items=18, callback=app._on_stadium_selected)
    elif app.stadium_listbox_tag and dpg.does_item_exist(app.stadium_listbox_tag):
        dpg.configure_item(app.stadium_listbox_tag, items=items)
    app.stadium_count_var.set(f"Stadiums: {len(app._filtered_stadium_entries)}")
    if getattr(app, "stadium_count_text_tag", None):
        dpg.set_value(app.stadium_count_text_tag, app.stadium_count_var.get())
    if app._filtered_stadium_entries:
        selected_index = app.selected_stadium_index
        if selected_index is None or all(entry[0] != selected_index for entry in app._filtered_stadium_entries):
            selected_index = app._filtered_stadium_entries[0][0]
        set_stadium_selection(app, [selected_index])
    else:
        app.selected_stadium_index = None
        on_stadium_selected(app, app.stadium_listbox_tag, None)


def on_stadium_selected(app: Any, _sender=None, app_data=None) -> None:
    selected_index = None
    if isinstance(app_data, str):
        selected_index = next(
            (entry_index for entry_index, label in app._filtered_stadium_entries if label == app_data),
            None,
        )
    app.selected_stadium_index = selected_index
    if app.btn_stadium_full and dpg.does_item_exist(app.btn_stadium_full):
        dpg.configure_item(app.btn_stadium_full, enabled=selected_index is not None)


def open_full_stadium_editor(app: Any, stadium_idx: int | None = None) -> None:
    if stadium_idx is None:
        stadium_idx = current_stadium_index(app)
    if stadium_idx is None:
        app.show_info("Stadium Editor", "Select a stadium first.")
        return
    try:
        _launch_full_editor_process(editor="stadium", index=stadium_idx)
    except Exception as exc:
        app.show_error("Stadium Editor", f"Unable to open stadium editor window: {exc}")


def get_stadium_list_items(app: Any) -> list[str]:
    return [name for _, name in app._filtered_stadium_entries] if app._filtered_stadium_entries else []


def get_selected_stadium_indices(app: Any) -> list[int]:
    selected_index = app.selected_stadium_index
    if selected_index is None:
        return []
    return [selected_index]


def set_stadium_selection(app: Any, positions: list[int]) -> None:
    if not positions:
        app.selected_stadium_index = None
        on_stadium_selected(app, app.stadium_listbox_tag, None)
        return
    target = positions[0]
    idx = next((pos for pos, entry in enumerate(app._filtered_stadium_entries) if entry[0] == target), None)
    if idx is None:
        return
    app.selected_stadium_index = target
    items = get_stadium_list_items(app)
    if app.stadium_listbox_tag and dpg.does_item_exist(app.stadium_listbox_tag):
        dpg.set_value(app.stadium_listbox_tag, items[idx])
    on_stadium_selected(app, app.stadium_listbox_tag, items[idx])
