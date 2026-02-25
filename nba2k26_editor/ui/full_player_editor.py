"""Full player editor window built with Dear PyGui."""
from __future__ import annotations

from collections.abc import Collection as CollectionABC
from typing import Collection, TYPE_CHECKING, Any, cast

import dearpygui.dearpygui as dpg

from ..core.config import TEXT_SECONDARY
from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    BADGE_NAME_TO_VALUE,
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    to_int as _to_int,
)
from ..core.extensions import FULL_EDITOR_EXTENSIONS
from ..models.data_model import PlayerDataModel
from ..models.player import Player
from ..models.schema import FieldMetadata

if TYPE_CHECKING:
    class RawFieldInspectorExtension: ...


class FullPlayerEditor:
    """Tabbed editor for advanced player attributes (Dear PyGui)."""

    _DPG_INT_MIN = -(1 << 31)
    _DPG_INT_MAX = (1 << 31) - 1
    _WIDTH_INT = 140
    _WIDTH_TEXT = 140
    _WIDTH_COMBO = 140
    _WIDTH_FLOAT = 140
    _SEASON_STATS_TAB = "Season Stats"
    _PLAYER_STATS_IDS_CATEGORY = "Stats - IDs"
    _PLAYER_STATS_SEASON_CATEGORY = "Stats - Season"
    _PLAYER_STATS_AWARDS_CATEGORY = "Stats - Awards"
    _SEASON_SLOT_SELECTOR_NAME = "Season Stat Slot"
    _SEASON_STATS_POINTER_KEYS: tuple[str, ...] = ()
    _EXACT_STRING_TYPES: set[str] = {
        "string",
        "text",
        "wstring",
        "wstr",
        "utf16",
        "wide",
        "char",
        "ptr_string",
        "pointer_string",
    }
    _EXACT_FLOAT_TYPES: set[str] = {"float", "double"}
    _EXACT_POINTER_TEXT_TYPES: set[str] = {"pointer", "ptr", "ptr_string", "pointer_string"}
    _EXACT_COLOR_TEXT_TYPES: set[str] = {"color", "color32", "rgb", "rgba", "argb", "bgra"}
    _EXACT_LARGE_INT_TYPES: set[str] = {
        "uint64",
        "ulonglong",
        "qword",
        "int64",
        "longlong",
        "integer64",
    }

    def __init__(self, app, players: Player | Collection[Player], model: PlayerDataModel):
        self.app = app
        self.model = model
        self._closed = False
        self.target_players: list[Player] = self._normalize_players(players)
        self.player: Player = self.target_players[0]
        if len(self.target_players) == 1:
            title = f"Edit Player: {self.player.full_name}"
        else:
            title = f"Edit {len(self.target_players)} Players (showing {self.player.full_name})"

        self.field_vars: dict[str, dict[str, int | str]] = {}
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        self.field_source_category: dict[tuple[str, str], str] = {}
        # Baseline UI-side values loaded from memory. Save should only write fields that
        # were successfully loaded into the editor and whose UI values differ from this baseline.
        self._baseline_values: dict[tuple[str, str], object] = {}
        self._unsaved_changes: set[tuple[str, str]] = set()
        self._initializing = True
        self._loading_values = False
        self._season_slot_selector_key: tuple[str, str] | None = None
        self._season_slot_defs: list[dict[str, object]] = []
        self._season_stat_field_keys: list[tuple[str, str]] = []

        self.window_tag = dpg.generate_uuid()
        self.tab_bar_tag = dpg.generate_uuid()

        with dpg.window(
            label=title,
            tag=self.window_tag,
            width=920,
            height=720,
            no_collapse=True,
            on_close=self._on_close,
        ):
            self._build_tabs()
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", width=100, callback=self._save_all)
                dpg.add_button(label="Close", width=100, callback=self._on_close)

        # Track open editors for control-bridge helpers.
        editors = getattr(self.app, "full_editors", None)
        if isinstance(editors, list):
            editors.append(self)
        else:
            self.app.full_editors = [self]

        self._load_all_values_async()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build_tabs(self) -> None:
        categories_map = self.model.get_categories_for_super("Players") or {}
        categories_map = self._prepare_stats_tabs(categories_map)
        ordered = sorted(categories_map.keys())
        if not ordered:
            self.app.show_warning("Full Player Editor", "No player categories available.")
            return

        with dpg.tab_bar(tag=self.tab_bar_tag, parent=self.window_tag):
            for cat in ordered:
                self._build_category_tab(cat, categories_map.get(cat))

        full_editor_context = {
            "tab_bar": self.tab_bar_tag,
            "player": self.player,
            "model": self.model,
            "app": self.app,
        }
        for factory in FULL_EDITOR_EXTENSIONS:
            try:
                factory(self, full_editor_context)
            except Exception:
                # Extensions are optional; ignore failures to keep base editor working.
                pass

    @staticmethod
    def _clone_fields_with_source(fields: list[dict], source_category: str) -> list[dict]:
        cloned: list[dict] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            field_copy = dict(field)
            field_copy["__source_category"] = source_category
            cloned.append(field_copy)
        return cloned

    @staticmethod
    def _stats_id_sort_key(item: dict[str, object]) -> tuple[int, int, int, str]:
        normalized = str(item.get("normalized_name") or item.get("name") or "").strip().upper()
        if normalized == "CURRENTYEARSTATID":
            return (0, 0, 0, normalized)
        if normalized.startswith("STATSID"):
            suffix = normalized.replace("STATSID", "", 1)
            return (1, int(suffix or 0) if suffix.isdigit() else 0, 0, normalized)
        return (
            2,
            _to_int(item.get("address")),
            _to_int(item.get("startBit", item.get("start_bit", 0))),
            normalized,
        )

    @classmethod
    def _build_season_slot_selector_field(cls, id_fields: list[dict[str, object]]) -> dict[str, object] | None:
        if not id_fields:
            return None

        ordered_ids = sorted((field for field in id_fields if isinstance(field, dict)), key=cls._stats_id_sort_key)
        slot_defs: list[dict[str, object]] = []
        next_slot = 0
        for id_field in ordered_ids:
            normalized = str(id_field.get("normalized_name") or id_field.get("name") or "").strip().upper()
            name = str(id_field.get("name") or normalized or "").strip()
            source_category = str(id_field.get("__source_category") or cls._PLAYER_STATS_IDS_CATEGORY)
            if not name:
                continue
            if normalized == "CURRENTYEARSTATID":
                slot = 0
                next_slot = max(next_slot, 1)
                label = "0 - Current Season"
            elif normalized.startswith("STATSID"):
                suffix = normalized.replace("STATSID", "", 1)
                slot = int(suffix) if suffix.isdigit() else next_slot
                next_slot = max(next_slot, slot + 1)
                label = f"{slot}"
            else:
                slot = next_slot
                next_slot += 1
                label = f"{slot} - {name}"
            slot_defs.append(
                {
                    "slot": slot,
                    "label": label,
                    "field_name": name,
                    "source_category": source_category,
                    "meta": dict(id_field),
                }
            )

        if not slot_defs:
            return None

        slot_defs = sorted(slot_defs, key=lambda item: (_to_int(item.get("slot")), str(item.get("label") or "")))
        labels = [str(item.get("label") or "") for item in slot_defs if str(item.get("label") or "")]
        if not labels:
            return None
        return {
            "name": cls._SEASON_SLOT_SELECTOR_NAME,
            "type": "combo",
            "values": labels,
            "__season_slot_selector": True,
            "__season_slot_defs": slot_defs,
            "__source_category": cls._PLAYER_STATS_IDS_CATEGORY,
        }

    @classmethod
    def _prepare_stats_tabs(cls, categories_map: dict[str, list[dict]]) -> dict[str, list[dict]]:
        prepared: dict[str, list[dict]] = {}
        for category_name, fields in (categories_map or {}).items():
            if not isinstance(fields, list):
                continue
            prepared[str(category_name)] = [field for field in fields if isinstance(field, dict)]

        career_key = "Stats - Career"
        season_key = "Stats - Season"
        awards_key = cls._PLAYER_STATS_AWARDS_CATEGORY
        ids_key = "Stats - IDs"

        awards_fields = prepared.get(awards_key, [])
        id_fields = prepared.get(ids_key, [])

        if career_key in prepared:
            career_fields = cls._clone_fields_with_source(prepared.get(career_key, []), career_key)
            if awards_fields:
                career_fields.extend(cls._clone_fields_with_source(awards_fields, awards_key))
            prepared["Career Stats"] = career_fields
            prepared.pop(career_key, None)

        if season_key in prepared:
            season_fields = cls._clone_fields_with_source(prepared.get(season_key, []), season_key)
            selector_added = False
            if id_fields:
                selector_field = cls._build_season_slot_selector_field(cls._clone_fields_with_source(id_fields, ids_key))
                if selector_field:
                    season_fields = [selector_field, *season_fields]
                    selector_added = True
            if awards_fields:
                season_fields.extend(cls._clone_fields_with_source(awards_fields, awards_key))
            prepared["Season Stats"] = season_fields
            prepared.pop(season_key, None)
            if selector_added:
                prepared.pop(ids_key, None)

        if awards_fields and ("Career Stats" in prepared or "Season Stats" in prepared):
            prepared.pop(awards_key, None)

        return prepared

    @staticmethod
    def _humanize_group_label(raw: object) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        text = text.replace("_", " ").replace("-", " ")
        parts = [segment for segment in text.split() if segment]
        if not parts:
            return ""
        words: list[str] = []
        for part in parts:
            if part.isupper() and len(part) <= 4:
                words.append(part)
            else:
                words.append(part.capitalize())
        return " ".join(words)

    def _group_label_for_field(self, category_name: str, field: dict) -> str:
        raw_group = field.get("source_table_group") or field.get("source_group") or ""
        group_label = self._humanize_group_label(raw_group)
        if group_label:
            return group_label
        source_category = str(
            field.get("__source_category")
            or field.get("source_category")
            or ""
        ).strip()
        if source_category and source_category.lower() != str(category_name).strip().lower():
            return self._humanize_group_label(source_category)
        return ""

    def _build_category_tab(self, category_name: str, fields_obj: list | None = None) -> None:
        fields = fields_obj if isinstance(fields_obj, list) else self.model.categories.get(category_name, [])
        with dpg.tab(label=category_name, parent=self.tab_bar_tag):
            if category_name in ("Attributes", "Durability", "Tendencies"):
                with dpg.group(horizontal=True):
                    for label, action in [
                        ("Min", "min"),
                        ("+5", "plus5"),
                        ("+10", "plus10"),
                        ("-5", "minus5"),
                        ("-10", "minus10"),
                        ("Max", "max"),
                    ]:
                        dpg.add_button(
                            label=label,
                            width=55,
                            callback=lambda _s, _a, cat=category_name, act=action: self._adjust_category(cat, act),
                        )
            with dpg.child_window(autosize_x=True, autosize_y=True, border=False) as _scroll:
                if not fields:
                    dpg.add_text(f"{category_name} editing not available.", color=self._color_tuple(TEXT_SECONDARY))
                    return
                table = dpg.add_table(
                    header_row=False,
                    resizable=False,
                    policy=dpg.mvTable_SizingStretchProp,
                    scrollX=False,
                    scrollY=False,
                )
                dpg.add_table_column(parent=table, width_fixed=True, init_width_or_weight=230)
                dpg.add_table_column(parent=table, init_width_or_weight=1.0)
                previous_group = ""
                for row, field in enumerate(fields):
                    name = field.get("name", f"Field {row}")
                    source_category = str(field.get("__source_category") or category_name)
                    group_label = self._group_label_for_field(category_name, field)
                    if group_label and group_label != previous_group:
                        with dpg.table_row(parent=table):
                            dpg.add_text(group_label, color=self._color_tuple(TEXT_SECONDARY))
                            dpg.add_text("")
                    previous_group = group_label
                    with dpg.table_row(parent=table):
                        dpg.add_text(f"{name}:")
                        control = self._add_field_control(category_name, name, field)
                    self.field_vars.setdefault(category_name, {})[name] = control
                    self.field_source_category[(category_name, name)] = source_category
                    if bool(field.get("__season_slot_selector")):
                        self._season_slot_selector_key = (category_name, name)
                        defs_raw = field.get("__season_slot_defs")
                        if isinstance(defs_raw, list):
                            self._season_slot_defs = [dict(item) for item in defs_raw if isinstance(item, dict)]
                        else:
                            self._season_slot_defs = []
                    elif (
                        category_name == self._SEASON_STATS_TAB
                        and source_category in (
                            self._PLAYER_STATS_SEASON_CATEGORY,
                            self._PLAYER_STATS_AWARDS_CATEGORY,
                        )
                    ):
                        self._season_stat_field_keys.append((category_name, name))

    @staticmethod
    def _normalize_data_type(data_type: str | None) -> str:
        return str(data_type or "").strip().lower()

    @classmethod
    def _control_mode_for_data_type(cls, data_type: str | None) -> str:
        normalized = cls._normalize_data_type(data_type)
        if normalized in cls._EXACT_LARGE_INT_TYPES:
            return "large_int_text"
        if (
            normalized in cls._EXACT_STRING_TYPES
            or normalized in cls._EXACT_POINTER_TEXT_TYPES
            or normalized in cls._EXACT_COLOR_TEXT_TYPES
        ):
            return "text"
        if normalized in cls._EXACT_FLOAT_TYPES:
            return "float"
        return "int"

    def _add_field_control(self, category_name: str, field_name: str, field: dict) -> int | str:
        offset_val = _to_int(field.get("offset"))
        start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
        length = _to_int(field.get("length", 8))
        raw_size = _to_int(field.get("size"))
        raw_length = _to_int(field.get("length") or 0)
        byte_length = raw_size if raw_size > 0 else raw_length
        requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
        deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
        raw_field_type = str(field.get("type") or "")
        field_type = self._normalize_data_type(raw_field_type)
        control_mode = self._control_mode_for_data_type(raw_field_type)

        values_list = field.get("values") if isinstance(field, dict) else None
        try:
            max_raw = (1 << length) - 1 if length and 0 < length < 31 else 999999
        except Exception:
            max_raw = 999999

        control: int | str
        if control_mode == "text":
            max_chars = length if length > 0 else byte_length
            if max_chars <= 0:
                max_chars = 64
            control = dpg.add_input_text(
                width=self._WIDTH_TEXT,
                default_value="",
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=max_chars,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                data_type=raw_field_type or "string",
                byte_length=byte_length,
            )
            return control

        if control_mode == "float":
            control = dpg.add_input_float(
                width=self._WIDTH_FLOAT,
                default_value=0.0,
                format="%.3f",
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                data_type=raw_field_type or "float",
                byte_length=byte_length,
            )
            return control

        if control_mode == "large_int_text":
            control = dpg.add_input_text(
                width=self._WIDTH_TEXT,
                default_value="0",
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                data_type=raw_field_type or "int64",
                byte_length=byte_length,
            )
            return control

        if bool(field.get("__season_slot_selector")):
            items = [str(v) for v in values_list] if isinstance(values_list, list) else []
            default_val = items[0] if items else ""
            control = dpg.add_combo(
                items=items,
                default_value=default_val,
                width=self._WIDTH_COMBO,
                callback=self._on_season_slot_changed,
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=False,
                deref_offset=0,
                widget=control,
                values=tuple(items),
                data_type="season_slot_selector",
                byte_length=byte_length,
            )
            return control

        if values_list:
            items = [str(v) for v in values_list]
            default_val = items[0] if items else ""
            control = dpg.add_combo(
                items=items,
                default_value=default_val,
                width=self._WIDTH_COMBO,
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                values=tuple(items),
                data_type=raw_field_type or None,
                byte_length=byte_length,
            )
            return control

        if category_name == "Badges":
            control = dpg.add_combo(
                items=list(BADGE_LEVEL_NAMES),
                default_value=BADGE_LEVEL_NAMES[0],
                width=self._WIDTH_COMBO,
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                values=tuple(BADGE_LEVEL_NAMES),
                data_type=raw_field_type or "badge",
                byte_length=byte_length,
            )
            return control

        # Numeric fields
        if category_name in ("Attributes", "Durability"):
            spin_from, spin_to = 25, 99
        elif category_name == "Tendencies":
            spin_from, spin_to = 0, 100
        elif field_name.lower() == "height":
            spin_from, spin_to = HEIGHT_MIN_INCHES, HEIGHT_MAX_INCHES
        else:
            spin_from, spin_to = 0, max_raw if max_raw > 0 else 0
        spin_from, spin_to = self._sanitize_input_int_range(spin_from, spin_to)

        control = dpg.add_input_int(
            width=self._WIDTH_INT,
            default_value=spin_from,
            min_value=spin_from,
            max_value=spin_to,
            min_clamped=True,
            max_clamped=True,
            callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
        )
        self.field_meta[(category_name, field_name)] = FieldMetadata(
            offset=offset_val,
            start_bit=start_bit,
            length=length,
            requires_deref=requires_deref,
            deref_offset=deref_offset,
            widget=control,
            data_type=raw_field_type or "int",
            byte_length=byte_length,
        )
        return control

    # ------------------------------------------------------------------
    # Data loading / saving
    # ------------------------------------------------------------------
    def _load_all_values_async(self) -> None:
        if self._loading_values:
            return
        self._loading_values = True
        player_record_ptr = getattr(self.player, "record_ptr", None)
        season_record_ptr = self._resolve_selected_season_record_ptr(self.player)
        values: dict[tuple[str, str], object] = {}
        for category, fields in self.field_vars.items():
            for field_name in fields.keys():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                if self._is_season_slot_selector_field(category, field_name):
                    continue
                try:
                    source_category = self.field_source_category.get((category, field_name), category)
                    target_record_ptr = player_record_ptr
                    if self._is_season_stats_field(category, source_category):
                        target_record_ptr = season_record_ptr
                        if target_record_ptr is None:
                            continue
                    value = self.model.decode_field_value(
                        entity_type="player",
                        entity_index=self.player.index,
                        category=source_category,
                        field_name=field_name,
                        meta=meta,
                        record_ptr=target_record_ptr,
                    )
                except Exception:
                    value = None
                if value is None:
                    continue
                values[(category, field_name)] = value
        self._loading_values = False
        if not self._closed:
            self._apply_loaded_values(values)

    def _apply_loaded_values(self, values: dict[tuple[str, str], object]) -> None:
        baseline_map = getattr(self, "_baseline_values", None)
        if not isinstance(baseline_map, dict):
            baseline_map = {}
            self._baseline_values = baseline_map
        for (category, field_name), value in values.items():
            control = self.field_vars.get(category, {}).get(field_name)
            meta = self.field_meta.get((category, field_name))
            if control is None or meta is None or not dpg.does_item_exist(control):
                continue
            control_mode = self._control_mode_for_data_type(meta.data_type)
            if meta.values:
                selection = ""
                vals = list(meta.values)
                if isinstance(value, str) and value in vals:
                    selection = value
                else:
                    try:
                        idx = self._coerce_int(value, default=0)
                        if 0 <= idx < len(vals):
                            selection = vals[idx]
                    except Exception:
                        selection = ""
                if not selection:
                    selection = vals[0] if vals else ""
                dpg.set_value(control, selection)
            elif control_mode == "text":
                dpg.set_value(control, "" if value is None else str(value))
            elif control_mode == "large_int_text":
                dpg.set_value(control, "0" if value is None else str(value))
            elif control_mode == "float":
                try:
                    dpg.set_value(control, float(cast(Any, value)))
                except Exception:
                    pass
            else:
                try:
                    dpg.set_value(control, self._clamp_dpg_int(_to_int(value)))
                except Exception:
                    pass
            try:
                baseline_map[(category, field_name)] = self._get_ui_value(meta, control)
            except Exception:
                pass
            try:
                self._unsaved_changes.discard((category, field_name))
            except Exception:
                pass
        self._initializing = False
        self._loading_values = False

    def _save_all(self) -> None:
        baseline_map = getattr(self, "_baseline_values", None)
        if not isinstance(baseline_map, dict) or not baseline_map:
            self.app.show_message("Save", "No changes to save.")
            return

        any_error = False
        targets = self.target_players or [self.player]
        changed_keys: list[tuple[str, str]] = []

        for (category, field_name), baseline_value in baseline_map.items():
            control = self.field_vars.get(category, {}).get(field_name)
            meta = self.field_meta.get((category, field_name))
            if control is None or meta is None or not dpg.does_item_exist(control):
                continue
            if self._is_season_slot_selector_field(category, field_name):
                continue
            try:
                ui_value = self._get_ui_value(meta, control)
            except Exception:
                any_error = True
                continue
            if ui_value == baseline_value:
                self._unsaved_changes.discard((category, field_name))
                continue
            changed_keys.append((category, field_name))
            source_category = self.field_source_category.get((category, field_name), category)
            field_ok = True
            for target in targets:
                target_record_ptr = getattr(target, "record_ptr", None)
                if self._is_season_stats_field(category, source_category):
                    target_record_ptr = self._resolve_selected_season_record_ptr(target)
                    if target_record_ptr is None:
                        any_error = True
                        field_ok = False
                        continue
                ok = self.model.encode_field_value(
                    entity_type="player",
                    entity_index=target.index,
                    category=source_category,
                    field_name=field_name,
                    meta=meta,
                    display_value=ui_value,
                    record_ptr=target_record_ptr,
                )
                if not ok:
                    any_error = True
                    field_ok = False
            if field_ok:
                baseline_map[(category, field_name)] = ui_value
                self._unsaved_changes.discard((category, field_name))

        if any_error:
            self.app.show_error("Save Error", "One or more fields could not be saved.")
            return
        if not changed_keys:
            self.app.show_message("Save", "No changes to save.")
            return
        if len(targets) > 1:
            self.app.show_message(
                "Save Successful",
                f"Saved {len(changed_keys)} field(s) for {len(targets)} players.",
            )
        else:
            self.app.show_message("Save Successful", f"Saved {len(changed_keys)} field(s).")

    def _get_ui_value(self, meta: FieldMetadata, control_tag: int | str) -> object:
        if meta.values:
            selected = dpg.get_value(control_tag)
            values_list = list(meta.values)
            if selected in values_list:
                idx = values_list.index(selected)
            else:
                idx = 0
            if values_list == list(BADGE_LEVEL_NAMES):
                return BADGE_NAME_TO_VALUE.get(selected, idx)
            return idx
        control_mode = self._control_mode_for_data_type(meta.data_type)
        value = dpg.get_value(control_tag)
        if control_mode == "text":
            return "" if value is None else str(value)
        if control_mode == "large_int_text":
            return _to_int(value)
        if control_mode == "float":
            try:
                return float(cast(Any, value))
            except Exception:
                return 0.0
        return _to_int(value)

    def _is_season_slot_selector_field(self, category_name: str, field_name: str) -> bool:
        return self._season_slot_selector_key == (category_name, field_name)

    def _is_season_stats_field(self, category_name: str, source_category: str) -> bool:
        return (
            category_name == self._SEASON_STATS_TAB
            and source_category in (
                self._PLAYER_STATS_SEASON_CATEGORY,
                self._PLAYER_STATS_AWARDS_CATEGORY,
            )
        )

    def _selected_season_slot_index(self) -> int:
        if not self._season_slot_defs or not self._season_slot_selector_key:
            return 0
        selector_category, selector_name = self._season_slot_selector_key
        control = self.field_vars.get(selector_category, {}).get(selector_name)
        if control is None or not dpg.does_item_exist(control):
            return 0
        try:
            selected_label = str(dpg.get_value(control) or "")
        except Exception:
            selected_label = ""
        if selected_label:
            for idx, slot_def in enumerate(self._season_slot_defs):
                if selected_label == str(slot_def.get("label") or ""):
                    return idx
        return 0

    def _season_stats_base_and_stride(self) -> tuple[int | None, int]:
        pointer_meta = getattr(self.model, "_league_pointer_meta", None)
        resolve_base = getattr(self.model, "_resolve_league_base", None)
        if callable(pointer_meta) and callable(resolve_base):
            for pointer_key in self._SEASON_STATS_POINTER_KEYS:
                try:
                    chains, stride = pointer_meta(pointer_key)
                except Exception:
                    continue
                if stride <= 0 or not chains:
                    continue
                try:
                    base_ptr = resolve_base(pointer_key, chains, None)
                except Exception:
                    base_ptr = None
                if base_ptr is not None and base_ptr > 0:
                    return int(base_ptr), int(stride)
        return None, 0

    def _resolve_selected_season_record_ptr(self, player: Player | None = None) -> int | None:
        if not self._season_slot_defs:
            return None
        slot_idx = self._selected_season_slot_index()
        if slot_idx < 0 or slot_idx >= len(self._season_slot_defs):
            slot_idx = 0
        slot_def = self._season_slot_defs[slot_idx]
        id_field_name = str(slot_def.get("field_name") or "").strip()
        if not id_field_name:
            return None
        id_source_category = str(slot_def.get("source_category") or self._PLAYER_STATS_IDS_CATEGORY)
        id_meta = slot_def.get("meta")
        if not isinstance(id_meta, dict):
            return None

        target_player = player if isinstance(player, Player) else self.player
        player_record_ptr = getattr(target_player, "record_ptr", None)
        try:
            raw_id_value = self.model.decode_field_value(
                entity_type="player",
                entity_index=target_player.index,
                category=id_source_category,
                field_name=id_field_name,
                meta=id_meta,
                record_ptr=player_record_ptr,
            )
        except Exception:
            raw_id_value = None
        stat_id = self._coerce_int(raw_id_value, default=-1)
        if stat_id < 0:
            return None

        base_ptr, stride = self._season_stats_base_and_stride()
        if base_ptr is None or stride <= 0:
            return None
        if stat_id >= base_ptr and ((stat_id - base_ptr) % stride == 0):
            return int(stat_id)
        return int(base_ptr + stat_id * stride)

    def _set_control_default_value(self, control_tag: int | str, meta: FieldMetadata) -> None:
        if not dpg.does_item_exist(control_tag):
            return
        if meta.values:
            values_list = list(meta.values)
            dpg.set_value(control_tag, values_list[0] if values_list else "")
            return
        control_mode = self._control_mode_for_data_type(meta.data_type)
        if control_mode == "large_int_text":
            dpg.set_value(control_tag, "0")
            return
        if control_mode == "text":
            dpg.set_value(control_tag, "")
            return
        if control_mode == "float":
            dpg.set_value(control_tag, 0.0)
            return
        dpg.set_value(control_tag, 0)

    def _load_selected_season_stats_values(self) -> None:
        if not self._season_stat_field_keys:
            return
        season_record_ptr = self._resolve_selected_season_record_ptr(self.player)
        baseline_map = getattr(self, "_baseline_values", None)
        if not isinstance(baseline_map, dict):
            baseline_map = {}
            self._baseline_values = baseline_map
        values: dict[tuple[str, str], object] = {}
        self._loading_values = True
        try:
            for category, field_name in self._season_stat_field_keys:
                control = self.field_vars.get(category, {}).get(field_name)
                meta = self.field_meta.get((category, field_name))
                if control is None or meta is None or not dpg.does_item_exist(control):
                    continue
                if season_record_ptr is None:
                    self._set_control_default_value(control, meta)
                    baseline_map.pop((category, field_name), None)
                    try:
                        self._unsaved_changes.discard((category, field_name))
                    except Exception:
                        pass
                    continue
                source_category = self.field_source_category.get((category, field_name), category)
                try:
                    value = self.model.decode_field_value(
                        entity_type="player",
                        entity_index=self.player.index,
                        category=source_category,
                        field_name=field_name,
                        meta=meta,
                        record_ptr=season_record_ptr,
                    )
                except Exception:
                    value = None
                if value is None:
                    self._set_control_default_value(control, meta)
                    baseline_map.pop((category, field_name), None)
                    try:
                        self._unsaved_changes.discard((category, field_name))
                    except Exception:
                        pass
                    continue
                values[(category, field_name)] = value
            if values:
                self._apply_loaded_values(values)
        finally:
            self._loading_values = False

    def _on_season_slot_changed(self, _sender=None, _app_data=None, _user_data=None) -> None:
        if self._closed:
            return
        self._load_selected_season_stats_values()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _adjust_category(self, category_name: str, action: str) -> None:
        fields = self.field_vars.get(category_name)
        if not fields:
            return
        for field_name, control in fields.items():
            meta = self.field_meta.get((category_name, field_name))
            if not meta or self._control_mode_for_data_type(meta.data_type) != "int":
                continue
            length = meta.length
            if category_name in ("Attributes", "Durability"):
                min_val, max_val = 25, 99
            elif category_name == "Tendencies":
                min_val, max_val = 0, 100
            else:
                min_val, max_val = 0, (1 << int(length)) - 1 if length else 0
            current = self._coerce_int(dpg.get_value(control), default=min_val)
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
            new_val = max(min_val, min(max_val, new_val))
            try:
                dpg.set_value(control, int(new_val))
                self._mark_unsaved(category_name, field_name)
            except Exception:
                continue

    def _mark_unsaved(self, category: str, field_name: str) -> None:
        if self._initializing or self._loading_values:
            return
        self._unsaved_changes.add((category, field_name))

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        try:
            return int(cast(Any, value))
        except Exception:
            return default

    @classmethod
    def _clamp_dpg_int(cls, value: int) -> int:
        if value < cls._DPG_INT_MIN:
            return cls._DPG_INT_MIN
        if value > cls._DPG_INT_MAX:
            return cls._DPG_INT_MAX
        return int(value)

    @classmethod
    def _sanitize_input_int_range(cls, min_value: int, max_value: int) -> tuple[int, int]:
        min_clamped = cls._clamp_dpg_int(min_value)
        max_clamped = cls._clamp_dpg_int(max_value)
        if max_clamped < min_clamped:
            max_clamped = min_clamped
        return min_clamped, max_clamped

    @staticmethod
    def _color_tuple(hex_color: str) -> tuple[int, int, int, int]:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b, 255)

    def _normalize_players(self, players: Player | Collection[Player]) -> list[Player]:
        player_list: list[Player] = []
        if isinstance(players, Player):
            player_list = [players]
        elif isinstance(players, CollectionABC) and not isinstance(players, (str, bytes)):
            player_list = [p for p in players if isinstance(p, Player)]
        if not player_list:
            raise ValueError("FullPlayerEditor requires at least one player.")
        return player_list

    def _on_close(self, _sender=None, _app_data=None, _user_data=None) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            editors = getattr(self.app, "full_editors", [])
            if isinstance(editors, list):
                try:
                    editors.remove(self)
                except ValueError:
                    pass
        except Exception:
            pass
        if self.window_tag and dpg.does_item_exist(self.window_tag):
            dpg.delete_item(self.window_tag)


__all__ = ["FullPlayerEditor"]
