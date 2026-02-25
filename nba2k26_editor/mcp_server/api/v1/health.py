from __future__ import annotations

from fastapi import APIRouter, Request

from .models import MCPInvokeRequest, MCPInvokeResponse


def create_router(container) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    def health(request: Request) -> dict[str, object]:
        return {
            "success": True,
            "service": "nba2k-myeras-mcp",
            "status": "ok",
            "request_id": getattr(request.state, "request_id", None),
        }

    @router.get("/capabilities")
    def capabilities() -> dict[str, object]:
        return {
            "service": "nba2k-myeras-mcp",
            "version": "v1",
            "eras": ["1980s", "1990s", "2000s", "modern"],
            "live_writes_enabled": container.settings.enable_live_writes,
            "capability_flags": {
                "cpu_ai_personality_v1": container.settings.enable_cpu_ai_personality_v1,
                "locker_room_personality_v1": container.settings.enable_locker_room_v1,
            },
            "tools": [tool["name"] for tool in container.mcp_server.list_tools()],
        }

    @router.get("/mcp/tools", tags=["mcp"])
    def list_mcp_tools() -> dict[str, object]:
        return {"tools": container.mcp_server.list_tools()}

    @router.post("/mcp/invoke", response_model=MCPInvokeResponse, tags=["mcp"])
    def invoke_mcp(request: MCPInvokeRequest) -> MCPInvokeResponse:
        result = container.mcp_server.invoke_tool(request.tool, request.arguments)
        return MCPInvokeResponse(tool=request.tool, result=result)

    return router
