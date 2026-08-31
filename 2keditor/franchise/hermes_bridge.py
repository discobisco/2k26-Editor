from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_HERMES_BRIDGE_HOST = "127.0.0.1"
DEFAULT_HERMES_BRIDGE_PORT = 8765
_GM_PLAYER_FIELDS: tuple[str, ...] = (
    "FIRSTNAME",
    "LASTNAME",
    "POSITION",
    "SECONDARYPOSITION",
    "HEIGHT",
    "WEIGHT",
    "SALARYYEAR1",
    "SALARYYEAR2",
    "SALARYYEAR3",
    "SALARYYEAR4",
    "SALARYYEAR5",
    "SALARYYEAR6",
)
_CURRENT_YEAR_STAT_SELECTOR = "CURRENTYEARSTATID"


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return str(value)


class _HermesEditorRequestHandler(BaseHTTPRequestHandler):
    bridge: "HermesEditorBridge"

    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)
        return

    def _write_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            status, payload = self.bridge.handle_get(self.path)
        except Exception as exc:
            self._write_json(500, {"error": str(exc)})
            return
        self._write_json(status, payload)

    def do_POST(self) -> None:
        self._write_json(405, {"error": "Hermes editor bridge is read-only"})

    def do_PUT(self) -> None:
        self._write_json(405, {"error": "Hermes editor bridge is read-only"})

    def do_PATCH(self) -> None:
        self._write_json(405, {"error": "Hermes editor bridge is read-only"})

    def do_DELETE(self) -> None:
        self._write_json(405, {"error": "Hermes editor bridge is read-only"})


class HermesEditorBridge:
    """Read-only loopback HTTP access to the editor-owned loaded data model."""

    def __init__(
        self,
        model: Any,
        *,
        host: str = DEFAULT_HERMES_BRIDGE_HOST,
        port: int = DEFAULT_HERMES_BRIDGE_PORT,
    ) -> None:
        self.model = model
        self.host = str(host)
        self.port = int(port)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self._server is not None:
            return
        bridge = self

        class Handler(_HermesEditorRequestHandler):
            pass

        Handler.bridge = bridge
        server = ThreadingHTTPServer((self.host, self.port), Handler)
        thread = threading.Thread(target=server.serve_forever, name="hermes-editor-bridge", daemon=True)
        self._server = server
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def _manifest(self) -> dict[str, Any]:
        domains = tuple(getattr(self.model, "loaded_items", {}))
        return {
            "object": "nba2k_editor.hermes_manifest",
            "read_only": True,
            "target_executable": str(getattr(self.model, "target_executable", "")),
            "runtime_status": str(self.model.runtime_status_text()),
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "domains": {
                domain: {
                    "count": int(self.model.domain_item_count(domain)),
                    "status": str(self.model.domain_status(domain)),
                }
                for domain in domains
            },
            "endpoints": (
                "/v1/manifest",
                "/v1/teams",
                "/v1/team/<team_index>",
                "/v1/snapshot",
                "/v1/domain/<domain>",
            ),
        }

    def _teams(self) -> dict[str, Any]:
        team_items = tuple(getattr(self.model, "loaded_items", {}).get("Teams", {}).values())
        placements = self.model.player_roster_slot_items_for_team_items(team_items)
        roster_counts: dict[int, int] = {}
        for _player, placement in placements:
            team_index = int(placement["team_index"])
            roster_counts[team_index] = roster_counts.get(team_index, 0) + 1
        teams = tuple(
            {
                "team_index": int(item.index),
                "label": str(item.label),
                "display_label": str(item.display_label),
                "roster_count": int(roster_counts[int(item.index)]),
            }
            for item in team_items
            if int(item.index) in roster_counts
        )
        return {
            "object": "nba2k_editor.simulation_teams",
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "count": len(teams),
            "teams": teams,
            "user_team_index": None,
        }

    def _domain_entries(self, domain: str) -> tuple[Any, ...]:
        return tuple(
            entry
            for groups in self.model.grouped_fields(domain).values()
            for entries in groups.values()
            for entry in entries
        )

    def _field_payload(self, entry: Any, *, index: int, stat_selector: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "normalized_name": str(entry.normalized_name),
            "display_name": str(entry.display_name),
        }
        try:
            value = self.model.read_entry_value(entry, index=int(index), stat_selector=stat_selector)
        except Exception as exc:
            payload.update({"available": False, "error": str(exc)})
        else:
            payload.update(
                {
                    "available": True,
                    "display_value": _json_safe_value(value.get("display_value")),
                    "raw_value": _json_safe_value(value.get("raw_value")),
                }
            )
        return payload

    def _player_state(self, player: Any) -> dict[str, Any]:
        entries = self._domain_entries("Players")
        entries_by_name = {str(entry.normalized_name).upper(): entry for entry in entries}
        player_fields: dict[str, Any] = {}
        for normalized_name in _GM_PLAYER_FIELDS:
            entry = entries_by_name.get(normalized_name)
            if entry is None:
                player_fields[normalized_name] = {
                    "normalized_name": normalized_name,
                    "available": False,
                    "error": "field is unavailable in the active editor layout",
                }
            else:
                player_fields[normalized_name] = self._field_payload(entry, index=int(player.index))

        current_stat_entry = entries_by_name.get(_CURRENT_YEAR_STAT_SELECTOR)
        current_stat_id = (
            {
                "normalized_name": _CURRENT_YEAR_STAT_SELECTOR,
                "available": False,
                "error": "field is unavailable in the active editor layout",
            }
            if current_stat_entry is None
            else self._field_payload(current_stat_entry, index=int(player.index))
        )
        stat_entries = tuple(entry for entry in entries if self.model.is_player_selected_stat_detail_entry(entry))
        current_season_stats = {
            str(entry.normalized_name): self._field_payload(
                entry,
                index=int(player.index),
                stat_selector=_CURRENT_YEAR_STAT_SELECTOR,
            )
            for entry in stat_entries
        }
        return {
            "player_index": int(player.index),
            "player_address": int(player.address),
            "player_label": str(player.label),
            "player_display_label": str(player.display_label),
            "fields": player_fields,
            "current_year_stat_id": current_stat_id,
            "current_season_stats": current_season_stats,
        }

    def _team_record_fields(self, team_index: int) -> dict[str, Any]:
        section = self.model.grouped_fields("Teams").get("Team Stats Edit", {})
        entries = tuple(entry for group_entries in section.values() for entry in group_entries)
        return {
            str(entry.normalized_name): self._field_payload(entry, index=int(team_index))
            for entry in entries
        }

    def _team_state(self, team_index: int) -> dict[str, Any]:
        team_item = getattr(self.model, "loaded_items", {}).get("Teams", {}).get(int(team_index))
        if team_item is None:
            raise KeyError(f"loaded Teams record not found: {int(team_index)}")
        placements = self.model.player_roster_slot_items_for_team_items((team_item,))
        roster = tuple(
            {
                "team_slot": int(placement["team_slot"]),
                "team_slot_field": str(placement["team_slot_field"]),
                "player": self._player_state(player),
            }
            for player, placement in placements
        )
        return {
            "object": "nba2k_editor.team_state",
            "read_only": True,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "team_index": int(team_index),
            "team_label": str(team_item.label),
            "team_display_label": str(team_item.display_label),
            "team_record_fields": self._team_record_fields(team_index),
            "roster_count": len(roster),
            "roster": roster,
            "nba_records_endpoint": "/v1/domain/NBA%20Records",
            "full_editor_endpoints": (
                "/v1/manifest",
                "/v1/snapshot",
                "/v1/domain/<domain>",
            ),
        }

    def handle_get(self, raw_path: str) -> tuple[int, object]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        if path in {"/health", "/v1/health"}:
            return 200, {"status": "ok", "read_only": True}
        if path == "/v1/manifest":
            return 200, self._manifest()
        if path == "/v1/teams":
            return 200, self._teams()
        team_prefix = "/v1/team/"
        if path.startswith(team_prefix):
            team_index_text = unquote(path[len(team_prefix) :])
            try:
                team_index = int(team_index_text)
            except ValueError:
                return 400, {"error": f"invalid team index: {team_index_text}"}
            if team_index not in getattr(self.model, "loaded_items", {}).get("Teams", {}):
                return 404, {"error": f"loaded Teams record not found: {team_index}"}
            return 200, self._team_state(team_index)
        if path == "/v1/snapshot":
            requested = parse_qs(parsed.query).get("domains", [])
            domains = tuple(part for value in requested for part in value.split(",") if part) or None
            return 200, self.model.app_dataset_snapshot(domains=domains)
        prefix = "/v1/domain/"
        if path.startswith(prefix):
            domain = unquote(path[len(prefix) :])
            if domain not in getattr(self.model, "loaded_items", {}):
                return 404, {"error": f"unknown editor domain: {domain}"}
            return 200, self.model.domain_dataset_snapshot(domain)
        return 404, {"error": "unknown Hermes editor bridge endpoint"}


__all__ = [
    "DEFAULT_HERMES_BRIDGE_HOST",
    "DEFAULT_HERMES_BRIDGE_PORT",
    "HermesEditorBridge",
]
