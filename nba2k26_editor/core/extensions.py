"""Extension registration hooks for custom UI add-ons."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .config import AUTOLOAD_EXT_FILE

EXTENSION_MODULE_PREFIX = "module:"

PlayerPanelExtension = Callable[[object, dict[str, Any]], None]
FullEditorExtension = Callable[[object, dict[str, Any]], None]

PLAYER_PANEL_EXTENSIONS: list[PlayerPanelExtension] = []
FULL_EDITOR_EXTENSIONS: list[FullEditorExtension] = []

_EXTENSION_LOGGER = logging.getLogger("nba2k26.extensions")


def register_player_panel_extension(factory: PlayerPanelExtension, *, prepend: bool = False) -> None:
    """Register a hook executed after the player detail panel is built."""
    if not callable(factory):
        _EXTENSION_LOGGER.debug("Ignoring non-callable player panel extension: %r", factory)
        return
    if prepend:
        PLAYER_PANEL_EXTENSIONS.insert(0, factory)
    else:
        PLAYER_PANEL_EXTENSIONS.append(factory)


def register_full_editor_extension(factory: FullEditorExtension, *, prepend: bool = False) -> None:
    """Register a hook executed after a full player editor window is created."""
    if not callable(factory):
        _EXTENSION_LOGGER.debug("Ignoring non-callable full editor extension: %r", factory)
        return
    if prepend:
        FULL_EDITOR_EXTENSIONS.insert(0, factory)
    else:
        FULL_EDITOR_EXTENSIONS.append(factory)


def load_autoload_extensions(path: Path | None = None) -> list[str]:
    """Return extension keys selected for auto-load on restart."""
    target = path or AUTOLOAD_EXT_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    keys: list[str] = []
    for raw in data:
        key = str(raw).strip()
        if not key:
            continue
        if key.startswith(EXTENSION_MODULE_PREFIX):
            keys.append(key)
            continue
        try:
            p = Path(key).expanduser().resolve()
        except Exception:
            p = Path(key)
        keys.append(str(p))
    return keys


def save_autoload_extensions(paths: list[Path | str], path: Path | None = None) -> None:
    """Persist extension keys selected for auto-load."""
    target = path or AUTOLOAD_EXT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized: list[str] = []
    for raw in paths:
        if isinstance(raw, str) and raw.startswith(EXTENSION_MODULE_PREFIX):
            serialized.append(raw)
            continue
        try:
            serialized.append(str(Path(raw).expanduser().resolve()))
        except Exception:
            continue
    target.write_text(json.dumps(serialized), encoding="utf-8")


__all__ = [
    "PlayerPanelExtension",
    "FullEditorExtension",
    "PLAYER_PANEL_EXTENSIONS",
    "FULL_EDITOR_EXTENSIONS",
    "EXTENSION_MODULE_PREFIX",
    "register_player_panel_extension",
    "register_full_editor_extension",
    "load_autoload_extensions",
    "save_autoload_extensions",
]
