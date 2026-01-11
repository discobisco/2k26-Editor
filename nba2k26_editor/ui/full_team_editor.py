"""Full team editor window (ported from the monolithic editor)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict

from ..core.config import (
    PANEL_BG,
    INPUT_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    ACCENT_BG,
    BUTTON_BG,
    BUTTON_ACTIVE_BG,
    BUTTON_TEXT,
    ENTRY_BG,
    ENTRY_FG,
    ENTRY_BORDER,
)
from ..core.conversions import to_int
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from ..models.schema import FieldMetadata
from .widgets import bind_mousewheel


class FullTeamEditor(tk.Toplevel):
    """Tabbed editor window for team offsets."""

    def __init__(self, parent: tk.Tk, team_index: int, team_name: str, model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.team_index = team_index
        self.team_name = team_name
        self.model = model
        self.title(f"Edit Team: {team_name}")
        self.geometry("700x480")
        self.configure(bg=PANEL_BG)
        style = ttk.Style(self)
        try:
            current_theme = style.theme_use()
            style.theme_use(current_theme)
        except Exception:
            pass
        style.configure("TeamEditor.TNotebook", background=PANEL_BG, borderwidth=0)
        style.configure(
            "TeamEditor.TNotebook.Tab",
            background=PANEL_BG,
            foreground=TEXT_SECONDARY,
            padding=(12, 6),
        )
        style.map(
            "TeamEditor.TNotebook.Tab",
            background=[("selected", BUTTON_BG), ("active", ACCENT_BG)],
            foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY)],
        )
        style.configure("TeamEditor.TFrame", background=PANEL_BG)
        try:
            style.configure(
                "TeamEditor.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=ACCENT_BG,
                arrowcolor=TEXT_PRIMARY,
            )
        except tk.TclError:
            style.configure(
                "TeamEditor.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
            )
        style.map(
            "TeamEditor.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", TEXT_PRIMARY)],
        )
        self.field_vars: dict[str, dict[str, tk.Variable]] = {}
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        self.spin_widgets: dict[tuple[str, str], tk.Spinbox] = {}
        self._unsaved_changes: set[tuple[str, str]] = set()
        self._initializing = True
        notebook = ttk.Notebook(self, style="TeamEditor.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)
        team_categories = self.model.get_categories_for_super("Teams") or {}
        if team_categories:
            ordered = sorted(team_categories.keys())
            for cat in ordered:
                frame = tk.Frame(notebook, bg=PANEL_BG, highlightthickness=0, bd=0)
                notebook.add(frame, text=cat)
                self._build_category_tab(frame, cat, team_categories.get(cat))
        else:
            frame = tk.Frame(notebook, bg=PANEL_BG, highlightthickness=0, bd=0)
            notebook.add(frame, text="Teams")
            tk.Label(
                frame,
                text="No team categories found in the offsets file.",
                bg=PANEL_BG,
                fg=TEXT_SECONDARY,
            ).pack(padx=12, pady=12, anchor="w")
        btn_frame = tk.Frame(self, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, pady=6)
        tk.Button(
            btn_frame,
            text="Save",
            command=self._save_all,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            bg="#B0413E",
            fg="white",
            activebackground="#8D2C29",
            activeforeground="white",
            relief=tk.FLAT,
        ).pack(side=tk.LEFT)
        self._load_all_values()
        self._initializing = False

    @staticmethod
    def _is_string_type(dtype: str | None) -> bool:
        if not dtype:
            return False
        dtype_lower = dtype.lower()
        return any(tag in dtype_lower for tag in ("string", "text", "char", "wstr", "utf", "wide"))

    @staticmethod
    def _is_float_type(dtype: str | None) -> bool:
        return bool(dtype and "float" in dtype.lower())

    @staticmethod
    def _is_color_type(dtype: str | None) -> bool:
        if not dtype:
            return False
        dtype_lower = dtype.lower()
        return any(tag in dtype_lower for tag in ("color", "pointer"))

    def _build_category_tab(self, parent: tk.Frame, category_name: str, fields_obj: list | None = None) -> None:
        fields = fields_obj if isinstance(fields_obj, list) else self.model.categories.get(category_name, [])
        if not fields:
            tk.Label(parent, text="No fields found for this category.", bg=PANEL_BG, fg=TEXT_SECONDARY).pack(
                padx=12, pady=12, anchor="w"
            )
            return
        container = tk.Frame(parent, bg=PANEL_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        canvas = tk.Canvas(container, bg=PANEL_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=PANEL_BG)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        bind_mousewheel(scroll_frame, canvas)
        category_vars: dict[str, tk.Variable] = {}
        self.field_vars[category_name] = category_vars
        row = 0
        for field in fields:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or f"Field {row + 1}")
            offset_val = to_int(field.get("offset") or field.get("address") or field.get("hex"))
            length = to_int(field.get("length") or field.get("size"))
            if offset_val is None or offset_val < 0 or length is None or length <= 0:
                continue
            start_bit = to_int(field.get("startBit") or field.get("start_bit"))
            field_type = str(field.get("type") or "")
            requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
            deref_offset = to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
            byte_length = to_int(
                field.get("byteLength")
                or field.get("byte_length")
                or field.get("lengthBytes")
                or field.get("size")
                or field.get("length")
            )
            values_list = field.get("values") if isinstance(field, dict) else None
            tk.Label(
                scroll_frame,
                text=name,
                bg=PANEL_BG,
                fg=TEXT_PRIMARY,
            ).grid(row=row, column=0, sticky=tk.W, padx=(0, 10), pady=2)
            if values_list:
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=values_list,
                    state="readonly",
                    width=20,
                    style="TeamEditor.TCombobox",
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                if values_list:
                    try:
                        combo.set(values_list[0])
                    except Exception:
                        pass

                def on_enum_selected(event, v=var, c=combo, vals=values_list):
                    try:
                        v.set(vals.index(c.get()))
                    except Exception:
                        v.set(0)

                combo.bind("<<ComboboxSelected>>", on_enum_selected)
                widget = combo
            elif self._is_string_type(field_type):
                var = tk.StringVar()
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    relief=tk.FLAT,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    highlightthickness=1,
                    highlightbackground=ENTRY_BORDER,
                )
                entry.grid(row=row, column=1, sticky=tk.W + tk.E, padx=(0, 10), pady=2)
                widget = entry
            elif self._is_float_type(field_type):
                var = tk.DoubleVar(value=0.0)
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    relief=tk.FLAT,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    highlightthickness=1,
                    highlightbackground=ENTRY_BORDER,
                )
                entry.grid(row=row, column=1, sticky=tk.W + tk.E, padx=(0, 10), pady=2)
                widget = entry
            elif self._is_color_type(field_type):
                var = tk.StringVar(value="")
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    relief=tk.FLAT,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    highlightthickness=1,
                    highlightbackground=ENTRY_BORDER,
                )
                entry.grid(row=row, column=1, sticky=tk.W + tk.E, padx=(0, 10), pady=2)
                widget = entry
            else:
                var = tk.IntVar(value=0)
                spin_from = 0
                try:
                    spin_to = (1 << length) - 1 if length and length < 31 else 999999
                except Exception:
                    spin_to = 999999
                spin = tk.Spinbox(
                    scroll_frame,
                    from_=spin_from,
                    to=spin_to,
                    textvariable=var,
                    width=12,
                    bg=INPUT_BG,
                    fg=TEXT_PRIMARY,
                    highlightbackground=ACCENT_BG,
                    highlightthickness=1,
                    relief=tk.FLAT,
                    insertbackground=TEXT_PRIMARY,
                )
                spin.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                spin.configure(selectbackground=ACCENT_BG, selectforeground=TEXT_PRIMARY)
                widget = spin
                self.spin_widgets[(category_name, name)] = spin
            category_vars[name] = var
            self.field_meta[(category_name, name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=widget,
                values=tuple(str(v) for v in values_list) if values_list else None,
                data_type=field_type.lower() if isinstance(field_type, str) else field_type,
                byte_length=byte_length,
            )

            def on_change(*args, cat=category_name, field_name=name):
                if getattr(self, "_initializing", False):
                    return
                self._unsaved_changes.add((cat, field_name))

            var.trace_add("write", on_change)
            row += 1
        for col in range(2):
            scroll_frame.grid_columnconfigure(col, weight=1)

    def _load_all_values(self) -> None:
        """Populate all fields from live memory."""
        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                value = self.model.decode_field_value(
                    entity_type="team",
                    entity_index=self.team_index,
                    category=category,
                    field_name=field_name,
                    meta=meta,
                )
                if value is None:
                    continue
                if meta.values and isinstance(var, tk.IntVar):
                    try:
                        idx = to_int(value)
                        var.set(idx)
                        widget = meta.widget
                        vals = list(meta.values)
                        if isinstance(widget, ttk.Combobox) and 0 <= idx < len(vals):
                            try:
                                widget.set(vals[idx])
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    try:
                        if isinstance(var, tk.StringVar):
                            var.set(str(value))
                        elif isinstance(var, tk.DoubleVar):
                            if isinstance(value, (int, float)):
                                var.set(float(value))
                            else:
                                var.set(float(str(value)))
                        else:
                            var.set(to_int(value))
                    except Exception:
                        pass

    def _save_all(self) -> None:
        """Write all edited fields back to the team record."""
        if not self.model.mem.hproc:
            messagebox.showerror("Save Error", "NBA 2K26 is not running.")
            return
        any_error = False
        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                try:
                    ui_value = var.get()
                except Exception:
                    any_error = True
                    continue
                ok = self.model.encode_field_value(
                    entity_type="team",
                    entity_index=self.team_index,
                    category=category,
                    field_name=field_name,
                    meta=meta,
                    display_value=ui_value,
                )
                any_error = any_error or not ok
        if any_error:
            messagebox.showerror("Save Error", "One or more fields could not be saved.")
        else:
            messagebox.showinfo("Save Successful", f"Saved fields for {self.team_name}.")


__all__ = ["FullTeamEditor"]
