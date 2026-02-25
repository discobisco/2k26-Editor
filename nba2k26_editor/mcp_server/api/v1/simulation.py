from __future__ import annotations

from ...mcp.tools import execute_season_simulator
from .models import SeasonSimulateRequest, SeasonSimulateResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="simulation",
        path="/season/simulate",
        request_model=SeasonSimulateRequest,
        response_model=SeasonSimulateResponse,
        executor=execute_season_simulator,
    )
