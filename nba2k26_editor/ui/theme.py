"""Dear PyGui theme utilities."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..core.config import (
    ACCENT_BG,
    BUTTON_ACTIVE_BG,
    BUTTON_BG,
    ENTRY_ACTIVE_BG,
    ENTRY_BORDER,
    INPUT_BG,
    PANEL_BG,
    PRIMARY_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def apply_base_theme() -> str:
    """
    Create and bind the base Dear PyGui theme.

    Returns the theme tag so callers can re-bind if needed.
    """
    theme_tag = "base_theme"
    if dpg.does_item_exist(theme_tag):
        dpg.bind_theme(theme_tag)
        return theme_tag

    with dpg.theme(tag=theme_tag):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, _rgb(PANEL_BG))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, _rgb(PANEL_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Border, _rgb(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_Text, _rgb(TEXT_PRIMARY))
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, _rgb(TEXT_SECONDARY))
            dpg.add_theme_color(dpg.mvThemeCol_Button, _rgb(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, _rgb(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Header, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, _rgb(ACCENT_BG))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)

    dpg.bind_theme(theme_tag)
    return theme_tag


def _rgb(hex_color: str) -> tuple[int, int, int, int]:
    """Convert #RRGGBB hex to Dear PyGui RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, 255)


__all__ = ["apply_base_theme"]
