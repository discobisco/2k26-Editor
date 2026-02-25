from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_profile_id(profile_id: str) -> str:
    raw = str(profile_id or "").strip()
    if not raw:
        return "default"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") or "default"


class LockerRoomProfileStore:
    """Profile-scoped disk store for locker-room simulation state."""

    _STORE_VERSION = 1

    def __init__(self, *, root_dir: Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _profile_lock(self, profile_id: str) -> threading.Lock:
        key = _safe_profile_id(profile_id)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def _profile_path(self, profile_id: str) -> Path:
        return self._root / f"{_safe_profile_id(profile_id)}.json"

    @staticmethod
    def _team_state_key(*, team_id: str, season: str, era: str) -> str:
        return f"{str(team_id)}|{str(season)}|{str(era).lower()}"

    def load_profile(self, *, profile_id: str) -> dict[str, Any]:
        path = self._profile_path(profile_id)
        lock = self._profile_lock(profile_id)
        with lock:
            if not path.exists():
                return {
                    "version": self._STORE_VERSION,
                    "profile_id": _safe_profile_id(profile_id),
                    "updated_at": _utc_now_iso(),
                    "teams": {},
                }
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {
                    "version": self._STORE_VERSION,
                    "profile_id": _safe_profile_id(profile_id),
                    "updated_at": _utc_now_iso(),
                    "teams": {},
                }
            payload.setdefault("version", self._STORE_VERSION)
            payload.setdefault("profile_id", _safe_profile_id(profile_id))
            payload.setdefault("updated_at", _utc_now_iso())
            payload.setdefault("teams", {})
            if not isinstance(payload["teams"], dict):
                payload["teams"] = {}
            return payload

    def save_profile(self, *, profile_id: str, payload: dict[str, Any]) -> None:
        path = self._profile_path(profile_id)
        lock = self._profile_lock(profile_id)
        with lock:
            payload["version"] = self._STORE_VERSION
            payload["profile_id"] = _safe_profile_id(profile_id)
            payload["updated_at"] = _utc_now_iso()
            payload.setdefault("teams", {})
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)

    def get_team_state(self, *, profile_id: str, team_id: str, season: str, era: str) -> dict[str, Any] | None:
        profile = self.load_profile(profile_id=profile_id)
        teams = profile.get("teams", {})
        if not isinstance(teams, dict):
            return None
        state = teams.get(self._team_state_key(team_id=team_id, season=season, era=era))
        return state if isinstance(state, dict) else None

    def upsert_team_state(
        self,
        *,
        profile_id: str,
        team_id: str,
        season: str,
        era: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        profile = self.load_profile(profile_id=profile_id)
        teams = profile.setdefault("teams", {})
        if not isinstance(teams, dict):
            teams = {}
            profile["teams"] = teams
        teams[self._team_state_key(team_id=team_id, season=season, era=era)] = state
        self.save_profile(profile_id=profile_id, payload=profile)
        return state

