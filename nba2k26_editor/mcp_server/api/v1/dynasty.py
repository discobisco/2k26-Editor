from __future__ import annotations

from ...mcp.tools import execute_dynasty_tracker
from .models import DynastyTrackRequest, DynastyTrackResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="dynasty",
        path="/dynasty/track",
        request_model=DynastyTrackRequest,
        response_model=DynastyTrackResponse,
        executor=execute_dynasty_tracker,
    )
