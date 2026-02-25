from __future__ import annotations

from fastapi import APIRouter, Query

from ...mcp.tools import (
    execute_locker_room_chemistry_calculate,
    execute_locker_room_conflict_simulate,
    execute_locker_room_morale_evaluate,
    execute_locker_room_personality_update,
    execute_locker_room_status_lookup,
)
from .models import (
    ChemistryCalculateRequest,
    ChemistryCalculateResponse,
    ConflictSimulateRequest,
    ConflictSimulateResponse,
    LockerRoomStatusResponse,
    MoraleEvaluateRequest,
    MoraleEvaluateResponse,
    PersonalityUpdateRequest,
    PersonalityUpdateResponse,
)


def create_router(container) -> APIRouter:
    router = APIRouter(tags=["locker_room"])

    @router.post("/chemistry/calculate", response_model=ChemistryCalculateResponse)
    def chemistry_calculate(request: ChemistryCalculateRequest) -> ChemistryCalculateResponse:
        result = execute_locker_room_chemistry_calculate(container, request.model_dump(by_alias=True))
        return ChemistryCalculateResponse.model_validate(result)

    @router.post("/personality/update", response_model=PersonalityUpdateResponse)
    def personality_update(request: PersonalityUpdateRequest) -> PersonalityUpdateResponse:
        result = execute_locker_room_personality_update(container, request.model_dump(by_alias=True))
        return PersonalityUpdateResponse.model_validate(result)

    @router.post("/conflict/simulate", response_model=ConflictSimulateResponse)
    def conflict_simulate(request: ConflictSimulateRequest) -> ConflictSimulateResponse:
        result = execute_locker_room_conflict_simulate(container, request.model_dump(by_alias=True))
        return ConflictSimulateResponse.model_validate(result)

    @router.post("/morale/evaluate", response_model=MoraleEvaluateResponse)
    def morale_evaluate(request: MoraleEvaluateRequest) -> MoraleEvaluateResponse:
        result = execute_locker_room_morale_evaluate(container, request.model_dump(by_alias=True))
        return MoraleEvaluateResponse.model_validate(result)

    @router.get("/locker-room/status/{team_id}", response_model=LockerRoomStatusResponse)
    def locker_room_status(
        team_id: str,
        profile_id: str = Query(..., alias="profile_id"),
        season: str = Query(...),
        era: str = Query(...),
    ) -> LockerRoomStatusResponse:
        result = execute_locker_room_status_lookup(
            container,
            {
                "team_id": team_id,
                "profile_id": profile_id,
                "season": season,
                "era": era,
            },
        )
        return LockerRoomStatusResponse.model_validate(result)

    return router

