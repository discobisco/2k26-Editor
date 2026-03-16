"""Shared list-screen builder for staff/stadium style entity views."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import dearpygui.dearpygui as dpg

from .theme import TEXT_HEADING, TEXT_SECONDARY, to_rgba


@dataclass(frozen=True)
class EntityListScreenConfig:
    screen_key: str
    screen_tag: str
    title: str
    status_attr: str
    status_text_tag_attr: str
    search_var_attr: str
    search_input_tag_attr: str
    list_container_tag: str
    list_container_attr: str
    detail_container_tag: str
    count_var_attr: str
    count_text_tag_attr: str
    full_button_attr: str
    full_button_label: str
    full_button_width: int
    empty_text: str
    search_hint: str
    refresh_callback: Callable[[Any], None]
    filter_callback: Callable[[Any], None]
    open_full_callback: Callable[[Any], None]


def build_entity_list_screen(app, cfg: EntityListScreenConfig) -> None:
    with dpg.child_window(
        tag=cfg.screen_tag,
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags[cfg.screen_key] = tag
        with dpg.group(horizontal=True):
            dpg.add_text(cfg.title, color=to_rgba(TEXT_HEADING))
            setattr(
                app,
                cfg.status_text_tag_attr,
                dpg.add_text(
                    getattr(app, cfg.status_attr).get(),
                    color=to_rgba(TEXT_SECONDARY),
                ),
            )
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_text("Search")
            setattr(
                app,
                cfg.search_input_tag_attr,
                dpg.add_input_text(
                    hint=cfg.search_hint,
                    width=240,
                    callback=lambda _s, value: _on_search_changed(app, cfg, value),
                ),
            )
            dpg.add_button(label="Refresh", width=90, callback=lambda: cfg.refresh_callback(app))
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            with dpg.child_window(tag=cfg.list_container_tag, width=360, autosize_y=True, border=True) as list_container:
                setattr(app, cfg.list_container_attr, list_container)
                dpg.add_text(cfg.empty_text)
            with dpg.child_window(tag=cfg.detail_container_tag, autosize_x=True, autosize_y=True, border=True):
                dpg.add_text(f"{cfg.title} Details", color=to_rgba(TEXT_HEADING))
                setattr(
                    app,
                    cfg.count_text_tag_attr,
                    dpg.add_text(
                        getattr(app, cfg.count_var_attr).get(),
                        color=to_rgba(TEXT_SECONDARY),
                        wrap=520,
                    ),
                )
                setattr(
                    app,
                    cfg.full_button_attr,
                    dpg.add_button(
                        label=cfg.full_button_label,
                        width=cfg.full_button_width,
                        enabled=False,
                        callback=lambda: cfg.open_full_callback(app),
                    ),
                )


def _on_search_changed(app, cfg: EntityListScreenConfig, value: str) -> None:
    getattr(app, cfg.search_var_attr).set(value or "")
    cfg.filter_callback(app)


__all__ = ["EntityListScreenConfig", "build_entity_list_screen"]
