"""Stadium screen hooked to live offsets when available."""
from __future__ import annotations

import tkinter as tk

from ..core.config import (
    PANEL_BG,
    PRIMARY_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BUTTON_BG,
    BUTTON_TEXT,
    BUTTON_ACTIVE_BG,
    ENTRY_BG,
    ENTRY_BORDER,
    ENTRY_FG,
)


def build_stadium_screen(app) -> None:
    app.stadium_frame = tk.Frame(app, bg=PRIMARY_BG)

    header = tk.Frame(app.stadium_frame, bg=PANEL_BG)
    header.pack(fill=tk.X, padx=12, pady=12)
    tk.Label(
        header,
        text="Stadium",
        font=("Segoe UI", 18, "bold"),
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
    ).pack(side=tk.LEFT)
    tk.Label(
        header,
        textvariable=app.stadium_status_var,
        bg=PANEL_BG,
        fg=TEXT_SECONDARY,
    ).pack(side=tk.LEFT, padx=(10, 0))

    body = tk.Frame(app.stadium_frame, bg=PRIMARY_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

    # Left: list
    left = tk.Frame(body, bg=PRIMARY_BG)
    left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
    tk.Label(left, text="Stadium List", bg=PRIMARY_BG, fg=TEXT_PRIMARY, font=("Segoe UI", 11, "bold")).pack(anchor="w")
    search = tk.Entry(
        left,
        textvariable=app.stadium_search_var,
        bg=ENTRY_BG,
        fg=ENTRY_FG,
        relief=tk.FLAT,
        insertbackground=ENTRY_FG,
        highlightbackground=ENTRY_BORDER,
        highlightthickness=1,
    )
    search.pack(fill=tk.X, pady=(4, 6))
    app.stadium_search_var.trace_add("write", lambda *_: app._filter_stadium_list())
    listbox = tk.Listbox(left, height=20, bg=PANEL_BG, fg=TEXT_PRIMARY, selectbackground=BUTTON_ACTIVE_BG)
    listbox.pack(fill=tk.BOTH, expand=True)
    listbox.bind("<<ListboxSelect>>", lambda *_: app._on_stadium_selected())
    listbox.bind("<Double-1>", lambda *_: app._open_full_stadium_editor(app._current_stadium_index()))

    # Right: detail
    right = tk.Frame(body, bg=PANEL_BG, bd=1, relief=tk.FLAT)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tk.Label(
        right,
        text="Stadium Details",
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
        font=("Segoe UI", 12, "bold"),
    ).pack(anchor="w", padx=12, pady=(10, 4))
    tk.Label(
        right,
        textvariable=app.stadium_count_var,
        bg=PANEL_BG,
        fg=TEXT_SECONDARY,
        justify=tk.LEFT,
        wraplength=520,
    ).pack(anchor="w", padx=12, pady=(0, 12))
    tk.Button(
        right,
        text="Open Stadium Editor",
        command=lambda: app._open_full_stadium_editor(app._current_stadium_index()),
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=14,
        pady=6,
    ).pack(anchor="w", padx=12, pady=(0, 10))

    # Expose widgets for future wiring
    app.stadium_listbox = listbox
    app.stadium_search = search
    app._refresh_stadium_list()


__all__ = ["build_stadium_screen"]
