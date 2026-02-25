from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MCPServerSettings:
    host: str = "127.0.0.1"
    port: int = 8787
    log_level: str = "INFO"
    rate_limit_per_minute: int = 120
    enable_live_writes: bool = False
    module_name: str = "nba2k26.exe"
    offsets_path: str = "nba2k_editor/Offsets"
    default_seed: int = 42
    enable_cpu_ai_personality_v1: bool = True
    ai_cache_ttl_seconds: int = 45
    ai_cache_max_entries: int = 4096
    enable_locker_room_v1: bool = True
    profile_store_dir: str = "nba2k_editor/mcp_server/data/profiles"


@lru_cache(maxsize=1)
def get_settings() -> MCPServerSettings:
    return MCPServerSettings(
        host=os.getenv("MYERAS_MCP_HOST", "127.0.0.1"),
        port=_get_int("MYERAS_MCP_PORT", 8787),
        log_level=os.getenv("MYERAS_MCP_LOG_LEVEL", "INFO"),
        rate_limit_per_minute=_get_int("MYERAS_MCP_RATE_LIMIT_PER_MINUTE", 120),
        enable_live_writes=_get_bool("MYERAS_MCP_ENABLE_LIVE_WRITES", False),
        module_name=os.getenv("MYERAS_MCP_MODULE_NAME", "nba2k26.exe"),
        offsets_path=os.getenv("MYERAS_MCP_OFFSETS_PATH", "nba2k_editor/Offsets"),
        default_seed=_get_int("MYERAS_MCP_DEFAULT_SEED", 42),
        enable_cpu_ai_personality_v1=_get_bool("MYERAS_MCP_ENABLE_CPU_AI_PERSONALITY_V1", True),
        ai_cache_ttl_seconds=_get_int("MYERAS_MCP_AI_CACHE_TTL_SECONDS", 45),
        ai_cache_max_entries=_get_int("MYERAS_MCP_AI_CACHE_MAX_ENTRIES", 4096),
        enable_locker_room_v1=_get_bool("MYERAS_MCP_ENABLE_LOCKER_ROOM_V1", True),
        profile_store_dir=os.getenv("MYERAS_MCP_PROFILE_STORE_DIR", "nba2k_editor/mcp_server/data/profiles"),
    )
