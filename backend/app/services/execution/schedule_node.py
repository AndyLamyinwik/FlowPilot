from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from pydantic import Field, JsonValue, ValidationError

from app.schemas.workflow import ApiSchema
from app.services.execution.context import NodeExecutionContext
from app.services.execution.executor import NodeExecutionError


class ScheduleConfig(ApiSchema):
    cron: str = Field(strict=True, min_length=1, max_length=256)
    timezone: str = Field(default="UTC", strict=True, min_length=1, max_length=128)


def parse_schedule(config: dict) -> tuple[ScheduleConfig, CronTrigger]:
    """Use APScheduler's five-field parser and the standard IANA database."""
    try:
        parsed = ScheduleConfig.model_validate(config)
    except ValidationError:
        raise NodeExecutionError(
            "INVALID_SCHEDULE_CONFIG", "Schedule configuration is invalid"
        ) from None
    try:
        timezone = ZoneInfo(parsed.timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise NodeExecutionError(
            "INVALID_SCHEDULE_TIMEZONE", "Schedule timezone must be an IANA timezone"
        ) from None
    try:
        trigger = CronTrigger.from_crontab(parsed.cron, timezone=timezone)
    except (ValueError, TypeError, OverflowError):
        raise NodeExecutionError(
            "INVALID_SCHEDULE_CRON", "Schedule cron must be a valid five-field expression"
        ) from None
    return parsed, trigger


class ScheduleTriggerExecutor:
    def validate_config(self, config: dict, upstream_ids: set[str]) -> None:
        parse_schedule(config)

    def execute(self, context: NodeExecutionContext) -> JsonValue:
        parse_schedule(context.node_config)
        value = context.metadata.get("scheduled_at")
        try:
            scheduled_at = datetime.fromisoformat(value) if isinstance(value, str) else None
            if scheduled_at is None or scheduled_at.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError):
            raise NodeExecutionError(
                "INVALID_SCHEDULE_CONTEXT", "Schedule trigger requires an aware trigger time"
            ) from None
        return {
            "trigger": "schedule",
            "scheduled_at": scheduled_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
