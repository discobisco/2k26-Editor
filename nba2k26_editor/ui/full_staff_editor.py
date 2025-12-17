"""Staff editor scaffold styled like the player editor."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.config import (
    PANEL_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BUTTON_BG,
    BUTTON_TEXT,
    BUTTON_ACTIVE_BG,
    ACCENT_BG,
    ENTRY_BG,
    ENTRY_FG,
    ENTRY_BORDER,
)
from ..core.conversions import to_int as _to_int
from ..models.schema import FieldMetadata


class FullStaffEditor(tk.Toplevel):
    """Notebook-based staff editor; reads categories only (no live memory until pointers are available)."""

    def __init__(self, parent: tk.Tk, model, staff_index: int | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.staff_index = staff_index if staff_index is not None else 0
        self.title("Staff Editor")
        self.geometry("720x520")
        self.configure(bg=PANEL_BG)
        self.field_vars: dict[tuple[str, str], tk.Variable] = {}
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        self._initializing = True

        header = tk.Frame(self, bg=PANEL_BG)
        header.pack(fill=tk.X, padx=12, pady=(12, 4))
        tk.Label(
            header,
            text="Staff Editor",
            fg=TEXT_PRIMARY,
            bg=PANEL_BG,
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Live editing will activate once staff base pointers/stride are defined in offsets.json.",
            fg=TEXT_SECONDARY,
            bg=PANEL_BG,
        ).pack(side=tk.LEFT, padx=(10, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        staff_categories = self.model.get_categories_for_super("Staff") or {}
        if not staff_categories:
            frame = tk.Frame(notebook, bg=PANEL_BG)
            notebook.add(frame, text="Staff")
            tk.Label(
                frame,
                text="No staff categories detected in offsets.json.",
                bg=PANEL_BG,
                fg=TEXT_SECONDARY,
            ).pack(padx=12, pady=12, anchor="w")
        else:
            for cat in sorted(staff_categories.keys()):
                frame = tk.Frame(notebook, bg=PANEL_BG)
                notebook.add(frame, text=cat)
                self._build_category_tab(frame, cat, staff_categories.get(cat))

        btn_row = tk.Frame(self, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Button(
            btn_row,
            text="Close",
            command=self.destroy,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
            padx=14,
            pady=6,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            btn_row,
            text="Save (disabled - waiting for pointers)",
            state=tk.DISABLED,
            bg=ACCENT_BG,
            fg=TEXT_PRIMARY,
            relief=tk.FLAT,
            padx=14,
            pady=6,
        ).pack(side=tk.RIGHT, padx=(0, 6))
        self._initializing = False

    def _build_category_tab(self, parent: tk.Frame, category_name: str, fields_obj: list | None = None) -> None:
        fields = fields_obj if isinstance(fields_obj, list) else self.model.categories.get(category_name, [])
        canvas = tk.Canvas(parent, bg=PANEL_BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=PANEL_BG)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set, bg=PANEL_BG)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for row, field in enumerate(fields):
            if not isinstance(field, dict):
                continue
            name = field.get("name", f"Field {row}")
            offset_val = _to_int(field.get("offset"))
            start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
            length = _to_int(field.get("length", 8))
            byte_length = _to_int(field.get("size") or field.get("length") or 0)
            field_type = str(field.get("type", "")).lower()
            tk.Label(scroll_frame, text=name + ":", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(
                row=row, column=0, sticky=tk.W, padx=(10, 5), pady=2
            )
            is_string = any(tag in field_type for tag in ("string", "text", "wstring", "wide", "utf16", "char"))
            var: tk.Variable
            if is_string:
                var = tk.StringVar(value="")
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=28,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                    state=tk.DISABLED,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
            else:
                var = tk.IntVar(value=0)
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=12,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                    state=tk.DISABLED,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
            self.field_vars[(category_name, name)] = var
            self.field_meta[(category_name, name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=bool(field.get("requiresDereference") or field.get("requires_deref")),
                deref_offset=_to_int(field.get("dereferenceAddress") or field.get("deref_offset")),
                widget=entry,
                data_type=field_type,
                byte_length=byte_length,
            )


__all__ = ["FullStaffEditor"]
