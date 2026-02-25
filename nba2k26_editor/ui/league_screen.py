"""League data screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg


def build_nba_history_screen(app) -> None:
    _build_league_screen(
        app,
        page_key="nba_history",
        screen_tag="screen_nba_history",
        title="NBA History",
    )


def build_nba_records_screen(app) -> None:
    _build_league_screen(
        app,
        page_key="nba_records",
        screen_tag="screen_nba_records",
        title="NBA Records",
    )


def _build_league_screen(app, *, page_key: str, screen_tag: str, title: str) -> None:
    state = app._league_state(page_key)
    status_var = state.get("status_var")
    count_var = state.get("count_var")
    status_text = status_var.get() if hasattr(status_var, "get") else ""
    count_text = count_var.get() if hasattr(count_var, "get") else "Records: 0"

    with dpg.child_window(
        tag=screen_tag,
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags[page_key] = tag
        with dpg.group(horizontal=True):
            dpg.add_text(title, color=(224, 225, 221, 255))
            status_text_tag = dpg.add_text(
                status_text,
                color=(155, 164, 181, 255),
                wrap=520,
            )
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_text("Category")
            category_combo_tag = dpg.add_combo(
                items=[],
                width=360,
                callback=lambda _s, value: _on_category_selected(app, page_key, value),
            )
            dpg.add_button(label="Refresh", width=90, callback=lambda: app._refresh_league_records(page_key))
        dpg.add_spacer(height=6)
        count_text_tag = dpg.add_text(
            count_text,
            color=(155, 164, 181, 255),
        )
        dpg.add_spacer(height=6)
        with dpg.child_window(
            tag=f"{page_key}_table_container",
            autosize_x=True,
            autosize_y=True,
            border=True,
        ) as table_container:
            app._register_league_widgets(
                page_key,
                status_text_tag=status_text_tag,
                category_combo_tag=category_combo_tag,
                count_text_tag=count_text_tag,
                table_container=table_container,
            )
            dpg.add_text("No league data loaded.")


def _on_category_selected(app, page_key: str, value: str) -> None:
    app._on_league_category_selected(page_key, value)


__all__ = ["build_nba_history_screen", "build_nba_records_screen"]
