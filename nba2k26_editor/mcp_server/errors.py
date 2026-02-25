from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class BoundValidationError(ServiceError):
    def __init__(self, message: str, *, details: dict[str, Any]) -> None:
        super().__init__(
            status_code=422,
            code="BOUND_VALIDATION_FAILED",
            message=message,
            details=details,
        )
