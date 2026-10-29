from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

TriggerType = Literal["manual", "schedule"]
ExecutionStatus = Literal["running", "success", "failed", "interrupted", "skipped"]


@dataclass(frozen=True)
class ExecutionRecord:
    """Persisted, privacy-filtered execution data; never the workflow config."""

    execution_id: UUID
    workflow_id: UUID
    trigger_type: TriggerType
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    node_results: list[dict[str, Any]]
    error: dict[str, Any] | None
    created_at: datetime
    definition_hash: str
    outputs_stored: bool = False
    history_truncated: bool = False
