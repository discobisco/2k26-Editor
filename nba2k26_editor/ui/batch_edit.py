"""Batch edit modal for Dear PyGui."""
from __future__ import annotations

from typing import cast

import dearpygui.dearpygui as dpg

from ..core.conversions import to_int
from ..core.offsets import PLAYER_STRIDE
from ..models.data_model import PlayerDataModel
from ..models.schema import FieldWriteSpec


class BatchEditWindow:
    """Apply a single field value across many players (team selection)."""

    def __init__(self, app, model: PlayerDataModel) -> None:
        self.app = app
        self.model = model
        self.window_tag: int | str = dpg.generate_uuid()
        self.category_combo: int | str | None = None
        self.field_combo: int | str | None = None
        self.value_tag: int | str | None = None
        self.value_kind: str | None = None  # "combo" or "int"
        self.team_tags: dict[str, int | str] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        with dpg.window(
            label="Batch Edit",
            tag=self.window_tag,
            modal=True,
            no_collapse=True,
            width=780,
            height=620,
        ):
            dpg.add_text("Choose a category/field, select teams, then apply the value.")
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_text("Category:")
                self.category_combo = dpg.add_combo(
                    items=list(self.model.categories.keys()),
                    width=220,
                    callback=lambda _s, value: self._on_category_selected(str(value)),
                )
                dpg.add_text("Field:")
                self.field_combo = dpg.add_combo(items=[], width=260, callback=lambda _s, value: self._on_field_selected(str(value)))
            dpg.add_spacer(height=6)
            self.value_container = dpg.add_child_window(height=60, border=False)
            dpg.add_spacer(height=4)
            dpg.add_text("Teams")
            with dpg.child_window(height=320, border=True):
                for team in self._team_names():
                    tag = dpg.add_checkbox(label=team, default_value=False)
                    self.team_tags[team] = tag
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Apply", width=120, callback=lambda: self._apply_changes())
                dpg.add_button(label="Reset Core Ratings", width=170, callback=lambda: self._reset_core_fields())
                dpg.add_button(label="Close", width=90, callback=lambda: dpg.delete_item(self.window_tag))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _on_category_selected(self, category: str) -> None:
        if not self.field_combo or not dpg.does_item_exist(self.field_combo):
            return
        self._clear_value_input()
        fields = self.model.categories.get(category, [])
        names = [str(f.get("name", "")) for f in fields]
        dpg.configure_item(self.field_combo, items=names)
        if names:
            dpg.set_value(self.field_combo, names[0])
            self._on_field_selected(names[0])

    def _on_field_selected(self, field_name: str) -> None:
        category = dpg.get_value(self.category_combo) if self.category_combo else ""
        self._clear_value_input()
        field_def = self._field_def(str(category), field_name)
        if not field_def or not self.value_container or not dpg.does_item_exist(self.value_container):
            return
        raw_values = field_def.get("values")
        values_list = [str(v) for v in raw_values] if isinstance(raw_values, (list, tuple)) else None
        length = to_int(field_def.get("length", 0)) or 8
        with dpg.group(parent=self.value_container):
            if values_list:
                self.value_kind = "combo"
                self.value_tag = dpg.add_combo(items=values_list, default_value=values_list[0] if values_list else "", width=200)
            else:
                self.value_kind = "int"
                if str(category) in ("Attributes", "Tendencies", "Durability"):
                    min_val, max_val = 25, 99
                else:
                    min_val = 0
                    max_val = (1 << length) - 1 if length else 255
                self.value_tag = dpg.add_input_int(default_value=min_val, min_value=0, max_value=max_val, width=200)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _apply_changes(self) -> None:
        cat_tag = self.category_combo if isinstance(self.category_combo, (int, str)) else None
        field_tag = self.field_combo if isinstance(self.field_combo, (int, str)) else None
        category = str(dpg.get_value(cat_tag) or "") if cat_tag and dpg.does_item_exist(cat_tag) else ""
        field_name = str(dpg.get_value(field_tag) or "") if field_tag and dpg.does_item_exist(field_tag) else ""
        if not category or not field_name:
            self.app.show_warning("Batch Edit", "Select a category and field first.")
            return
        field_def = self._field_def(category, field_name)
        if not field_def:
            self.app.show_error("Batch Edit", "Field definition not found.")
            return
        selected_teams = self._selected_teams()
        if not selected_teams:
            self.app.show_warning("Batch Edit", "Select one or more teams first.")
            return
        offset_val = to_int(field_def.get("offset"))
        start_bit = to_int(field_def.get("startBit", field_def.get("start_bit", 0)))
        length = to_int(field_def.get("length", 0))
        requires_deref = bool(field_def.get("requiresDereference") or field_def.get("requires_deref"))
        deref_offset = to_int(field_def.get("dereferenceAddress") or field_def.get("deref_offset"))
        if length is None or length <= 0 or offset_val is None:
            self.app.show_error("Batch Edit", f"Invalid metadata for '{field_name}'.")
            return
        display_value: object = 0
        values_list = field_def.get("values")
        if values_list and self.value_kind == "combo" and self.value_tag:
            display_value = dpg.get_value(self.value_tag) or ""
            if not str(display_value).strip():
                self.app.show_warning("Batch Edit", "Pick a value before applying.")
                return
        elif self.value_kind == "int" and self.value_tag:
            try:
                display_value = int(dpg.get_value(self.value_tag))
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
            self.app.show_warning("Batch Edit", "Invalid value for the selected field.")
            return
        if self.model.external_loaded or not self.model.mem.open_process():
            self.app.show_warning("Batch Edit", "NBA 2K26 is not running or roster is external; cannot apply.")
            return
        player_base = self.model._resolve_player_table_base()
        if player_base is None:
            self.app.show_warning("Batch Edit", "Player table not resolved; try scanning players first.")
            return
        cached_players = list(self.model.players or [])
        if not cached_players:
            self.app.show_warning("Batch Edit", "No cached players. Scan players before batch editing.")
            return
        selected_lower = {name.lower() for name in selected_teams}
        targets = cached_players if "all players" in selected_lower else [p for p in cached_players if (p.team or "").lower() in selected_lower]
        if not targets:
            self.app.show_warning("Batch Edit", "No players matched the selected teams.")
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
            for player in targets:
                if player.index in seen_indices:
                    continue
                seen_indices.add(player.index)
                record_addr = player_base + player.index * PLAYER_STRIDE
                if self.model._apply_field_assignments(record_addr, (assignment,)):
                    total_changed += 1
        else:
            for player in targets:
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
        self.app.show_message("Batch Edit", f"Applied value to {total_changed} player(s).")
        try:
            self.model.refresh_players()
        except Exception:
            pass
        dpg.delete_item(self.window_tag)

    def _reset_core_fields(self) -> None:
        """Baseline attributes/durability/badges/potential/vitals for selected players."""
        if self.model.external_loaded:
            self.app.show_warning("Batch Edit", "NBA 2K26 roster is loaded from external files. Cannot apply changes.")
            return
        if not self.model.mem.hproc and not self.model.mem.open_process():
            self.app.show_warning("Batch Edit", "NBA 2K26 is not running. Cannot apply changes.")
            return
        selected_teams = self._selected_teams()
        cached_players = list(self.model.players or [])
        if not cached_players:
            self.app.show_warning("Batch Edit", "No player data cached. Scan players first.")
            return
        if selected_teams:
            selected_lower = {name.lower() for name in selected_teams}
            if "all players" in selected_lower:
                filtered_players = cached_players
            else:
                filtered_players = [p for p in cached_players if (p.team or "").lower() in selected_lower]
        else:
            filtered_players = cached_players
        players_to_update = list({p.index: p for p in filtered_players}.values())
        if not players_to_update:
            self.app.show_warning("Batch Edit", "No players were found to update.")
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
                if offset_val is None or offset_val <= 0 or length is None or length <= 0:
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
            self.app.show_error("Batch Edit", "No eligible fields were found to update.")
            return
        if not self.model.mem.open_process():
            self.app.show_warning("Batch Edit", "NBA 2K26 is not running. Cannot apply changes.")
            return
        player_base = self.model._resolve_player_table_base()
        if player_base is None:
            self.app.show_warning("Batch Edit", "Unable to resolve player table. Cannot apply changes.")
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
                if assignments and self.model._apply_field_assignments(record_addr, tuple(assignments)):
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
        self.app.show_message("Batch Edit", f"Reset core fields for {len(players_to_update)} player(s).")
        try:
            self.model.refresh_players()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clear_value_input(self) -> None:
        if self.value_container and dpg.does_item_exist(self.value_container):
            for child in list(dpg.get_item_children(self.value_container, 1) or []):
                dpg.delete_item(child)
        self.value_tag = None
        self.value_kind = None

    def _field_def(self, category: str, field_name: str):
        return next((fd for fd in self.model.categories.get(category, []) if fd.get("name") == field_name), None)

    def _team_names(self) -> list[str]:
        try:
            names = self.model.get_teams()
        except Exception:
            names = []
        if names:
            return list(names)
        try:
            return [name for _, name in self.model.team_list]
        except Exception:
            return []

    def _selected_teams(self) -> list[str]:
        return [name for name, tag in self.team_tags.items() if dpg.does_item_exist(tag) and dpg.get_value(tag)]


def open_batch_edit(app) -> BatchEditWindow:
    """Convenience helper to open the batch edit modal."""
    return BatchEditWindow(app, app.model)


__all__ = ["BatchEditWindow", "open_batch_edit"]
