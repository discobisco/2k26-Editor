"""Stadium editor scaffold styled like the player editor."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

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


class FullStadiumEditor(tk.Toplevel):
    """Notebook-based stadium editor; reads categories only (no live memory until pointers are available)."""

    def __init__(self, parent: tk.Tk, model, stadium_index: int | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.stadium_index = stadium_index if stadium_index is not None else 0
        self.title("Stadium Editor")
        self.geometry("720x520")
        self.configure(bg=PANEL_BG)
        self._editor_type = "stadium"
        self.field_vars: dict[tuple[str, str], tk.Variable] = {}
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        self._initializing = True
        self._unsaved_changes: set[tuple[str, str]] = set()

        header = tk.Frame(self, bg=PANEL_BG)
        header.pack(fill=tk.X, padx=12, pady=(12, 4))
        tk.Label(
            header,
            text="Stadium Editor",
            fg=TEXT_PRIMARY,
            bg=PANEL_BG,
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Live editing will activate once stadium base pointers/stride are defined in offsets.json.",
            fg=TEXT_SECONDARY,
            bg=PANEL_BG,
        ).pack(side=tk.LEFT, padx=(10, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        stadium_categories = self.model.get_categories_for_super("Stadiums") or {}
        if not stadium_categories:
            frame = tk.Frame(notebook, bg=PANEL_BG)
            notebook.add(frame, text="Stadium")
            tk.Label(
                frame,
                text="No stadium categories detected in offsets.json.",
                bg=PANEL_BG,
                fg=TEXT_SECONDARY,
            ).pack(padx=12, pady=12, anchor="w")
        else:
            for cat in sorted(stadium_categories.keys()):
                frame = tk.Frame(notebook, bg=PANEL_BG)
                notebook.add(frame, text=cat)
                self._build_category_tab(frame, cat, stadium_categories.get(cat))

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
            text="Save",
            command=self._save_all,
            bg=ACCENT_BG,
            fg=TEXT_PRIMARY,
            relief=tk.FLAT,
            padx=14,
            pady=6,
        ).pack(side=tk.RIGHT, padx=(0, 6))
        self._load_all_values()
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
            values_list = field.get("values") if isinstance(field, dict) else None
            tk.Label(scroll_frame, text=name + ":", bg=PANEL_BG, fg=TEXT_PRIMARY).grid(
                row=row, column=0, sticky=tk.W, padx=(10, 5), pady=2
            )
            is_string = any(tag in field_type for tag in ("string", "text", "wstring", "wide", "utf16", "char"))
            is_float = "float" in field_type
            is_color = any(tag in field_type for tag in ("color", "pointer"))
            var: tk.Variable
            if values_list:
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=values_list,
                    state="readonly",
                    width=20,
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                def on_enum_selected(event=None, v=var, c=combo, vals=values_list):
                    try:
                        v.set(vals.index(c.get()))
                    except Exception:
                        v.set(0)
                combo.bind("<<ComboboxSelected>>", on_enum_selected)
                entry = combo
            elif is_string:
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
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
            elif is_float:
                var = tk.DoubleVar(value=0.0)
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=16,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
            elif is_color:
                var = tk.StringVar(value="")
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=16,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
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
                values=tuple(str(v) for v in values_list) if values_list else None,
                data_type=field_type,
                byte_length=byte_length,
            )
            var.trace_add("write", lambda *_a, key=(category_name, name): self._mark_dirty(key))

    def _mark_dirty(self, key: tuple[str, str]) -> None:
        if self._initializing:
            return
        self._unsaved_changes.add(key)

    def _load_all_values(self) -> None:
        try:
            self.model.refresh_stadiums()
        except Exception:
            return
        for (cat, name), meta in self.field_meta.items():
            var = self.field_vars.get((cat, name))
            if var is None:
                continue
            val = self.model.decode_field_value(
                entity_type="stadium",
                entity_index=self.stadium_index,
                category=cat,
                field_name=name,
                meta=meta,
            )
            if val is None:
                continue
            if meta.values and isinstance(var, tk.IntVar):
                try:
                    idx = int(val)
                except Exception:
                    idx = 0
                var.set(idx)
                widget = meta.widget
                vals = list(meta.values)
                if isinstance(widget, ttk.Combobox) and 0 <= idx < len(vals):
                    try:
                        widget.set(vals[idx])
                    except Exception:
                        pass
            elif isinstance(var, tk.StringVar):
                var.set(str(val))
            elif isinstance(var, tk.DoubleVar):
                try:
                    var.set(float(val))
                except Exception:
                    pass
            else:
                try:
                    var.set(int(val))
                except Exception:
                    var.set(0)
        self._unsaved_changes.clear()

    def _save_all(self) -> None:
        errors: list[str] = []
        for (cat, name), meta in self.field_meta.items():
            var = self.field_vars.get((cat, name))
            if var is None:
                continue
            try:
                raw = var.get()
            except Exception:
                continue
            success = self.model.encode_field_value(
                entity_type="stadium",
                entity_index=self.stadium_index,
                category=cat,
                field_name=name,
                meta=meta,
                display_value=raw,
            )
            if not success:
                errors.append(f"{cat} / {name}")
        if errors:
            messagebox.showerror("Stadium Editor", f"Failed to save fields:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Stadium Editor", "Saved stadium values.")
            self._unsaved_changes.clear()


__all__ = ["FullStadiumEditor"]
