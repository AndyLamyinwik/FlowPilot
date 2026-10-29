from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.execution.context import NodeExecutionContext
from app.services.execution.executor import NodeExecutionError
from app.services.execution.schedule_node import ScheduleTriggerExecutor, parse_schedule


@pytest.mark.parametrize("cron", ["*/5 * * * *", "0 * * * *", "0 9 * * *", "0 9 * * mon", "0 9 1 * *"])
def test_valid_five_field_cron(cron):
    parsed, trigger = parse_schedule({"cron": cron})
    assert parsed.timezone == "UTC"
    assert trigger.get_next_fire_time(None, datetime(2026, 10, 28, tzinfo=UTC)) is not None


@pytest.mark.parametrize("config,code", [
    ({}, "INVALID_SCHEDULE_CONFIG"),
    ({"cron": 12}, "INVALID_SCHEDULE_CONFIG"),
    ({"cron": "* * * * *", "unexpected": 2}, "INVALID_SCHEDULE_CONFIG"),
    ({"cron": "* * * *"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "* * * * * *"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "60 * * * *"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "* 24 * * *"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "*/0 * * * *"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "* * * * 7"}, "INVALID_SCHEDULE_CRON"),
    ({"cron": "* * * * *", "timezone": "Invalid/Nowhere"}, "INVALID_SCHEDULE_TIMEZONE"),
    ({"cron": "* * * * *", "timezone": "../UTC"}, "INVALID_SCHEDULE_TIMEZONE"),
    ({"cron": "* * * * *", "timezone": "/etc/passwd"}, "INVALID_SCHEDULE_TIMEZONE"),
])
def test_invalid_config_is_safe(config, code):
    with pytest.raises(NodeExecutionError) as error:
        parse_schedule(config)
    assert error.value.code == code
    assert str(config) not in error.value.public_message


def test_weekday_numbers_follow_apscheduler_monday_zero():
    now = datetime(2026, 10, 25, 10, tzinfo=UTC)  # Sunday
    _, monday = parse_schedule({"cron": "0 9 * * 0"})
    _, tuesday = parse_schedule({"cron": "0 9 * * 1"})
    _, named = parse_schedule({"cron": "0 9 * * mon"})
    assert monday.get_next_fire_time(None, now) == datetime(2026, 10, 26, 9, tzinfo=UTC)
    assert tuesday.get_next_fire_time(None, now) == datetime(2026, 10, 27, 9, tzinfo=UTC)
    assert named.get_next_fire_time(None, now) == monday.get_next_fire_time(None, now)


@pytest.mark.parametrize("timezone,expected_utc_hour", [("UTC", 9), ("Asia/Singapore", 1), ("Asia/Tokyo", 0)])
def test_iana_timezones(timezone, expected_utc_hour):
    _, trigger = parse_schedule({"cron": "0 9 * * *", "timezone": timezone})
    value = trigger.get_next_fire_time(None, datetime(2026, 10, 28, tzinfo=UTC))
    assert value.astimezone(UTC).hour == expected_utc_hour
    assert value.tzinfo is not None


def test_dst_fall_back_repeats_wall_time_with_distinct_utc_instants():
    _, trigger = parse_schedule({"cron": "30 1 * * *", "timezone": "America/New_York"})
    now = datetime(2026, 11, 1, 4, tzinfo=UTC)
    first = trigger.get_next_fire_time(None, now)
    second = trigger.get_next_fire_time(first, first)
    assert first.astimezone(UTC) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert second.astimezone(UTC) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def make_context(metadata):
    return NodeExecutionContext(
        execution_id=uuid4(), workflow_id=uuid4(), node_id="schedule",
        node_config={"cron": "*/5 * * * *"}, input_data={}, metadata=metadata,
    )


def test_schedule_trigger_output_uses_supplied_trigger_time_in_utc():
    output = ScheduleTriggerExecutor().execute(make_context({"scheduled_at": "2026-10-28T17:00:00+08:00"}))
    assert output == {"trigger": "schedule", "scheduled_at": "2026-10-28T09:00:00Z"}


@pytest.mark.parametrize("value", [None, "not-a-time", "2026-10-28T09:00:00", 42])
def test_schedule_trigger_rejects_missing_or_naive_time(value):
    with pytest.raises(NodeExecutionError, match="aware trigger time"):
        ScheduleTriggerExecutor().execute(make_context({"scheduled_at": value}))


def test_scheduler_settings_defaults_and_environment(monkeypatch):
    settings = Settings(_env_file=None)
    assert settings.scheduler_enabled is True
    assert settings.scheduler_workers == 4
    assert settings.store_execution_outputs is False
    assert settings.history_retention_days == 30
    assert settings.history_max_record_bytes == 262144
    monkeypatch.setenv("FLOWPILOT_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("FLOWPILOT_SCHEDULER_WORKERS", "2")
    monkeypatch.setenv("FLOWPILOT_STORE_EXECUTION_OUTPUTS", "true")
    assert Settings(_env_file=None).scheduler_enabled is False
    assert Settings(_env_file=None).scheduler_workers == 2
    assert Settings(_env_file=None).store_execution_outputs is True


@pytest.mark.parametrize("kwargs", [
    {"scheduler_workers": 0}, {"scheduler_workers": 33},
    {"history_retention_days": 0}, {"history_retention_days": 3651},
    {"history_max_record_bytes": 100}, {"history_max_record_bytes": 20_000_000},
])
def test_scheduler_settings_bounds(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)
