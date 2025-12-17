"""Styling and palette helpers for the Tk UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.config import (
    PANEL_BG,
    INPUT_BG,
    ACCENT_BG,
    BUTTON_BG,
    BUTTON_ACTIVE_BG,
    BUTTON_TEXT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ENTRY_BG,
    ENTRY_ACTIVE_BG,
    ENTRY_BORDER,
    ENTRY_FG,
)


def apply_base_theme(root: tk.Misc) -> None:
    """Apply base styles used across editor windows."""
    style = ttk.Style(root)
    # Force the explicit theme (no fallbacks)
    style.theme_use("alt")
    style.configure("App.TFrame", background=PANEL_BG)
    style.configure("App.TLabel", background=PANEL_BG, foreground=TEXT_PRIMARY)
    style.configure("App.TButton", background=BUTTON_BG, foreground=BUTTON_TEXT, relief=tk.FLAT)
    style.map(
        "App.TButton",
        background=[("active", BUTTON_ACTIVE_BG)],
        foreground=[("active", BUTTON_TEXT)],
    )
    style.configure(
        "App.TCombobox",
        fieldbackground=INPUT_BG,
        background=INPUT_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=ACCENT_BG,
        arrowcolor=TEXT_PRIMARY,
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", INPUT_BG)],
        foreground=[("readonly", TEXT_PRIMARY)],
        arrowcolor=[("readonly", TEXT_PRIMARY)],
    )
    style.configure(
        "App.TEntry",
        fieldbackground=ENTRY_BG,
        foreground=ENTRY_FG,
        bordercolor=ENTRY_BORDER,
    )
    style.map(
        "App.TEntry",
        fieldbackground=[("focus", ENTRY_ACTIVE_BG)],
        foreground=[("focus", ENTRY_FG)],
    )
    # Shared tab background (lighter blue for readability)
    tab_bg = "#1F3F6B"
    # Default notebook styling (global) for consistent tab appearance
    style.configure("TNotebook", background=PANEL_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=tab_bg,
        foreground=TEXT_PRIMARY,
        padding=(10, 6),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BUTTON_BG), ("active", BUTTON_ACTIVE_BG), ("!selected", tab_bg)],
        foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY), ("!selected", TEXT_PRIMARY)],
    )


__all__ = ["apply_base_theme"]
