from __future__ import annotations

from ...mcp.tools import execute_progression_simulator
from .models import ProgressionSimulateRequest, ProgressionSimulateResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="progression",
        path="/progression/simulate",
        request_model=ProgressionSimulateRequest,
        response_model=ProgressionSimulateResponse,
        executor=execute_progression_simulator,
    )
