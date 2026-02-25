"""Excel import/export screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg


def build_excel_screen(app) -> None:
    with dpg.child_window(
        tag="screen_excel",
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags["excel"] = tag
        dpg.add_text("Excel Import / Export", color=(224, 225, 221, 255))
        dpg.add_spacer(height=6)
        with dpg.child_window(border=True, autosize_x=True, height=240, menubar=False):
            dpg.add_text(
                "Use the template workbooks in Offsets to import or export data.",
                color=(155, 164, 181, 255),
                wrap=680,
            )
            dpg.add_spacer(height=6)
            _add_section(app, title="Import", is_import=True)
            dpg.add_spacer(height=8)
            _add_section(app, title="Export", is_import=False)
        dpg.add_spacer(height=8)
        app.excel_status_text_tag = dpg.add_text(
            app.excel_status_var.get(),
            color=(155, 164, 181, 255),
            wrap=720,
        )
        app.excel_progress_bar_tag = dpg.add_progress_bar(
            default_value=app.excel_progress_var.get(),
            width=420,
            height=14,
        )


def _add_section(app, *, title: str, is_import: bool) -> None:
    dpg.add_text(title, color=(224, 225, 221, 255))
    with dpg.group(horizontal=True, indent=10):
        labels = [
            ("Players", "players"),
            ("Teams", "teams"),
            ("Staff", "staff"),
            ("Stadiums", "stadiums"),
        ]
        for label, key in labels:
            dpg.add_button(
                label=label,
                width=120,
                callback=(lambda *_args, k=key: app._import_excel(k)) if is_import else (lambda *_args, k=key: app._export_excel(k)),
            )


__all__ = ["build_excel_screen"]
