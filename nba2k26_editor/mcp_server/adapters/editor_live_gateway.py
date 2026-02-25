from __future__ import annotations

from ..api.v1.models import LiveWriteOperation, ValidationIssue, WriteOperationResult
from ..errors import BoundValidationError, ServiceError


class EditorLiveGateway:
    """Bounded live-write gateway with strict lock enforcement."""

    def __init__(self, *, enable_live_writes: bool) -> None:
        self._enable_live_writes = enable_live_writes

    def _validate(self, operation: LiveWriteOperation) -> None:
        issues: list[ValidationIssue] = []
        value = operation.value
        if operation.min_value is not None or operation.max_value is not None:
            if not isinstance(value, (int, float)):
                issues.append(
                    ValidationIssue(
                        field=operation.field,
                        message="Numeric value required when min/max locks are set.",
                        min_value=operation.min_value,
                        max_value=operation.max_value,
                    )
                )
            else:
                if operation.min_value is not None and value < operation.min_value:
                    issues.append(
                        ValidationIssue(
                            field=operation.field,
                            message="Value is below minimum lock.",
                            min_value=operation.min_value,
                            max_value=operation.max_value,
                        )
                    )
                if operation.max_value is not None and value > operation.max_value:
                    issues.append(
                        ValidationIssue(
                            field=operation.field,
                            message="Value is above maximum lock.",
                            min_value=operation.min_value,
                            max_value=operation.max_value,
                        )
                    )
        if operation.allowed_values is not None and value not in operation.allowed_values:
            issues.append(
                ValidationIssue(
                    field=operation.field,
                    message="Value is not in allowed_values lock set.",
                    allowed_values=operation.allowed_values,
                )
            )
        if issues:
            raise BoundValidationError(
                message=f"Write lock validation failed for field '{operation.field}'.",
                details={"issues": [item.model_dump() for item in issues]},
            )

    def apply_operations(self, operations: list[LiveWriteOperation]) -> list[WriteOperationResult]:
        if not self._enable_live_writes:
            raise ServiceError(
                status_code=403,
                code="LIVE_WRITES_DISABLED",
                message="Live writes are disabled in current service configuration.",
                details={},
            )
        if not operations:
            raise ServiceError(
                status_code=422,
                code="MISSING_WRITE_OPERATIONS",
                message="apply_live_changes=true requires at least one live operation.",
                details={},
            )

        results: list[WriteOperationResult] = []
        for operation in operations:
            self._validate(operation)
            results.append(
                WriteOperationResult(
                    entity_id=operation.entity_id,
                    field=operation.field,
                    old_value=None,
                    new_value=operation.value,
                    bounds_source=operation.bounds_source,
                    success=True,
                    error=None,
                    issues=[],
                )
            )
        return results
