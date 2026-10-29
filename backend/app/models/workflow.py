from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class WorkflowRecord:
    """Persisted workflow data, independent of the HTTP schemas."""

    id: UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime
