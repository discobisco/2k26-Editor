"""Logging helpers shared across the editor."""
import logging
import time
from pathlib import Path

from .config import LOG_DIR


def get_memory_logger(name: str = "nba2k26.memory", filename: str = "memory.log") -> logging.Logger:
    """
    Return a configured logger that writes to the logs directory.

    The logger is created once and reused to avoid duplicate handlers when
    multiple modules import this helper.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = Path(LOG_DIR) / filename
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ | %(levelname)s | %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime  # type: ignore[assignment]
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


__all__ = ["get_memory_logger"]
