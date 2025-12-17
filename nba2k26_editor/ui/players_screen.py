"""Players screen builder extracted from PlayerEditorApp."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import cast

from ..core.config import (
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    ENTRY_BG,
    ENTRY_BORDER,
    ENTRY_FG,
    PANEL_BG,
    INPUT_PLACEHOLDER_FG,
    INPUT_TEXT_FG,
)
from ..core.extensions import PLAYER_PANEL_EXTENSIONS
from .widgets import bind_mousewheel

_EXTENSION_LOGGER = logging.getLogger("nba2k26.extensions")


def build_players_screen(app) -> None:
    app.players_frame = tk.Frame(app, bg="#0F1C2E")
    controls = tk.Frame(app.players_frame, bg="#0F1C2E")
    controls.pack(fill=tk.X, padx=20, pady=15)
    tk.Label(
        controls,
        text="Search",
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=0, column=0, sticky="w")
    app.player_search_var = tk.StringVar()
    app.search_entry = tk.Entry(
        controls,
        textvariable=app.player_search_var,
        width=30,
        font=("Segoe UI", 11),
        relief=tk.FLAT,
        fg=INPUT_PLACEHOLDER_FG,
        bg=ENTRY_BG,
        insertbackground=ENTRY_FG,
        highlightthickness=1,
        highlightbackground=ENTRY_BORDER,
        disabledbackground=ENTRY_BG,
        disabledforeground=ENTRY_FG,
    )
    app.search_entry.grid(row=0, column=1, padx=(8, 20), sticky="w")
    app.search_entry.insert(0, "Search players.")

    def _on_search_focus_in(_event):
        if app.search_entry.get() == "Search players.":
            app.search_entry.delete(0, tk.END)
            app.search_entry.configure(fg=INPUT_TEXT_FG)

    def _on_search_focus_out(_event):
        if not app.search_entry.get():
            app.search_entry.insert(0, "Search players.")
            app.search_entry.configure(fg=INPUT_PLACEHOLDER_FG)

    app.search_entry.bind("<FocusIn>", _on_search_focus_in)
    app.search_entry.bind("<FocusOut>", _on_search_focus_out)
    refresh_btn = tk.Button(
        controls,
        text="Refresh",
        command=app._start_scan,
        bg="#778DA9",
        fg=BUTTON_TEXT,
        relief=tk.FLAT,
        activebackground="#415A77",
        activeforeground=BUTTON_TEXT,
        padx=16,
        pady=4,
    )
    refresh_btn.grid(row=0, column=2, padx=(0, 20))
    tk.Label(
        controls,
        text="Player Dataset",
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=0, column=3, sticky="w")
    app.dataset_var = tk.StringVar(value="All Data")
    dataset_combo = ttk.Combobox(
        controls,
        textvariable=app.dataset_var,
        values=["All Data"],
        state="readonly",
        width=15,
        style="App.TCombobox",
    )
    dataset_combo.grid(row=0, column=4, padx=(8, 0), sticky="w")
    controls.columnconfigure(5, weight=1)
    app.player_count_var = tk.StringVar(value="Players: 0")
    tk.Label(
        controls,
        textvariable=app.player_count_var,
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=0, column=5, sticky="e")
    tk.Label(
        controls,
        text="Team",
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=1, column=0, sticky="w", pady=(10, 0))
    app.team_var = tk.StringVar()
    app.team_dropdown = ttk.Combobox(
        controls,
        textvariable=app.team_var,
        state="readonly",
        width=25,
        style="App.TCombobox",
    )
    app.team_dropdown.grid(row=1, column=1, padx=(8, 0), pady=(10, 0), sticky="w")
    app.team_dropdown.bind("<<ComboboxSelected>>", app._on_team_selected)
    app.scan_status_var = tk.StringVar(value="")
    app.scan_status_label = tk.Label(
        controls,
        textvariable=app.scan_status_var,
        font=("Segoe UI", 10, "italic"),
        bg="#0F1C2E",
        fg="#9BA4B5",
    )
    app.scan_status_label.grid(row=1, column=2, columnspan=3, sticky="w", pady=(10, 0))

    content = tk.Frame(app.players_frame, bg="#0F1C2E")
    content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
    list_container = tk.Frame(content, bg="#0F1C2E")
    list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    app.player_listbox = tk.Listbox(
        list_container,
        selectmode=tk.EXTENDED,
        exportselection=False,
        font=("Segoe UI", 11),
        bg="#0F1C2E",
        fg="#E0E1DD",
        highlightthickness=0,
        relief=tk.FLAT,
    )
    app.player_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    app.player_listbox.bind("<<ListboxSelect>>", app._on_player_selected)
    app.player_listbox.bind("<Double-Button-1>", lambda _e: app._open_full_editor())
    bind_mousewheel(app.player_listbox)
    list_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=app.player_listbox.yview)
    list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app.player_listbox.configure(yscrollcommand=list_scroll.set)
    detail_container = tk.Frame(content, bg=PANEL_BG, width=420)
    detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(20, 0))
    detail_container.pack_propagate(False)
    app.player_portrait = tk.Canvas(detail_container, width=150, height=150, bg=PANEL_BG, highlightthickness=0)
    app.player_portrait.pack(pady=(30, 15))
    app.player_portrait_circle = app.player_portrait.create_oval(25, 25, 125, 125, fill="#415A77", outline="")
    app.player_portrait_text = app.player_portrait.create_text(75, 75, text="", fill="#E0E1DD", font=("Segoe UI", 24, "bold"))
    app.player_name_var = tk.StringVar(value="Select a player")
    app.player_name_label = tk.Label(
        detail_container,
        textvariable=app.player_name_var,
        font=("Segoe UI", 18, "bold"),
        bg=PANEL_BG,
        fg="#E0E1DD",
    )
    app.player_name_label.pack()
    app.player_ovr_var = tk.StringVar(value="OVR --")
    app.player_ovr_label = tk.Label(
        detail_container,
        textvariable=app.player_ovr_var,
        font=("Segoe UI", 14),
        bg=PANEL_BG,
        fg="#E63946",
    )
    app.player_ovr_label.pack(pady=(0, 20))
    info_grid = tk.Frame(detail_container, bg=PANEL_BG)
    info_grid.pack(padx=35, pady=10, fill=tk.X)
    app.player_detail_fields = cast(dict[str, tk.StringVar], {})
    detail_widgets = cast(dict[str, tk.Widget], {})
    detail_fields = [
        ("Position", "--"),
        ("Number", "--"),
        ("Height", "--"),
        ("Weight", "--"),
        ("Face ID", "--"),
        ("Unique ID", "--"),
    ]
    for idx, (label, default) in enumerate(detail_fields):
        row = idx // 2
        col = (idx % 2) * 2
        name_label = tk.Label(
            info_grid,
            text=label,
            bg=PANEL_BG,
            fg="#E0E1DD",
            font=("Segoe UI", 11),
        )
        name_label.grid(row=row, column=col, sticky="w", pady=4, padx=(0, 12))
        var = tk.StringVar(value=default)
        value_label = tk.Label(
            info_grid,
            textvariable=var,
            bg=PANEL_BG,
            fg="#9BA4B5",
            font=("Segoe UI", 11, "bold"),
        )
        value_label.grid(row=row, column=col + 1, sticky="w", pady=4, padx=(0, 20))
        app.player_detail_fields[label] = var
        detail_widgets[label] = value_label
    app.player_detail_widgets = detail_widgets
    info_grid.columnconfigure(1, weight=1)
    info_grid.columnconfigure(3, weight=1)
    form = tk.Frame(detail_container, bg=PANEL_BG)
    form.pack(padx=35, pady=(10, 0), fill=tk.X)
    tk.Label(form, text="First Name", bg=PANEL_BG, fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=4)
    app.var_first = tk.StringVar()
    first_entry = tk.Entry(
        form,
        textvariable=app.var_first,
        relief=tk.FLAT,
        width=20,
        fg=ENTRY_FG,
        bg=ENTRY_BG,
        insertbackground=ENTRY_FG,
        highlightthickness=1,
        highlightbackground=ENTRY_BORDER,
        disabledbackground=ENTRY_BG,
        disabledforeground=ENTRY_FG,
    )
    first_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))
    tk.Label(form, text="Last Name", bg=PANEL_BG, fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=4)
    app.var_last = tk.StringVar()
    last_entry = tk.Entry(
        form,
        textvariable=app.var_last,
        relief=tk.FLAT,
        width=20,
        fg=ENTRY_FG,
        bg=ENTRY_BG,
        insertbackground=ENTRY_FG,
        highlightthickness=1,
        highlightbackground=ENTRY_BORDER,
        disabledbackground=ENTRY_BG,
        disabledforeground=ENTRY_FG,
    )
    last_entry.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
    tk.Label(form, text="Team", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w", pady=4)
    app.var_player_team = tk.StringVar()
    team_value_label = tk.Label(
        form,
        textvariable=app.var_player_team,
        bg="#16213E",
        fg="#9BA4B5",
        font=("Segoe UI", 11, "bold"),
    )
    team_value_label.grid(row=2, column=1, sticky="w", pady=4, padx=(8, 0))
    edit_team_btn = tk.Button(
        form,
        text="Edit Team",
        command=app._open_team_editor_from_player,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=10,
        pady=4,
    )
    edit_team_btn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
    form.columnconfigure(1, weight=1)
    app.first_name_entry = first_entry
    app.last_name_entry = last_entry
    app.team_value_label = team_value_label
    panel_context = {
        "panel_parent": detail_container,
        "detail_widgets": detail_widgets,
        "detail_vars": app.player_detail_fields,
        "first_name_entry": first_entry,
        "last_name_entry": last_entry,
        "team_widget": team_value_label,
        "inspector": app.player_panel_inspector,
        "ai_settings": app.ai_settings,
    }
    for factory in PLAYER_PANEL_EXTENSIONS:
        try:
            factory(app, panel_context)
        except Exception as exc:
            _EXTENSION_LOGGER.exception("Player panel extension failed: %s", exc)
    btn_row = tk.Frame(detail_container, bg="#16213E")
    btn_row.pack(pady=(20, 0))
    app.btn_save = tk.Button(
        btn_row,
        text="Save",
        command=app._save_player,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        disabledforeground=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        state=tk.DISABLED,
        padx=16,
        pady=6,
    )
    app.btn_save.pack(side=tk.LEFT, padx=5)
    app.btn_edit = tk.Button(
        btn_row,
        text="Edit Player",
        command=app._open_full_editor,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        disabledforeground=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        state=tk.DISABLED,
        padx=16,
        pady=6,
    )
    app.btn_edit.pack(side=tk.LEFT, padx=5)
    app.btn_copy = tk.Button(
        btn_row,
        text="Copy Player",
        command=app._open_copy_dialog,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        disabledforeground=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        state=tk.DISABLED,
        padx=16,
        pady=6,
    )
    app.btn_copy.pack(side=tk.LEFT, padx=5)
    app.btn_import = tk.Button(
        btn_row,
        text="Import Data",
        command=app._open_import_dialog,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=16,
        pady=6,
    )
    app.btn_import.pack(side=tk.LEFT, padx=5)
    app.btn_export = tk.Button(
        btn_row,
        text="Export CSV",
        command=app._open_export_dialog,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        padx=16,
        pady=6,
    )
    app.btn_export.pack(side=tk.LEFT, padx=5)
    app.current_players = []
    app.filtered_player_indices = []
    app.selected_player = None
    app.player_listbox.delete(0, tk.END)
    app.player_count_var.set("Players: 0")
    app.player_listbox.insert(tk.END, "No players available.")
    app.player_search_var.trace_add("write", lambda *_: app._filter_player_list())


__all__ = ["build_players_screen"]
