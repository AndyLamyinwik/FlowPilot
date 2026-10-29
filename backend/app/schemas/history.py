from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.models.execution import ExecutionStatus, TriggerType
from app.schemas.execution import ExecutionError, NodeExecutionResult
from app.schemas.workflow import ApiSchema


class HistoryNodeResult(NodeExecutionResult):
    duration_ms: int | None = Field(default=None, ge=0)


class ExecutionSummary(ApiSchema):
    execution_id: UUID
    workflow_id: UUID
    trigger_type: TriggerType
    status: ExecutionStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
    duration_ms: int | None = Field(ge=0)

    _normalize_utc = field_validator("started_at", "finished_at")(
        NodeExecutionResult.normalize_utc.__func__
    )


class ExecutionHistoryDetail(ExecutionSummary):
    node_results: list[HistoryNodeResult]
    error: ExecutionError | None
    created_at: AwareDatetime
    definition_hash: str
    outputs_stored: bool
    history_truncated: bool

    _normalize_created = field_validator("created_at")(
        NodeExecutionResult.normalize_utc.__func__
    )


class ExecutionHistoryPage(ApiSchema):
    items: list[ExecutionSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
