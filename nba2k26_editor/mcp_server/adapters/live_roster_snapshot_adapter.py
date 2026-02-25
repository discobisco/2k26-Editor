from __future__ import annotations

import re
from typing import Any

from ..errors import ServiceError
from ...memory.game_memory import GameMemory
from ...models.data_model import PlayerDataModel


class LiveRosterSnapshotAdapter:
    """Builds a lightweight roster/personality snapshot directly from live NBA 2K memory."""

    def __init__(self, *, module_name: str) -> None:
        self._module_name = module_name

    @staticmethod
    def _team_prefix(team_id: str) -> str:
        raw = str(team_id or "").strip().upper()
        if "_" in raw:
            return raw.split("_", 1)[0]
        return raw

    @staticmethod
    def _normalize_team_text(text: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", str(text or "").upper())

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _matches_team(self, *, player_team_id: int | None, player_team_text: str, team_id: str) -> bool:
        raw = str(team_id).strip()
        if raw.isdigit():
            return self._safe_int(player_team_id, default=-9999) == int(raw)
        if re.fullmatch(r"[A-Z]{2,4}_\d{4}", raw.upper()):
            prefix = self._team_prefix(raw)
            return prefix in self._normalize_team_text(player_team_text)
        prefix = self._team_prefix(raw)
        normalized = self._normalize_team_text(player_team_text)
        if prefix and prefix in normalized:
            return True
        return self._normalize_team_text(raw) in normalized

    @staticmethod
    def _panel_value(panel: dict[str, Any], key: str, *, fallback: Any = None) -> Any:
        for k, value in panel.items():
            if str(k).strip().lower() == key.strip().lower():
                return value
        return fallback

    def load_team_snapshot(self, *, team_id: str, season: str) -> dict[str, Any]:
        mem = GameMemory(module_name=self._module_name)
        if not mem.open_process():
            raise ServiceError(
                status_code=503,
                code="LIVE_CONNECTION_UNAVAILABLE",
                message="Could not connect to live NBA 2K process.",
                details={"module_name": self._module_name},
            )
        model = PlayerDataModel(mem=mem)
        model.refresh_players()
        if not model.players:
            raise ServiceError(
                status_code=503,
                code="LIVE_ROSTER_UNAVAILABLE",
                message="Live roster scan returned no players.",
                details={},
            )

        roster: list[dict[str, Any]] = []
        for player in model.players:
            if not self._matches_team(
                player_team_id=getattr(player, "team_id", None),
                player_team_text=getattr(player, "team", ""),
                team_id=team_id,
            ):
                continue
            panel = model.get_player_panel_snapshot(player)
            overall = self._safe_float(self._panel_value(panel, "Overall", fallback=74), default=74.0)
            age = self._safe_int(self._panel_value(panel, "Age", fallback=26), default=26)
            potential = self._safe_float(self._panel_value(panel, "Potential", fallback=min(99.0, overall + 6.0)), default=min(99.0, overall + 6.0))
            minutes = self._safe_float(self._panel_value(panel, "Minutes", fallback=24.0), default=24.0)
            usage = self._safe_float(self._panel_value(panel, "Usage", fallback=0.2), default=0.2)
            if usage > 1.0:
                usage = max(0.05, min(0.45, usage / 100.0))
            roster.append(
                {
                    "player_id": int(player.index),
                    "name": player.full_name,
                    "team": getattr(player, "team", ""),
                    "team_id": getattr(player, "team_id", None),
                    "age": age,
                    "overall": max(40.0, min(99.0, overall)),
                    "potential": max(40.0, min(99.0, potential)),
                    "actual_minutes": max(0.0, min(48.0, minutes)),
                    "actual_usage_rate": max(0.01, min(0.6, usage)),
                }
            )
        if not roster:
            raise ServiceError(
                status_code=404,
                code="LIVE_TEAM_NOT_FOUND",
                message=f"No live roster players matched team '{team_id}'.",
                details={"season": season},
            )
        return {
            "team_id": team_id,
            "season": season,
            "roster": roster,
            "live": True,
        }

