from __future__ import annotations

from fastapi import APIRouter, Query

from ...mcp.tools import (
    execute_ai_draft_decision,
    execute_ai_free_agency_decision,
    execute_ai_franchise_direction,
    execute_ai_profile_lookup,
    execute_ai_trade_decision,
)
from .models import (
    AiDraftDecisionRequest,
    AiDraftDecisionResponse,
    AiFreeAgencyDecisionRequest,
    AiFreeAgencyDecisionResponse,
    AiFranchiseDirectionRequest,
    AiFranchiseDirectionResponse,
    AiProfileResponse,
    AiTradeDecisionRequest,
    AiTradeDecisionResponse,
)


def create_router(container) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["ai"])

    @router.post("/trade-decision", response_model=AiTradeDecisionResponse)
    def trade_decision(request: AiTradeDecisionRequest) -> AiTradeDecisionResponse:
        result = execute_ai_trade_decision(container, request.model_dump())
        return AiTradeDecisionResponse.model_validate(result)

    @router.post("/draft-decision", response_model=AiDraftDecisionResponse)
    def draft_decision(request: AiDraftDecisionRequest) -> AiDraftDecisionResponse:
        result = execute_ai_draft_decision(container, request.model_dump())
        return AiDraftDecisionResponse.model_validate(result)

    @router.post("/free-agency-decision", response_model=AiFreeAgencyDecisionResponse)
    def free_agency_decision(request: AiFreeAgencyDecisionRequest) -> AiFreeAgencyDecisionResponse:
        result = execute_ai_free_agency_decision(container, request.model_dump())
        return AiFreeAgencyDecisionResponse.model_validate(result)

    @router.post("/franchise-direction", response_model=AiFranchiseDirectionResponse)
    def franchise_direction(request: AiFranchiseDirectionRequest) -> AiFranchiseDirectionResponse:
        result = execute_ai_franchise_direction(container, request.model_dump())
        return AiFranchiseDirectionResponse.model_validate(result)

    @router.get("/profile/{team_id}", response_model=AiProfileResponse)
    def profile_lookup(
        team_id: str,
        era: str = Query(default="modern"),
        season: str = Query(default="2025-26"),
    ) -> AiProfileResponse:
        result = execute_ai_profile_lookup(
            container,
            {
                "team_id": team_id,
                "era": era,
                "season": season,
            },
        )
        return AiProfileResponse.model_validate(result)

    return router
