"""Staff screen for Dear PyGui."""
from __future__ import annotations

from .entity_list_screen import EntityListScreenConfig, build_entity_list_screen


def build_staff_screen(app) -> None:
    build_entity_list_screen(
        app,
        EntityListScreenConfig(
            screen_key="staff",
            screen_tag="screen_staff",
            title="Staff",
            status_attr="staff_status_var",
            status_text_tag_attr="staff_status_text_tag",
            search_var_attr="staff_search_var",
            search_input_tag_attr="staff_search_input_tag",
            list_container_tag="staff_list_container",
            list_container_attr="staff_list_container",
            detail_container_tag="staff_detail_container",
            count_var_attr="staff_count_var",
            count_text_tag_attr="staff_count_text_tag",
            full_button_attr="btn_staff_full",
            full_button_label="Open Staff Editor",
            full_button_width=180,
            empty_text="No staff loaded.",
            search_hint="Search staff.",
            refresh_callback=lambda x: x._refresh_staff_list(),
            filter_callback=lambda x: x._filter_staff_list(),
            open_full_callback=lambda x: x._open_full_staff_editor(),
        ),
    )


__all__ = ["build_staff_screen"]

