from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_EDITOR_API_URL = "http://127.0.0.1:8765"
_PROTOCOL_VERSION = "2024-11-05"
_EDITOR_SCREENS = (
    "Players",
    "Teams",
    "Staff",
    "Stadiums",
    "NBA History",
    "NBA Records",
)


def _tool_specs() -> list[dict[str, Any]]:
    screen_schema = {"type": "string", "enum": list(_EDITOR_SCREENS)}
    return [
        {
            "name": "editor_status",
            "description": "Inspect the live NBA2K editor connection, loaded screen counts, scope, and available operations.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "open_player_generator",
            "description": "Open the Player Generator workflow state as currently shown by the NBA2K editor.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_editor_snapshot",
            "description": "Read a snapshot of the loaded editor data. Pass domains to limit the snapshot to one or more screens.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domains": {
                        "type": "array",
                        "items": screen_schema,
                        "description": "Optional subset of screens to include in the snapshot.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "list_editor_fields",
            "description": "Discover exact section, group, and normalized field identities on one editor screen before reading or writing a field.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
                    "section": {"type": "string", "description": "Optional exact section label."},
                    "group": {"type": "string", "description": "Optional exact group label; section is then required."},
                    "search": {"type": "string", "default": ""},
                    "include_options": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include authored/runtime dropdown options for each returned field.",
                    },
                },
                "required": ["screen"],
                "additionalProperties": False,
            },
        },
        {
            "name": "read_editor_field",
            "description": "Read one exact field from one stable record without opening every field in the full editor payload.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "index": {"type": "integer"},
                    "section": {"type": "string"},
                    "group": {"type": "string"},
                    "normalized_name": {"type": "string"},
                    "stat_selector": {
                        "type": "string",
                        "description": "Required only for a player season-stat detail field.",
                    },
                },
                "required": ["screen", "index", "section", "group", "normalized_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "read_editor_fields",
            "description": "Read up to 100 exact fields from one stable record in one call. Results preserve request order and report per-field errors without writing.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "index": {"type": "integer"},
                    "fields": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 100,
                        "items": {
                            "type": "object",
                            "properties": {
                                "section": {"type": "string"},
                                "group": {"type": "string"},
                                "normalized_name": {"type": "string"},
                                "stat_selector": {
                                    "type": "string",
                                    "description": "Required only for a player season-stat detail field.",
                                },
                            },
                            "required": ["section", "group", "normalized_name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["screen", "index", "fields"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_editor_records",
            "description": "List, search, filter, and sort stable records on one NBA2K editor screen. Players reuse the editor's team and position filters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "offset": {"type": "integer", "minimum": 0, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
                    "search": {"type": "string", "default": ""},
                    "team_filter": {
                        "oneOf": [
                            {"type": "integer"},
                            {
                                "type": "string",
                                "enum": [
                                    "All Players",
                                    "Teams 0-29",
                                    "Free Agents",
                                    "Draft Class",
                                    "Franchise Prospects",
                                ],
                            },
                        ],
                        "description": "Players only: exact team index or editor filter value.",
                    },
                    "position_filter": {
                        "type": "string",
                        "enum": ["All Positions", "PG", "SG", "SF", "PF", "C"],
                        "description": "Players-only primary-position filter.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["index", "name", "team", "position", "overall", "salary_year_1", "field"],
                        "default": "index",
                    },
                    "sort_order": {"type": "string", "enum": ["asc", "desc"], "default": "asc"},
                    "sort_section": {"type": "string", "description": "Required when sort_by is field."},
                    "sort_group": {"type": "string", "description": "Required when sort_by is field."},
                    "sort_field": {"type": "string", "description": "Exact normalized field name required when sort_by is field."},
                    "sort_stat_selector": {"type": "string", "description": "Required when an exact sort field is season-stat routed."},
                },
                "required": ["screen"],
                "additionalProperties": False,
            },
        },
        {
            "name": "open_editor_record",
            "description": "Open one record exactly as the editor does, preserving section/group hierarchy, field values, options, and writability.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "index": {"type": "integer"},
                    "stat_selector": {
                        "type": "string",
                        "description": "Player season Stat ID selector returned by the record's Active Season Stat ID control.",
                    },
                },
                "required": ["screen", "index"],
                "additionalProperties": False,
            },
        },
        {
            "name": "write_editor_field",
            "description": "Write one exact field through the editor's normal write path and return the read-back value. Never identifies records by name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "screen": screen_schema,
                    "index": {"type": "integer"},
                    "section": {"type": "string"},
                    "group": {"type": "string"},
                    "normalized_name": {"type": "string"},
                    "value": {},
                    "stat_selector": {
                        "type": "string",
                        "description": "Required only for a player season-stat detail field.",
                    },
                },
                "required": ["screen", "index", "section", "group", "normalized_name", "value"],
                "additionalProperties": False,
            },
        },
        {
            "name": "refresh_editor_screen",
            "description": "Attach if needed and refresh one supported editor screen through the editor model.",
            "inputSchema": {
                "type": "object",
                "properties": {"screen": screen_schema},
                "required": ["screen"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_franchise_team_state",
            "description": "Read one loaded team's franchise-facing roster, player facts, current-season stats, and team record fields.",
            "inputSchema": {
                "type": "object",
                "properties": {"team_index": {"type": "integer"}},
                "required": ["team_index"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_franchise_teams",
            "description": "List the loaded Teams records that currently contribute to franchise roster mapping.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"} if data is not None else {},
    )
    try:
        with urlopen(request, timeout=120) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        return 503, {
            "error": "NBA2K editor API is unavailable",
            "detail": str(exc.reason),
            "expected_url": base_url,
        }
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return 502, {"error": "NBA2K editor API returned non-JSON data", "status": status, "body": raw}


def _required(arguments: dict[str, Any], name: str) -> Any:
    if name not in arguments:
        raise ValueError(f"missing required argument: {name}")
    return arguments[name]


def _call_editor_tool(base_url: str, name: str, arguments: dict[str, Any]) -> tuple[int, object]:
    if name == "editor_status":
        return _http_json(base_url, "GET", "/v1/manifest")
    if name == "open_player_generator":
        return _http_json(base_url, "GET", "/v1/player-generator")
    if name == "get_editor_snapshot":
        query_values: dict[str, object] = {}
        domains = arguments.get("domains")
        if domains is not None:
            if not isinstance(domains, list):
                raise ValueError("domains must be an array")
            query_values["domains"] = ",".join(str(domain) for domain in domains)
        suffix = "" if not query_values else f"?{urlencode(query_values)}"
        return _http_json(base_url, "GET", f"/v1/snapshot{suffix}")
    if name == "list_editor_fields":
        screen = quote(str(_required(arguments, "screen")), safe="")
        include_options = arguments.get("include_options", False)
        if not isinstance(include_options, bool):
            raise ValueError("include_options must be a boolean")
        query_values: dict[str, object] = {
            "offset": int(arguments.get("offset", 0)),
            "limit": int(arguments.get("limit", 100)),
            "search": str(arguments.get("search", "")),
            "include_options": "true" if include_options else "false",
        }
        for key in ("section", "group"):
            if arguments.get(key) is not None:
                query_values[key] = str(arguments[key])
        return _http_json(base_url, "GET", f"/v1/screen/{screen}/fields?{urlencode(query_values)}")
    if name == "read_editor_field":
        screen = quote(str(_required(arguments, "screen")), safe="")
        index = int(_required(arguments, "index"))
        query_values = {
            "section": str(_required(arguments, "section")),
            "group": str(_required(arguments, "group")),
            "normalized_name": str(_required(arguments, "normalized_name")),
        }
        if arguments.get("stat_selector") is not None:
            query_values["stat_selector"] = str(arguments["stat_selector"])
        return _http_json(
            base_url,
            "GET",
            f"/v1/screen/{screen}/record/{index}/field?{urlencode(query_values)}",
        )
    if name == "read_editor_fields":
        screen = quote(str(_required(arguments, "screen")), safe="")
        index = int(_required(arguments, "index"))
        fields = _required(arguments, "fields")
        if not isinstance(fields, list):
            raise ValueError("fields must be an array")
        return _http_json(
            base_url,
            "POST",
            f"/v1/screen/{screen}/record/{index}/fields/read",
            body={"fields": fields},
        )
    if name == "list_editor_records":
        screen = quote(str(_required(arguments, "screen")), safe="")
        query_values: dict[str, object] = {
            "offset": int(arguments.get("offset", 0)),
            "limit": int(arguments.get("limit", 100)),
            "search": str(arguments.get("search", "")),
            "sort_by": str(arguments.get("sort_by", "index")),
            "sort_order": str(arguments.get("sort_order", "asc")),
        }
        for key in (
            "team_filter",
            "position_filter",
            "sort_section",
            "sort_group",
            "sort_field",
            "sort_stat_selector",
        ):
            if arguments.get(key) is not None:
                query_values[key] = arguments[key]
        query = urlencode(query_values)
        return _http_json(base_url, "GET", f"/v1/screen/{screen}?{query}")
    if name == "open_editor_record":
        screen = quote(str(_required(arguments, "screen")), safe="")
        index = int(_required(arguments, "index"))
        selector = arguments.get("stat_selector")
        suffix = "" if selector is None else f"?{urlencode({'stat_selector': str(selector)})}"
        return _http_json(base_url, "GET", f"/v1/screen/{screen}/record/{index}{suffix}")
    if name == "write_editor_field":
        screen = quote(str(_required(arguments, "screen")), safe="")
        index = int(_required(arguments, "index"))
        field = {
            "section": str(_required(arguments, "section")),
            "group": str(_required(arguments, "group")),
            "normalized_name": str(_required(arguments, "normalized_name")),
            "value": _required(arguments, "value"),
        }
        if arguments.get("stat_selector") is not None:
            field["stat_selector"] = str(arguments["stat_selector"])
        return _http_json(
            base_url,
            "PATCH",
            f"/v1/screen/{screen}/record/{index}",
            body={"field": field},
        )
    if name == "refresh_editor_screen":
        screen = quote(str(_required(arguments, "screen")), safe="")
        return _http_json(base_url, "POST", f"/v1/screen/{screen}/refresh", body={})
    if name == "get_franchise_team_state":
        team_index = int(_required(arguments, "team_index"))
        return _http_json(base_url, "GET", f"/v1/team/{team_index}")
    if name == "list_franchise_teams":
        return _http_json(base_url, "GET", "/v1/teams")
    raise ValueError(f"unknown tool: {name}")


def _tool_result(status: int, payload: object) -> dict[str, Any]:
    result_payload = {"http_status": int(status), "response": payload}
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result_payload, sort_keys=True),
            }
        ],
        "isError": status >= 400,
    }


def _success(request_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": int(code), "message": str(message)}}


def _handle_message(message: dict[str, Any], *, base_url: str) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    request_id = message.get("id")
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        raw_params = message.get("params")
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
        requested_version = str(params.get("protocolVersion") or _PROTOCOL_VERSION)
        return _success(
            request_id,
            {
                "protocolVersion": requested_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nba2k-editor", "version": "1.2.0"},
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": _tool_specs()})
    if method == "tools/call":
        call_params = message.get("params")
        if not isinstance(call_params, dict):
            return _error(request_id, -32602, "tools/call params must be an object")
        name = str(call_params.get("name") or "")
        arguments = call_params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "tool arguments must be an object")
        try:
            status, payload = _call_editor_tool(base_url, name, arguments)
        except (TypeError, ValueError) as exc:
            return _success(request_id, _tool_result(400, {"error": str(exc)}))
        return _success(request_id, _tool_result(status, payload))
    return _error(request_id, -32601, f"method not found: {method}")


def serve_stdio(*, base_url: str = DEFAULT_EDITOR_API_URL) -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("MCP message must be a JSON object")
            response = _handle_message(message, base_url=base_url)
        except (json.JSONDecodeError, ValueError) as exc:
            response = _error(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes MCP tools for the live NBA2K editor")
    parser.add_argument("--base-url", default=DEFAULT_EDITOR_API_URL)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return serve_stdio(base_url=str(args.base_url))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_EDITOR_API_URL", "build_parser", "main", "serve_stdio"]
