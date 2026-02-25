"""Players screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg



def build_players_screen(app) -> None:
    with dpg.child_window(tag="screen_players", parent=app.content_root, autosize_x=True, autosize_y=True, show=False) as tag:
        app.screen_tags["players"] = tag
        with dpg.group(horizontal=True):
            dpg.add_text("Search")
            app.player_search_input_tag = dpg.add_input_text(
                hint="Search players.",
                width=220,
                callback=lambda s, a: _on_search_changed(app, a),
            )
            dpg.add_button(label="Refresh", callback=app._start_scan, width=90)
            dpg.add_spacer(width=10)
            dpg.add_text("Player Dataset")
            app.dataset_combo_tag = dpg.add_combo(items=["All Data"], default_value="All Data")
            dpg.add_spacer(width=10)
            app.player_count_text_tag = dpg.add_text(app.player_count_var.get())
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_text("Team")
            app.team_combo_tag = dpg.add_combo(items=[], width=220, callback=lambda s, a: app._on_team_selected(None, a))
            app.scan_status_text_tag = dpg.add_text(app.scan_status_var.get(), color=(155, 164, 181, 255))
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="player_list_container", width=420, autosize_y=True) as list_container:
                app.player_list_container = list_container
                dpg.add_text("No players available.")
            with dpg.child_window(tag="player_detail_container", autosize_x=True, autosize_y=True, border=True):
                _build_player_detail_panel(app)


def _on_search_changed(app, value: str) -> None:
    app.player_search_var.set(value or "")
    app._filter_player_list()


def _build_player_detail_panel(app):
    app.player_name_text = dpg.add_text(app.player_name_var.get(), bullet=False, color=(224, 225, 221, 255))
    app.player_ovr_text = dpg.add_text(app.player_ovr_var.get(), color=(230, 57, 70, 255))
    dpg.add_spacer(height=6)
    with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, row_background=False, resizable=False):
        # Define columns once before adding rows (DPG requirement).
        dpg.add_table_column()
        dpg.add_table_column()
        labels_defaults = [
            ("Position", "--"),
            ("Number", "--"),
            ("Height", "--"),
            ("Weight", "--"),
            ("Face ID", "--"),
            ("Unique ID", "--"),
        ]
        app.player_detail_fields = {}
        app.player_detail_widgets = {}
        for label, default in labels_defaults:
            with dpg.table_row():
                dpg.add_text(label)
                val_tag = dpg.add_text(default, color=(155, 164, 181, 255))
            app.player_detail_fields[label] = app.player_detail_fields.get(label) or app.player_detail_fields.setdefault(label, app.var_first.__class__(default))
            app.player_detail_widgets[label] = val_tag
    dpg.add_spacer(height=8)
    with dpg.group(horizontal=True):
        app.btn_edit = dpg.add_button(label="Edit Player", callback=app._open_full_editor, enabled=False)
        app.btn_copy = dpg.add_button(label="Copy Player", callback=app._open_copy_dialog, enabled=False)
    with dpg.group(horizontal=True):
        export_cb = app._export_selected_player if hasattr(app, "_export_selected_player") else (lambda *_a, **_k: None)
        import_cb = app._import_selected_player if hasattr(app, "_import_selected_player") else (lambda *_a, **_k: None)
        app.btn_player_export = dpg.add_button(label="Export Player", callback=export_cb, enabled=False)
        app.btn_player_import = dpg.add_button(label="Import Player", callback=import_cb, enabled=False)


__all__ = ["build_players_screen"]
