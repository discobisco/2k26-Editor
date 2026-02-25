from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..errors import ServiceError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError):  # type: ignore[override]
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):  # type: ignore[override]
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "REQUEST_VALIDATION_FAILED",
                    "message": "Request validation failed.",
                    "details": {"issues": exc.errors()},
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )
