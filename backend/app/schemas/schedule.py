from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, StrictBool, field_validator

from app.schemas.workflow import ApiSchema


class ScheduleUpdate(ApiSchema):
    enabled: StrictBool


class ScheduleRead(ApiSchema):
    workflow_id: UUID
    enabled: bool
    cron: str | None = None
    timezone: str | None = None
    next_run_at: AwareDatetime | None = None
    scheduler_running: bool = False
    last_error: str | None = None

    @field_validator("next_run_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None
