"""Stadium screen for Dear PyGui."""
from __future__ import annotations

from .entity_list_screen import EntityListScreenConfig, build_entity_list_screen


def build_stadium_screen(app) -> None:
    build_entity_list_screen(
        app,
        EntityListScreenConfig(
            screen_key="stadium",
            screen_tag="screen_stadium",
            title="Stadiums",
            status_attr="stadium_status_var",
            status_text_tag_attr="stadium_status_text_tag",
            search_var_attr="stadium_search_var",
            search_input_tag_attr="stadium_search_input_tag",
            list_container_tag="stadium_list_container",
            list_container_attr="stadium_list_container",
            detail_container_tag="stadium_detail_container",
            count_var_attr="stadium_count_var",
            count_text_tag_attr="stadium_count_text_tag",
            full_button_attr="btn_stadium_full",
            full_button_label="Open Stadium Editor",
            full_button_width=200,
            empty_text="No stadiums loaded.",
            search_hint="Search stadiums.",
            refresh_callback=lambda x: x._refresh_stadium_list(),
            filter_callback=lambda x: x._filter_stadium_list(),
            open_full_callback=lambda x: x._open_full_stadium_editor(x._current_stadium_index()),
        ),
    )


__all__ = ["build_stadium_screen"]

