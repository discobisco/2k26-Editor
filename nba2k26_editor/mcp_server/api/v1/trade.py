from __future__ import annotations

from ...mcp.tools import execute_trade_evaluator
from .models import TradeEvaluateRequest, TradeEvaluateResponse
from .simple_router import create_simple_post_router


def create_router(container):
    return create_simple_post_router(
        container=container,
        tag="trade",
        path="/trade/evaluate",
        request_model=TradeEvaluateRequest,
        response_model=TradeEvaluateResponse,
        executor=execute_trade_evaluator,
    )
