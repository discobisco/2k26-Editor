"""Dear PyGui theme utilities."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

PRIMARY_BG = "#020812"
PANEL_BG = "#051426"
INPUT_BG = "#081B31"
ACCENT_BG = "#0D3872"
BUTTON_BG = "#0A2446"
BUTTON_ACTIVE_BG = "#134C91"
BUTTON_SELECTED_BG = "#135BA5"
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
    """Convert exact '#RRGGBB' hex to an RGBA tuple."""
    if len(hex_color) != 7 or not hex_color.startswith("#"):
        raise ValueError(f"Expected exact color hex '#RRGGBB', got {hex_color!r}")
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
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
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, to_rgba(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, to_rgba(PANEL_BG))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, to_rgba(PANEL_BG))
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, to_rgba(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Border, to_rgba(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, to_rgba(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(TEXT_PRIMARY))
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, to_rgba(TEXT_SECONDARY))
            dpg.add_theme_color(dpg.mvThemeCol_Button, to_rgba(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, to_rgba(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, to_rgba(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, to_rgba(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Header, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, to_rgba(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, to_rgba(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, to_rgba(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, to_rgba(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_Tab, to_rgba(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_Separator, to_rgba(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripActive, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, to_rgba(PRIMARY_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_NavHighlight, to_rgba(TEXT_ACCENT))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, to_rgba(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, to_rgba(ENTRY_BORDER))
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, to_rgba(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, to_rgba(INPUT_BG))
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
            dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(INPUT_TEXT_FG))
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, to_rgba(ACCENT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, to_rgba(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, to_rgba(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, to_rgba(ENTRY_ACTIVE_BG))

        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(BUTTON_TEXT))
            dpg.add_theme_color(dpg.mvThemeCol_Button, to_rgba(BUTTON_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, to_rgba(BUTTON_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, to_rgba(BUTTON_ACTIVE_BG))

        with dpg.theme_component(dpg.mvCombo):
            dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(ENTRY_FG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, to_rgba(INPUT_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, to_rgba(ENTRY_ACTIVE_BG))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, to_rgba(ENTRY_ACTIVE_BG))

    dpg.bind_theme(theme_tag)
    return theme_tag


def ensure_editor_themes() -> dict[str, str]:
    """Create reusable item themes for the compact editor shell."""
    themes = {
        "nav": "nav_button_theme",
        "nav_selected": "nav_button_selected_theme",
        "accent_text": "accent_text_theme",
        "muted_text": "muted_text_theme",
    }
    if not dpg.does_item_exist(themes["nav"]):
        with dpg.theme(tag=themes["nav"]):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, to_rgba(BUTTON_BG))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, to_rgba(BUTTON_ACTIVE_BG))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, to_rgba(BUTTON_ACTIVE_BG))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 9)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
    if not dpg.does_item_exist(themes["nav_selected"]):
        with dpg.theme(tag=themes["nav_selected"]):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, to_rgba(BUTTON_SELECTED_BG))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, to_rgba(BUTTON_SELECTED_BG))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, to_rgba(BUTTON_SELECTED_BG))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 9)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
    if not dpg.does_item_exist(themes["accent_text"]):
        with dpg.theme(tag=themes["accent_text"]):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(TEXT_ACCENT))
    if not dpg.does_item_exist(themes["muted_text"]):
        with dpg.theme(tag=themes["muted_text"]):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, to_rgba(TEXT_SECONDARY))
    return themes


__all__ = [
    "PRIMARY_BG",
    "PANEL_BG",
    "INPUT_BG",
    "ACCENT_BG",
    "BUTTON_BG",
    "BUTTON_ACTIVE_BG",
    "BUTTON_SELECTED_BG",
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
    "ensure_editor_themes",
]
