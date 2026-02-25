from __future__ import annotations

from typing import Any

from ..errors import ServiceError
from .schemas import get_tool_schemas
from .tools import TOOL_EXECUTORS


class MyErasMCPServer:
    def __init__(self, container) -> None:
        self._container = container

    def list_tools(self) -> list[dict[str, object]]:
        return get_tool_schemas()

    def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        executor = TOOL_EXECUTORS.get(tool)
        if executor is None:
            raise ServiceError(
                status_code=404,
                code="UNKNOWN_MCP_TOOL",
                message=f"MCP tool '{tool}' is not registered.",
                details={"available_tools": sorted(TOOL_EXECUTORS.keys())},
            )
        return executor(self._container, arguments)
