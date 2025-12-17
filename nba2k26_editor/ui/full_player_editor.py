"""Full player editor window (verbatim port from the monolithic editor)."""
from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Collection as CollectionABC
from typing import Collection, Dict, Sequence, TYPE_CHECKING
from tkinter import ttk, messagebox

from ..core.config import (
    PANEL_BG,
    INPUT_BG,
    PRIMARY_BG,
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
from ..core import offsets as offsets_module
from ..core.offsets import PLAYER_PANEL_FIELDS, PLAYER_PANEL_OVR_FIELD, ATTR_IMPORT_ORDER, TEND_IMPORT_ORDER, DUR_IMPORT_ORDER
from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    BADGE_NAME_TO_VALUE,
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    convert_minmax_potential_to_raw,
    convert_raw_to_minmax_potential,
    convert_raw_to_rating,
    convert_tendency_raw_to_rating,
    convert_rating_to_raw,
    convert_rating_to_tendency_raw,
    height_inches_to_raw,
    raw_height_to_inches,
    read_weight,
    to_int as _to_int,
    write_weight,
)
from ..core.extensions import FULL_EDITOR_EXTENSIONS
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from ..models.schema import FieldMetadata
from .widgets import bind_mousewheel

if TYPE_CHECKING:
    class RawFieldInspectorExtension: ...

_EXTENSION_LOGGER = logging.getLogger("nba2k26.extensions")


class FullPlayerEditor(tk.Toplevel):
    """A tabbed editor window for advanced player attributes."""
    def __init__(self, parent: tk.Tk, players: Player | Collection[Player], model: PlayerDataModel):
        super().__init__(parent)
        player_list: list[Player] = []
        if isinstance(players, Player):
            player_list = [players]
        elif isinstance(players, CollectionABC) and not isinstance(players, (str, bytes)):
            player_list = [p for p in players if isinstance(p, Player)]
        if not player_list:
            raise ValueError("FullPlayerEditor requires at least one player.")
        self.target_players: list[Player] = player_list
        self.player = self.target_players[0]
        self.model = model
        if len(self.target_players) == 1:
            title = f"Edit Player: {self.player.full_name}"
        else:
            title = f"Edit {len(self.target_players)} Players (showing {self.player.full_name})"
        self.title(title)
        # Dimensions: slightly larger for many fields
        self.geometry("700x500")
        self.configure(bg=PANEL_BG)
        style = ttk.Style(self)
        try:
            current_theme = style.theme_use()
            style.theme_use(current_theme)
        except Exception:
            pass
        style.configure("FullEditor.TNotebook", background=PANEL_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        tab_bg = "#1F3F6B"
        style.configure(
            "FullEditor.TNotebook.Tab",
            background=tab_bg,
            foreground=TEXT_PRIMARY,
            padding=(12, 6),
            borderwidth=0,
        )
        style.map(
            "FullEditor.TNotebook.Tab",
            background=[("selected", BUTTON_BG), ("active", BUTTON_ACTIVE_BG), ("!selected", tab_bg)],
            foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY), ("!selected", TEXT_PRIMARY)],
        )
        style.configure("FullEditor.TFrame", background=PANEL_BG, borderwidth=0)
        # Dictionary mapping category names to a mapping of field names to
        # Tkinter variables.  This allows us to load and save values easily.
        self.field_vars: dict[str, dict[str, tk.Variable]] = {}
        # Dictionary mapping (category_name, field_name) -> metadata dict
        # describing offset, start bit and bit length.  Using the tuple
        # avoids using unhashable Tkinter variables as keys.
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        # Dictionary to hold Spinbox widgets for each field.  The key is
        # (category_name, field_name) and the value is the Spinbox
        # instance.  Storing these allows us to compute min/max values
        # dynamically based on the widget's configuration (e.g. range)
        # when adjusting entire categories via buttons.
        self.spin_widgets: dict[tuple[str, str], tk.Spinbox] = {}
        self.raw_field_inspector: "RawFieldInspectorExtension | None" = None
        # Track fields edited since last save
        self._unsaved_changes: set[tuple[str, str]] = set()
        # Suppress change-trace callbacks while populating initial values
        self._initializing = True
        # Notebook for category tabs
        notebook = ttk.Notebook(self, style="FullEditor.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)
        # Determine which categories are available from the model.  If
        # categories are missing, we still display the tab with a placeholder.
        # Determine tab order.  Start with the common categories defined in
        # the offset map.  Then append any additional categories found in
        # the model that are not already listed.  Finally include
        # placeholder tabs for future extensions (Accessories, Contract).
        categories_map = self.model.get_categories_for_super("Players") or {}
        ordered = sorted(categories_map.keys())
        if not ordered:
            return
        for cat in ordered:
            frame = tk.Frame(notebook, bg=PANEL_BG, highlightthickness=0, bd=0)
            notebook.add(frame, text=cat)
            self._build_category_tab(frame, cat, categories_map.get(cat))
        # Extension hooks can attach a raw-field inspector to expose raw memory values.
        full_editor_context = {
            "notebook": notebook,
            "player": self.player,
            "model": model,
            "inspector": self.raw_field_inspector,
        }
        for factory in FULL_EDITOR_EXTENSIONS:
            try:
                factory(self, full_editor_context)
            except Exception as exc:
                _EXTENSION_LOGGER.exception("Full editor extension failed: %s", exc)
        # Action buttons at bottom
        btn_frame = tk.Frame(self, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, pady=5)
        save_btn = tk.Button(
            btn_frame,
            text="Save",
            command=self._save_all,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
        )
        save_btn.pack(side=tk.LEFT, padx=10)
        close_btn = tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            bg="#B0413E",
            fg="white",
            activebackground="#8D2C29",
            activeforeground="white",
            relief=tk.FLAT,
        )
        close_btn.pack(side=tk.LEFT)
        # Populate field values from memory
        self._load_all_values()
        self._initializing = False
    def _build_category_tab(self, parent: tk.Frame, category_name: str, fields_obj: list | None = None) -> None:
        """
        Build the UI for a specific category.  If field definitions are
        available for the category, create a grid of labels and spinboxes
        for each field.  Otherwise, display a placeholder message.
        """
        fields = fields_obj if isinstance(fields_obj, list) else self.model.categories.get(category_name, [])
        # Add category-level adjustment buttons for Attributes, Durability, and Tendencies
        if category_name in ("Attributes", "Durability", "Tendencies"):
            btn_frame = tk.Frame(parent, bg=PANEL_BG)
            btn_frame.pack(fill=tk.X, padx=10, pady=(5))
            actions = [
                ("Min", "min"),
                ("+5", "plus5"),
                ("+10", "plus10"),
                ("-5", "minus5"),
                ("-10", "minus10"),
                ("Max", "max"),
            ]
            for label, action in actions:
                tk.Button(
                    btn_frame,
                    text=label,
                    command=lambda act=action, cat=category_name: self._adjust_category(cat, act),
                    bg=BUTTON_BG,
                    fg=BUTTON_TEXT,
                    activebackground=BUTTON_ACTIVE_BG,
                    activeforeground=BUTTON_TEXT,
                    relief=tk.FLAT,
                    width=5,
                ).pack(side=tk.LEFT, padx=2)
        # Container for scrolled view if many fields
        canvas = tk.Canvas(parent, bg=PANEL_BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        try:
            scrollbar.configure(bg=PANEL_BG, troughcolor=PANEL_BG, activebackground=ACCENT_BG)
        except tk.TclError:
            pass
        scroll_frame = tk.Frame(canvas, bg=PANEL_BG)
        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set, bg=PANEL_BG)
        bind_mousewheel(scroll_frame, canvas)
        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Save variables mapping
        category_vars = self.field_vars.get(category_name)
        if category_vars is None:
            category_vars = dict[str, tk.Variable]()
            self.field_vars[category_name] = category_vars
        if not fields:
            # No definitions found
            tk.Label(
                scroll_frame,
                text=f"{category_name} editing not available.",
                bg=PANEL_BG,
                fg=TEXT_SECONDARY,
            ).pack(padx=10, pady=10)
            return
        # Build rows for each field
        for row, field in enumerate(fields):
            name = field.get("name", f"Field {row}")
            offset_val = _to_int(field.get("offset"))
            start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
            length = _to_int(field.get("length", 8))
            raw_size = _to_int(field.get("size"))
            raw_length = _to_int(field.get("length") or 0)
            byte_length = raw_size if raw_size > 0 else raw_length
            requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
            deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
            field_type = str(field.get("type", "")).lower()
            is_string_field = any(tag in field_type for tag in ("string", "text", "wstring", "wide", "utf16", "char"))
            is_float_field = "float" in field_type
            # Treat binary types as regular numeric bitfields; reserve this flag for pointer/color only.
            is_color_like = any(tag in field_type for tag in ("color", "pointer"))
            # Label
            lbl = tk.Label(scroll_frame, text=name + ":", bg=PANEL_BG, fg=TEXT_PRIMARY)
            lbl.grid(row=row, column=0, sticky=tk.W, padx=(10, 5), pady=2)
            if is_string_field:
                max_chars = length if length > 0 else byte_length
                enc_tag = field_type or "utf16"
                enc_norm = self.model._normalize_encoding_tag(enc_tag)
                # For UTF-16 strings the length from offsets is typically bytes; convert to chars when even.
                if enc_norm == "utf16" and max_chars > 0 and max_chars % 2 == 0:
                    max_chars = max_chars // 2
                if max_chars <= 0:
                    max_chars = 64
                var = tk.StringVar(value="")
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=24,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                    disabledbackground=ENTRY_BG,
                    disabledforeground=ENTRY_FG,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                category_vars[name] = var
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=max_chars,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=entry,
                    data_type=field_type or "string",
                    byte_length=byte_length,
                )
                def on_text_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_text_change)
                continue
            # Variable and spinbox
            var = tk.IntVar(value=0)
            # Determine raw maximum value for the bitfield
            max_raw = (1 << length) - 1
            # Compute the range shown in the spinbox.  For Attributes
            # categories we convert the raw 0..max_raw values to the 2K
            # rating scale of 25..99.  This mapping is handled in
            # _load_all_values/_save_all; here we restrict the spinbox
            # range to reflect the rating bounds.  For all other
            # categories we use the raw bit range.
            # Determine the displayed range of the Spinbox.  For
            # Attributes, Durability and Tendencies we display the
            # familiar 25..99 rating scale.  Conversion to/from raw
            # bitfield values is handled in the load/save methods.  For
            # all other categories, use the raw bit range.
            if category_name in ("Attributes", "Durability"):
                # Attributes and Durability use the familiar 25-99 rating scale
                spin_from = 25
                spin_to = 99
            elif category_name == "Tendencies":
                # Tendencies are displayed on a 0-100 scale
                spin_from = 0
                spin_to = 100
            elif name.lower() == "height":
                spin_from = HEIGHT_MIN_INCHES
                spin_to = HEIGHT_MAX_INCHES
            else:
                spin_from = 0
                spin_to = max_raw
            # Determine if this field has an enumeration of values defined.
            # If the field contains a "values" list, we use a combobox
            # populated with those values.  Otherwise we fall back to
            # category-specific handling (badges) or a numeric spinbox.
            if is_float_field:
                var = tk.DoubleVar(value=0.0)
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=18,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                    disabledbackground=ENTRY_BG,
                    disabledforeground=ENTRY_FG,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                category_vars[name] = var
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=entry,
                    data_type=field_type or "float",
                    byte_length=byte_length,
                )
                def on_float_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_float_change)
                continue
            if is_color_like:
                var = tk.StringVar(value="")
                entry = tk.Entry(
                    scroll_frame,
                    textvariable=var,
                    width=18,
                    bg=ENTRY_BG,
                    fg=ENTRY_FG,
                    insertbackground=ENTRY_FG,
                    relief=tk.FLAT,
                    highlightbackground=ENTRY_BORDER,
                    highlightthickness=1,
                    disabledbackground=ENTRY_BG,
                    disabledforeground=ENTRY_FG,
                )
                entry.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                category_vars[name] = var
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=entry,
                    data_type=field_type or "pointer",
                    byte_length=byte_length,
                )
                def on_color_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_color_change)
                continue
            values_list = field.get("values") if isinstance(field, dict) else None
            if values_list:
                # Create an IntVar to store the selected index
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=values_list,
                    state="readonly",
                    width=16,
                    style="App.TCombobox",
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                # When user picks an entry, update the IntVar accordingly
                def on_enum_selected(event=None, v=var, c=combo, vals=values_list):
                    try:
                        v.set(vals.index(c.get()))
                    except Exception:
                        v.set(0)
                combo.bind("<<ComboboxSelected>>", on_enum_selected)
                # Store variable
                category_vars[name] = var
                # Record metadata; keep reference to combobox and values list
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=combo,
                    values=tuple(str(v) for v in values_list),
                    data_type=field_type,
                    byte_length=byte_length,
                )
                # Flag unsaved changes
                def on_enum_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_enum_change)
            elif category_name == "Badges":
                # Special handling for badge levels: expose a human-readable
                # combobox instead of a numeric spinbox.  Each badge uses a
                # 3-bit field (0-7) but the game recognises only 0..4.
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=BADGE_LEVEL_NAMES,
                    state="readonly",
                    width=12,
                    style="App.TCombobox",
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                # When the user picks a level, update the IntVar
                def on_combo_selected(event, v=var, c=combo):
                    val_name = c.get()
                    v.set(BADGE_NAME_TO_VALUE.get(val_name, 0))
                combo.bind("<<ComboboxSelected>>", on_combo_selected)
                # Store variable for this field
                category_vars[name] = var
                # Record metadata; also keep reference to combobox for later update
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=combo,
                    values=tuple(BADGE_LEVEL_NAMES),
                    data_type=field_type,
                    byte_length=byte_length,
                )
                # Flag unsaved changes
                def on_badge_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_badge_change)
            else:
                # Use Spinbox for numeric values; large ranges may be unwieldy
                spin = tk.Spinbox(
                    scroll_frame,
                    from_=spin_from,
                    to=spin_to,
                    textvariable=var,
                    width=10,
                    bg=INPUT_BG,
                    fg=TEXT_PRIMARY,
                    highlightbackground=ACCENT_BG,
                    highlightthickness=1,
                    relief=tk.FLAT,
                    insertbackground=TEXT_PRIMARY,
                )
                spin.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                spin.configure(selectbackground=ACCENT_BG, selectforeground=TEXT_PRIMARY)
                # Store variable by name for this category
                category_vars[name] = var
                # Record metadata keyed by (category, field_name)
                self.field_meta[(category_name, name)] = FieldMetadata(
                    offset=offset_val,
                    start_bit=start_bit,
                    length=length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    widget=spin,
                    data_type=field_type,
                    byte_length=byte_length,
                )
                # Save the Spinbox widget for later category-wide adjustments
                self.spin_widgets[(category_name, name)] = spin
                # Flag unsaved changes when the value changes
                def on_spin_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_spin_change)
    def _load_all_values(self) -> None:
        """
        Populate all spinboxes with current values from memory.  This
        iterates over the categories and fields stored in
        ``self.field_vars`` and calls ``model.get_field_value`` for
        each one.
        """
        def _is_string_meta(meta: FieldMetadata | None) -> bool:
            if not meta or not meta.data_type:
                return False
            dtype = meta.data_type.lower()
            return any(tag in dtype for tag in ("string", "text", "char", "wstr", "utf", "wide"))
        def _is_float_meta(meta: FieldMetadata | None) -> bool:
            return bool(meta and meta.data_type and "float" in meta.data_type.lower())
        def _is_color_meta(meta: FieldMetadata | None) -> bool:
            if not meta or not meta.data_type:
                return False
            dtype = meta.data_type.lower()
            return any(tag in dtype for tag in ("color", "pointer"))
        # Iterate over each category and field to load values using stored
        # metadata.  The metadata is stored in ``self.field_meta`` keyed by
        # (category, field_name).  We then set the associated variable.
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
                    record_addr = self.model._player_record_address(
                        self.player.index, record_ptr=getattr(self.player, "record_ptr", None)
                    )
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
                            # Convert byte length to characters for wide strings when applicable.
                            char_limit = max(char_limit, meta.byte_length // 2)
                        text_val = self.model._read_string(addr, char_limit, enc_tag)
                        var.set(text_val)
                    except Exception:
                        continue
                    continue
                if _is_float_meta(meta):
                    value = self.model.get_field_value_typed(
                        self.player.index,
                        offset,
                        start_bit,
                        length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=meta.data_type,
                        byte_length=meta.byte_length,
                        record_ptr=getattr(self.player, "record_ptr", None),
                    )
                    if value is not None:
                        try:
                            var.set(float(value))
                        except Exception:
                            pass
                    continue
                if _is_color_meta(meta):
                    value = self.model.get_field_value_typed(
                        self.player.index,
                        offset,
                        start_bit,
                        length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=meta.data_type,
                        byte_length=meta.byte_length,
                        record_ptr=getattr(self.player, "record_ptr", None),
                    )
                    if value is not None:
                        try:
                            byte_len = self.model._effective_byte_length(meta.byte_length, meta.length, default=4)
                        except Exception:
                            byte_len = 4
                        width = max(1, byte_len * 2)
                        try:
                            var.set(f"0x{int(value) & ((1 << (width * 4)) - 1):0{width}X}")
                        except Exception:
                            var.set(str(value))
                    continue
                value = self.model.get_field_value(
                    self.player.index,
                    offset,
                    start_bit,
                    length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                    record_ptr=getattr(self.player, "record_ptr", None),
                )
                if value is not None:
                    try:
                        # Convert raw bitfield values to user‑friendly values
                        field_name_lower = field_name.lower()
                        if field_name_lower == "height":
                            inches_val = raw_height_to_inches(int(value))
                            inches_val = max(HEIGHT_MIN_INCHES, min(HEIGHT_MAX_INCHES, inches_val))
                            var.set(inches_val)
                        elif field_name_lower == "weight":
                            try:
                                self.model.mem.open_process()
                            except Exception:
                                pass
                            record_addr = self.model._player_record_address(
                                self.player.index, record_ptr=getattr(self.player, "record_ptr", None)
                            )
                            if record_addr is not None:
                                wval = read_weight(self.model.mem, record_addr + offset)
                                var.set(int(round(wval)))
                            else:
                                var.set(0)
                        elif category in ("Attributes", "Durability"):  # Map the raw bitfield value into the 25-99 rating scale
                            rating = convert_raw_to_rating(int(value), length)
                            var.set(int(rating))
                        elif category == "Potential":
                            if "min" in field_name_lower or "max" in field_name_lower:
                                rating = convert_raw_to_minmax_potential(int(value), length)
                                var.set(int(rating))
                            else:
                                rating = convert_raw_to_rating(int(value), length)
                                var.set(int(rating))
                        elif category == "Tendencies":
                            # Tendencies use a 0–100 scale
                            rating = convert_tendency_raw_to_rating(int(value), length)
                            var.set(int(rating))
                        elif category == "Badges":
                            # Badges are stored as 3‑bit fields; clamp to 0–4
                            lvl = int(value)
                            if lvl < 0:
                                lvl = 0
                            elif lvl > 4:
                                lvl = 4
                            var.set(lvl)
                            # Update combobox display if present
                            widget = meta.widget
                            if isinstance(widget, ttk.Combobox):
                                try:
                                    widget.set(BADGE_LEVEL_NAMES[lvl])
                                except Exception:
                                    pass
                        elif meta.values:
                            # Enumerated field: clamp the raw value to the index range
                            vals = meta.values
                            values_len = len(vals)
                            if values_len == 0:
                                continue
                            idx = int(value)
                            if idx < 0:
                                idx = 0
                            elif idx >= values_len:
                                idx = values_len - 1
                            var.set(idx)
                            # Update combobox display
                            widget = meta.widget
                            if isinstance(widget, ttk.Combobox):
                                try:
                                    widget.set(vals[idx])
                                except Exception:
                                    pass
                        else:
                            # Other categories are shown as their raw integer values
                            var.set(int(value))
                    except Exception:
                        pass
    def _save_all(self) -> None:
        """
        Iterate over all fields and write the current values back to the
        player's record in memory.
        """
        # Iterate similar to load
        any_error = False
        targets = self.target_players or [self.player]
        player_base_addr: int | None = None
        def _is_string_meta(meta: FieldMetadata | None) -> bool:
            if not meta or not meta.data_type:
                return False
            dtype = meta.data_type.lower()
            return any(tag in dtype for tag in ("string", "text", "char", "wstr", "utf", "wide"))
        def _is_float_meta(meta: FieldMetadata | None) -> bool:
            return bool(meta and meta.data_type and "float" in meta.data_type.lower())
        def _is_color_meta(meta: FieldMetadata | None) -> bool:
            if not meta or not meta.data_type:
                return False
            dtype = meta.data_type.lower()
            return any(tag in dtype for tag in ("color", "pointer", "binary"))
        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                try:
                    offset = meta.offset
                    start_bit = meta.start_bit
                    length = meta.length
                    requires_deref = meta.requires_deref
                    deref_offset = meta.deref_offset
                    if _is_string_meta(meta):
                        try:
                            self.model.mem.open_process()
                        except Exception:
                            any_error = True
                            continue
                        try:
                            text_val = str(var.get())
                        except Exception:
                            text_val = ""
                        char_limit = length if length > 0 else meta.byte_length
                        if char_limit <= 0:
                            char_limit = max(len(text_val), 1)
                        enc_tag = meta.data_type or "utf16"
                        enc_norm = self.model._normalize_encoding_tag(enc_tag)
                        if enc_norm == "utf16" and meta.byte_length and meta.byte_length % 2 == 0:
                            char_limit = max(char_limit, meta.byte_length // 2)
                        for target in targets:
                            try:
                                record_addr = self.model._player_record_address(
                                    target.index, record_ptr=getattr(target, "record_ptr", None)
                                )
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
                        for target in targets:
                            ok = self.model.set_field_value_typed(
                                target.index,
                                offset,
                                start_bit,
                                length,
                                ui_val,
                                requires_deref=requires_deref,
                                deref_offset=deref_offset,
                                field_type=meta.data_type,
                                byte_length=meta.byte_length,
                                record_ptr=getattr(target, "record_ptr", None),
                            )
                            any_error = any_error or not ok
                        continue
                    if _is_color_meta(meta):
                        try:
                            raw_text = str(var.get())
                        except Exception:
                            raw_text = ""
                        parsed_val: int | None = None
                        if raw_text:
                            try:
                                cleaned = raw_text.strip()
                                if cleaned.startswith("#"):
                                    cleaned = cleaned[1:]
                                parsed_val = int(cleaned, 16) if cleaned.lower().startswith("0x") or raw_text.strip().startswith("#") else int(cleaned, 0)
                            except Exception:
                                try:
                                    parsed_val = int(float(raw_text))
                                except Exception:
                                    parsed_val = None
                        if parsed_val is None:
                            any_error = True
                            continue
                        # Clamp to bit-length if available
                        if length > 0:
                            mask = (1 << length) - 1
                            parsed_val &= mask
                        for target in targets:
                            ok = self.model.set_field_value_typed(
                                target.index,
                                offset,
                                start_bit,
                                length,
                                parsed_val,
                                requires_deref=requires_deref,
                                deref_offset=deref_offset,
                                field_type=meta.data_type,
                                byte_length=meta.byte_length,
                                record_ptr=getattr(target, "record_ptr", None),
                            )
                            any_error = any_error or not ok
                        continue
                    # Retrieve the value from the UI
                    ui_value = var.get()
                    # Convert rating back to raw bitfield for Attributes,
                    # Durability and Tendencies.  Observations indicate
                    # that ratings are stored with an offset of 10 (i.e., a
                    # rating of 25 corresponds to raw 15 and a rating of 99
                    # corresponds to raw 89).  Therefore we simply
                    # subtract 10 from the rating and clamp the result to
                    # the valid bitfield range.  Other categories are
                    # written as-is.
                    field_name_lower = field_name.lower()
                    if field_name_lower == "height":
                        try:
                            inches_val = int(ui_value)
                        except Exception:
                            inches_val = HEIGHT_MIN_INCHES
                        if inches_val < HEIGHT_MIN_INCHES:
                            inches_val = HEIGHT_MIN_INCHES
                        elif inches_val > HEIGHT_MAX_INCHES:
                            inches_val = HEIGHT_MAX_INCHES
                        value_to_write = height_inches_to_raw(inches_val)
                    elif field_name_lower == "weight":
                        try:
                            wval = float(ui_value)
                        except Exception:
                            wval = 0.0
                        try:
                            self.model.mem.open_process()
                        except Exception:
                            pass
                        for target in targets:
                            try:
                                addr = self.model._player_record_address(
                                    target.index, record_ptr=getattr(target, "record_ptr", None)
                                )
                                if addr is None:
                                    any_error = True
                                    continue
                                write_weight(self.model.mem, addr + offset, wval)
                            except Exception:
                                any_error = True
                        continue
                    elif category in ("Attributes", "Durability"):  # Convert the UI rating back into a raw bitfield value.
                        try:
                            rating_val = int(ui_value)
                        except Exception:
                            rating_val = 25
                        value_to_write = convert_rating_to_raw(rating_val, length)
                    elif category == "Tendencies":
                        # Tendencies: convert the 0–100 rating back to raw bitfield
                        try:
                            rating_val = float(ui_value)
                        except Exception:
                            rating_val = 0.0
                        value_to_write = convert_rating_to_tendency_raw(rating_val, length)
                    elif category == "Badges":
                        # Badges: clamp UI value (0-4) to the underlying bitfield
                        try:
                            lvl = int(ui_value)
                        except Exception:
                            lvl = 0
                        if lvl < 0:
                            lvl = 0
                        max_raw = (1 << length) - 1
                        if lvl > max_raw:
                            lvl = max_raw
                        value_to_write = lvl
                    elif meta.values:
                        # Enumerated field: clamp UI value to the bitfield range
                        values_tuple = meta.values
                        values_len = len(values_tuple)
                        if values_len == 0:
                            continue
                        try:
                            idx_val = int(ui_value)
                        except Exception:
                            idx_val = 0
                        if idx_val < 0:
                            idx_val = 0
                        max_raw = (1 << length) - 1
                        if idx_val > max_raw:
                            idx_val = max_raw
                        if idx_val >= values_len:
                            idx_val = values_len - 1
                        value_to_write = idx_val
                    else:
                        # For other categories, write the raw value directly
                        value_to_write = ui_value
                    for target in targets:
                        if not self.model.set_field_value(
                            target.index,
                            offset,
                            start_bit,
                            length,
                            value_to_write,
                            requires_deref=requires_deref,
                            deref_offset=deref_offset,
                            record_ptr=getattr(target, "record_ptr", None),
                        ):
                            any_error = True
                except Exception:
                    any_error = True
        if any_error:
            messagebox.showerror("Save Error", "One or more fields could not be saved.")
        else:
            if len(targets) > 1:
                messagebox.showinfo("Save Successful", f"All fields saved for {len(targets)} players.")
            else:
                messagebox.showinfo("Save Successful", "All fields saved successfully.")
    def _adjust_category(self, category_name: str, action: str) -> None:
        """
        Adjust all values within a category according to the specified action.
        Actions can be one of: 'min', 'max', 'plus5', 'plus10', 'minus5', 'minus10'.
        For Attributes, Durability and Tendencies categories, values are clamped
        to the 25..99 scale.  For other categories, values are clamped to the
        raw bitfield range (0..(2^length - 1)).
        """
        # Ensure the category exists
        fields = self.field_vars.get(category_name)
        if not fields:
            return
        for field_name, var in fields.items():
            # Retrieve bit length from metadata
            meta = self.field_meta.get((category_name, field_name))
            if not meta:
                continue
            if meta.data_type and any(
                tag in meta.data_type.lower() for tag in ("string", "text", "char", "wstr", "utf", "wide")
            ):
                continue
            length = meta.length
            # Determine min and max values based on category
            if category_name in ("Attributes", "Durability"):
                # Attributes and Durability: clamp to 25..99
                min_val = 25
                max_val = 99
            elif category_name == "Tendencies":
                # Tendencies: clamp to 0..100
                min_val = 0
                max_val = 100
            else:
                min_val = 0
                max_val = (1 << int(length)) - 1
            current = var.get()
            new_val = current
            if action == "min":
                new_val = min_val
            elif action == "max":
                new_val = max_val
            elif action == "plus5":
                new_val = current + 5
            elif action == "plus10":
                new_val = current + 10
            elif action == "minus5":
                new_val = current - 5
            elif action == "minus10":
                new_val = current - 10
            # Clamp to allowed range
            if new_val < min_val:
                new_val = min_val
            if new_val > max_val:
                new_val = max_val
            var.set(int(new_val))
# ---------------------------------------------------------------------
# Team full editor
# ---------------------------------------------------------------------


__all__ = ["FullPlayerEditor"]
