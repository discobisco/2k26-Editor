"""Teams screen builder extracted from PlayerEditorApp."""
from __future__ import annotations

import tkinter as tk
from typing import cast

from ..core.config import (
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    BUTTON_TEXT,
    ENTRY_BG,
    ENTRY_BORDER,
    ENTRY_FG,
    INPUT_PLACEHOLDER_FG,
    INPUT_TEXT_FG,
)
from ..core.offsets import TEAM_FIELD_DEFS
from .widgets import bind_mousewheel


def build_teams_screen(app) -> None:
    """Construct the Teams editing screen on the provided app instance."""
    app.teams_frame = tk.Frame(app, bg="#0F1C2E")
    controls = tk.Frame(app.teams_frame, bg="#0F1C2E")
    controls.pack(fill=tk.X, padx=20, pady=15)
    tk.Label(
        controls,
        text="Search",
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=0, column=0, sticky="w")
    app.team_search_var = tk.StringVar()
    app.team_search_entry = tk.Entry(
        controls,
        textvariable=app.team_search_var,
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
    app.team_search_entry.grid(row=0, column=1, padx=(8, 20), sticky="w")
    app.team_search_entry.insert(0, "Search teams.")

    def _on_team_search_focus_in(_event):
        if app.team_search_entry.get() == "Search teams.":
            app.team_search_entry.delete(0, tk.END)
            app.team_search_entry.configure(fg=INPUT_TEXT_FG)

    def _on_team_search_focus_out(_event):
        if not app.team_search_entry.get():
            app.team_search_entry.insert(0, "Search teams.")
            app.team_search_entry.configure(fg=INPUT_PLACEHOLDER_FG)

    app.team_search_entry.bind("<FocusIn>", _on_team_search_focus_in)
    app.team_search_entry.bind("<FocusOut>", _on_team_search_focus_out)
    refresh_btn = tk.Button(
        controls,
        text="Refresh",
        command=app._start_team_scan,
        bg="#778DA9",
        fg=BUTTON_TEXT,
        relief=tk.FLAT,
        activebackground="#415A77",
        activeforeground=BUTTON_TEXT,
        padx=16,
        pady=4,
    )
    refresh_btn.grid(row=0, column=2, padx=(0, 20))
    app.team_count_var = tk.StringVar(value="Teams: 0")
    tk.Label(
        controls,
        textvariable=app.team_count_var,
        font=("Segoe UI", 11, "bold"),
        bg="#0F1C2E",
        fg="#E0E1DD",
    ).grid(row=0, column=3, sticky="e")
    controls.columnconfigure(4, weight=1)
    app.team_scan_status_var = tk.StringVar()
    app.team_scan_status_label = tk.Label(
        controls,
        textvariable=app.team_scan_status_var,
        font=("Segoe UI", 10, "italic"),
        bg="#0F1C2E",
        fg="#9BA4B5",
    )
    app.team_scan_status_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
    content = tk.Frame(app.teams_frame, bg="#0F1C2E")
    content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
    list_container = tk.Frame(content, bg="#0F1C2E")
    list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    app.team_editor_listbox = tk.Listbox(
        list_container,
        selectmode=tk.SINGLE,
        exportselection=False,
        font=("Segoe UI", 11),
        bg="#0F1C2E",
        fg="#E0E1DD",
        highlightthickness=0,
        relief=tk.FLAT,
    )
    app.team_editor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    app.team_editor_listbox.bind("<<ListboxSelect>>", app._on_team_listbox_select)
    bind_mousewheel(app.team_editor_listbox)
    team_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=app.team_editor_listbox.yview)
    team_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    app.team_editor_listbox.configure(yscrollcommand=team_scroll.set)
    detail_container = tk.Frame(content, bg="#16213E", width=460)
    detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(20, 0))
    detail_container.pack_propagate(False)
    app.team_editor_detail_name_var = tk.StringVar(value="Select a team")
    tk.Label(
        detail_container,
        textvariable=app.team_editor_detail_name_var,
        font=("Segoe UI", 18, "bold"),
        bg="#16213E",
        fg="#E0E1DD",
    ).pack(pady=(25, 10))
    tk.Label(
        detail_container,
        text="Team Details",
        font=("Segoe UI", 12, "bold"),
        bg="#16213E",
        fg="#E0E1DD",
    ).pack(anchor="w", padx=30, pady=(0, 6))
    # Form for each team field
    app.team_editor_field_vars = cast(dict[str, tk.StringVar], {})
    form = tk.Frame(detail_container, bg="#16213E")
    form.pack(fill=tk.X, padx=30, pady=5)
    row = 0
    if TEAM_FIELD_DEFS:
        for label in TEAM_FIELD_DEFS.keys():
            tk.Label(form, text=f"{label}:", bg="#16213E", fg="#9BA4B5").grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            entry = tk.Entry(
                form,
                textvariable=var,
                bg=ENTRY_BG,
                fg=ENTRY_FG,
                relief=tk.FLAT,
                insertbackground=ENTRY_FG,
                highlightthickness=1,
                highlightbackground=ENTRY_BORDER,
                highlightcolor=ENTRY_BORDER,
                disabledbackground=ENTRY_BG,
                disabledforeground=ENTRY_FG,
            )
            entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
            app.team_editor_field_vars[label] = var
            row += 1
        form.columnconfigure(1, weight=1)
    else:
        tk.Label(
            form,
            text="No team field offsets found. Update Offsets/offsets.json to enable editing.",
            bg="#16213E",
            fg="#B0413E",
            wraplength=360,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=4)
    # Action buttons
    btn_row = tk.Frame(detail_container, bg="#16213E")
    btn_row.pack(fill=tk.X, padx=30, pady=16)
    app.btn_team_save = tk.Button(
        btn_row,
        text="Save Fields",
        command=app._save_team,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        state=tk.DISABLED,
        padx=16,
        pady=6,
    )
    app.btn_team_save.pack(side=tk.LEFT, padx=(0, 8))
    app.btn_team_full = tk.Button(
        btn_row,
        text="Full Editor",
        command=app._open_full_team_editor,
        bg=BUTTON_BG,
        fg=BUTTON_TEXT,
        activebackground=BUTTON_ACTIVE_BG,
        activeforeground=BUTTON_TEXT,
        relief=tk.FLAT,
        state=tk.DISABLED,
        padx=16,
        pady=6,
    )
    app.btn_team_full.pack(side=tk.LEFT)
    # Data holders for filtering
    app.team_edit_var = tk.StringVar()
    app.all_team_names = cast(list[str], [])
    app.filtered_team_names = cast(list[str], [])
    app.team_editor_listbox.insert(tk.END, "No teams available.")
    app.team_search_var.trace_add("write", app._filter_team_list)


__all__ = ["build_teams_screen"]
