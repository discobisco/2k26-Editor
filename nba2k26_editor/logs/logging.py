"""Logging helpers shared across the editor."""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from ..core.config import LOG_DIR

_SCAN_PLAYER_FUNCTIONS = {
    "_scan_all_players",
    "scan_team_players",
    "_scan_players_with_ranges",
    "_scan_player_names",
}
_SCAN_TEAM_FUNCTIONS = {
    "_scan_team_names",
    "_scan_teams_with_ranges",
}
_MEMORY_LOG_ENV = "NBA2K26_MEMORY_LOG"
_AI_LOG_ENV = "NBA2K26_AI_LOG"
_AI_TRACE_ENV = "NBA2K26_AI_TRACE"
_AI_TRACE_FUNCS_ENV = "NBA2K26_AI_TRACE_FUNCS"
_AI_TRACE_CALLS_ENV = "NBA2K26_AI_TRACE_CALLS"
_MEMORY_LOG_CALLER_ENV = "NBA2K26_MEMORY_LOG_CALLER"
_MEMORY_LOG_TAGS_ENV = "NBA2K26_MEMORY_LOG_TAGS"
_MEMORY_LOG_STACK_ENV = "NBA2K26_MEMORY_LOG_STACK"
_MEMORY_LOG_STACK_DEPTH_ENV = "NBA2K26_MEMORY_LOG_STACK_DEPTH"
_MEMORY_LOG_THREAD_ENV = "NBA2K26_MEMORY_LOG_THREAD"
_DEFAULT_TAG_FUNCTIONS = {
    "_scan_all_players": "player_scan",
    "_scan_player_names": "player_scan",
    "_scan_players_with_ranges": "player_scan",
    "scan_team_players": "team_scan",
    "_scan_team_names": "team_scan",
    "_scan_teams_with_ranges": "team_scan",
    "_resolve_player_base_ptr": "player_base",
    "_resolve_team_base_ptr": "team_base",
    "_resolve_staff_base_ptr": "staff_base",
    "_resolve_stadium_base_ptr": "stadium_base",
    "refresh_players": "refresh_players",
    "refresh_staff": "refresh_staff",
    "update_player": "player_write",
    "copy_player_data": "player_copy",
    "get_team_fields": "team_read",
    "set_team_fields": "team_write",
    "get_player_panel_snapshot": "player_snapshot",
    "get_field_value_typed": "field_read",
    "set_field_value_typed": "field_write",
    "decode_field_value": "field_read",
    "encode_field_value": "field_write",
    "_on_request": "ai_request",
    "_run_ai": "ai_request",
    "call_local_process": "ai_local",
    "call_python_backend": "ai_python",
    "call_remote_api": "ai_remote",
    "invoke_ai_backend": "ai_invoke",
    "generate_text_async": "ai_stream",
    "generate_text_sync": "ai_sync",
    "load_python_instance": "ai_backend_load",
}

_AI_TRACE_DEFAULT_FUNCS = {
    "_on_request",
    "_run_ai",
    "invoke_ai_backend",
    "call_local_process",
    "call_python_backend",
    "call_remote_api",
    "generate_text_async",
    "generate_text_sync",
    "load_python_instance",
}
_LOG_DIR_ENV = "NBA2K26_LOG_DIR"


def _null_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def _truthy_env(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _parse_list_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return []
    items = []
    for entry in raw.replace(";", ",").split(","):
        entry = entry.strip()
        if entry:
            items.append(entry)
    return items


def _infer_scan_context(max_depth: int = 25) -> str | None:
    try:
        frame = sys._getframe(2)
    except Exception:
        return None
    for _ in range(max_depth):
        if frame is None:
            break
        func_name = frame.f_code.co_name
        if func_name in _SCAN_PLAYER_FUNCTIONS:
            return "player"
        if func_name in _SCAN_TEAM_FUNCTIONS:
            return "team"
        frame = frame.f_back
    return None


def _parse_tag_overrides() -> dict[str, str]:
    raw = os.getenv(_MEMORY_LOG_TAGS_ENV, "")
    if not raw:
        return {}
    mapping: dict[str, str] = {}
    for entry in raw.replace(";", ",").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            func_name, tag = entry.split("=", 1)
        else:
            func_name, tag = entry, entry
        func_name = func_name.strip()
        tag = tag.strip() or func_name
        if func_name:
            mapping[func_name] = tag
    return mapping


_TAG_FUNCTIONS = {**_DEFAULT_TAG_FUNCTIONS, **_parse_tag_overrides()}


def _infer_tag_context(max_depth: int = 25) -> str | None:
    try:
        frame = sys._getframe(2)
    except Exception:
        return None
    for _ in range(max_depth):
        if frame is None:
            break
        func_name = frame.f_code.co_name
        tag = _TAG_FUNCTIONS.get(func_name)
        if tag:
            return tag
        frame = frame.f_back
    return None


def _infer_caller(max_depth: int = 25) -> str | None:
    try:
        frame = sys._getframe(2)
    except Exception:
        return None
    for _ in range(max_depth):
        if frame is None:
            break
        module = frame.f_globals.get("__name__")
        func_name = frame.f_code.co_name
        if module and not module.endswith("logs.logging"):
            return f"{module}.{func_name}"
        frame = frame.f_back
    return None


def _infer_stack(max_depth: int = 25, max_items: int = 6) -> str | None:
    try:
        frame = sys._getframe(2)
    except Exception:
        return None
    items: list[str] = []
    for _ in range(max_depth):
        if frame is None:
            break
        module = frame.f_globals.get("__name__")
        func_name = frame.f_code.co_name
        if module and not module.endswith("logs.logging") and not module.startswith("logging"):
            items.append(f"{module}.{func_name}")
            if len(items) >= max_items:
                break
        frame = frame.f_back
    if not items:
        return None
    items.reverse()
    return ">".join(items)


def _thread_context() -> str | None:
    try:
        import threading

        thread = threading.current_thread()
        return f"{thread.name}:{threading.get_ident()}"
    except Exception:
        return None


class _ScanContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _infer_scan_context()
        tag = _infer_tag_context()
        caller = _infer_caller() if _truthy_env(_MEMORY_LOG_CALLER_ENV) else None
        stack = None
        if _truthy_env(_MEMORY_LOG_STACK_ENV):
            depth = _int_env(_MEMORY_LOG_STACK_DEPTH_ENV, 8)
            stack = _infer_stack(max_items=max(1, min(depth, 20)))
        thread_ctx = _thread_context() if _truthy_env(_MEMORY_LOG_THREAD_ENV) else None
        if isinstance(record.msg, str):
            parts: list[str] = []
            if context and "scan=" not in record.msg:
                parts.append(f"scan={context}")
            if tag and "tag=" not in record.msg:
                parts.append(f"tag={tag}")
            if caller and "caller=" not in record.msg:
                parts.append(f"caller={caller}")
            if stack and "stack=" not in record.msg:
                parts.append(f"stack={stack}")
            if thread_ctx and "thread=" not in record.msg:
                parts.append(f"thread={thread_ctx}")
            if parts:
                record.msg = f"{' | '.join(parts)} | {record.msg}"
        return True


def _attach_scan_filter(logger: logging.Logger) -> None:
    for existing in logger.filters:
        if isinstance(existing, _ScanContextFilter):
            return
    logger.addFilter(_ScanContextFilter())


def _effective_log_dir() -> Path:
    override = os.getenv(_LOG_DIR_ENV)
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent / "logs"
        except Exception:
            return LOG_DIR
    return LOG_DIR


def _file_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_dir = _effective_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / filename, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


def format_event(event: str, **fields: object) -> str:
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, float):
            parts.append(f"{key}={value:.3f}")
        else:
            parts.append(f"{key}={value}")
    return " | ".join(parts)


def _load_logger_from_path(path: Path) -> Callable[..., logging.Logger] | None:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("nba2k_editor_memory_logging", str(path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    get_logger = getattr(module, "get_memory_logger", None)
    if callable(get_logger):
        return get_logger  # type: ignore[return-value]
    return None


def _load_dev_logger() -> Callable[..., logging.Logger] | None:
    return _load_logger_from_path(LOG_DIR / "dev_memory_logging.py")


def get_memory_logger(name: str = "nba2k_editor.memory", filename: str = "memory.log") -> logging.Logger:
    """
    Return a configured logger for memory operations.

    Development-only file logging can be enabled by providing a
    top-level dev_memory_logging.py module. Production builds will fall
    back to a no-op logger.
    """
    dev_logger = _load_dev_logger()
    if dev_logger is not None:
        try:
            logger = dev_logger(name=name, filename=filename)
            _attach_scan_filter(logger)
            return logger
        except Exception:
            return _null_logger(name)
    if _truthy_env(_MEMORY_LOG_ENV):
        logger = _file_logger(name=name, filename=filename)
        _attach_scan_filter(logger)
        return logger
    return _null_logger(name)


def get_ai_logger(name: str = "nba2k_editor.ai", filename: str = "ai.log") -> logging.Logger:
    if _truthy_env(_AI_LOG_ENV) or _truthy_env(_MEMORY_LOG_ENV):
        logger = _file_logger(name=name, filename=filename)
        _attach_scan_filter(logger)
        return logger
    return _null_logger(name)


def log_ai_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    try:
        AI_LOGGER.log(level, format_event(event, **fields))
    except Exception:
        pass


LOG_INFO = logging.INFO
LOG_ERROR = logging.ERROR
MEMORY_LOGGER = get_memory_logger()
AI_LOGGER = get_ai_logger()


def _install_ai_trace() -> None:
    if not _truthy_env(_AI_TRACE_ENV):
        return
    include_funcs = set(_parse_list_env(_AI_TRACE_FUNCS_ENV)) or set(_AI_TRACE_DEFAULT_FUNCS)
    log_calls = _truthy_env(_AI_TRACE_CALLS_ENV)
    try:
        import threading
        import time
        import weakref
    except Exception:
        return
    try:
        prev_profile = sys.getprofile()
    except Exception:
        prev_profile = None
    start_times: "weakref.WeakKeyDictionary[object, float]" = weakref.WeakKeyDictionary()

    def _profile(frame, event, arg):
        try:
            module = frame.f_globals.get("__name__", "")
            if not module.startswith("nba2k_editor.ai"):
                if prev_profile:
                    return prev_profile(frame, event, arg)
                return None
            func = frame.f_code.co_name
            if include_funcs and func not in include_funcs:
                if prev_profile:
                    return prev_profile(frame, event, arg)
                return None
            if event == "call":
                start_times[frame] = time.perf_counter()
                if log_calls:
                    log_ai_event("ai_call", module=module, func=func)
            elif event in ("return", "exception"):
                start = start_times.pop(frame, None)
                duration_ms = (time.perf_counter() - start) * 1000 if start is not None else None
                if event == "exception":
                    exc_type = arg[0].__name__ if isinstance(arg, tuple) and arg else "unknown"
                    log_ai_event("ai_exception", module=module, func=func, duration_ms=duration_ms, error=exc_type)
                else:
                    log_ai_event("ai_return", module=module, func=func, duration_ms=duration_ms)
            if prev_profile:
                return prev_profile(frame, event, arg)
        except Exception:
            return None
        return None

    try:
        sys.setprofile(_profile)
        threading.setprofile(_profile)
    except Exception:
        pass


__all__ = [
    "get_memory_logger",
    "get_ai_logger",
    "format_event",
    "log_ai_event",
    "LOG_INFO",
    "LOG_ERROR",
    "MEMORY_LOGGER",
    "AI_LOGGER",
]

_install_ai_trace()
