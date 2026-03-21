"""Teams workflow controller helpers."""
from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ..full_editor_launch import launch_full_editor_process as _launch_full_editor_process


def ensure_team_listbox(app: Any) -> None:
    if app.team_list_container is None or not dpg.does_item_exist(app.team_list_container):
        return
    if not app.team_listbox_tag or not dpg.does_item_exist(app.team_listbox_tag):
        with dpg.group(parent=app.team_list_container):
            app.team_listbox_tag = dpg.add_listbox(
                items=app.team_list_items,
                num_items=20,
                callback=app._on_team_listbox_select,
            )


def start_team_scan(app: Any) -> None:
    app._start_roster_scan(apply_pending_team_select=True)


def scan_teams_thread(app: Any) -> None:
    app._run_roster_scan(apply_pending_team_select=True)


def filter_team_list(app: Any, *_args) -> None:
    if not app.team_list_container:
        return
    query_raw = (app.team_search_var.get() or "").strip().lower()
    placeholder = "search teams."
    teams = list(app.all_team_names or [])
    if teams and query_raw and query_raw != placeholder:
        filtered = [team_name for team_name in teams if query_raw in str(team_name).lower()]
    else:
        filtered = teams
    app.filtered_team_names = filtered
    app.team_list_items = filtered
    app._ensure_team_listbox()
    empty_text_tag = getattr(app, "team_empty_text_tag", None)
    has_items = bool(filtered)
    if empty_text_tag and dpg.does_item_exist(empty_text_tag):
        dpg.configure_item(empty_text_tag, show=not has_items)
    if not app.team_listbox_tag or not dpg.does_item_exist(app.team_listbox_tag):
        return
    dpg.configure_item(app.team_listbox_tag, items=filtered)
    target_name = app.team_edit_var.get()
    if not target_name or target_name not in filtered:
        target_name = filtered[0] if filtered else ""
        app.team_edit_var.set(target_name)
    if target_name:
        try:
            dpg.set_value(app.team_listbox_tag, target_name)
        except Exception:
            pass
    app.team_count_var.set(f"Teams: {len(filtered)}")
    if getattr(app, "team_count_text_tag", None):
        dpg.set_value(app.team_count_text_tag, app.team_count_var.get())
    app._on_team_edit_selected()


def on_team_listbox_select(app: Any, _sender, app_data) -> None:
    name = str(app_data) if app_data is not None else ""
    app.team_edit_var.set(name)
    app._on_team_edit_selected()


def on_team_edit_selected(app: Any) -> None:
    team_name = app.team_edit_var.get()
    if getattr(app, "team_editor_detail_name_tag", None):
        dpg.set_value(app.team_editor_detail_name_tag, team_name if team_name else "Select a team")
    if not team_name:
        if app.btn_team_save:
            dpg.configure_item(app.btn_team_save, enabled=False)
        if app.btn_team_full:
            dpg.configure_item(app.btn_team_full, enabled=False)
        for var in app.team_field_vars.values():
            var.set("")
        for tag in app.team_field_input_tags.values():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, "")
        return
    teams = app.model.get_teams()
    team_idx = app.model._team_index_for_display_name(team_name)
    if team_idx is None:
        try:
            team_idx = teams.index(team_name)
        except ValueError:
            if app.btn_team_save:
                dpg.configure_item(app.btn_team_save, enabled=False)
            if app.btn_team_full:
                dpg.configure_item(app.btn_team_full, enabled=False)
            return
    fields = app.model.get_team_fields(team_idx)
    if not isinstance(fields, dict):
        for var in app.team_field_vars.values():
            var.set("")
        if app.btn_team_save:
            dpg.configure_item(app.btn_team_save, enabled=False)
        return
    for label, var in app.team_field_vars.items():
        val = fields.get(label, "")
        var.set(val)
        tag = app.team_field_input_tags.get(label)
        if tag and dpg.does_item_exist(tag):
            dpg.set_value(tag, str(val))
    enable_live = bool(app.model.mem.hproc)
    if app.btn_team_save:
        dpg.configure_item(app.btn_team_save, enabled=enable_live)
    if app.btn_team_full:
        dpg.configure_item(app.btn_team_full, enabled=enable_live)


def on_team_field_changed(app: Any, label: str) -> None:
    tag = app.team_field_input_tags.get(label)
    if not tag or not dpg.does_item_exist(tag):
        return
    value = dpg.get_value(tag)
    app.team_field_vars[label].set(value)


def save_team(app: Any) -> None:
    team_name = app.team_edit_var.get()
    if not team_name:
        return
    teams = app.model.get_teams()
    team_idx = app.model._team_index_for_display_name(team_name)
    if team_idx is None:
        try:
            team_idx = teams.index(team_name)
        except ValueError:
            return
    values = {label: var.get() for label, var in app.team_field_vars.items()}
    ok = app.model.set_team_fields(team_idx, values)
    if ok:
        app.show_info("Success", f"Updated {team_name} successfully.")
        app.model.refresh_players()
        teams = app.model.get_teams()
        app._update_team_dropdown(teams)
        new_name = values.get("Team Name")
        if new_name:
            app.team_edit_var.set(str(new_name))
        app._on_team_edit_selected()
    else:
        app.show_error("Error", "Failed to write team data. Make sure the game is running and try again.")


def open_full_team_editor(app: Any) -> None:
    team_name = app.team_edit_var.get()
    if not team_name:
        app.show_info("Edit Team", "Please select a team first.")
        return
    teams = app.model.get_teams()
    if not teams:
        app.show_info("Edit Team", "No teams available. Refresh and try again.")
        return
    team_idx = app.model._team_index_for_display_name(team_name)
    if team_idx is None:
        try:
            team_idx = teams.index(team_name)
        except ValueError:
            app.show_error("Edit Team", "Selected team could not be resolved.")
            return
    try:
        _launch_full_editor_process(editor="team", index=team_idx)
    except Exception as exc:
        app.show_error("Edit Team", f"Unable to open team editor window: {exc}")

