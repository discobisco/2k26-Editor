from __future__ import annotations

from fastapi import APIRouter

from ...mcp.tools import execute_draft_generator, execute_draft_lottery
from .models import (
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftLotteryRequest,
    DraftLotteryResponse,
)


def create_router(container) -> APIRouter:
    router = APIRouter(tags=["draft"])

    @router.post("/draft/generate", response_model=DraftGenerateResponse)
    def generate(request: DraftGenerateRequest) -> DraftGenerateResponse:
        result = execute_draft_generator(container, request.model_dump())
        return DraftGenerateResponse.model_validate(result)

    @router.post("/draft/simulate-lottery", response_model=DraftLotteryResponse)
    def simulate_lottery(request: DraftLotteryRequest) -> DraftLotteryResponse:
        result = execute_draft_lottery(container, request.model_dump())
        return DraftLotteryResponse.model_validate(result)

    return router
