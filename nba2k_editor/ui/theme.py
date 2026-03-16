"""Dear PyGui theme utilities."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

PRIMARY_BG = "#020812"
PANEL_BG = "#051426"
INPUT_BG = "#081B31"
ACCENT_BG = "#0D3872"
BUTTON_BG = "#0A2446"
BUTTON_ACTIVE_BG = "#134C91"
TEXT_PRIMARY = "#EEF6FF"
TEXT_SECONDARY = "#7F99B8"
TEXT_HEADING = "#F6FBFF"
TEXT_LABEL = "#A3B8D2"
TEXT_ACCENT = "#35C9FF"
TEXT_SUCCESS = "#18E0D1"
TEXT_DANGER = "#F06A7C"
BUTTON_TEXT = "#F7FBFF"
TEXT_BADGE = "#B8D7FF"
INPUT_TEXT_FG = "#E6F1FF"
INPUT_PLACEHOLDER_FG = "#587495"
ENTRY_BG = INPUT_BG
ENTRY_ACTIVE_BG = "#0E2C54"
ENTRY_FG = BUTTON_TEXT
ENTRY_BORDER = "#0E3A71"


def to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert #RRGGBB hex to an RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, alpha)


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
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Border, _rgb(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Text, _rgb(TEXT_PRIMARY))
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, _rgb(TEXT_SECONDARY))
            dpg.add_theme_color(dpg.mvThemeCol_Button, _rgb(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, _rgb(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Header, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, _rgb(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, _rgb(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, _rgb(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_Tab, _rgb(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Separator, _rgb(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripActive, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, _rgb(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_NavHighlight, _rgb(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, _rgb(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, _rgb(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, _rgb(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, _rgb(INPUT_BG))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 12)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 14)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 12)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)

        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_Text, _rgb(INPUT_TEXT_FG))
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, _rgb(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, _rgb(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, _rgb(ENTRY_ACTIVE_BG))

        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, _rgb(BUTTON_TEXT))
            dpg.add_theme_color(dpg.mvThemeCol_Button, _rgb(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _rgb(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, _rgb(BUTTON_ACTIVE_BG))

        with dpg.theme_component(dpg.mvCombo):
            dpg.add_theme_color(dpg.mvThemeCol_Text, _rgb(ENTRY_FG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, _rgb(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, _rgb(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, _rgb(ENTRY_ACTIVE_BG))

    dpg.bind_theme(theme_tag)
    return theme_tag


def _rgb(hex_color: str) -> tuple[int, int, int, int]:
    """Convert #RRGGBB hex to Dear PyGui RGBA tuple."""
    return to_rgba(hex_color)


__all__ = [
    "PRIMARY_BG",
    "PANEL_BG",
    "INPUT_BG",
    "ACCENT_BG",
    "BUTTON_BG",
    "BUTTON_ACTIVE_BG",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_HEADING",
    "TEXT_LABEL",
    "TEXT_ACCENT",
    "TEXT_SUCCESS",
    "TEXT_DANGER",
    "BUTTON_TEXT",
    "TEXT_BADGE",
    "INPUT_TEXT_FG",
    "INPUT_PLACEHOLDER_FG",
    "ENTRY_BG",
    "ENTRY_ACTIVE_BG",
    "ENTRY_FG",
    "ENTRY_BORDER",
    "to_rgba",
    "apply_base_theme",
]
