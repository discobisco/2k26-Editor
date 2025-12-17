"""AI settings load/save scaffold."""
import json
from pathlib import Path
from typing import Any

from ..core.config import AI_SETTINGS_PATH

DEFAULT_AI_SETTINGS: dict[str, Any] = {
    "mode": "none",
    "remote": {"base_url": "", "api_key": "", "model": "", "timeout": 30},
    "local": {"command": "", "arguments": "", "working_dir": ""},
}


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load AI settings from disk or return defaults."""
    target = path or AI_SETTINGS_PATH
    if not target.exists():
        return dict(DEFAULT_AI_SETTINGS)
    try:
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            merged = dict(DEFAULT_AI_SETTINGS)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_AI_SETTINGS)


def save_settings(settings: dict[str, Any], path: Path | None = None) -> None:
    """Persist AI settings to disk."""
    target = path or AI_SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


__all__ = ["DEFAULT_AI_SETTINGS", "load_settings", "save_settings"]
