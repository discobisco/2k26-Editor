"""Trade Players screen for Dear PyGui UI."""
from __future__ import annotations

import dearpygui.dearpygui as dpg


def build_trade_players_screen(app) -> None:
    """Build the trade players screen and wire callbacks into the app."""
    with dpg.child_window(tag="screen_trade", parent=app.content_root, autosize_x=True, autosize_y=True, show=False) as tag:
        app.screen_tags["trade"] = tag

        with dpg.group(horizontal=True):
            dpg.add_text("Add Team")
            app.trade_add_team_combo_tag = dpg.add_combo(
                items=app.trade_team_options,
                width=220,
                callback=lambda s, v: app._trade_add_participant(v),
            )
            dpg.add_spacer(width=10)
            dpg.add_text("Participants")
            app.trade_participants_list_tag = dpg.add_listbox(
                items=[],
                num_items=6,
                width=220,
                callback=app._trade_set_active_team_from_list,
            )
            dpg.add_spacer(width=10)
            dpg.add_button(label="Trade Players", width=140, callback=app._trade_open_player_modal)

        dpg.add_spacer(height=8)

        with dpg.group(horizontal=True):
            dpg.add_text("Trade Slot")
            app.trade_slot_combo_tag = dpg.add_combo(
                items=[f"Slot {i+1}" for i in range(36)],
                default_value="Slot 1",
                width=120,
                callback=lambda s, v: app._trade_select_slot(v),
            )
            dpg.add_spacer(width=12)
            dpg.add_button(label="Clear Slot", width=100, callback=app._trade_clear_slot)

        dpg.add_spacer(height=8)

        with dpg.group(horizontal=True):
            with dpg.child_window(border=True, width=360, height=260):
                dpg.add_text("Outgoing Players by Team")
                app.trade_outgoing_container = dpg.add_child_window(border=False, width=-1, height=-1)
            with dpg.child_window(border=True, width=360, height=260):
                dpg.add_text("Incoming Players by Team")
                app.trade_incoming_container = dpg.add_child_window(border=False, width=-1, height=-1)

        dpg.add_spacer(height=8)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Propose Trade", width=140, callback=app._trade_propose)
            dpg.add_button(label="Clear Packages", width=140, callback=app._trade_clear)
            app.trade_status_text_tag = dpg.add_text(app.trade_status_var.get(), wrap=420)

__all__ = ["build_trade_players_screen"]
