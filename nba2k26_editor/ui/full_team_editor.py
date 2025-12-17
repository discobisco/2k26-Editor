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

        def _is_string_meta(meta: FieldMetadata | None) -> bool:
            return self._is_string_type(meta.data_type if meta else None)
        def _is_float_meta(meta: FieldMetadata | None) -> bool:
            return self._is_float_type(meta.data_type if meta else None)
        def _is_color_meta(meta: FieldMetadata | None) -> bool:
            return self._is_color_type(meta.data_type if meta else None)

        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                offset = meta.offset
                start_bit = meta.start_bit
                length = meta.length
                requires_deref = meta.requires_deref
                deref_offset = meta.deref_offset
                if _is_string_meta(meta):
                    try:
                        self.model.mem.open_process()
                    except Exception:
                        continue
                    record_addr = self.model._team_record_address(self.team_index)
                    if record_addr is None:
                        continue
                    try:
                        addr = record_addr + offset
                        if requires_deref and deref_offset:
                            struct_ptr = self.model.mem.read_uint64(record_addr + deref_offset)
                            if not struct_ptr:
                                continue
                            addr = struct_ptr + offset
                        char_limit = length if length > 0 else meta.byte_length
                        if char_limit <= 0:
                            char_limit = 64
                        enc_tag = meta.data_type or "utf16"
                        enc_norm = self.model._normalize_encoding_tag(enc_tag)
                        if enc_norm == "utf16" and meta.byte_length and meta.byte_length % 2 == 0:
                            char_limit = max(char_limit, meta.byte_length // 2)
                        text_val = self.model._read_string(addr, char_limit, enc_tag)
                        var.set(text_val)
                    except Exception:
                        continue
                    continue
                if _is_float_meta(meta):
                    value = self.model.get_team_field_value_typed(
                        self.team_index,
                        offset,
                        start_bit,
                        length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=meta.data_type,
                        byte_length=meta.byte_length,
                    )
                    if value is None:
                        continue
                    try:
                        var.set(float(value))
                    except Exception:
                        continue
                    continue
                if _is_color_meta(meta):
                    value = self.model.get_team_field_value_typed(
                        self.team_index,
                        offset,
                        start_bit,
                        length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=meta.data_type,
                        byte_length=meta.byte_length,
                    )
                    if value is None:
                        continue
                    try:
                        bitlen = length if length > 0 else meta.byte_length * 8
                        width = max(1, (bitlen + 3) // 4)
                        var.set(f"0x{int(value) & ((1 << bitlen) - 1):0{width}X}")
                    except Exception:
                        try:
                            var.set(str(value))
                        except Exception:
                            pass
                    continue
                value = self.model.get_team_field_value_typed(
                    self.team_index,
                    offset,
                    start_bit,
                    length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    field_type=meta.data_type,
                    byte_length=meta.byte_length,
                )
                if value is None:
                    continue
                if meta.values and isinstance(var, tk.IntVar):
                    try:
                        var.set(int(value))
                        widget = meta.widget
                        vals = list(meta.values)
                        if isinstance(widget, ttk.Combobox) and 0 <= int(value) < len(vals):
                            try:
                                widget.set(vals[int(value)])
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    try:
                        if isinstance(var, tk.StringVar):
                            var.set(str(value))
                        else:
                            var.set(int(value))
                    except Exception:
                        pass

    def _save_all(self) -> None:
        """Write all edited fields back to the team record."""
        if not self.model.mem.hproc:
            messagebox.showerror("Save Error", "NBA 2K26 is not running.")
            return
        any_error = False

        def _is_string_meta(meta: FieldMetadata | None) -> bool:
            return self._is_string_type(meta.data_type if meta else None)

        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                offset = meta.offset
                start_bit = meta.start_bit
                length = meta.length
                requires_deref = meta.requires_deref
                deref_offset = meta.deref_offset
                if _is_string_meta(meta):
                    try:
                        text_val = str(var.get())
                    except Exception:
                        text_val = ""
                    try:
                        record_addr = self.model._team_record_address(self.team_index)
                        if record_addr is None:
                            any_error = True
                            continue
                        addr = record_addr + offset
                        if requires_deref and deref_offset:
                            struct_ptr = self.model.mem.read_uint64(record_addr + deref_offset)
                            if not struct_ptr:
                                any_error = True
                                continue
                            addr = struct_ptr + offset
                        char_limit = length if length > 0 else meta.byte_length
                        if char_limit <= 0:
                            char_limit = max(len(text_val), 1)
                        enc_tag = meta.data_type or "utf16"
                        enc_norm = self.model._normalize_encoding_tag(enc_tag)
                        if enc_norm == "utf16" and meta.byte_length and meta.byte_length % 2 == 0:
                            char_limit = max(char_limit, meta.byte_length // 2)
                        self.model._write_string(addr, text_val, char_limit, enc_tag)
                    except Exception:
                        any_error = True
                    continue
                if _is_float_meta(meta):
                    try:
                        ui_val = float(var.get())
                    except Exception:
                        any_error = True
                        continue
                    try:
                        ok = self.model.set_team_field_value_typed(
                            self.team_index,
                            offset,
                            start_bit,
                            length,
                            ui_val,
                            requires_deref=requires_deref,
                            deref_offset=deref_offset,
                            field_type=meta.data_type,
                            byte_length=meta.byte_length,
                        )
                        any_error = any_error or not ok
                    except Exception:
                        any_error = True
                    continue
                if _is_color_meta(meta):
                    try:
                        raw_text = str(var.get()).strip()
                    except Exception:
                        raw_text = ""
                    parsed_val: int | None = None
                    if raw_text:
                        try:
                            cleaned = raw_text
                            if cleaned.startswith("#"):
                                cleaned = cleaned[1:]
                            parsed_val = int(cleaned, 16) if cleaned.lower().startswith("0x") or raw_text.startswith("#") else int(cleaned, 0)
                        except Exception:
                            try:
                                parsed_val = int(float(raw_text))
                            except Exception:
                                parsed_val = None
                    if parsed_val is None:
                        any_error = True
                        continue
                    try:
                        ok = self.model.set_team_field_value_typed(
                            self.team_index,
                            offset,
                            start_bit,
                            length,
                            parsed_val,
                            requires_deref=requires_deref,
                            deref_offset=deref_offset,
                            field_type=meta.data_type,
                            byte_length=meta.byte_length,
                        )
                        any_error = any_error or not ok
                    except Exception:
                        any_error = True
                    continue
                try:
                    ui_value = var.get()
                except Exception:
                    any_error = True
                    continue
                if meta.values:
                    try:
                        max_raw = (1 << length) - 1
                    except Exception:
                        max_raw = len(meta.values) - 1
                    try:
                        idx_val = int(ui_value)
                    except Exception:
                        idx_val = 0
                    if idx_val < 0:
                        idx_val = 0
                    if max_raw > 0 and idx_val > max_raw:
                        idx_val = max_raw
                    if idx_val >= len(meta.values):
                        idx_val = len(meta.values) - 1
                    value_to_write = idx_val
                else:
                    try:
                        value_to_write = int(ui_value)
                    except Exception:
                        any_error = True
                        continue
                if not self.model.set_team_field_value_typed(
                    self.team_index,
                    offset,
                    start_bit,
                    length,
                    value_to_write,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    field_type=meta.data_type,
                    byte_length=meta.byte_length,
                ):
                    any_error = True
        if any_error:
            messagebox.showerror("Save Error", "One or more fields could not be saved.")
        else:
            messagebox.showinfo("Save Successful", f"Saved fields for {self.team_name}.")


__all__ = ["FullTeamEditor"]
