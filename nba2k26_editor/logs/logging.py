"""Logging helpers shared across the editor."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Callable

from ..core.config import LOG_DIR


def _null_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def _load_logger_from_path(path: Path) -> Callable[..., logging.Logger] | None:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("nba2k26_memory_logging", str(path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    get_logger = getattr(module, "get_memory_logger", None)
    if callable(get_logger):
        return get_logger
    return None


def _load_dev_logger() -> Callable[..., logging.Logger] | None:
    return _load_logger_from_path(LOG_DIR / "dev_memory_logging.py")


def get_memory_logger(name: str = "nba2k26.memory", filename: str = "memory.log") -> logging.Logger:
    """
    Return a configured logger for memory operations.

    Development-only file logging can be enabled by providing a
    top-level dev_memory_logging.py module. Production builds will fall
    back to a no-op logger.
    """
    dev_logger = _load_dev_logger()
    if dev_logger is not None:
        try:
            return dev_logger(name=name, filename=filename)
        except Exception:
            return _null_logger(name)
    return _null_logger(name)

LOG_INFO = logging.INFO
LOG_ERROR = logging.ERROR
MEMORY_LOGGER = get_memory_logger()


__all__ = ["get_memory_logger", "LOG_INFO", "LOG_ERROR", "MEMORY_LOGGER"]
