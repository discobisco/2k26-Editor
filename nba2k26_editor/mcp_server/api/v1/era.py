from __future__ import annotations

from ...mcp.tools import execute_era_transition_handler
from .models import EraTransitionRequest, EraTransitionResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="era",
        path="/era/transition",
        request_model=EraTransitionRequest,
        response_model=EraTransitionResponse,
        executor=execute_era_transition_handler,
    )
