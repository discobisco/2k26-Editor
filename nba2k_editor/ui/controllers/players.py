"""Players workflow controller helpers."""
from __future__ import annotations

import queue
import re
import threading
from typing import Any

import dearpygui.dearpygui as dpg

from ...core.conversions import (
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    format_height_inches,
    raw_height_to_inches,
)
from ...models.player import Player
from ..full_editor_launch import launch_full_editor_process as _launch_full_editor_process


def render_player_list(app: Any, items: list[str] | None = None, message: str | None = None) -> None:
    if app.player_list_container is None or not dpg.does_item_exist(app.player_list_container):
        return
    if items is None:
        items = []
    if message:
        items = [message]
    if not app.player_listbox_tag or not dpg.does_item_exist(app.player_listbox_tag):
        with dpg.group(parent=app.player_list_container):
            app.player_listbox_tag = dpg.add_listbox(
                items=items,
                num_items=28,
                callback=app._on_player_selected,
            )
    else:
        dpg.configure_item(app.player_listbox_tag, items=items)
    if not items or message:
        app.clear_player_selection()
        return
    app.set_selected_player_indices([0])


def start_scan(app: Any) -> None:
    app._start_roster_scan(apply_pending_team_select=False)


def scan_thread(app: Any) -> None:
    app._run_roster_scan(apply_pending_team_select=False)


def start_roster_scan(app: Any, *, apply_pending_team_select: bool) -> None:
    if app.scanning:
        return
    app.scanning = True
    status_msg = "Scanning... please wait"
    app.scan_status_var.set(status_msg)
    app.team_scan_status_var.set(status_msg)
    app._render_player_list(message="Scanning players...")
    run_roster_scan(app, apply_pending_team_select=apply_pending_team_select)


def run_roster_scan(app: Any, *, apply_pending_team_select: bool) -> None:
    teams: list[str] = []
    error_msg = ""
    try:
        app.model.refresh_players()
        teams = app.model.get_teams()
    except Exception as exc:
        error_msg = str(exc) or exc.__class__.__name__

    def update_ui() -> None:
        app.scanning = False
        app._update_team_dropdown(teams)
        app._refresh_player_list()
        status_msg = ""
        if error_msg:
            status_msg = f"Scan failed: {error_msg}"
        elif not app.model.mem.hproc:
            status_msg = "NBA 2K26 is not running."
        elif not teams:
            status_msg = "No teams available."
        app.scan_status_var.set(status_msg)
        app.team_scan_status_var.set(status_msg)
        if apply_pending_team_select and not error_msg and app._pending_team_select and app._pending_team_select in teams:
            app.team_edit_var.set(app._pending_team_select)
            app._on_team_edit_selected()
            app._pending_team_select = None

    update_ui()


def refresh_player_list(app: Any) -> None:
    team = (app.team_var.get() or "").strip()
    if not team:
        team = "All Players"
    try:
        app.team_var.set(team)
    except Exception:
        pass
    if team.lower() == "all players" and not app.model.players:
        status_msg = "Players not loaded. Click Scan to load players."
        if app.scanning:
            status_msg = "Scanning... please wait"
        elif not app.model.mem.hproc:
            status_msg = "NBA 2K26 is not running."
        app.scan_status_var.set(status_msg)
        app.team_scan_status_var.set(status_msg)
    team_lower = team.lower()
    if team_lower == "draft prospects":
        app.current_players = app.model.get_draft_prospects()
    elif team_lower == "free agents":
        app.current_players = app.model.get_free_agents_by_flags()
    else:
        app.current_players = app.model.get_players_by_team(team) if team else []
    app.selected_player = None
    app.selected_players = []
    app._filter_player_list()
    if app.filtered_player_indices:
        app.set_selected_player_indices([0])
    else:
        app._update_detail_fields()


def filter_player_list(app: Any) -> None:
    search = (app.player_search_var.get() or "").strip().lower()
    if search == "search players.":
        search = ""
    app.filtered_player_indices = []
    app.player_list_items = []
    if not app.current_players:
        app._render_player_list(message="No players available." if app.model.mem.hproc else "NBA 2K26 is not running.")
        app.player_count_var.set("Players: 0")
        if hasattr(app, "player_count_text_tag") and app.player_count_text_tag:
            dpg.set_value(app.player_count_text_tag, app.player_count_var.get())
        return
    visible_names: list[str] = []
    if not search:
        app.filtered_player_indices = list(range(len(app.current_players)))
        visible_names = [p.full_name for p in app.current_players]
    else:
        for idx, player in enumerate(app.current_players):
            if search in player.full_name.lower():
                app.filtered_player_indices.append(idx)
                visible_names.append(player.full_name)
    if not visible_names:
        app._render_player_list(message="No players match the current filter.")
    else:
        app.player_list_items = visible_names
        app._render_player_list(items=visible_names)
    app.player_count_var.set(f"Players: {len(app.filtered_player_indices)}")
    if getattr(app, "player_count_text_tag", None):
        dpg.set_value(app.player_count_text_tag, app.player_count_var.get())


def on_team_selected(app: Any, _sender, value: str | None) -> None:
    selected_team = value or (app.team_var.get() or "").strip()
    app.team_var.set(selected_team)
    app._refresh_player_list()


def on_player_selected(app: Any, _sender=None, app_data=None) -> None:
    name = str(app_data) if app_data is not None else ""
    idx = app.player_list_items.index(name) if name in app.player_list_items else -1
    selected_players: list[Player] = []
    if 0 <= idx < len(app.filtered_player_indices):
        p_idx = app.filtered_player_indices[idx]
        if 0 <= p_idx < len(app.current_players):
            selected_players.append(app.current_players[p_idx])
    app.selected_players = selected_players
    app.selected_player = selected_players[0] if selected_players else None
    app._update_detail_fields()


def update_detail_fields(app: Any) -> None:
    p = app.selected_player
    selection_count = len(app.selected_players)
    if not p:
        app.player_name_var.set("Select a player")
        app.player_ovr_var.set("OVR --")
        app.var_first.set("")
        app.var_last.set("")
        app.var_player_team.set("")
        for var in app.player_detail_fields.values():
            var.set("--")
        if app.btn_save:
            dpg.configure_item(app.btn_save, enabled=False)
        if app.btn_edit:
            dpg.configure_item(app.btn_edit, enabled=False)
        if app.btn_copy:
            dpg.configure_item(app.btn_copy, enabled=False)
        if app.btn_player_export:
            dpg.configure_item(app.btn_player_export, enabled=False)
        if app.btn_player_import:
            dpg.configure_item(app.btn_player_import, enabled=False)
    else:
        display_name = p.full_name or f"Player {p.index}"
        if selection_count > 1:
            display_name = f"{display_name} (+{selection_count - 1} more)"
        app.player_name_var.set(display_name)
        app.var_first.set(p.first_name)
        app.var_last.set(p.last_name)
        team_display = p.team
        try:
            if app.model.is_player_free_agent_group(p):
                team_display = ""
        except Exception:
            team_display = p.team
        app.var_player_team.set(team_display)
        snapshot: dict[str, object] = {}
        try:
            snapshot = app.model.get_player_panel_snapshot(p)
        except Exception:
            snapshot = {}
        overall_val = snapshot.get("Overall")
        if isinstance(overall_val, (int, float)):
            app.player_ovr_var.set(f"OVR {int(overall_val)}")
        else:
            app.player_ovr_var.set("OVR --")

        def _format_detail(label: str, value: object) -> str:
            if label == "Height" and isinstance(value, (int, float)):
                inches_val = int(value)
                if inches_val > HEIGHT_MAX_INCHES:
                    inches_val = raw_height_to_inches(inches_val)
                inches_val = max(HEIGHT_MIN_INCHES, min(HEIGHT_MAX_INCHES, inches_val))
                return format_height_inches(inches_val)
            if value is None:
                return "--"
            if isinstance(value, float):
                return f"{value:.3f}".rstrip("0").rstrip(".") or "0"
            return str(value)

        for label, var in app.player_detail_fields.items():
            var.set(_format_detail(label, snapshot.get(label)))
            widget = app.player_detail_widgets.get(label)
            if widget and dpg.does_item_exist(widget):
                dpg.set_value(widget, var.get())
    if getattr(app, "player_name_text", None):
        dpg.set_value(app.player_name_text, app.player_name_var.get())
    if getattr(app, "player_ovr_text", None):
        dpg.set_value(app.player_ovr_text, app.player_ovr_var.get())
    enable_save = app.model.mem.hproc is not None and not getattr(app.model, "external_loaded", False)
    if app.btn_save:
        dpg.configure_item(app.btn_save, enabled=enable_save)
    if app.btn_edit:
        dpg.configure_item(app.btn_edit, enabled=bool(p))
    enable_copy = enable_save and p is not None
    if app.btn_copy:
        dpg.configure_item(app.btn_copy, enabled=enable_copy)
    enable_io = app.model.mem.hproc is not None and p is not None
    if app.btn_player_export:
        dpg.configure_item(app.btn_player_export, enabled=enable_io)
    if app.btn_player_import:
        dpg.configure_item(app.btn_player_import, enabled=enable_io)
    inspector = getattr(app, "player_panel_inspector", None)
    if inspector:
        try:
            inspector.refresh_for_player()
        except Exception:
            pass


def save_player(app: Any) -> None:
    p = app.selected_player
    if not p:
        return
    p.first_name = str(app.var_first.get()).strip()
    p.last_name = str(app.var_last.get()).strip()
    try:
        app.model.update_player(p)
        app.show_info("Success", "Player updated successfully")
    except Exception as exc:
        app.show_error("Error", f"Failed to save changes:\n{exc}")
    app._refresh_player_list()


def open_full_editor(app: Any) -> None:
    selected = app.selected_players or ([app.selected_player] if app.selected_player else [])
    if not selected:
        return
    player_indices: list[int] = []
    seen: set[int] = set()
    for player in selected:
        try:
            idx = int(getattr(player, "index", -1))
        except Exception:
            continue
        if idx < 0 or idx in seen:
            continue
        seen.add(idx)
        player_indices.append(idx)
    if not player_indices:
        app.show_error("Player Editor", "Selected players could not be resolved.")
        return
    try:
        _launch_full_editor_process(editor="player", indices=player_indices)
    except Exception as exc:
        app.show_error("Player Editor", f"Unable to open player editor window: {exc}")


def open_copy_dialog(app: Any) -> None:
    src = app.selected_player
    if not src:
        app.show_info("Copy Player Data", "Select a player to copy from.")
        return
    dest_players: list[Player] = []
    if app.model.players:
        dest_players = [p for p in app.model.players if p.index != src.index]
    elif app.model.team_list:
        for idx, _name in app.model.team_list:
            try:
                for p in app.model.scan_team_players(idx):
                    if p.index != src.index:
                        dest_players.append(p)
            except Exception:
                continue
    seen: set[int] = set()
    uniq_dest: list[Player] = []
    for player in dest_players:
        if player.index in seen:
            continue
        seen.add(player.index)
        uniq_dest.append(player)
    dest_players = uniq_dest
    if not dest_players:
        app.show_info("Copy Player Data", "No other players are available to copy to.")
        return
    if app.copy_dialog_tag and dpg.does_item_exist(app.copy_dialog_tag):
        dpg.delete_item(app.copy_dialog_tag)
    app.copy_dialog_tag = dpg.generate_uuid()
    dest_names = [p.full_name for p in dest_players]
    dest_map = {p.full_name: p for p in dest_players}
    with dpg.window(
        label="Copy Player Data",
        tag=app.copy_dialog_tag,
        modal=True,
        no_collapse=True,
        width=440,
        height=340,
    ):
        dpg.add_text(f"Copy from: {src.full_name}")
        dpg.add_spacer(height=6)
        combo_tag = dpg.add_combo(items=dest_names, default_value=dest_names[0], width=260, label="Copy to")
        dpg.add_spacer(height=8)
        chk_full = dpg.add_checkbox(label="Full Player", default_value=False)
        chk_attr = dpg.add_checkbox(label="Attributes", default_value=False)
        chk_tend = dpg.add_checkbox(label="Tendencies", default_value=False)
        chk_badges = dpg.add_checkbox(label="Badges", default_value=False)
        dpg.add_spacer(height=10)

        def _close_dialog() -> None:
            if app.copy_dialog_tag and dpg.does_item_exist(app.copy_dialog_tag):
                dpg.delete_item(app.copy_dialog_tag)
            app.copy_dialog_tag = None

        def _do_copy() -> None:
            dest_name = str(dpg.get_value(combo_tag) or "").strip()
            dest_player = dest_map.get(dest_name)
            if not dest_player:
                app.show_error("Copy Player Data", "No destination player selected.")
                return
            categories: list[str] = []
            if dpg.get_value(chk_full):
                categories = ["full"]
            else:
                if dpg.get_value(chk_attr):
                    categories.append("attributes")
                if dpg.get_value(chk_tend):
                    categories.append("tendencies")
                if dpg.get_value(chk_badges):
                    categories.append("badges")
            if not categories:
                app.show_warning("Copy Player Data", "Please select at least one data category to copy.")
                return
            success = app.model.copy_player_data(
                src.index,
                dest_player.index,
                categories,
                src_record_ptr=getattr(src, "record_ptr", None),
                dst_record_ptr=getattr(dest_player, "record_ptr", None),
            )
            if success:
                app.show_info("Copy Player Data", "Data copied successfully.")
                app._start_scan()
            else:
                app.show_error("Copy Player Data", "Failed to copy data. Make sure the game is running and try again.")
            _close_dialog()

        with dpg.group(horizontal=True):
            dpg.add_button(label="Copy", width=80, callback=lambda *_: _do_copy())
            dpg.add_button(label="Cancel", width=80, callback=lambda *_: _close_dialog())


def export_selected_player(app: Any) -> None:
    try:
        from ...importing.excel_import import export_excel_workbook, template_path_for
    except Exception as exc:
        app.show_error("Excel Export", f"Export helpers not available: {exc}")
        return
    if app._excel_export_thread is not None and app._excel_export_thread.is_alive():
        app.show_info("Excel Export", "An export is already running.")
        return
    player = app.selected_player
    if not player:
        app.show_info("Excel Export", "Select a player to export.")
        return
    if not app.model.mem.open_process():
        app.show_error("Excel Export", "NBA 2K26 is not running.")
        return
    template = template_path_for("players")
    safe_name = re.sub(r'[<>:"/\\\\|?*]', "_", player.full_name or f"Player_{player.index}")
    safe_name = re.sub(r"\\s+", "_", safe_name).strip("_")
    if not safe_name:
        safe_name = f"Player_{player.index}"
    default_name = f"{safe_name}_export.xlsx"

    def _after_choose(path: str) -> None:
        if not path:
            return
        app._reset_excel_progress()
        status = f"Exporting {player.full_name}..."
        app.excel_status_var.set(status)
        if app.excel_status_text_tag and dpg.does_item_exist(app.excel_status_text_tag):
            dpg.set_value(app.excel_status_text_tag, status)
        app._excel_export_entity_label = "Player"
        app._excel_export_queue = queue.Queue()
        progress_cb = app._queue_excel_export_progress

        def _run_export() -> None:
            try:
                result = export_excel_workbook(
                    app.model,
                    path,
                    "players",
                    template_path=template,
                    progress_cb=progress_cb,
                    players=[player],
                )
                if app._excel_export_queue is not None:
                    app._excel_export_queue.put(("done", result, None))
            except Exception as exc:
                if app._excel_export_queue is not None:
                    app._excel_export_queue.put(("done", None, exc))

        app._excel_export_thread = threading.Thread(target=_run_export, daemon=True)
        app._excel_export_thread.start()
        if not app._excel_export_polling:
            app._poll_excel_export()

    app._open_file_dialog(
        "Save player workbook",
        default_path=str(template.parent),
        default_filename=default_name,
        file_types=[("Excel files", ".xlsx")],
        callback=_after_choose,
        save=True,
    )


def import_selected_player(app: Any) -> None:
    try:
        from ...importing.excel_import import import_excel_workbook, template_path_for
    except Exception as exc:
        app.show_error("Excel Import", f"Import helpers not available: {exc}")
        return
    player = app.selected_player
    if not player:
        app.show_info("Excel Import", "Select a player to import.")
        return
    if not app.model.mem.open_process():
        app.show_error("Excel Import", "NBA 2K26 is not running.")
        return
    template = template_path_for("players")

    def _after_choose(path: str) -> None:
        if not path:
            return
        try:
            if not app.model.players:
                app.model.refresh_players()
        except Exception:
            pass
        app._reset_excel_progress()
        status = f"Importing {player.full_name}..."
        app.excel_status_var.set(status)
        if app.excel_status_text_tag and dpg.does_item_exist(app.excel_status_text_tag):
            dpg.set_value(app.excel_status_text_tag, status)
        progress_cb = app._excel_progress_callback("Importing", "Player")
        try:
            result = import_excel_workbook(
                app.model,
                path,
                "players",
                only_names={player.full_name},
                progress_cb=progress_cb,
            )
        except Exception as exc:
            app.excel_status_var.set("")
            if app.excel_status_text_tag and dpg.does_item_exist(app.excel_status_text_tag):
                dpg.set_value(app.excel_status_text_tag, "")
            app._reset_excel_progress()
            app.show_error("Excel Import", f"Import failed: {exc}")
            return
        app.excel_status_var.set("")
        if app.excel_status_text_tag and dpg.does_item_exist(app.excel_status_text_tag):
            dpg.set_value(app.excel_status_text_tag, "")
        app._reset_excel_progress()
        if result.rows_applied:
            app.show_info("Excel Import", result.summary_text())
            app._start_scan()
            return
        if result.missing_names:
            app.show_warning(
                "Excel Import",
                f"No rows matched {player.full_name}. Use the Excel screen to map names.",
            )
            return
        app.show_info("Excel Import", result.summary_text())

    app._open_file_dialog(
        "Select player workbook to import",
        default_path=str(template.parent),
        default_filename=str(template.name),
        file_types=[("Excel files", ".xlsx")],
        callback=_after_choose,
        save=False,
    )


def get_player_list_items(app: Any) -> list[str]:
    return list(app.player_list_items)


def get_selected_player_indices(app: Any) -> list[int]:
    if not app.player_listbox_tag or not dpg.does_item_exist(app.player_listbox_tag):
        return []
    val = dpg.get_value(app.player_listbox_tag)
    if val is None:
        return []
    try:
        idx = app.player_list_items.index(val)
    except ValueError:
        return []
    return [idx]


def set_selected_player_indices(app: Any, indices: list[int]) -> None:
    if not indices:
        return
    idx = indices[0]
    if 0 <= idx < len(app.player_list_items) and app.player_listbox_tag and dpg.does_item_exist(app.player_listbox_tag):
        dpg.set_value(app.player_listbox_tag, app.player_list_items[idx])
        app._on_player_selected(app.player_listbox_tag, app.player_list_items[idx])


def clear_player_selection(app: Any) -> None:
    if app.player_listbox_tag and dpg.does_item_exist(app.player_listbox_tag):
        try:
            dpg.set_value(app.player_listbox_tag, None)
        except Exception:
            pass
    app.selected_player = None
    app.selected_players = []
    app._update_detail_fields()


def roster_needs_refresh(app: Any) -> bool:
    try:
        players_dirty = bool(app.model.is_dirty("players"))
        teams_dirty = bool(app.model.is_dirty("teams"))
        if players_dirty or teams_dirty:
            return True
    except Exception:
        pass
    if not getattr(app.model, "players", None):
        return True
    if not getattr(app.model, "team_list", None):
        return True
    return False


def ensure_roster_loaded(app: Any, *, apply_pending_team_select: bool, force: bool = False) -> None:
    if force or app._roster_needs_refresh():
        app._start_roster_scan(apply_pending_team_select=apply_pending_team_select)
        return
    try:
        teams = app.model.get_teams()
    except Exception:
        teams = []
    app._update_team_dropdown(teams)
    app._refresh_player_list()
    status_msg = ""
    if not app.model.mem.hproc:
        status_msg = "NBA 2K26 is not running."
    elif not teams:
        status_msg = "No teams available."
    app.scan_status_var.set(status_msg)
    app.team_scan_status_var.set(status_msg)
    if apply_pending_team_select and app._pending_team_select and app._pending_team_select in teams:
        app.team_edit_var.set(app._pending_team_select)
        app._on_team_edit_selected()
        app._pending_team_select = None


def update_team_dropdown(app: Any, teams: list[str]) -> None:
    special_filters = ["Free Agents", "Draft Prospects"]

    def _append_unique(values: list[str], name: str) -> None:
        if not name:
            return
        if any(existing.lower() == name.lower() for existing in values):
            return
        values.append(name)

    app.all_team_names = list(teams or [])
    if app.team_combo_tag and dpg.does_item_exist(app.team_combo_tag):
        previous_selection = app.team_var.get()
        player_list = ["All Players"]
        for name in special_filters:
            _append_unique(player_list, name)
        for name in teams or []:
            _append_unique(player_list, name)
        dpg.configure_item(app.team_combo_tag, items=player_list)
        if previous_selection in player_list:
            app.team_var.set(previous_selection)
            dpg.set_value(app.team_combo_tag, previous_selection)
        elif player_list:
            app.team_var.set(player_list[0])
            dpg.set_value(app.team_combo_tag, player_list[0])
    app.team_list_items = list(teams or [])
    app._filter_team_list()
