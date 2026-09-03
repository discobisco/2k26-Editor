from __future__ import annotations

import json
import threading
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_HERMES_BRIDGE_HOST = "127.0.0.1"
DEFAULT_HERMES_BRIDGE_PORT = 8765
HERMES_EDITOR_DOMAINS: tuple[str, ...] = (
    "Players",
    "Teams",
    "Staff",
    "Stadiums",
    "NBA History",
    "NBA Records",
)
HERMES_WORKFLOW_SCREENS: tuple[str, ...] = ("Player Generator",)
HERMES_AI_SCREENS: tuple[str, ...] = (*HERMES_EDITOR_DOMAINS, *HERMES_WORKFLOW_SCREENS)
HERMES_EXCLUDED_SCREENS: tuple[str, ...] = (
    "Jerseys",
    "Shoes",
)
_MAX_REQUEST_BODY_BYTES = 1_048_576
_DEFAULT_RECORD_PAGE_SIZE = 100
_MAX_RECORD_PAGE_SIZE = 500
_DEFAULT_FIELD_PAGE_SIZE = 100
_MAX_FIELD_PAGE_SIZE = 500
_MAX_BATCH_FIELD_READS = 100
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
_LIST_SORT_FIELDS: tuple[str, ...] = (
    "index",
    "name",
    "team",
    "position",
    "overall",
    "salary_year_1",
    "field",
)
_PLAYER_SORT_FIELD_PATHS: dict[str, tuple[str, str, str, str | None]] = {
    "position": ("Vitals", "Vitals", "POSITION", None),
    "overall": ("Stats", "Season IDs", "OVERALL", _CURRENT_YEAR_STAT_SELECTOR),
    "salary_year_1": ("Contract", "Salary", "SALARYYEAR1", None),
}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_value(asdict(value))
    return str(value)


class _HermesEditorRequestHandler(BaseHTTPRequestHandler):
    bridge: "HermesEditorBridge"

    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)

    def _write_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_object(self, *, required: bool) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            if required:
                raise ValueError("JSON request body is required")
            return {}
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if content_length < 0 or content_length > _MAX_REQUEST_BODY_BYTES:
            raise ValueError("request body size is invalid")
        if content_length == 0:
            if required:
                raise ValueError("JSON request body is required")
            return {}
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:
        try:
            status, payload = self.bridge.handle_get(self.path)
        except Exception as exc:
            self._write_json(500, {"error": str(exc)})
            return
        self._write_json(status, payload)

    def do_POST(self) -> None:
        try:
            body = self._read_json_object(required=False)
            status, payload = self.bridge.handle_post(self.path, body)
        except ValueError as exc:
            self._write_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self._write_json(500, {"error": str(exc)})
            return
        self._write_json(status, payload)

    def do_PATCH(self) -> None:
        try:
            body = self._read_json_object(required=True)
            status, payload = self.bridge.handle_patch(self.path, body)
        except ValueError as exc:
            self._write_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self._write_json(500, {"error": str(exc)})
            return
        self._write_json(status, payload)

    def do_PUT(self) -> None:
        self._write_json(405, {"error": "use PATCH for one editor field write"})

    def do_DELETE(self) -> None:
        self._write_json(405, {"error": "delete is not an editor operation"})


class HermesEditorBridge:
    """Loopback HTTP access to the editor's existing record and field operations."""

    def __init__(
        self,
        model: Any,
        *,
        host: str = DEFAULT_HERMES_BRIDGE_HOST,
        port: int = DEFAULT_HERMES_BRIDGE_PORT,
        player_generator_state_provider: Any | None = None,
    ) -> None:
        self.model = model
        self.host = str(host)
        self.port = int(port)
        self.player_generator_state_provider = player_generator_state_provider
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._server is not None:
            return
        bridge = self

        class Handler(_HermesEditorRequestHandler):
            pass

        Handler.bridge = bridge
        server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(server.server_address[1])
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
        loaded = getattr(self.model, "loaded_items", {})
        screens = {
            domain: {
                "kind": "record_editor",
                "count": int(self.model.domain_item_count(domain)),
                "status": str(self.model.domain_status(domain)),
                "loaded": bool(loaded.get(domain)),
                "record_list_endpoint": f"/v1/screen/{domain}",
            }
            for domain in HERMES_EDITOR_DOMAINS
        }
        screens["Player Generator"] = {
            "kind": "workflow",
            "status": "available" if self.player_generator_state_provider is not None else "not connected",
            "endpoint": "/v1/player-generator",
        }
        return {
            "object": "nba2k_editor.hermes_manifest",
            "api_version": 1,
            "read_only": False,
            "bind": self.host,
            "base_url": self.base_url,
            "target_executable": str(getattr(self.model, "target_executable", "")),
            "runtime_status": str(self.model.runtime_status_text()),
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "screens": screens,
            "excluded_screens": HERMES_EXCLUDED_SCREENS,
            "endpoints": {
                "manifest": "/v1/manifest",
                "screens": "/v1/screens",
                "records": "/v1/screen/<screen>?offset=0&limit=100&search=",
                "fields": "/v1/screen/<screen>/fields?offset=0&limit=100&search=",
                "record_editor": "/v1/screen/<screen>/record/<index>?stat_selector=",
                "read_field": "/v1/screen/<screen>/record/<index>/field?section=&group=&normalized_name=&stat_selector=",
                "read_fields": "POST /v1/screen/<screen>/record/<index>/fields/read",
                "write_field": "PATCH /v1/screen/<screen>/record/<index>",
                "refresh_screen": "POST /v1/screen/<screen>/refresh",
                "player_generator": "/v1/player-generator",
                "franchise_teams": "/v1/teams",
                "franchise_team": "/v1/team/<team_index>",
            },
        }

    def _player_generator_state(self) -> tuple[int, object]:
        if self.player_generator_state_provider is None:
            return 503, {"error": "Player Generator is not connected to the Hermes API"}
        state = self.player_generator_state_provider()
        return 200, {
            "object": "nba2k_editor.player_generator",
            "screen": "Player Generator",
            "state": _json_safe_value(state),
        }

    def _validate_domain(self, domain: str) -> tuple[int, object] | None:
        if domain in HERMES_EXCLUDED_SCREENS:
            return 403, {"error": f"screen is outside the Hermes API scope: {domain}"}
        if domain not in HERMES_EDITOR_DOMAINS:
            return 404, {"error": f"unknown Hermes editor screen: {domain}"}
        return None

    def _record_item(self, domain: str, index: int) -> Any | None:
        for item in getattr(self.model, "loaded_items", {}).get(domain, {}).values():
            if int(item.index) == int(index):
                return item
        return None

    def _player_filter_value(
        self,
        requested: str | None,
        options: tuple[tuple[str, str | int], ...],
    ) -> tuple[str | int | None, tuple[int, object] | None]:
        if not options:
            return None, (409, {"error": "Players filter options are unavailable"})
        if requested is None or requested == "":
            return options[0][1], None
        values = tuple(value for _label, value in options)
        if requested in values:
            return requested, None
        try:
            numeric = int(requested)
        except ValueError:
            numeric = None
        if numeric is not None and numeric in values:
            return numeric, None
        return None, (
            400,
            {
                "error": f"unknown Players team filter: {requested}",
                "options": tuple({"label": label, "value": value} for label, value in options),
            },
        )

    def _player_list_items(
        self,
        query: dict[str, list[str]],
        search: str,
    ) -> tuple[tuple[Any, ...], dict[str, Any], tuple[int, object] | None]:
        team_options = tuple(self.model.player_team_filter_options())
        position_options = tuple(self.model.player_position_filter_options())
        requested_team = query.get("team_filter", [None])[0]
        team_filter, error = self._player_filter_value(requested_team, team_options)
        if error is not None:
            return (), {}, error
        requested_position = query.get("position_filter", [None])[0]
        position_values = tuple(value for _label, value in position_options)
        position_filter = position_values[0] if requested_position in {None, ""} and position_values else requested_position
        if position_filter not in position_values:
            return (), {}, (
                400,
                {
                    "error": f"unknown Players position filter: {requested_position}",
                    "options": tuple({"label": label, "value": value} for label, value in position_options),
                },
            )
        view = self.model.prepare_player_list_view(team_filter, search, position_filter)
        filters = {
            "team": {
                "selected": team_filter,
                "options": tuple({"label": label, "value": value} for label, value in team_options),
            },
            "position": {
                "selected": position_filter,
                "options": tuple({"label": label, "value": value} for label, value in position_options),
            },
        }
        return tuple(view.items), filters, None

    def _player_placements(self) -> dict[int, dict[str, Any]]:
        team_items = tuple(getattr(self.model, "loaded_items", {}).get("Teams", {}).values())
        return {
            int(player.index): dict(placement)
            for player, placement in self.model.player_roster_slot_items_for_team_items(team_items)
        }

    def _sort_field_entry(
        self,
        domain: str,
        sort_by: str,
        query: dict[str, list[str]],
    ) -> tuple[Any | None, str | None, tuple[int, object] | None]:
        if sort_by in _PLAYER_SORT_FIELD_PATHS:
            if domain != "Players":
                return None, None, (400, {"error": f"{sort_by} sorting is only available for Players"})
            section, group, normalized_name, stat_selector = _PLAYER_SORT_FIELD_PATHS[sort_by]
        elif sort_by == "field":
            section = str(query.get("sort_section", [""])[0])
            group = str(query.get("sort_group", [""])[0])
            normalized_name = str(query.get("sort_field", [""])[0])
            if not section or not group or not normalized_name:
                return None, None, (
                    400,
                    {"error": "field sorting requires sort_section, sort_group, and sort_field"},
                )
            stat_selector = query.get("sort_stat_selector", [None])[0]
        else:
            return None, None, None
        entry = self._field_entry(
            domain,
            section=section,
            group=group,
            normalized_name=normalized_name,
        )
        if entry is None:
            return None, None, (
                404,
                {
                    "error": "exact sort field not found",
                    "field": {
                        "section": section,
                        "group": group,
                        "normalized_name": normalized_name,
                    },
                },
            )
        if self._is_stat_detail(entry) and stat_selector is None:
            return None, None, (400, {"error": "sort_stat_selector is required for a season-stat detail field"})
        return entry, stat_selector, None

    def _sorted_record_items(
        self,
        domain: str,
        items: tuple[Any, ...],
        query: dict[str, list[str]],
        placements: dict[int, dict[str, Any]],
    ) -> tuple[tuple[Any, ...], dict[int, Any], dict[str, Any], tuple[int, object] | None]:
        sort_by = str(query.get("sort_by", ["index"])[0])
        sort_order = str(query.get("sort_order", ["asc"])[0])
        if sort_by not in _LIST_SORT_FIELDS:
            return (), {}, {}, (400, {"error": f"unknown sort_by: {sort_by}", "options": _LIST_SORT_FIELDS})
        if sort_order not in {"asc", "desc"}:
            return (), {}, {}, (400, {"error": "sort_order must be asc or desc"})
        entry, stat_selector, error = self._sort_field_entry(domain, sort_by, query)
        if error is not None:
            return (), {}, {}, error
        values: dict[int, Any] = {}
        available: list[tuple[tuple[int, Any], Any]] = []
        unavailable: list[Any] = []
        for item in items:
            try:
                if sort_by == "index":
                    value: Any = int(item.index)
                elif sort_by == "name":
                    value = str(item.label)
                elif sort_by == "team":
                    if domain != "Players":
                        return (), {}, {}, (400, {"error": "team sorting is only available for Players"})
                    placement = placements.get(int(item.index))
                    if placement is None:
                        unavailable.append(item)
                        values[int(item.index)] = None
                        continue
                    value = int(placement["team_index"])
                else:
                    value_info = self.model.read_entry_value_for_item(entry, item, stat_selector=stat_selector)
                    value = value_info.get("raw_value")
                    if value is None:
                        value = value_info.get("display_value")
                values[int(item.index)] = _json_safe_value(value)
                key = (0, float(value)) if isinstance(value, (bool, int, float)) else (1, str(value).casefold())
                available.append((key, item))
            except Exception:
                values[int(item.index)] = None
                unavailable.append(item)
        ordered = tuple(
            item
            for _key, item in sorted(
                available,
                key=lambda pair: (pair[0], int(pair[1].index)),
                reverse=sort_order == "desc",
            )
        ) + tuple(sorted(unavailable, key=lambda item: int(item.index)))
        return ordered, values, {"by": sort_by, "order": sort_order}, None

    def _record_list_payload(self, domain: str, query: dict[str, list[str]]) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        try:
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", [str(_DEFAULT_RECORD_PAGE_SIZE)])[0])
        except ValueError:
            return 400, {"error": "offset and limit must be integers"}
        if offset < 0:
            return 400, {"error": "offset must be zero or greater"}
        if limit < 1 or limit > _MAX_RECORD_PAGE_SIZE:
            return 400, {"error": f"limit must be between 1 and {_MAX_RECORD_PAGE_SIZE}"}
        search = str(query.get("search", [""])[0]).strip()
        filters: dict[str, Any] = {}
        if domain == "Players":
            items, filters, error = self._player_list_items(query, search)
            if error is not None:
                return error
        else:
            items = tuple(getattr(self.model, "loaded_items", {}).get(domain, {}).values())
            if search:
                query_text = search.casefold()
                items = tuple(item for item in items if query_text in str(item.display_label).casefold())
        placements = self._player_placements() if domain == "Players" else {}
        items, sort_values, sort_payload, error = self._sorted_record_items(domain, items, query, placements)
        if error is not None:
            return error
        total = len(items)
        page = items[offset : offset + limit]
        selected = self.model.selected_item(domain)
        return 200, {
            "object": "nba2k_editor.record_list",
            "screen": domain,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "status": str(self.model.domain_status(domain)),
            "selected_index": None if selected is None else int(selected.index),
            "search": search,
            "filters": filters,
            "sort": sort_payload,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
            "records": tuple(
                {
                    "domain": str(item.domain),
                    "index": int(item.index),
                    "address": int(item.address),
                    "label": str(item.label),
                    "display_label": str(item.display_label),
                    "team": _json_safe_value(placements.get(int(item.index))),
                    "sort_value": sort_values.get(int(item.index)),
                    "editor_endpoint": f"/v1/screen/{domain}/record/{int(item.index)}",
                }
                for item in page
            ),
        }

    def _is_stat_selector(self, entry: Any) -> bool:
        return bool(self.model.is_player_season_id_selector_entry(entry))

    def _is_stat_detail(self, entry: Any) -> bool:
        return bool(self.model.is_player_selected_stat_detail_entry(entry))

    def _field_role(self, entry: Any) -> str:
        if self._is_stat_selector(entry):
            return "player_season_stat_selector"
        if self._is_stat_detail(entry):
            return "player_season_stat_detail"
        return "record_field"

    def _field_catalog_payload(self, domain: str, query: dict[str, list[str]]) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        try:
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", [str(_DEFAULT_FIELD_PAGE_SIZE)])[0])
        except ValueError:
            return 400, {"error": "offset and limit must be integers"}
        if offset < 0:
            return 400, {"error": "offset must be zero or greater"}
        if limit < 1 or limit > _MAX_FIELD_PAGE_SIZE:
            return 400, {"error": f"limit must be between 1 and {_MAX_FIELD_PAGE_SIZE}"}

        section = query.get("section", [None])[0]
        group = query.get("group", [None])[0]
        search = str(query.get("search", [""])[0]).strip()
        raw_include_options = str(query.get("include_options", ["false"])[0]).casefold()
        if raw_include_options not in {"false", "true", "0", "1"}:
            return 400, {"error": "include_options must be true or false"}
        include_options = raw_include_options in {"true", "1"}
        if group is not None and section is None:
            return 400, {"error": "section is required when group is provided"}

        grouped = self.model.grouped_fields(domain)
        available_sections = tuple(
            {"section": str(section_label), "groups": tuple(str(group_label) for group_label in groups)}
            for section_label, groups in grouped.items()
        )
        if section is not None and section not in grouped:
            return 404, {
                "error": f"exact editor section not found: {section}",
                "available_sections": available_sections,
            }
        if group is not None and group not in grouped[section]:
            return 404, {
                "error": f"exact editor group not found: {section} / {group}",
                "available_groups": tuple(str(label) for label in grouped[section]),
            }

        entries: list[Any] = []
        for section_label, groups in grouped.items():
            if section is not None and section_label != section:
                continue
            for group_label, group_entries in groups.items():
                if group is not None and group_label != group:
                    continue
                entries.extend(group_entries)
        if search:
            search_text = search.casefold()
            entries = [
                entry
                for entry in entries
                if search_text
                in " ".join(
                    (
                        str(entry.section),
                        str(entry.group),
                        str(entry.normalized_name),
                        str(entry.display_name),
                    )
                ).casefold()
            ]

        total = len(entries)
        page = entries[offset : offset + limit]
        fields: list[dict[str, Any]] = []
        for entry in page:
            field: dict[str, Any] = {
                "section": str(entry.section),
                "group": str(entry.group),
                "normalized_name": str(entry.normalized_name),
                "display_name": str(entry.display_name),
                "role": self._field_role(entry),
            }
            if include_options:
                field["options"] = tuple(str(option) for option in self.model.field_options(entry))
            fields.append(field)
        return 200, {
            "object": "nba2k_editor.field_catalog",
            "screen": domain,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "filters": {
                "section": section,
                "group": group,
                "search": search,
                "include_options": include_options,
            },
            "available_sections": available_sections,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
            "fields": tuple(fields),
        }

    def _read_record_field(
        self,
        domain: str,
        index: int,
        query: dict[str, list[str]],
    ) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        item = self._record_item(domain, index)
        if item is None:
            return 404, {"error": f"loaded {domain} record not found: {int(index)}"}
        required = ("section", "group", "normalized_name")
        missing = tuple(name for name in required if not query.get(name, [""])[0])
        if missing:
            return 400, {"error": f"field query is missing required keys: {', '.join(missing)}"}
        section = str(query["section"][0])
        group = str(query["group"][0])
        normalized_name = str(query["normalized_name"][0])
        entry = self._field_entry(
            domain,
            section=section,
            group=group,
            normalized_name=normalized_name,
        )
        if entry is None:
            return 404, {
                "error": "exact editor field not found",
                "field": {
                    "section": section,
                    "group": group,
                    "normalized_name": normalized_name,
                },
            }
        stat_selector = query.get("stat_selector", [None])[0]
        if self._is_stat_detail(entry):
            options = tuple(str(option) for option in self.model.player_season_stat_id_options(int(item.index)))
            if stat_selector is None:
                return 400, {
                    "error": "stat_selector is required for a season-stat detail field",
                    "options": options,
                }
            if stat_selector not in options:
                return 400, {
                    "error": f"unknown player season Stat ID selector: {stat_selector}",
                    "options": options,
                }
        return 200, {
            "object": "nba2k_editor.field_read",
            "screen": domain,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "record": {
                "domain": str(item.domain),
                "index": int(item.index),
                "address": int(item.address),
                "label": str(item.label),
                "display_label": str(item.display_label),
            },
            "field": self._field_payload(entry, item, stat_selector=stat_selector),
        }

    def _read_record_fields(
        self,
        domain: str,
        index: int,
        body: dict[str, Any],
    ) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        item = self._record_item(domain, index)
        if item is None:
            return 404, {"error": f"loaded {domain} record not found: {int(index)}"}
        requested_fields = body.get("fields")
        if not isinstance(requested_fields, list):
            return 400, {"error": "body must contain a fields array"}
        if not requested_fields or len(requested_fields) > _MAX_BATCH_FIELD_READS:
            return 400, {"error": f"fields must contain between 1 and {_MAX_BATCH_FIELD_READS} entries"}

        results: list[dict[str, Any]] = []
        succeeded = 0
        for position, request in enumerate(requested_fields):
            request_payload = _json_safe_value(request)
            if not isinstance(request, dict):
                results.append(
                    {
                        "position": position,
                        "request": request_payload,
                        "http_status": 400,
                        "error": "field request must be an object",
                    }
                )
                continue
            required = ("section", "group", "normalized_name")
            missing = tuple(name for name in required if name not in request)
            if missing:
                results.append(
                    {
                        "position": position,
                        "request": request_payload,
                        "http_status": 400,
                        "error": f"field request is missing required keys: {', '.join(missing)}",
                    }
                )
                continue
            invalid_types = tuple(
                name for name in required if not isinstance(request[name], str) or not request[name]
            )
            stat_selector = request.get("stat_selector")
            if stat_selector is not None and not isinstance(stat_selector, str):
                invalid_types = (*invalid_types, "stat_selector")
            if invalid_types:
                results.append(
                    {
                        "position": position,
                        "request": request_payload,
                        "http_status": 400,
                        "error": f"field request values must be non-empty strings: {', '.join(invalid_types)}",
                    }
                )
                continue
            query = {
                "section": [request["section"]],
                "group": [request["group"]],
                "normalized_name": [request["normalized_name"]],
            }
            if stat_selector is not None:
                query["stat_selector"] = [stat_selector]
            status, payload = self._read_record_field(domain, index, query)
            result: dict[str, Any] = {
                "position": position,
                "request": request_payload,
                "http_status": int(status),
            }
            if status == 200 and isinstance(payload, dict):
                result["field"] = payload["field"]
                if bool(payload["field"].get("available")):
                    succeeded += 1
            elif isinstance(payload, dict):
                result["error"] = str(payload.get("error") or "field read failed")
                if "options" in payload:
                    result["options"] = payload["options"]
            else:
                result["error"] = "field read failed"
            results.append(result)

        return 200, {
            "object": "nba2k_editor.field_read_batch",
            "screen": domain,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "record": {
                "domain": str(item.domain),
                "index": int(item.index),
                "address": int(item.address),
                "label": str(item.label),
                "display_label": str(item.display_label),
            },
            "requested": len(requested_fields),
            "succeeded": succeeded,
            "failed": len(requested_fields) - succeeded,
            "complete": succeeded == len(requested_fields),
            "results": tuple(results),
        }

    def _stat_control(
        self,
        item: Any,
        entries: tuple[Any, ...],
        requested_selector: str | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        detail_entries = tuple(entry for entry in entries if self._is_stat_detail(entry))
        if not detail_entries:
            return None, None
        options = tuple(str(option) for option in self.model.player_season_stat_id_options(int(item.index)))
        if requested_selector is not None and requested_selector not in options:
            raise ValueError(f"unknown player season Stat ID selector: {requested_selector}")
        active = requested_selector if requested_selector is not None else (options[0] if options else None)
        return {
            "type": "player_season_stat_id",
            "label": "Active Season Stat ID",
            "options": options,
            "value": active,
        }, active

    def _field_payload(self, entry: Any, item: Any, *, stat_selector: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section": str(entry.section),
            "group": str(entry.group),
            "normalized_name": str(entry.normalized_name),
            "display_name": str(entry.display_name),
            "options": tuple(str(option) for option in self.model.field_options(entry)),
        }
        try:
            value = self.model.read_entry_value_for_item(entry, item, stat_selector=stat_selector)
        except Exception as exc:
            payload.update({"available": False, "error": str(exc), "writeable": False})
        else:
            payload.update(
                {
                    "available": True,
                    "address": int(value["address"]) if value.get("address") is not None else None,
                    "display_value": _json_safe_value(value.get("display_value")),
                    "raw_value": _json_safe_value(value.get("raw_value")),
                    "writeable": bool(value.get("writeable")),
                    "value_behavior": str(value.get("value_behavior") or ""),
                }
            )
        if stat_selector is not None and self._is_stat_detail(entry):
            payload["stat_selector"] = stat_selector
        return payload

    def _record_editor_payload(
        self,
        domain: str,
        index: int,
        *,
        requested_selector: str | None = None,
    ) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        item = self._record_item(domain, index)
        if item is None:
            return 404, {"error": f"loaded {domain} record not found: {int(index)}"}
        sections: list[dict[str, Any]] = []
        try:
            grouped = self.model.grouped_fields(domain)
            for section, groups in grouped.items():
                section_groups: list[dict[str, Any]] = []
                for group, group_entries in groups.items():
                    entries = tuple(group_entries)
                    control, stat_selector = self._stat_control(item, entries, requested_selector)
                    fields = tuple(
                        self._field_payload(entry, item, stat_selector=stat_selector)
                        for entry in entries
                        if not self._is_stat_selector(entry)
                    )
                    group_payload: dict[str, Any] = {"label": str(group), "fields": fields}
                    if control is not None:
                        group_payload["controls"] = (control,)
                    section_groups.append(group_payload)
                sections.append({"label": str(section), "groups": tuple(section_groups)})
        except ValueError as exc:
            return 400, {"error": str(exc)}
        return 200, {
            "object": "nba2k_editor.record_editor",
            "screen": domain,
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "record": {
                "domain": str(item.domain),
                "index": int(item.index),
                "address": int(item.address),
                "label": str(item.label),
                "display_label": str(item.display_label),
            },
            "sections": tuple(sections),
            "write_contract": {
                "method": "PATCH",
                "endpoint": f"/v1/screen/{domain}/record/{int(item.index)}",
                "body": {
                    "field": {
                        "section": "exact section label",
                        "group": "exact group label",
                        "normalized_name": "exact normalized field name",
                        "value": "new display value",
                        "stat_selector": "required only for a season-stat detail field",
                    }
                },
            },
        }

    def _field_entry(self, domain: str, *, section: str, group: str, normalized_name: str) -> Any | None:
        entries = self.model.grouped_fields(domain).get(section, {}).get(group, ())
        matches = tuple(entry for entry in entries if str(entry.normalized_name) == normalized_name)
        return matches[0] if len(matches) == 1 else None

    def _write_record_field(self, domain: str, index: int, body: dict[str, Any]) -> tuple[int, object]:
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        item = self._record_item(domain, index)
        if item is None:
            return 404, {"error": f"loaded {domain} record not found: {int(index)}"}
        update = body.get("field")
        if not isinstance(update, dict):
            return 400, {"error": "body must contain one field object"}
        required = ("section", "group", "normalized_name", "value")
        missing = tuple(name for name in required if name not in update)
        if missing:
            return 400, {"error": f"field is missing required keys: {', '.join(missing)}"}
        section = str(update["section"])
        group = str(update["group"])
        normalized_name = str(update["normalized_name"])
        entry = self._field_entry(
            domain,
            section=section,
            group=group,
            normalized_name=normalized_name,
        )
        if entry is None:
            return 404, {
                "error": "exact editor field not found",
                "field": {
                    "section": section,
                    "group": group,
                    "normalized_name": normalized_name,
                },
            }
        if self._is_stat_selector(entry):
            return 409, {"error": "season Stat ID selectors are editor controls, not writable detail fields"}
        stat_selector_value = update.get("stat_selector")
        stat_selector = None if stat_selector_value is None else str(stat_selector_value)
        if self._is_stat_detail(entry):
            options = tuple(str(option) for option in self.model.player_season_stat_id_options(int(item.index)))
            if stat_selector is None:
                return 400, {"error": "stat_selector is required for a season-stat detail field"}
            if stat_selector not in options:
                return 400, {"error": f"unknown player season Stat ID selector: {stat_selector}"}
        before = self.model.read_entry_value_for_item(entry, item, stat_selector=stat_selector)
        if not bool(before.get("writeable")):
            return 409, {"error": f"field is not writable: {section} / {group} / {normalized_name}"}
        try:
            self.model.write_entry_value_for_item(
                entry,
                item,
                value=update["value"],
                stat_selector=stat_selector,
            )
            after = self.model.read_entry_value_for_item(entry, item, stat_selector=stat_selector)
        except (PermissionError, TypeError, ValueError) as exc:
            return 422, {"error": str(exc)}
        field_identity = {
            "section": section,
            "group": group,
            "normalized_name": normalized_name,
            "display_name": str(entry.display_name),
        }
        if stat_selector is not None:
            field_identity["stat_selector"] = stat_selector
        return 200, {
            "object": "nba2k_editor.field_write",
            "screen": domain,
            "record_index": int(item.index),
            "field": field_identity,
            "before": {
                "display_value": _json_safe_value(before.get("display_value")),
                "raw_value": _json_safe_value(before.get("raw_value")),
            },
            "after": {
                "display_value": _json_safe_value(after.get("display_value")),
                "raw_value": _json_safe_value(after.get("raw_value")),
            },
            "verified": True,
            "data_version": int(getattr(self.model, "_data_version", 0)),
        }

    def _parse_screen_path(self, path: str) -> tuple[str, int | None, str | None] | None:
        prefix = "/v1/screen/"
        if not path.startswith(prefix):
            return None
        remainder = path[len(prefix) :]
        if remainder.endswith("/refresh"):
            return unquote(remainder[: -len("/refresh")]), None, "refresh"
        if remainder.endswith("/fields"):
            return unquote(remainder[: -len("/fields")]), None, "fields"
        record_marker = "/record/"
        if record_marker not in remainder:
            return unquote(remainder), None, "list"
        encoded_domain, record_path = remainder.split(record_marker, 1)
        operation = "record"
        if record_path.endswith("/fields/read"):
            record_path = record_path[: -len("/fields/read")]
            operation = "read_fields"
        elif record_path.endswith("/field"):
            record_path = record_path[: -len("/field")]
            operation = "field"
        try:
            index = int(unquote(record_path))
        except ValueError:
            return unquote(encoded_domain), None, "invalid_record"
        return unquote(encoded_domain), index, operation

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

    def _index_field_payload(self, entry: Any, *, index: int, stat_selector: str | None = None) -> dict[str, Any]:
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
                player_fields[normalized_name] = self._index_field_payload(entry, index=int(player.index))

        current_stat_entry = entries_by_name.get(_CURRENT_YEAR_STAT_SELECTOR)
        current_stat_id = (
            {
                "normalized_name": _CURRENT_YEAR_STAT_SELECTOR,
                "available": False,
                "error": "field is unavailable in the active editor layout",
            }
            if current_stat_entry is None
            else self._index_field_payload(current_stat_entry, index=int(player.index))
        )
        stat_entries = tuple(entry for entry in entries if self.model.is_player_selected_stat_detail_entry(entry))
        current_season_stats = {
            str(entry.normalized_name): self._index_field_payload(
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
            str(entry.normalized_name): self._index_field_payload(entry, index=int(team_index))
            for entry in entries
        }

    def _team_state(self, team_index: int) -> dict[str, Any]:
        team_item = self._record_item("Teams", team_index)
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
            "data_version": int(getattr(self.model, "_data_version", 0)),
            "team_index": int(team_index),
            "team_label": str(team_item.label),
            "team_display_label": str(team_item.display_label),
            "team_record_fields": self._team_record_fields(team_index),
            "roster_count": len(roster),
            "roster": roster,
            "record_editor_endpoint": f"/v1/screen/Teams/record/{int(team_index)}",
            "nba_records_endpoint": "/v1/screen/NBA%20Records",
        }

    def handle_get(self, raw_path: str) -> tuple[int, object]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query, keep_blank_values=True)
        if path in {"/health", "/v1/health"}:
            return 200, {
                "status": "ok",
                "read_only": False,
                "screens": HERMES_AI_SCREENS,
                "excluded_screens": HERMES_EXCLUDED_SCREENS,
            }
        if path == "/v1/manifest":
            return 200, self._manifest()
        if path == "/v1/screens":
            return 200, {
                "object": "nba2k_editor.screens",
                "screens": HERMES_AI_SCREENS,
                "excluded_screens": HERMES_EXCLUDED_SCREENS,
            }
        if path == "/v1/player-generator":
            return self._player_generator_state()
        screen_path = self._parse_screen_path(path)
        if screen_path is not None:
            domain, index, operation = screen_path
            if operation == "invalid_record":
                return 400, {"error": "record index must be an integer"}
            if operation == "refresh":
                return 405, {"error": "use POST to refresh an editor screen"}
            if operation == "list":
                return self._record_list_payload(domain, query)
            if operation == "fields":
                return self._field_catalog_payload(domain, query)
            if index is None:
                return 400, {"error": "record index must be an integer"}
            if operation == "field":
                return self._read_record_field(domain, index, query)
            requested = query.get("stat_selector", [None])[0]
            return self._record_editor_payload(domain, index, requested_selector=requested)
        if path == "/v1/teams":
            return 200, self._teams()
        team_prefix = "/v1/team/"
        if path.startswith(team_prefix):
            team_index_text = unquote(path[len(team_prefix) :])
            try:
                team_index = int(team_index_text)
            except ValueError:
                return 400, {"error": f"invalid team index: {team_index_text}"}
            if self._record_item("Teams", team_index) is None:
                return 404, {"error": f"loaded Teams record not found: {team_index}"}
            return 200, self._team_state(team_index)
        if path == "/v1/snapshot":
            requested = parse_qs(parsed.query).get("domains", [])
            domains = tuple(part for value in requested for part in value.split(",") if part) or HERMES_EDITOR_DOMAINS
            for domain in domains:
                invalid = self._validate_domain(domain)
                if invalid is not None:
                    return invalid
            return 200, self.model.app_dataset_snapshot(domains=domains)
        prefix = "/v1/domain/"
        if path.startswith(prefix):
            domain = unquote(path[len(prefix) :])
            invalid = self._validate_domain(domain)
            if invalid is not None:
                return invalid
            return 200, self.model.domain_dataset_snapshot(domain)
        return 404, {"error": "unknown Hermes editor API endpoint"}

    def handle_post(self, raw_path: str, body: dict[str, Any]) -> tuple[int, object]:
        _ = body
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        screen_path = self._parse_screen_path(path)
        if screen_path is None:
            return 404, {"error": "unknown Hermes editor API endpoint"}
        domain, index, operation = screen_path
        if operation == "read_fields" and index is not None:
            return self._read_record_fields(domain, index, body)
        if operation != "refresh":
            return 405, {"error": "POST is only supported for screen refresh or exact field reads"}
        invalid = self._validate_domain(domain)
        if invalid is not None:
            return invalid
        self.model.refresh_domains((domain,))
        return self._record_list_payload(domain, {})

    def handle_patch(self, raw_path: str, body: dict[str, Any]) -> tuple[int, object]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        screen_path = self._parse_screen_path(path)
        if screen_path is None:
            return 404, {"error": "unknown Hermes editor API endpoint"}
        domain, index, operation = screen_path
        if operation != "record" or index is None:
            return 405, {"error": "PATCH requires an exact screen record endpoint"}
        return self._write_record_field(domain, index, body)


__all__ = [
    "DEFAULT_HERMES_BRIDGE_HOST",
    "DEFAULT_HERMES_BRIDGE_PORT",
    "HERMES_AI_SCREENS",
    "HERMES_EDITOR_DOMAINS",
    "HERMES_EXCLUDED_SCREENS",
    "HERMES_WORKFLOW_SCREENS",
    "HermesEditorBridge",
]
