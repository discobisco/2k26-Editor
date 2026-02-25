from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


def create_simple_post_router(
    *,
    container: Any,
    tag: str,
    path: str,
    request_model: type,
    response_model: type,
    executor: Callable[[Any, dict[str, Any]], dict[str, Any]],
) -> APIRouter:
    """Build a one-endpoint POST router with consistent execution wiring."""
    router = APIRouter(tags=[tag])

    @router.post(path, response_model=response_model)
    def _handle(request: request_model):  # type: ignore[valid-type]
        result = executor(container, request.model_dump())
        return response_model.model_validate(result)

    return router
