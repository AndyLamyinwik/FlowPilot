from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, field_validator

from app.schemas.errors import RequestValidationIssue
from app.schemas.workflow import ApiSchema, ValidationIssue


class ExecutionError(ApiSchema):
    code: str
    message: str
    node_id: str | None = None


class NodeExecutionResult(ApiSchema):
    node_id: str
    status: Literal["pending", "running", "success", "failed", "skipped"] = "pending"
    output: JsonValue = None
    error: ExecutionError | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @field_validator("started_at", "finished_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class WorkflowExecutionResult(ApiSchema):
    execution_id: UUID
    workflow_id: UUID
    status: Literal["running", "success", "failed"] = "running"
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    node_results: list[NodeExecutionResult] = Field(default_factory=list)
    error: ExecutionError | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class ExecutionReadinessError(ApiSchema):
    code: Literal["WORKFLOW_NOT_EXECUTABLE"]
    errors: list[ValidationIssue]


class ExecutionInputError(ApiSchema):
    detail: list[RequestValidationIssue] | ExecutionReadinessError
