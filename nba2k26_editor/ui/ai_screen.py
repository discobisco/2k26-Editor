"""AI Assistant screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg



def build_ai_screen(app) -> None:
    with dpg.child_window(
        tag="screen_ai",
        parent=app.content_root,
        autosize_x=True,
        autosize_y=True,
        show=False,
    ) as tag:
        app.screen_tags["ai"] = tag
        dpg.add_text("AI Assistant", color=(224, 225, 221, 255))
        dpg.add_spacer(height=4)
        dpg.add_text(
            "Uses the currently selected player from the Players screen. "
            "Configure AI settings on the Home/AI Settings tab, then ask for roster edits or guidance.",
            wrap=760,
            color=(155, 164, 181, 255),
        )
        dpg.add_spacer(height=8)
        with dpg.child_window(tag="ai_panel_container", autosize_x=True, autosize_y=True, border=True) as panel:
            try:
                if getattr(app, "ai_assistant", None) is None:
                    from ..ai.assistant import PlayerAIAssistant

                    context = {"panel_parent": panel, "detail_vars": app.player_detail_fields}
                    app.ai_assistant = PlayerAIAssistant(app, context)
            except Exception as exc:  # noqa: BLE001
                dpg.add_text(f"AI Assistant unavailable: {exc}", color=(200, 80, 80, 255))
        dpg.add_spacer(height=8)
        dpg.add_button(label="Go to Players", width=140, callback=app.show_players)


__all__ = ["build_ai_screen"]
