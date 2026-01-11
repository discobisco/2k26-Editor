"""
Central configuration and shared constants for the NBA 2K26 editor.

Values here are intentionally lightweight so they can be imported from both
UI and non-UI modules without side effects.
"""
from pathlib import Path

APP_NAME = "NBA 2K26 Live Memory Editor"
APP_VERSION = "v2K26.0.1"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR

# Paths reused across modules
AI_SETTINGS_PATH = CONFIG_DIR / "ai_settings.json"
AUTOLOAD_EXT_FILE = CONFIG_DIR / "autoload_extensions.json"
CACHE_DIR = CONFIG_DIR / "cache"

# Offsets and schema files (single unified bundle under Offsets/offsets.json)
DEFAULT_OFFSET_FILES: tuple[str, ...] = ("offsets.json",)

# Game module targets
MODULE_NAME = "NBA2K26.exe"
HOOK_TARGETS: tuple[tuple[str, str], ...] = (
    ("NBA 2K22", "NBA2K22.exe"),
    ("NBA 2K23", "NBA2K23.exe"),
    ("NBA 2K24", "NBA2K24.exe"),
    ("NBA 2K25", "NBA2K25.exe"),
    ("NBA 2K26", "NBA2K26.exe"),
)
HOOK_TARGET_LABELS = {exe.lower(): label for label, exe in HOOK_TARGETS}
ALLOWED_MODULE_NAMES = {exe.lower() for _, exe in HOOK_TARGETS}

# UI palette (used by Tk theme helpers)
PRIMARY_BG = "#0C1220"
PANEL_BG = "#0E1729"
INPUT_BG = "#111C30"
ACCENT_BG = "#2C4C7B"
BUTTON_BG = "#265DAB"
BUTTON_ACTIVE_BG = "#2F6FD6"
TEXT_PRIMARY = "#E8EDF5"
TEXT_SECONDARY = "#B6C2D4"
BUTTON_TEXT = "#F7FAFF"
TEXT_BADGE = "#E2E8F0"
INPUT_TEXT_FG = "#E6EDF7"
INPUT_PLACEHOLDER_FG = "#9AA7BC"
ENTRY_BG = BUTTON_BG
ENTRY_ACTIVE_BG = BUTTON_ACTIVE_BG
ENTRY_FG = BUTTON_TEXT
ENTRY_BORDER = ACCENT_BG
PLAYER_PANEL_FIELDS: tuple[tuple[str, str, str], ...] = ()
PLAYER_PANEL_OVR_FIELD: tuple[str, str] = ("", "")

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "BASE_DIR",
    "LOG_DIR",
    "CONFIG_DIR",
    "AI_SETTINGS_PATH",
    "AUTOLOAD_EXT_FILE",
    "DEFAULT_OFFSET_FILES",
    "MODULE_NAME",
    "HOOK_TARGETS",
    "HOOK_TARGET_LABELS",
    "ALLOWED_MODULE_NAMES",
    "CACHE_DIR",
    "PRIMARY_BG",
    "PANEL_BG",
    "INPUT_BG",
    "ACCENT_BG",
    "BUTTON_BG",
    "BUTTON_ACTIVE_BG",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "BUTTON_TEXT",
    "TEXT_BADGE",
    "INPUT_TEXT_FG",
    "INPUT_PLACEHOLDER_FG",
    "ENTRY_BG",
    "ENTRY_ACTIVE_BG",
    "ENTRY_FG",
    "ENTRY_BORDER",
]
