"""League workflow controller helpers."""
from __future__ import annotations

from typing import Any, cast

import dearpygui.dearpygui as dpg


def state_for(app: Any, page_key: str) -> dict[str, object]:
    state = app.league_states.get(page_key)
    if state is None:
        state = app.league_states["nba_history"]
    return state


def is_nba_records_category(category_name: str) -> bool:
    cat_lower = (category_name or "").strip().lower()
    if not cat_lower:
        return False
    return (
        "record" in cat_lower
        or cat_lower.startswith("career/")
        or cat_lower.startswith("season/")
        or "single game" in cat_lower
    )


def filter_page_categories(
    app: Any,
    page_key: str,
    categories: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    del app
    if page_key == "nba_records":
        return {name: fields for name, fields in categories.items() if is_nba_records_category(name)}
    if page_key == "nba_history":
        return {name: fields for name, fields in categories.items() if not is_nba_records_category(name)}
    return dict(categories)


def register_widgets(
    app: Any,
    page_key: str,
    *,
    status_text_tag: int | str | None = None,
    category_combo_tag: int | str | None = None,
    count_text_tag: int | str | None = None,
    table_container: int | str | None = None,
) -> None:
    state = state_for(app, page_key)
    state["status_text_tag"] = status_text_tag
    state["category_combo_tag"] = category_combo_tag
    state["count_text_tag"] = count_text_tag
    state["table_container"] = table_container


def on_category_selected(app: Any, page_key: str, value: str) -> None:
    state = state_for(app, page_key)
    state["selected_category"] = value
    app._refresh_league_records(page_key)


def ensure_categories(app: Any, page_key: str = "nba_history") -> None:
    state = state_for(app, page_key)
    categories: dict[str, list[dict]] = {}
    target_super = app.league_page_super_types.get(page_key, "League")
    getter = getattr(app.model, "get_categories_for_super", None)
    if callable(getter):
        try:
            resolved = getter(target_super)
            if isinstance(resolved, dict):
                categories = resolved
        except Exception:
            categories = {}
    if not categories and callable(getter):
        try:
            league_categories = getter("League")
            if isinstance(league_categories, dict):
                categories = filter_page_categories(app, page_key, league_categories)
        except Exception:
            categories = {}
    if not categories:
        legacy_getter = getattr(app.model, "get_league_categories", None)
        if callable(legacy_getter):
            try:
                legacy_categories = legacy_getter()
                if isinstance(legacy_categories, dict):
                    categories = filter_page_categories(app, page_key, legacy_categories)
            except Exception:
                categories = {}
    state["category_map"] = categories or {}
    names = sorted((state.get("category_map") or {}).keys())
    state["categories"] = names
    selected = state.get("selected_category")
    if names:
        if not selected or selected not in names:
            selected = names[0]
    else:
        selected = None
    state["selected_category"] = selected
    category_combo_tag = state.get("category_combo_tag")
    if category_combo_tag and dpg.does_item_exist(category_combo_tag):
        dpg.configure_item(category_combo_tag, items=names)
        if selected:
            try:
                dpg.set_value(category_combo_tag, selected)
            except Exception:
                pass


def update_status(app: Any, page_key: str = "nba_history") -> None:
    state = state_for(app, page_key)
    status_var = cast(Any, state.get("status_var"))
    count_var = cast(Any, state.get("count_var"))
    status_text_tag = state.get("status_text_tag")
    count_text_tag = state.get("count_text_tag")
    if status_text_tag and dpg.does_item_exist(status_text_tag):
        dpg.set_value(status_text_tag, status_var.get())
    if count_text_tag and dpg.does_item_exist(count_text_tag):
        dpg.set_value(count_text_tag, count_var.get())


def clear_table(app: Any, page_key: str = "nba_history", placeholder: str = "No league data loaded.") -> None:
    state = state_for(app, page_key)
    table_container = state.get("table_container")
    if not table_container or not dpg.does_item_exist(table_container):
        return
    children = dpg.get_item_children(table_container, 1) or []
    for child in children:
        dpg.delete_item(child)
    dpg.add_text(placeholder, parent=table_container)
    state["table_tag"] = None


def render_table(
    app: Any,
    page_key: str,
    category_name: str,
    records: list[dict[str, object]],
) -> None:
    state = state_for(app, page_key)
    table_container = state.get("table_container")
    if not table_container or not dpg.does_item_exist(table_container):
        return
    children = dpg.get_item_children(table_container, 1) or []
    for child in children:
        dpg.delete_item(child)
    category_map = cast(dict[str, list[dict]], state.get("category_map") or {})
    fields = [f for f in category_map.get(category_name, []) if isinstance(f, dict)]
    columns = [str(f.get("name", "")) or f"Field {idx + 1}" for idx, f in enumerate(fields)]
    if not columns and records:
        sample = records[0]
        columns = [key for key in sample.keys() if key != "_index"]
    if not records:
        dpg.add_text("No league data found.", parent=table_container)
        state["table_tag"] = None
        return
    with dpg.table(
        parent=table_container,
        header_row=True,
        resizable=True,
        policy=dpg.mvTable_SizingStretchProp,
    ) as table:
        state["table_tag"] = table
        dpg.add_table_column(label="#")
        for col in columns:
            dpg.add_table_column(label=col)
        for row in records:
            with dpg.table_row():
                dpg.add_text(str(row.get("_index", len(records))))
                for col in columns:
                    val = row.get(col, "")
                    if isinstance(val, float):
                        text_val = f"{val:.3f}".rstrip("0").rstrip(".")
                    elif val is None:
                        text_val = ""
                    else:
                        text_val = str(val)
                    dpg.add_text(text_val)


def refresh_records(app: Any, page_key: str = "nba_history", *_args) -> None:
    state = state_for(app, page_key)
    status_var = cast(Any, state.get("status_var"))
    count_var = cast(Any, state.get("count_var"))
    ensure_categories(app, page_key)
    categories = cast(list[str], state.get("categories") or [])
    category = state.get("selected_category") or (categories[0] if categories else None)
    if not category:
        status_var.set("No league offsets available.")
        update_status(app, page_key)
        clear_table(app, page_key, "No league offsets found in the active schema.")
        return
    state["selected_category"] = category
    try:
        app.model.mem.open_process()
    except Exception:
        pass
    if not app.model.mem.hproc:
        status_var.set("NBA 2K26 is not running; league data unavailable.")
        update_status(app, page_key)
        clear_table(app, page_key, "Start the game to view league data.")
        return
    status_var.set(f"Loading {category}...")
    update_status(app, page_key)
    try:
        records = app.model.get_league_records(str(category))
    except Exception as exc:
        status_var.set(f"Failed to load league data: {exc}")
        update_status(app, page_key)
        return
    state["records"] = records
    count_var.set(f"Records: {len(records)}")
    if records:
        status_var.set(f"Loaded {len(records)} records from {category}.")
    else:
        status_var.set(f"No data found for {category}.")
    update_status(app, page_key)
    render_table(app, page_key, str(category), records)
