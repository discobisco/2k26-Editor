"""Home screen builders extracted from PlayerEditorApp."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.config import (
    ACCENT_BG,
    APP_VERSION,
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    ENTRY_BG,
    ENTRY_BORDER,
    ENTRY_FG,
    HOOK_TARGETS,
    PANEL_BG,
    PRIMARY_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from . import extensions_ui


def build_home_screen(app) -> None:
    app.home_frame = tk.Frame(app, bg=PRIMARY_BG)
    tk.Label(
        app.home_frame,
        text="2K26 Offline Player Editor",
        font=("Segoe UI", 20, "bold"),
        bg=PRIMARY_BG,
        fg=TEXT_PRIMARY,
    ).pack(pady=(40, 10))
    content = tk.Frame(app.home_frame, bg=PANEL_BG, padx=20, pady=20)
    content.pack(pady=(0, 30), padx=40, fill=tk.BOTH, expand=False)
    notebook = ttk.Notebook(content)
    notebook.pack(fill=tk.BOTH, expand=True)
    overview_tab = tk.Frame(notebook, bg=PANEL_BG)
    settings_tab = tk.Frame(notebook, bg=PANEL_BG)
    notebook.add(overview_tab, text="Overview")
    notebook.add(settings_tab, text="AI Settings")
    build_home_overview_tab(app, overview_tab)
    app._build_ai_settings_tab(settings_tab)  # reuse existing method
    tk.Label(
        app.home_frame,
        text=f"Version {APP_VERSION}",
        font=("Segoe UI", 9, "italic"),
        bg=PRIMARY_BG,
        fg=TEXT_SECONDARY,
    ).pack(side=tk.BOTTOM, pady=20)


def build_home_overview_tab(app, parent: tk.Frame) -> None:
    tk.Label(
        parent,
        text="Hook target",
        font=("Segoe UI", 12, "bold"),
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
    ).pack(anchor="w", pady=(0, 8))
    hook_row = tk.Frame(parent, bg=PANEL_BG)
    hook_row.pack(anchor="w", pady=(0, 20))
    for label, exe in HOOK_TARGETS:
        tk.Radiobutton(
            hook_row,
            text=label,
            variable=app.hook_target_var,
            value=exe,
            command=lambda value=exe: app._set_hook_target(value),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=PANEL_BG,
            activeforeground=TEXT_PRIMARY,
            selectcolor=ACCENT_BG,
            indicatoron=False,
            relief=tk.FLAT,
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 10), pady=2)
    app.status_var = tk.StringVar()
    app.status_label = tk.Label(
        parent,
        textvariable=app.status_var,
        font=("Segoe UI", 12),
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
    )
    app.status_label.pack(pady=(0, 15))
    tk.Button(
        parent,
        text="Refresh",
        command=app._update_status,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        relief=tk.FLAT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
    ).pack()
    build_extension_loader(app, parent)


def build_extension_loader(app, parent: tk.Frame) -> None:
    container = tk.Frame(parent, bg=PANEL_BG)
    container.pack(fill=tk.X, pady=(24, 0))
    tk.Label(
        container,
        text="Extensions",
        font=("Segoe UI", 12, "bold"),
        bg=PANEL_BG,
        fg=TEXT_PRIMARY,
    ).pack(anchor="w")
    files = extensions_ui.discover_extension_files()
    if not files:
        tk.Label(
            container,
            text="No additional Python modules detected in the editor directory.",
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "italic"),
        ).pack(anchor="w", pady=(4, 0))
    else:
        list_frame = tk.Frame(container, bg=PANEL_BG)
        list_frame.pack(fill=tk.X, pady=(4, 0))
        for path in files:
            key = str(path.resolve())
            already_loaded = extensions_ui.is_extension_loaded(app, path)
            var = tk.BooleanVar(value=already_loaded)
            app.extension_vars[key] = var
            chk = tk.Checkbutton(
                list_frame,
                text=path.name,
                variable=var,
                command=lambda p=path, v=var: extensions_ui.toggle_extension_module(app, p, v),
                bg=PANEL_BG,
                fg=TEXT_PRIMARY,
                activebackground=PANEL_BG,
                activeforeground=TEXT_PRIMARY,
                selectcolor=ACCENT_BG,
                anchor="w",
                justify="left",
            )
            chk.pack(fill=tk.X, anchor="w")
            if already_loaded:
                chk.configure(state=tk.DISABLED)
                app.loaded_extensions.add(key)
            app.extension_checkbuttons[key] = chk
    tk.Label(
        container,
        textvariable=app.extension_status_var,
        bg=PANEL_BG,
        fg=TEXT_SECONDARY,
        font=("Segoe UI", 10, "italic"),
        wraplength=400,
        justify="left",
    ).pack(anchor="w", pady=(6, 0))
    tk.Button(
        container,
        text="Reload with selected extensions",
        command=lambda: extensions_ui.reload_with_selected_extensions(app),
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        relief=tk.FLAT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
    ).pack(anchor="w", pady=(8, 0))
    extensions_ui.autoload_extensions_from_file(app)


__all__ = ["build_home_screen"]
