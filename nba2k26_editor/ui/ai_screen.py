"""Standalone AI Assistant screen."""
from __future__ import annotations

import tkinter as tk

from ..ai.assistant import PlayerAIAssistant
from ..core.config import BUTTON_ACTIVE_BG, BUTTON_BG, BUTTON_TEXT, PANEL_BG, PRIMARY_BG, TEXT_PRIMARY, TEXT_SECONDARY


def build_ai_screen(app) -> None:
    """Create the AI Assistant screen and wire it to existing player state."""
    app.ai_frame = tk.Frame(app, bg=PRIMARY_BG)
    header = tk.Frame(app.ai_frame, bg=PRIMARY_BG)
    header.pack(fill=tk.X, padx=20, pady=(24, 12))
    tk.Label(
        header,
        text="AI Assistant",
        font=("Segoe UI", 20, "bold"),
        bg=PRIMARY_BG,
        fg=TEXT_PRIMARY,
    ).pack(anchor="w")
    tk.Label(
        header,
        text="Uses the currently selected player. Switch to Players to change selection.",
        font=("Segoe UI", 11),
        bg=PRIMARY_BG,
        fg=TEXT_SECONDARY,
    ).pack(anchor="w", pady=(4, 0))
    status_row = tk.Frame(app.ai_frame, bg=PRIMARY_BG)
    status_row.pack(fill=tk.X, padx=20, pady=(0, 10))
    tk.Label(status_row, text="Selected player:", bg=PRIMARY_BG, fg=TEXT_SECONDARY, font=("Segoe UI", 10, "bold")).pack(
        side=tk.LEFT
    )
    tk.Label(status_row, textvariable=app.player_name_var, bg=PRIMARY_BG, fg=TEXT_PRIMARY, font=("Segoe UI", 12, "bold")).pack(
        side=tk.LEFT, padx=(8, 0)
    )
    tk.Button(
        status_row,
        text="Go to Players",
        command=app.show_players,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        relief=tk.FLAT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        padx=10,
        pady=4,
    ).pack(side=tk.RIGHT)
    bridge_row = tk.Frame(app.ai_frame, bg=PRIMARY_BG)
    bridge_row.pack(fill=tk.X, padx=20, pady=(0, 10))
    bridge_text = "Control bridge unavailable."
    if getattr(app, "control_bridge", None):
        bridge_text = f"External control available at {app.control_bridge.server_address()}"
    tk.Label(
        bridge_row,
        text=bridge_text,
        bg=PRIMARY_BG,
        fg=TEXT_SECONDARY if "unavailable" in bridge_text else TEXT_PRIMARY,
        font=("Segoe UI", 10, "italic"),
        wraplength=600,
        justify="left",
    ).pack(anchor="w")
    body = tk.Frame(app.ai_frame, bg=PANEL_BG, padx=16, pady=16)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
    assistant_container = tk.Frame(body, bg=PANEL_BG)
    assistant_container.pack(fill=tk.BOTH, expand=True)
    context = {
        "panel_parent": assistant_container,
        "detail_vars": getattr(app, "player_detail_fields", {}),
        "first_name_entry": getattr(app, "first_name_entry", None),
        "last_name_entry": getattr(app, "last_name_entry", None),
        "team_widget": getattr(app, "team_value_label", None),
        "ai_settings": app.ai_settings,
    }
    app.ai_assistant = PlayerAIAssistant(app, context)


__all__ = ["build_ai_screen"]
