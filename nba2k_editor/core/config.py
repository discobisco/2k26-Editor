"""
Central configuration and shared constants for the NBA 2K26 editor.

Values here are intentionally lightweight so they can be imported from both
UI and non-UI modules without side effects.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "NBA 2K26 Live Memory Editor"
APP_VERSION = "v2K26.0.1"

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR

AI_SETTINGS_PATH = CONFIG_DIR / "ai_settings.json"
AUTOLOAD_EXT_FILE = CONFIG_DIR / "autoload_extensions.json"
CACHE_DIR = CONFIG_DIR / "cache"
AUTOLOAD_EXTENSIONS = os.environ.get("NBA2K_EXTENSIONS_AUTOLOAD", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

MODULE_NAME = "NBA2K26.exe"
HOOK_TARGETS: tuple[tuple[str, str], ...] = (
    ("NBA 2K22", "NBA2K22.exe"),
    ("NBA 2K23", "NBA2K23.exe"),
    ("NBA 2K24", "NBA2K24.exe"),
    ("NBA 2K25", "NBA2K25.exe"),
    ("NBA 2K26", "NBA2K26.exe"),
)
HOOK_TARGET_LABELS = {exe.lower(): label for label, exe in HOOK_TARGETS}

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
    "AUTOLOAD_EXTENSIONS",
    "MODULE_NAME",
    "HOOK_TARGETS",
    "HOOK_TARGET_LABELS",
    "CACHE_DIR",
]
