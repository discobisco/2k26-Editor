"""Shared full-entity editor primitives for team/staff/stadium."""
from __future__ import annotations

import threading
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import dearpygui.dearpygui as dpg

from ..core.conversions import to_int as _to_int
from ..models.schema import FieldMetadata

if TYPE_CHECKING:
    from ..models.data_model import PlayerDataModel


@dataclass(frozen=True)
class EntityEditorConfig:
    editor_type: str
    entity_type: str
    index_attr: str
    name_attr: str | None
    super_type: str
    label: str
    width: int
    height: int
    save_error_title: str
    save_success_title: str
    save_success_message: str
    detailed_errors: bool = False
    require_process_for_save: bool = False
    empty_categories_message: str = "No categories found in the offsets file."
    empty_fields_message: str = "No fields found for this category."
    notice_text: str | None = None
    notice_wrap: int = 680
    refresh_before_load: str | None = None


class BaseEntityEditor:
    """Common Dear PyGui editor for non-player entities."""

    def __init__(
        self,
        app: Any,
        model: "PlayerDataModel",
        entity_index: int,
        entity_name: str | None,
        config: EntityEditorConfig,
    ) -> None:
        self.app = app
        self.model = model
        self._config = config
        self._editor_type = config.editor_type
        self._closed = False
        self.field_vars: dict[str, dict[str, int | str]] = {}
        self.field_meta: dict[tuple[str, str], FieldMetadata] = {}
        self._baseline_values: dict[tuple[str, str], object] = {}
        self._unsaved_changes: set[tuple[str, str]] = set()
        self._initializing = True
        self._loading_values = False

        self.entity_index = int(entity_index)
        setattr(self, config.index_attr, self.entity_index)
        self.entity_name = entity_name or ""
        if config.name_attr:
            setattr(self, config.name_attr, self.entity_name)

        self.window_tag = dpg.generate_uuid()
        self.tab_bar_tag = dpg.generate_uuid()
        with dpg.window(
            label=config.label.format(name=self.entity_name or config.editor_type.title()),
            tag=self.window_tag,
            width=config.width,
            height=config.height,
            no_collapse=True,
            on_close=self._on_close,
        ):
            if config.notice_text:
                dpg.add_text(config.notice_text, wrap=config.notice_wrap)
            self._build_tabs()
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save", width=100, callback=self._save_all)
                dpg.add_button(label="Close", width=100, callback=self._on_close)

        editors = getattr(self.app, "full_editors", None)
        if isinstance(editors, list):
            editors.append(self)
        else:
            self.app.full_editors = [self]

        self._load_all_values_async()

    def _build_tabs(self) -> None:
        categories = self.model.get_categories_for_super(self._config.super_type) or {}
        ordered = sorted(categories.keys())
        if not ordered:
            dpg.add_text(self._config.empty_categories_message, parent=self.window_tag)
            return
        with dpg.tab_bar(tag=self.tab_bar_tag, parent=self.window_tag):
            for category_name in ordered:
                self._build_category_tab(category_name, categories.get(category_name))

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
        source_category = str(field.get("source_category") or "").strip()
        if source_category and source_category.lower() != str(category_name).strip().lower():
            return self._humanize_group_label(source_category)
        return ""

    def _build_category_tab(self, category_name: str, fields_obj: list | None = None) -> None:
        fields = fields_obj if isinstance(fields_obj, list) else self.model.categories.get(category_name, [])
        with dpg.tab(label=category_name, parent=self.tab_bar_tag):
            if not fields:
                dpg.add_text(self._config.empty_fields_message)
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
                if not isinstance(field, dict):
                    continue
                name = str(field.get("name") or f"Field {row + 1}")
                group_label = self._group_label_for_field(category_name, field)
                if group_label and group_label != previous_group:
                    with dpg.table_row(parent=table):
                        dpg.add_text(group_label)
                        dpg.add_text("")
                previous_group = group_label
                with dpg.table_row(parent=table):
                    dpg.add_text(name if self._config.editor_type == "team" else f"{name}:")
                    control = self._add_field_control(category_name, name, field)
                self.field_vars.setdefault(category_name, {})[name] = control

    def _add_field_control(self, category_name: str, field_name: str, field: dict) -> int | str:
        offset_val = _to_int(field.get("offset") or field.get("address") or field.get("hex"))
        length = _to_int(field.get("length") or field.get("size") or 8)
        start_bit = _to_int(field.get("startBit") or field.get("start_bit") or 0)
        requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
        deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
        byte_length = _to_int(
            field.get("byteLength")
            or field.get("byte_length")
            or field.get("lengthBytes")
            or field.get("size")
            or field.get("length")
            or 0
        )
        field_type = str(field.get("type") or "").lower()
        values_list = field.get("values") if isinstance(field, dict) else None

        is_string = any(tag in field_type for tag in ("string", "text", "char", "wstr", "utf", "wide"))
        is_float = "float" in field_type
        is_color = any(tag in field_type for tag in ("color", "pointer"))
        max_raw = (1 << length) - 1 if length and length < 31 else 999999

        if values_list:
            items = [str(v) for v in values_list]
            control = dpg.add_combo(
                items=items,
                default_value=items[0] if items else "",
                width=200,
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
                data_type=field_type or None,
                byte_length=byte_length,
            )
            return control

        if is_string:
            max_chars = length if length > 0 else byte_length if byte_length > 0 else 64
            control = dpg.add_input_text(
                width=260,
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
                data_type=field_type or "string",
                byte_length=byte_length,
            )
            return control

        if is_float:
            control = dpg.add_input_float(
                width=160,
                default_value=0.0,
                format="%.4f",
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                data_type=field_type or "float",
                byte_length=byte_length,
            )
            return control

        if is_color:
            control = dpg.add_input_text(
                width=180,
                default_value="",
                callback=lambda _s, _a, cat=category_name, fname=field_name: self._mark_unsaved(cat, fname),
            )
            self.field_meta[(category_name, field_name)] = FieldMetadata(
                offset=offset_val,
                start_bit=start_bit,
                length=length,
                requires_deref=requires_deref,
                deref_offset=deref_offset,
                widget=control,
                data_type=field_type or "pointer",
                byte_length=byte_length,
            )
            return control

        control = dpg.add_input_int(
            width=140,
            default_value=0,
            min_value=0,
            max_value=max_raw,
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
            data_type=field_type or "int",
            byte_length=byte_length,
        )
        return control

    def _load_all_values_async(self) -> None:
        if self._loading_values:
            return
        self._loading_values = True

        def _worker() -> None:
            refresh_method = self._config.refresh_before_load
            if refresh_method:
                try:
                    getattr(self.model, refresh_method)()
                except Exception:
                    pass
            values: dict[tuple[str, str], object] = {}
            for category, fields in self.field_vars.items():
                for field_name in fields.keys():
                    meta = self.field_meta.get((category, field_name))
                    if not meta:
                        continue
                    value = self.model.decode_field_value(
                        entity_type=self._config.entity_type,
                        entity_index=self.entity_index,
                        category=category,
                        field_name=field_name,
                        meta=meta,
                    )
                    if value is None:
                        continue
                    values[(category, field_name)] = value

            def _apply() -> None:
                if self._closed:
                    return
                self._apply_loaded_values(values)

            try:
                self.app.run_on_ui_thread(_apply)
            except Exception:
                _apply()

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_loaded_values(self, values: dict[tuple[str, str], object]) -> None:
        api = self._dpg_api()
        baseline_map = getattr(self, "_baseline_values", None)
        if not isinstance(baseline_map, dict):
            baseline_map = {}
            self._baseline_values = baseline_map
        for (category, field_name), value in values.items():
            control = self.field_vars.get(category, {}).get(field_name)
            meta = self.field_meta.get((category, field_name))
            if control is None or meta is None or not api.does_item_exist(control):
                continue
            if meta.values:
                vals = list(meta.values)
                selection = vals[0] if vals else ""
                if isinstance(value, str) and value in vals:
                    selection = value
                else:
                    idx = self._coerce_int(value, default=0)
                    if 0 <= idx < len(vals):
                        selection = vals[idx]
                api.set_value(control, selection)
            else:
                dtype = (meta.data_type or "").lower()
                if any(tag in dtype for tag in ("string", "text", "char", "pointer", "wide")):
                    api.set_value(control, "" if value is None else str(value))
                elif "float" in dtype:
                    try:
                        api.set_value(control, float(cast(Any, value)))
                    except Exception:
                        pass
                else:
                    api.set_value(control, _to_int(value))
            try:
                baseline_map[(category, field_name)] = self._get_ui_value(meta, control)
            except Exception:
                pass
            self._unsaved_changes.discard((category, field_name))
        self._initializing = False
        self._loading_values = False

    def _save_all(self) -> None:
        api = self._dpg_api()
        config = self._effective_config()
        if config.require_process_for_save and not self.model.mem.hproc:
            self.app.show_error("Save Error", "NBA 2K26 is not running.")
            return

        baseline_map = getattr(self, "_baseline_values", None)
        if not isinstance(baseline_map, dict) or not baseline_map:
            self.app.show_message("Save", "No changes to save.")
            return

        errors: list[str] = []
        changed_keys: list[tuple[str, str]] = []
        for (category, field_name), baseline_value in baseline_map.items():
            control = self.field_vars.get(category, {}).get(field_name)
            meta = self.field_meta.get((category, field_name))
            if control is None or meta is None or not api.does_item_exist(control):
                continue
            try:
                ui_value = self._get_ui_value(meta, control)
            except Exception:
                errors.append(f"{category}/{field_name}")
                continue
            if ui_value == baseline_value:
                self._unsaved_changes.discard((category, field_name))
                continue
            changed_keys.append((category, field_name))
            success = self.model.encode_field_value(
                entity_type=config.entity_type,
                entity_index=getattr(self, "entity_index", getattr(self, config.index_attr, 0)),
                category=category,
                field_name=field_name,
                meta=meta,
                display_value=ui_value,
            )
            if success:
                baseline_map[(category, field_name)] = ui_value
                self._unsaved_changes.discard((category, field_name))
            else:
                errors.append(f"{category}/{field_name}")

        if errors:
            if config.detailed_errors:
                self.app.show_error(
                    config.save_error_title,
                    "Failed to save fields:\n" + "\n".join(errors),
                )
            else:
                self.app.show_error(config.save_error_title, "One or more fields could not be saved.")
            return
        if not changed_keys:
            self.app.show_message("Save", "No changes to save.")
            return
        self.app.show_message(
            config.save_success_title,
            config.save_success_message.format(count=len(changed_keys), name=getattr(self, "entity_name", "")),
        )

    def _get_ui_value(self, meta: FieldMetadata, control_tag: int | str) -> object:
        api = self._dpg_api()
        if meta.values:
            selected = api.get_value(control_tag)
            values_list = list(meta.values)
            if selected in values_list:
                return values_list.index(selected)
            return 0
        dtype = (meta.data_type or "").lower()
        value = api.get_value(control_tag)
        if any(tag in dtype for tag in ("string", "text", "char", "pointer", "wide")):
            return "" if value is None else str(value)
        if "float" in dtype:
            try:
                return float(cast(Any, value))
            except Exception:
                return 0.0
        return _to_int(value)

    def _mark_unsaved(self, category: str, field_name: str) -> None:
        if self._initializing:
            return
        self._unsaved_changes.add((category, field_name))

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        try:
            return int(cast(Any, value))
        except Exception:
            return default

    def _on_close(self, _sender=None, _app_data=None, _user_data=None) -> None:
        api = self._dpg_api()
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
        if self.window_tag and api.does_item_exist(self.window_tag):
            api.delete_item(self.window_tag)

    def _dpg_api(self):
        module = sys.modules.get(self.__class__.__module__)
        if module is not None:
            override = getattr(module, "dpg", None)
            if override is not None:
                return override
        return dpg

    def _effective_config(self) -> EntityEditorConfig:
        config = getattr(self, "_config", None)
        if isinstance(config, EntityEditorConfig):
            return config
        editor_type = str(getattr(self, "_editor_type", "")).strip().lower()
        if not editor_type:
            if hasattr(self, "team_index"):
                editor_type = "team"
            elif hasattr(self, "staff_index"):
                editor_type = "staff"
            elif hasattr(self, "stadium_index"):
                editor_type = "stadium"
            else:
                editor_type = "team"
        defaults: dict[str, EntityEditorConfig] = {
            "team": EntityEditorConfig(
                editor_type="team",
                entity_type="team",
                index_attr="team_index",
                name_attr="team_name",
                super_type="Teams",
                label="Edit Team: {name}",
                width=820,
                height=640,
                save_error_title="Save Error",
                save_success_title="Save Successful",
                save_success_message="Saved {count} field(s) for {name}.",
                detailed_errors=False,
                require_process_for_save=True,
            ),
            "staff": EntityEditorConfig(
                editor_type="staff",
                entity_type="staff",
                index_attr="staff_index",
                name_attr=None,
                super_type="Staff",
                label="Staff Editor",
                width=780,
                height=620,
                save_error_title="Staff Editor",
                save_success_title="Staff Editor",
                save_success_message="Saved {count} field(s).",
                detailed_errors=True,
            ),
            "stadium": EntityEditorConfig(
                editor_type="stadium",
                entity_type="stadium",
                index_attr="stadium_index",
                name_attr=None,
                super_type="Stadiums",
                label="Stadium Editor",
                width=780,
                height=620,
                save_error_title="Stadium Editor",
                save_success_title="Stadium Editor",
                save_success_message="Saved {count} field(s).",
                detailed_errors=True,
            ),
        }
        return defaults.get(editor_type, defaults["team"])


__all__ = ["BaseEntityEditor", "EntityEditorConfig"]
