"""Teams screen for the Dear PyGui UI."""
from __future__ import annotations

import dearpygui.dearpygui as dpg
from ..core.offsets import TEAM_FIELD_DEFS


def build_teams_screen(app) -> None:
    with dpg.child_window(
        tag="screen_teams",
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags["teams"] = tag

        with dpg.group(horizontal=True):
            dpg.add_text("Search")
            app.team_search_input_tag = dpg.add_input_text(
                hint="Search teams.",
                width=240,
                callback=lambda _s, value: _on_search_changed(app, value),
            )
            dpg.add_button(label="Refresh", width=90, callback=app._start_team_scan)
            app.team_count_text_tag = dpg.add_text(app.team_count_var.get())
        app.team_scan_status_text_tag = dpg.add_text(
            app.team_scan_status_var.get(),
            color=(155, 164, 181, 255),
        )
        dpg.add_spacer(height=8)

        with dpg.group(horizontal=True):
            with dpg.child_window(tag="team_list_container", width=340, autosize_y=True, border=True) as list_container:
                app.team_list_container = list_container
                dpg.add_text("No teams available.")

            with dpg.child_window(tag="team_detail_container", autosize_x=True, autosize_y=True, border=True, menubar=False):
                app.team_editor_detail_name_tag = dpg.add_text(
                    "Select a team",
                    color=(224, 225, 221, 255),
                )
                app.team_status_text_tag = dpg.add_text(
                    app.team_scan_status_var.get(),
                    color=(155, 164, 181, 255),
                    wrap=520,
                )
                dpg.add_spacer(height=6)
                app.team_field_input_tags = {}
                if TEAM_FIELD_DEFS:
                    for label in TEAM_FIELD_DEFS.keys():
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"{label}:", color=(200, 208, 214, 255))
                            tag_input = dpg.add_input_text(
                                width=-1,
                                callback=lambda _s, _a, key=label: app._on_team_field_changed(key),
                            )
                            app.team_field_input_tags[label] = tag_input
                else:
                    dpg.add_text(
                        "No team field offsets found. Update Offsets/offsets.json to enable editing.",
                        color=(192, 80, 64, 255),
                        wrap=500,
                    )
                dpg.add_spacer(height=10)
                with dpg.group(horizontal=True):
                    app.btn_team_save = dpg.add_button(
                        label="Save Fields",
                        width=120,
                        enabled=False,
                        callback=app._save_team,
                    )
                    app.btn_team_full = dpg.add_button(
                        label="Edit Team",
                        width=120,
                        enabled=False,
                        callback=app._open_full_team_editor,
                    )
                dpg.add_spacer(height=10)
                dpg.add_text("Team Players", color=(224, 225, 221, 255))
                with dpg.child_window(border=True, height=220, autosize_x=True):
                    app.team_players_listbox_tag = dpg.add_listbox(
                        items=["(No players found)"],
                        num_items=12,
                        callback=app._on_team_player_selected,
                    )
                with dpg.group(horizontal=True):
                    app.btn_team_player = dpg.add_button(
                        label="Open Player",
                        width=120,
                        enabled=False,
                        callback=app._open_team_player_editor,
                    )


def _on_search_changed(app, value: str) -> None:
    app.team_search_var.set(value or "")
    app._filter_team_list()


__all__ = ["build_teams_screen"]
