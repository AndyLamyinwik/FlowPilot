import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from threading import Event
from uuid import uuid4

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED

from app.db.database import Database
from app.db.schedules import ScheduleRepository
from app.db.workflows import WorkflowRepository
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import NodeExecutionError, create_default_executor_registry
from app.services.execution.validation import ExecutionValidationError
from app.services.execution_service import ExecutionService, WorkflowNotFound
from app.services.scheduler import SchedulerService


def definition(cron="0 9 * * mon"):
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "schedule", "type": "trigger.schedule", "name": "Schedule",
             "position": {"x": 0.0, "y": 0.0}, "config": {"cron": cron}},
            {"id": "logger", "type": "utility.logger", "name": "Log",
             "position": {"x": 1.0, "y": 0.0}, "config": {}},
        ],
        "edges": [{"id": "edge", "source": "schedule", "target": "logger"}],
    }


@pytest.fixture
def setup_scheduler(tmp_path):
    database = Database(tmp_path / "scheduler.db")
    database.initialize()
    executions = ExecutionService(database, ExecutionEngine)
    service = SchedulerService(database, executions)
    record = WorkflowRepository(database).create("scheduled", None, definition())
    service.start()
    try:
        yield database, executions, service, record.id
    finally:
        service.shutdown()


def history(executions, workflow_id):
    return executions.history.repository.list_for_workflow(workflow_id, limit=100, offset=0)


def test_start_shutdown_are_idempotent(setup_scheduler):
    _, _, service, _ = setup_scheduler
    scheduler = service.scheduler
    service.start()
    service.start()
    assert service.scheduler is scheduler
    assert scheduler.running
    assert {job.id for job in scheduler.get_jobs()} == {"history:cleanup", "schedules:reconcile"}
    service.shutdown()
    service.shutdown()
    assert not scheduler.running


def test_housekeeping_is_bounded_frequent_and_conservative(setup_scheduler):
    _, _, service, _ = setup_scheduler
    for job_id in ("history:cleanup", "schedules:reconcile"):
        job = service.scheduler.get_job(job_id)
        assert job.trigger.interval.total_seconds() == 60
        assert job.coalesce is True
        assert job.max_instances == 1
        assert job.misfire_grace_time == 60


def test_enable_preserves_single_source_and_no_duplicate_jobs(setup_scheduler):
    database, _, service, workflow_id = setup_scheduler
    for _ in range(3):
        status = service.set_enabled(workflow_id, True)
        service.reconcile()
    assert status.enabled and status.scheduler_running
    assert status.cron == "0 9 * * mon"
    assert status.timezone == "UTC"
    assert status.next_run_at.tzinfo is not None
    jobs = [job for job in service.scheduler.get_jobs() if job.id == f"workflow:{workflow_id}"]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.coalesce and job.max_instances == 1 and job.misfire_grace_time == 60
    with database.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflow_schedules)")}
    assert "cron" not in columns and "timezone" not in columns


def test_reconcile_does_not_reset_next_fire_for_unchanged_definition(setup_scheduler):
    _, _, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    job = service.scheduler.get_job(service.job_id(workflow_id))
    next_fire = job.next_run_time
    service.reconcile()
    assert service.scheduler.get_job(service.job_id(workflow_id)) is job
    assert job.next_run_time == next_fire


def test_disabled_schedule_cannot_run_and_disable_is_idempotent(setup_scheduler):
    _, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    service.set_enabled(workflow_id, False)
    service.set_enabled(workflow_id, False)
    service.run_workflow(workflow_id)
    state = service.get(workflow_id)
    assert not state.enabled and state.next_run_at is None
    assert service.scheduler.get_job(service.job_id(workflow_id)) is None
    assert history(executions, workflow_id)[1] == 0


def test_schedule_callback_runs_shared_engine_and_creates_history(setup_scheduler):
    _, executions, service, workflow_id = setup_scheduler
    service.clock = lambda: datetime(2026, 10, 28, 9, tzinfo=UTC)
    service.set_enabled(workflow_id, True)
    service.run_workflow(workflow_id)
    records, total = history(executions, workflow_id)
    assert total == 1
    record = records[0]
    assert record.trigger_type == "schedule" and record.status == "success"
    assert [node["status"] for node in record.node_results] == ["success", "success"]
    assert all(node["output"] is None for node in record.node_results)
    assert record.definition_hash


def test_apscheduler_dispatches_a_due_workflow_without_direct_callback(setup_scheduler, monkeypatch):
    _, executions, service, workflow_id = setup_scheduler
    finished = Event()
    original = executions.execute

    def record_completion(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(executions, "execute", record_completion)
    service.set_enabled(workflow_id, True)
    service.scheduler.modify_job(service.job_id(workflow_id), next_run_time=datetime.now(UTC))
    service.scheduler.wakeup()
    assert finished.wait(3), "APScheduler did not dispatch the due job"
    records, total = history(executions, workflow_id)
    assert total == 1 and records[0].status == "success"
    assert records[0].trigger_type == "schedule"


def test_schedule_failure_is_recorded_without_disabling_other_jobs(setup_scheduler):
    database, executions, service, workflow_id = setup_scheduler

    class Failure:
        def execute(self, context):
            raise NodeExecutionError("TEST_FAILURE", "Safe failure")

    registry = create_default_executor_registry()
    registry._executors["utility.logger"] = Failure()
    executions.engine_factory = lambda: ExecutionEngine(registry)
    other = WorkflowRepository(database).create("other", None, definition())
    service.set_enabled(workflow_id, True)
    service.set_enabled(other.id, True)
    service.run_workflow(workflow_id)
    records, total = history(executions, workflow_id)
    assert total == 1 and records[0].status == "failed"
    assert records[0].error["code"] == "TEST_FAILURE"
    assert service.scheduler.get_job(service.job_id(other.id)) is not None
    assert service.get(workflow_id).enabled


def test_overlapping_schedule_is_skipped_and_recorded(setup_scheduler):
    _, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    with executions.exclusive(workflow_id):
        service.run_workflow(workflow_id)
    records, total = history(executions, workflow_id)
    assert total == 1 and records[0].status == "skipped"
    assert records[0].error["code"] == "WORKFLOW_ALREADY_RUNNING"
    assert records[0].node_results == []


def test_restart_restores_only_enabled_jobs_without_duplicates(setup_scheduler):
    database, executions, service, workflow_id = setup_scheduler
    disabled = WorkflowRepository(database).create("disabled", None, definition())
    service.set_enabled(workflow_id, True)
    service.set_enabled(disabled.id, False)
    service.shutdown()
    restored = SchedulerService(database, executions)
    try:
        restored.start()
        restored.reconcile()
        assert restored.get(workflow_id).enabled
        assert restored.scheduler.get_job(restored.job_id(workflow_id)) is not None
        assert restored.scheduler.get_job(restored.job_id(disabled.id)) is None
        assert len(restored.scheduler.get_jobs()) == 3
        assert history(executions, workflow_id)[1] == 0
    finally:
        restored.shutdown()


def test_update_cron_replaces_job_and_draft_disables_it(setup_scheduler):
    database, _, service, workflow_id = setup_scheduler
    workflows = WorkflowRepository(database)
    service.set_enabled(workflow_id, True)
    with service.mutation():
        workflows.update(workflow_id, "new", None, definition("0 8 * * tue"))
        changed = service.workflow_updated(workflow_id)
    assert changed.enabled and changed.cron == "0 8 * * tue"
    assert len([job for job in service.scheduler.get_jobs() if job.id.startswith("workflow:")]) == 1
    with service.mutation():
        workflows.update(workflow_id, "draft", None, {"schema_version": 1, "nodes": [], "edges": []})
        changed = service.workflow_updated(workflow_id)
    assert not changed.enabled and changed.last_error == "SCHEDULE_INVALID_WORKFLOW"
    assert service.scheduler.get_job(service.job_id(workflow_id)) is None


def test_invalid_enabled_config_on_restart_is_disabled(setup_scheduler):
    database, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    service.shutdown()
    WorkflowRepository(database).update(workflow_id, "corrupt", None, definition("INVALID PRIVATE_MARKER"))
    restored = SchedulerService(database, executions)
    try:
        restored.start()
        state = restored.get(workflow_id)
        assert not state.enabled and state.last_error == "SCHEDULE_INVALID_WORKFLOW"
        assert state.next_run_at is None
    finally:
        restored.shutdown()


def test_delete_cascades_schedule_and_callback_cannot_restore_it(setup_scheduler):
    database, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    with executions.exclusive(workflow_id), service.mutation():
        WorkflowRepository(database).delete(workflow_id)
        service.workflow_deleted(workflow_id)
    service.run_workflow(workflow_id)
    service.reconcile()
    assert ScheduleRepository(database).get(workflow_id) is None
    assert service.scheduler.get_job(service.job_id(workflow_id)) is None
    assert workflow_id not in service._quarantined


def test_global_scheduler_disable_retains_metadata_without_jobs(setup_scheduler):
    database, executions, service, workflow_id = setup_scheduler
    service.shutdown()
    disabled = SchedulerService(database, executions, enabled=False)
    try:
        disabled.start()
        state = disabled.set_enabled(workflow_id, True)
        assert state.enabled and not state.scheduler_running and state.next_run_at is None
        assert disabled.scheduler.get_jobs() == []
        disabled.run_workflow(workflow_id)
        assert history(executions, workflow_id)[1] == 0
    finally:
        disabled.shutdown()


@pytest.mark.parametrize("bad", ["* * * *", "99 * * * *"])
def test_invalid_schedule_cannot_enable(setup_scheduler, bad):
    database, _, service, workflow_id = setup_scheduler
    WorkflowRepository(database).update(workflow_id, "draft", None, definition(bad))
    with pytest.raises(ExecutionValidationError):
        service.set_enabled(workflow_id, True)
    assert not service.get(workflow_id).enabled


def test_nonexistent_workflow_schedule_is_not_created(setup_scheduler):
    _, _, service, _ = setup_scheduler
    with pytest.raises(WorkflowNotFound):
        service.set_enabled(uuid4(), True)


def test_registration_failure_disables_durable_state_and_can_be_reenabled(setup_scheduler, monkeypatch):
    database, _, service, workflow_id = setup_scheduler
    original = service.scheduler.add_job

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_MARKER must not reach logs")

    monkeypatch.setattr(service.scheduler, "add_job", fail)
    result = service.set_enabled(workflow_id, True)
    assert not result.enabled and result.last_error == "SCHEDULE_SYNC_FAILED"
    assert not ScheduleRepository(database).get(workflow_id).enabled
    monkeypatch.setattr(service.scheduler, "add_job", original)
    assert service.set_enabled(workflow_id, True).enabled


@pytest.mark.parametrize("delete", [False, True])
def test_removal_failure_is_recoverable_and_stale_job_cannot_execute(setup_scheduler, monkeypatch, delete):
    database, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)
    original = service.scheduler.remove_job

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_MARKER")

    monkeypatch.setattr(service.scheduler, "remove_job", fail)
    if delete:
        WorkflowRepository(database).delete(workflow_id)
        service.workflow_deleted(workflow_id)
    else:
        result = service.set_enabled(workflow_id, False)
        assert not result.enabled and result.last_error == "SCHEDULE_SYNC_FAILED"
        assert result.next_run_at is None
    assert service.scheduler.get_job(service.job_id(workflow_id)) is not None
    service.run_workflow(workflow_id)
    assert history(executions, workflow_id)[1] == 0
    monkeypatch.setattr(service.scheduler, "remove_job", original)
    service.reconcile()
    assert service.scheduler.get_job(service.job_id(workflow_id)) is None
    assert workflow_id not in service._quarantined


def test_callback_errors_and_scheduler_events_do_not_log_sensitive_values(setup_scheduler, monkeypatch, caplog):
    _, executions, service, workflow_id = setup_scheduler
    service.set_enabled(workflow_id, True)

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_MARKER")

    monkeypatch.setattr(executions, "execute", fail)
    caplog.set_level(logging.WARNING, logger="flowpilot.scheduler")
    service.run_workflow(workflow_id)
    for code in (EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_MAX_INSTANCES):
        service._on_event(SimpleNamespace(
            code=code, job_id=service.job_id(workflow_id), exception=RuntimeError("PRIVATE_MARKER"),
            traceback="PRIVATE_MARKER",
        ))
    assert "PRIVATE_MARKER" not in caplog.text
    assert "job_error" in caplog.text and "misfire" in caplog.text and "max_instances" in caplog.text


def test_housekeeping_failure_does_not_raise_or_log_exception(setup_scheduler, monkeypatch, caplog):
    _, executions, service, _ = setup_scheduler

    def fail():
        raise RuntimeError("PRIVATE_MARKER")

    monkeypatch.setattr(executions.history, "cleanup", fail)
    caplog.set_level(logging.ERROR, logger="flowpilot.scheduler")
    service._cleanup()
    assert "History retention failed" in caplog.text and "PRIVATE_MARKER" not in caplog.text


@pytest.mark.parametrize("workers", [0, 33, True, 4.5])
def test_worker_pool_bounds(setup_scheduler, workers):
    database, executions, _, _ = setup_scheduler
    with pytest.raises(ValueError, match="worker count"):
        SchedulerService(database, executions, workers=workers)
