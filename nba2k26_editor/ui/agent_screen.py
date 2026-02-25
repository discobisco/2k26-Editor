"""GM Agent screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..core.config import TEXT_PRIMARY, TEXT_SECONDARY


def build_agent_screen(app) -> None:
    with dpg.child_window(
        tag="screen_agent",
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags["agent"] = tag
        dpg.add_text("GM Agent (PPO)", color=TEXT_PRIMARY)
        dpg.add_spacer(height=4)
        dpg.add_text(
            "This is an in-editor page, not a standalone program. "
            "Run PPO evaluation or live-assist loops without blocking the editor. "
            "Live adapter defaults to dry-run (no memory writes) until you enable writes below.",
            wrap=760,
            color=TEXT_SECONDARY,
        )
        dpg.add_spacer(height=6)

        with dpg.group(horizontal=True):
            dpg.add_text("Adapter", color=TEXT_SECONDARY)
            app.agent_adapter_combo = dpg.add_combo(
                items=["mock", "live"],
                default_value=app.agent_adapter_var.get(),
                width=140,
                callback=lambda _s, v: app.agent_adapter_var.set(v or "mock"),
            )
            app.agent_apply_writes_checkbox = dpg.add_checkbox(
                label="Apply writes to game memory",
                default_value=app.agent_apply_writes_var.get(),
                callback=lambda s, v: app.agent_apply_writes_var.set(bool(v)),
            )
            dpg.add_button(
                label="Refresh roster snapshot",
                width=200,
                callback=lambda *_: app._agent_refresh_snapshot(),
            )

        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_text("Team ID", color=TEXT_SECONDARY)
            app.agent_team_input = dpg.add_input_text(
                width=80,
                default_value=app.agent_team_id_var.get(),
                callback=lambda s, v: app.agent_team_id_var.set(str(v)),
            )
            dpg.add_text("Episodes", color=TEXT_SECONDARY)
            app.agent_episode_input = dpg.add_input_text(
                width=80,
                default_value=app.agent_episodes_var.get(),
                callback=lambda s, v: app.agent_episodes_var.set(str(v)),
            )

        dpg.add_spacer(height=4)
        dpg.add_text("Checkpoint", color=TEXT_SECONDARY)
        with dpg.group(horizontal=True):
            app.agent_checkpoint_input = dpg.add_input_text(
                width=420,
                default_value=app.agent_checkpoint_var.get(),
                callback=lambda s, v: app.agent_checkpoint_var.set(str(v)),
            )
            dpg.add_button(label="Browse", width=90, callback=lambda *_: app._agent_pick_checkpoint())

        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Run Evaluate",
                width=130,
                callback=lambda *_: app._agent_start_evaluate(),
            )
            dpg.add_button(
                label="Start Live Assist",
                width=150,
                callback=lambda *_: app._agent_start_live_assist(),
            )
            dpg.add_button(
                label="Stop",
                width=100,
                callback=lambda *_: app._agent_stop_runtime(),
            )

        dpg.add_spacer(height=6)
        dpg.add_text("Training config", color=TEXT_SECONDARY)
        with dpg.group(horizontal=True):
            app.agent_config_input = dpg.add_input_text(
                width=420,
                default_value=app.agent_config_var.get(),
                callback=lambda s, v: app.agent_config_var.set(str(v)),
            )
            dpg.add_button(label="Browse", width=90, callback=lambda *_: app._agent_pick_config())
            dpg.add_button(label="Start Training", width=140, callback=lambda *_: app._agent_start_training())

        dpg.add_spacer(height=8)
        app.agent_status_text_tag = dpg.add_text(app.agent_status_var.get(), wrap=760, color=TEXT_SECONDARY)
        app.agent_log_tag = dpg.add_input_text(
            multiline=True,
            readonly=True,
            width=-1,
            height=240,
            default_value="",
            tag="agent_log_box",
        )

__all__ = ["build_agent_screen"]
