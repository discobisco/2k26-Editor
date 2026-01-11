from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.config import (
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    PANEL_BG,
    PRIMARY_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def build_excel_screen(app) -> None:
    app.excel_frame = tk.Frame(app, bg=PRIMARY_BG)
    tk.Label(
        app.excel_frame,
        text="Excel Import / Export",
        font=("Segoe UI", 18, "bold"),
        bg=PRIMARY_BG,
        fg=TEXT_PRIMARY,
    ).pack(pady=(30, 10))
    container = tk.Frame(app.excel_frame, bg=PANEL_BG, padx=20, pady=20)
    container.pack(padx=40, pady=(0, 20), fill=tk.BOTH, expand=False)
    tk.Label(
        container,
        text="Use the template workbooks in Offsets to import or export data.",
        font=("Segoe UI", 10),
        bg=PANEL_BG,
        fg=TEXT_SECONDARY,
        wraplength=640,
        justify="left",
    ).pack(anchor="w", pady=(0, 16))
    import_frame = tk.LabelFrame(container, text="Import", bg=PANEL_BG, fg=TEXT_PRIMARY, padx=10, pady=10)
    import_frame.pack(fill=tk.X, pady=(0, 12))
    export_frame = tk.LabelFrame(container, text="Export", bg=PANEL_BG, fg=TEXT_PRIMARY, padx=10, pady=10)
    export_frame.pack(fill=tk.X)
    _add_entity_buttons(import_frame, app, is_import=True)
    _add_entity_buttons(export_frame, app, is_import=False)
    status = tk.Label(
        container,
        textvariable=app.excel_status_var,
        font=("Segoe UI", 10, "italic"),
        bg=PANEL_BG,
        fg=TEXT_SECONDARY,
        wraplength=600,
        justify="left",
    )
    status.pack(anchor="w", pady=(12, 0))
    app.excel_progress = ttk.Progressbar(
        container,
        orient="horizontal",
        mode="determinate",
        maximum=100,
        variable=app.excel_progress_var,
        length=400,
    )
    app.excel_progress.pack(fill=tk.X, pady=(8, 0))


def _add_entity_buttons(parent: tk.Widget, app, *, is_import: bool) -> None:
    row = tk.Frame(parent, bg=PANEL_BG)
    row.pack(fill=tk.X, pady=(0, 6))
    button_cfg = {
        "bg": BUTTON_BG,
        "fg": BUTTON_TEXT,
        "relief": tk.FLAT,
        "activebackground": BUTTON_ACTIVE_BG,
        "activeforeground": BUTTON_TEXT,
        "width": 16,
    }
    labels = [
        ("Players", "players"),
        ("Teams", "teams"),
        ("Staff", "staff"),
        ("Stadiums", "stadiums"),
    ]
    for label, key in labels:
        cmd = app._import_excel if is_import else app._export_excel
        tk.Button(row, text=label, command=lambda k=key, c=cmd: c(k), **button_cfg).pack(
            side=tk.LEFT, padx=(0, 10)
        )


__all__ = ["build_excel_screen"]
