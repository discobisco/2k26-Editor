"""Batch edit window (ported from the monolithic editor)."""
from __future__ import annotations

import tkinter as tk
from typing import cast
from tkinter import ttk

from ..core.conversions import to_int
from ..core.offsets import PLAYER_STRIDE
from ..models.data_model import PlayerDataModel
from ..models.schema import FieldWriteSpec
from .widgets import bind_mousewheel


class BatchEditWindow(tk.Toplevel):
    """
    Apply a single field value across many players (by team selection).

    Supports enumerated fields (combobox) and numeric fields (spinbox),
    plus a convenience button to reset core ratings.
    """

    def __init__(self, parent: tk.Tk, model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Batch Edit")
        self.model = model
        self.team_vars: dict[str, tk.BooleanVar] = {}
        self.category_var = tk.StringVar()
        self.field_var = tk.StringVar()
        self.value_widget: tk.Widget | None = None
        self.value_var: tk.Variable | None = None
        self.configure(bg="#F5F5F5")
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        """Construct controls for category/field selection and team targeting."""
        tk.Label(self, text="Select teams, choose a field and enter a value:", bg="#F5F5F5", font=("Segoe UI", 11)).pack(
            pady=(10, 5)
        )
        sel_frame = tk.Frame(self, bg="#F5F5F5")
        sel_frame.pack(fill=tk.X, padx=10)
        tk.Label(sel_frame, text="Category:", bg="#F5F5F5").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        categories = list(self.model.categories.keys())
        self.category_combo = ttk.Combobox(sel_frame, textvariable=self.category_var, state="readonly", values=categories)
        self.category_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_selected)
        tk.Label(sel_frame, text="Field:", bg="#F5F5F5").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.field_combo = ttk.Combobox(sel_frame, textvariable=self.field_var, state="readonly", values=[])
        self.field_combo.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.field_combo.bind("<<ComboboxSelected>>", self._on_field_selected)
        self.input_frame = tk.Frame(self, bg="#F5F5F5")
        self.input_frame.pack(fill=tk.X, padx=10, pady=(5, 5))
        teams_frame = tk.Frame(self, bg="#F5F5F5")
        teams_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(teams_frame, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(teams_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        bind_mousewheel(scroll_frame, canvas)
        try:
            team_names = self.model.get_teams()
        except Exception:
            team_names = []
        if not team_names:
            team_names = [name for _, name in self.model.team_list]
        for idx, name in enumerate(team_names):
            var = tk.BooleanVar(value=False)
            self.team_vars[name] = var
            tk.Checkbutton(scroll_frame, text=name, variable=var, bg="#F5F5F5").grid(row=idx, column=0, sticky=tk.W, padx=5, pady=2)
        btn_frame = tk.Frame(self, bg="#F5F5F5")
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Button(btn_frame, text="Apply", command=self._apply_changes, bg="#52796F", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(
            btn_frame,
            text="Reset Core Ratings",
            command=self._reset_core_fields,
            bg="#386641",
            fg="white",
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(side=tk.RIGHT)

    def _on_category_selected(self, _event: tk.Event | None = None) -> None:
        """Update field dropdown when category changes."""
        category = self.category_var.get()
        self.field_var.set("")
        if self.value_widget is not None:
            self.value_widget.destroy()
            self.value_widget = None
            self.value_var = None
        fields = self.model.categories.get(category, [])
        names = [f.get("name", "") for f in fields]
        self.field_combo.config(values=names)
        self.field_combo.set("")

    def _on_field_selected(self, _event: tk.Event | None = None) -> None:
        """Create the appropriate input control for the selected field."""
        category = self.category_var.get()
        field_name = self.field_var.get()
        if self.value_widget is not None:
            self.value_widget.destroy()
            self.value_widget = None
            self.value_var = None
        field_def = next((fd for fd in self.model.categories.get(category, []) if fd.get("name") == field_name), None)
        if not field_def:
            return
        raw_values = field_def.get("values")
        values_list = [str(v) for v in raw_values] if isinstance(raw_values, (list, tuple)) else None
        length = to_int(field_def.get("length", 0)) or 8
        if values_list:
            self.value_var = tk.IntVar()
            combo = ttk.Combobox(self.input_frame, state="readonly", values=values_list, width=25)
            combo.pack(fill=tk.X, pady=(0, 5))
            self.value_widget = combo
            if values_list:
                combo.set(values_list[0])
        else:
            if category in ("Attributes", "Tendencies", "Durability"):
                min_val, max_val = 25, 99
            else:
                min_val = 0
                max_val = (1 << length) - 1 if length else 255
            self.value_var = tk.IntVar(value=min_val)
            spin = tk.Spinbox(
                self.input_frame,
                from_=min_val,
                to=max_val,
                textvariable=self.value_var,
                width=10,
                increment=1,
                justify=tk.LEFT,
            )
            spin.pack(fill=tk.X, pady=(0, 5))
            self.value_widget = spin

    def _apply_changes(self) -> None:
        """Write the selected value to the chosen field for selected teams."""
        import tkinter.messagebox as mb

        category = self.category_var.get()
        field_name = self.field_var.get()
        if not category or not field_name:
            mb.showinfo("Batch Edit", "Please select a category and field.")
            return
        selected_teams = [name for name, var in self.team_vars.items() if var.get()]
        if not selected_teams:
            mb.showinfo("Batch Edit", "Please select one or more teams.")
            return
        field_def = next((fd for fd in self.model.categories.get(category, []) if fd.get("name") == field_name), None)
        if not field_def:
            mb.showerror("Batch Edit", "Field definition not found.")
            return
        offset_val = to_int(field_def.get("offset"))
        start_bit = to_int(field_def.get("startBit", field_def.get("start_bit", 0)))
        length = to_int(field_def.get("length", 0))
        requires_deref = bool(field_def.get("requiresDereference") or field_def.get("requires_deref"))
        deref_offset = to_int(field_def.get("dereferenceAddress") or field_def.get("deref_offset"))
        if length <= 0:
            mb.showerror("Batch Edit", f"Invalid length for field '{field_name}'.")
            return
        raw_values = field_def.get("values")
        values_list = list(raw_values) if isinstance(raw_values, (list, tuple)) else None
        if values_list:
            if isinstance(self.value_widget, ttk.Combobox):
                sel_idx = self.value_widget.current()
                if sel_idx < 0:
                    mb.showinfo("Batch Edit", "Please select a value.")
                    return
                display_value: object = self.value_widget.get()
                if not str(display_value).strip():
                    mb.showinfo("Batch Edit", "Please select a value.")
                    return
            else:
                display_value = 0
        else:
            try:
                display_value = self.value_var.get() if self.value_var else 0
            except Exception:
                display_value = 0
        kind, value, _char_limit, _enc = self.model.coerce_field_value(
            entity_type="player",
            category=category,
            field_name=field_name,
            meta=field_def,
            display_value=display_value,
        )
        if kind == "skip":
            mb.showinfo("Batch Edit", "Invalid value provided for the selected field.")
            return
        if not self.model.mem.hproc or self.model.external_loaded or not self.model.mem.open_process():
            mb.showinfo("Batch Edit", "NBA 2K26 is not running or roster loaded from external files. Cannot apply changes.")
            return
        player_base = self.model._resolve_player_table_base()
        if player_base is None:
            mb.showinfo("Batch Edit", "Unable to resolve player table. Cannot apply changes.")
            return
        cached_players = list(self.model.players or [])
        if not cached_players:
            mb.showinfo("Batch Edit", "No player data cached. Refresh the roster before applying batch edits.")
            return
        selected_lower = {name.lower() for name in selected_teams}
        if "all players" in selected_lower:
            target_players = cached_players
        else:
            target_players = [p for p in cached_players if (p.team or "").lower() in selected_lower]
        if not target_players:
            mb.showinfo("Batch Edit", "No players matched the selected teams.")
            return
        total_changed = 0
        seen_indices: set[int] = set()
        if kind == "int":
            assignment: FieldWriteSpec = (
                offset_val,
                start_bit,
                length,
                to_int(value),
                requires_deref,
                deref_offset,
            )
            for player in target_players:
                if player.index in seen_indices:
                    continue
                seen_indices.add(player.index)
                record_addr = player_base + player.index * PLAYER_STRIDE
                applied = self.model._apply_field_assignments(record_addr, (assignment,))
                if applied:
                    total_changed += 1
        else:
            for player in target_players:
                if player.index in seen_indices:
                    continue
                seen_indices.add(player.index)
                ok = self.model.encode_field_value(
                    entity_type="player",
                    entity_index=player.index,
                    category=category,
                    field_name=field_name,
                    meta=field_def,
                    display_value=display_value,
                    record_ptr=getattr(player, "record_ptr", None),
                )
                if ok:
                    total_changed += 1
        mb.showinfo("Batch Edit", f"Applied value to {total_changed} player(s).")
        try:
            self.model.refresh_players()
        except Exception:
            pass
        self.destroy()

    def _reset_core_fields(self) -> None:
        """Baseline attributes/durability/badges/potential/vitals for selected players."""
        import tkinter.messagebox as mb

        if self.model.external_loaded:
            mb.showinfo("Batch Edit", "NBA 2K26 roster is loaded from external files. Cannot apply changes.")
            return
        if not self.model.mem.hproc and not self.model.mem.open_process():
            mb.showinfo("Batch Edit", "NBA 2K26 is not running. Cannot apply changes.")
            return
        selected_teams = [name for name, var in self.team_vars.items() if var.get()]
        cached_players = list(self.model.players or [])
        if not cached_players:
            mb.showinfo("Batch Edit", "No player data cached. Refresh the roster before applying batch edits.")
            return
        if selected_teams:
            selected_lower = {name.lower() for name in selected_teams}
            if "all players" in selected_lower:
                filtered_players = cached_players
            else:
                filtered_players = [p for p in cached_players if (p.team or "").lower() in selected_lower]
        else:
            filtered_players = cached_players
        player_map = {p.index: p for p in filtered_players}
        players_to_update = list(player_map.values())
        if not players_to_update:
            mb.showinfo("Batch Edit", "No players were found to update.")
            return
        categories = self.model.categories or {}
        lower_map = {name.lower(): name for name in categories.keys()}
        attr_key = lower_map.get("attributes")
        durability_key = lower_map.get("durability")
        potential_keys = [name for name in categories.keys() if "potential" in name.lower()]
        badge_keys = [name for name in categories.keys() if "badge" in name.lower()]

        class _NumericFieldSpec(dict):
            pass

        def collect_numeric_fields(cat_name: str | None, *, skip_enums: bool = True) -> list[_NumericFieldSpec]:
            results: list[_NumericFieldSpec] = []
            if not cat_name:
                return results
            for field in categories.get(cat_name, []):
                if not isinstance(field, dict):
                    continue
                offset_val = to_int(field.get("offset") or field.get("address"))
                length = to_int(field.get("length"))
                if offset_val <= 0 or length <= 0:
                    continue
                raw_values = field.get("values")
                if skip_enums and isinstance(raw_values, (list, tuple)) and raw_values:
                    continue
                start_bit = to_int(field.get("startBit", field.get("start_bit", 0)))
                requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
                deref_offset = to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
                results.append(
                    _NumericFieldSpec(
                        name=str(field.get("name", "")),
                        category=cat_name,
                        meta=field,
                        offset=offset_val,
                        start_bit=start_bit,
                        length=length,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                        field_type=str(field.get("type", "")).lower() if field.get("type") else "",
                    )
                )
            return results

        attribute_fields = collect_numeric_fields(attr_key)
        durability_fields = collect_numeric_fields(durability_key)
        potential_fields: list[_NumericFieldSpec] = []
        for key in potential_keys:
            potential_fields.extend(collect_numeric_fields(key))
        badge_fields: list[_NumericFieldSpec] = []
        for key in badge_keys:
            badge_fields.extend(collect_numeric_fields(key, skip_enums=False))
        tendencies_fields = collect_numeric_fields(lower_map.get("tendencies"), skip_enums=True)
        vitals_fields = collect_numeric_fields(lower_map.get("vitals"), skip_enums=False)
        if not (attribute_fields or durability_fields or badge_fields or potential_fields or tendencies_fields or vitals_fields):
            mb.showerror("Batch Edit", "No eligible fields were found to update.")
            return
        if not self.model.mem.open_process():
            mb.showinfo("Batch Edit", "NBA 2K26 is not running. Cannot apply changes.")
            return
        player_base = self.model._resolve_player_table_base()
        if player_base is None:
            mb.showinfo("Batch Edit", "Unable to resolve player table. Cannot apply changes.")
            return
        group_assignments: dict[str, list[FieldWriteSpec]] = {
            "attributes": [],
            "durability": [],
            "badges": [],
            "potential": [],
            "tendencies": [],
            "vitals": [],
        }
        post_actions: list[tuple[_NumericFieldSpec, object]] = []

        def _queue_assignment(group_key: str, spec: _NumericFieldSpec, display_value: object) -> None:
            kind, value, _char_limit, _enc = self.model.coerce_field_value(
                entity_type="player",
                category=str(spec.get("category") or ""),
                field_name=str(spec.get("name", "")),
                meta=cast(dict, spec.get("meta")),
                display_value=display_value,
            )
            if kind == "int":
                group_assignments[group_key].append(
                    (
                        int(spec["offset"]),
                        int(spec["start_bit"]),
                        int(spec["length"]),
                        to_int(value),
                        bool(spec["requires_deref"]),
                        int(spec["deref_offset"]),
                    )
                )
            elif kind != "skip":
                post_actions.append((spec, display_value))
        for spec in attribute_fields:
            _queue_assignment("attributes", spec, 25)
        for spec in durability_fields:
            _queue_assignment("durability", spec, 25)
        for spec in potential_fields:
            field_name = str(spec.get("name", "")).lower()
            if "min" in field_name:
                target_rating = 40
            elif "max" in field_name:
                target_rating = 41
            else:
                continue
            _queue_assignment("potential", spec, target_rating)
        for spec in badge_fields:
            _queue_assignment("badges", spec, 0)
        for spec in tendencies_fields:
            field_name = str(spec.get("name", "")).lower()
            target_rating = 100 if "foul" in field_name else 0
            _queue_assignment("tendencies", spec, target_rating)
        for spec in vitals_fields:
            field_name = str(spec.get("name", "")).lower()
            if "birth" in field_name and "year" in field_name:
                _queue_assignment("vitals", spec, 2007)
            elif field_name == "height":
                _queue_assignment("vitals", spec, 60)
            elif field_name == "weight":
                post_actions.append((spec, 100.0))
        total_updated = 0
        for player in players_to_update:
            record_addr = player_base + player.index * PLAYER_STRIDE
            for assignments in group_assignments.values():
                if not assignments:
                    continue
                if self.model._apply_field_assignments(record_addr, tuple(assignments)):
                    total_updated += 1
            for spec, value in post_actions:
                ok = self.model.encode_field_value(
                    entity_type="player",
                    entity_index=player.index,
                    category=str(spec.get("category") or ""),
                    field_name=str(spec.get("name", "")),
                    meta=cast(dict, spec.get("meta")),
                    display_value=value,
                    record_ptr=getattr(player, "record_ptr", None),
                )
                if ok:
                    total_updated += 1
        mb.showinfo("Batch Edit", f"Reset core fields for {len(players_to_update)} player(s).")
        try:
            self.model.refresh_players()
        except Exception:
            pass


__all__ = ["BatchEditWindow"]
