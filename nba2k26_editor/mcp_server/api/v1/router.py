from __future__ import annotations

from fastapi import APIRouter

from . import ai, draft, dynasty, era, franchise, health, locker_room, progression, simulation, trade


def build_router(container) -> APIRouter:
    router = APIRouter(prefix="/v1")
    router.include_router(health.create_router(container))
    router.include_router(ai.create_router(container))
    router.include_router(franchise.create_router(container))
    router.include_router(trade.create_router(container))
    router.include_router(locker_room.create_router(container))
    router.include_router(draft.create_router(container))
    router.include_router(progression.create_router(container))
    router.include_router(simulation.create_router(container))
    router.include_router(dynasty.create_router(container))
    router.include_router(era.create_router(container))
    return router
