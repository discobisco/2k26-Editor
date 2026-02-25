from __future__ import annotations

from ...mcp.tools import execute_franchise_optimizer
from .models import FranchiseOptimizeRequest, FranchiseOptimizeResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="franchise",
        path="/franchise/optimize",
        request_model=FranchiseOptimizeRequest,
        response_model=FranchiseOptimizeResponse,
        executor=execute_franchise_optimizer,
    )
