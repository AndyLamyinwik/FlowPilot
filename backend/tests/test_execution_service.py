import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from app.db.database import Database
from app.db.workflows import WorkflowRepository
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import (
    ExecutorRegistry, LoggerExecutor, ManualTriggerExecutor, NodeExecutionError,
)
from app.services.execution.validation import ExecutionValidationError
from app.services.execution_service import (
    ExecutionConflict, ExecutionService, ExecutionServiceError,
    ExecutionStorageError, WorkflowNotFound,
)


def definition(*, trigger="manual", marker="before"):
    return {"schema_version": 1, "nodes": [
        {"id": "start", "type": f"trigger.{trigger}", "name": "Start",
         "position": {"x": 0, "y": 0},
         "config": {} if trigger == "manual" else {"cron": "*/5 * * * *", "timezone": "UTC"}},
        {"id": "logger", "type": "utility.logger", "name": "Log",
         "position": {"x": 100, "y": 0}, "config": {"marker": marker}},
    ], "edges": [{"id": "edge", "source": "start", "target": "logger"}]}


@pytest.fixture
def database(tmp_path: Path):
    db = Database(tmp_path / "execution.db")
    db.initialize()
    return db


@pytest.fixture
def workflow(database):
    return WorkflowRepository(database).create("Manual", None, definition())


def with_logger(logger) -> ExecutionEngine:
    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("utility.logger", logger)
    return ExecutionEngine(registry)


class BlockingLogger:
    def __init__(self):
        self.entered = Event()
        self.release = Event()
        self.configs = []

    def execute(self, context):
        self.configs.append(context.node_config)
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Test did not release executor")
        return {"recorded": context.node_config["marker"]}


def test_manual_execution_creates_same_id_history(database, workflow):
    service = ExecutionService(database, ExecutionEngine)
    result = service.execute(workflow.id)
    saved = service.history.repository.get(result.execution_id)
    assert saved.status == result.status == "success"
    assert saved.workflow_id == workflow.id and saved.trigger_type == "manual"
    assert len(saved.definition_hash) == 64
    assert saved.node_results[0]["output"] is None
    assert result.node_results[0].output == {"trigger": "manual"}
    assert all(item["duration_ms"] is not None for item in saved.node_results)


def test_running_history_is_committed_before_node_execution_and_no_db_lock_held(database, workflow):
    observed = []
    class InspectLogger:
        def execute(self, context):
            with database.connect() as connection:
                row = connection.execute(
                    "SELECT status FROM workflow_executions WHERE id = ?", (str(context.execution_id),)
                ).fetchone()
                assert row["status"] == "running"
                # A separate connection can write during execution.
                connection.execute("UPDATE workflows SET name='Updated during run' WHERE id=?", (str(workflow.id),))
            observed.append(context.execution_id)
            return {}
    service = ExecutionService(database, lambda: with_logger(InspectLogger()))
    result = service.execute(workflow.id)
    assert observed == [result.execution_id]
    assert WorkflowRepository(database).get(workflow.id).name == "Updated during run"


def test_preflight_failure_has_no_history_and_releases_guard(database, workflow):
    service = ExecutionService(database, ExecutionEngine)
    repository = WorkflowRepository(database)
    repository.update(workflow.id, "Draft", None, {"schema_version": 1, "nodes": [], "edges": []})
    with pytest.raises(ExecutionValidationError):
        service.execute(workflow.id)
    assert service.history.repository.list_for_workflow(workflow.id) == ([], 0)
    repository.update(workflow.id, "Valid", None, definition())
    assert service.execute(workflow.id).status == "success"


def test_missing_workflow_returns_controlled_exception(database):
    service = ExecutionService(database, ExecutionEngine)
    with pytest.raises(WorkflowNotFound, match="Workflow not found"):
        service.execute(uuid4())


def test_node_failure_is_stored_and_guard_released(database, workflow):
    class Fail:
        def execute(self, context):
            raise NodeExecutionError("TEST_FAILURE", "private-error-marker")
    service = ExecutionService(database, lambda: with_logger(Fail()))
    result = service.execute(workflow.id)
    assert result.status == "failed"
    saved = service.history.repository.get(result.execution_id)
    assert [node["status"] for node in saved.node_results] == ["success", "failed"]
    assert "private-error-marker" not in json.dumps(saved.error)
    assert service.execute(workflow.id, engine=ExecutionEngine()).status == "success"


def test_same_workflow_excludes_manual_and_delete_but_different_workflows_run(database, workflow):
    blocking = BlockingLogger()
    service = ExecutionService(database, lambda: with_logger(blocking))
    other = WorkflowRepository(database).create("Other", None, definition())
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(service.execute, workflow.id)
        try:
            assert blocking.entered.wait(2)
            with pytest.raises(ExecutionConflict):
                service.execute(workflow.id)
            with pytest.raises(ExecutionConflict):
                with service.exclusive(workflow.id):
                    pytest.fail("Delete acquired active execution guard")
            assert service.execute(other.id, engine=ExecutionEngine()).status == "success"
            # Neither conflicts nor the other workflow alter the active record.
            active, total = service.history.repository.list_for_workflow(workflow.id)
            assert total == 1 and active[0].status == "running"
        finally:
            blocking.release.set()
        assert future.result(timeout=2).status == "success"
    assert service.execute(workflow.id).status == "success"


def test_schedule_overlap_is_skipped_and_recorded_without_running_second_engine(database, workflow):
    blocking = BlockingLogger()
    service = ExecutionService(database, lambda: with_logger(blocking))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, workflow.id)
        try:
            assert blocking.entered.wait(2)
            assert service.execute(workflow.id, trigger_type="schedule", scheduled_at=datetime.now(UTC)) is None
            skipped, total = service.history.repository.list_for_workflow(workflow.id, status="skipped")
            assert total == 1
            assert skipped[0].trigger_type == "schedule"
            assert skipped[0].error["code"] == "WORKFLOW_ALREADY_RUNNING"
            assert len(blocking.configs) == 1
        finally:
            blocking.release.set()
        assert future.result(timeout=2).status == "success"


def test_disabled_schedule_callback_is_noop_without_history(database, workflow):
    def unexpected_factory():
        pytest.fail("Disabled schedule created an engine")
    service = ExecutionService(database, unexpected_factory)
    assert service.execute(workflow.id, trigger_type="schedule", run_if=lambda: False) is None
    assert service.history.repository.list_for_workflow(workflow.id) == ([], 0)


def test_execution_uses_snapshot_while_workflow_updates(database, workflow):
    blocking = BlockingLogger()
    service = ExecutionService(database, lambda: with_logger(blocking), store_outputs=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, workflow.id)
        try:
            assert blocking.entered.wait(2)
            WorkflowRepository(database).update(workflow.id, "Changed", None, definition(marker="after"))
        finally:
            blocking.release.set()
        first = future.result(timeout=2)
    assert first.node_results[-1].output == {"recorded": "before"}
    second = service.execute(workflow.id)
    assert second.node_results[-1].output == {"recorded": "after"}
    assert service.history.repository.get(first.execution_id).definition_hash != service.history.repository.get(second.execution_id).definition_hash


def test_history_insert_failure_prevents_effects_and_releases_guard(database, workflow, monkeypatch):
    calls = []
    class Effect:
        def execute(self, context):
            calls.append(context.node_id)
            return {}
    service = ExecutionService(database, lambda: with_logger(Effect()))
    original = service.history.repository.create_running
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("secret-error-marker")
    monkeypatch.setattr(service.history.repository, "create_running", fail)
    with pytest.raises(ExecutionStorageError) as error:
        service.execute(workflow.id)
    assert "secret" not in str(error.value) and calls == []
    monkeypatch.setattr(service.history.repository, "create_running", original)
    assert service.execute(workflow.id).status == "success"


def test_finalization_failure_is_observable_not_retried_and_recovered(database, workflow, monkeypatch):
    calls = []
    class Effect:
        def execute(self, context):
            calls.append(context.execution_id)
            return {}
    service = ExecutionService(database, lambda: with_logger(Effect()))
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("secret-marker")
    monkeypatch.setattr(service.history.repository, "finish", fail)
    with pytest.raises(ExecutionStorageError):
        service.execute(workflow.id)
    assert len(calls) == 1
    assert service.history.repository.get(calls[0]).status == "running"
    # A new startup can mark interrupted, but never retries side effects.
    assert service.history.recover_interrupted() == 1
    assert service.history.repository.get(calls[0]).status == "interrupted"
    assert len(calls) == 1


def test_unexpected_engine_failure_is_safe_and_terminal(database, workflow):
    class BrokenEngine(ExecutionEngine):
        def execute(self, *args, **kwargs):
            raise RuntimeError("private traceback and credential-marker")
    service = ExecutionService(database, BrokenEngine)
    with pytest.raises(ExecutionServiceError) as error:
        service.execute(workflow.id)
    assert "credential-marker" not in str(error.value)
    records, total = service.history.repository.list_for_workflow(workflow.id)
    assert total == 1 and records[0].status == "failed"
    assert "credential-marker" not in json.dumps(records[0].error)
    assert service.execute(workflow.id, engine=ExecutionEngine()).status == "success"


def test_base_exception_records_interrupted_and_releases_guard(database, workflow):
    class InterruptedEngine(ExecutionEngine):
        def execute(self, *args, **kwargs):
            raise KeyboardInterrupt()
    service = ExecutionService(database, InterruptedEngine)
    with pytest.raises(KeyboardInterrupt):
        service.execute(workflow.id)
    records, _ = service.history.repository.list_for_workflow(workflow.id)
    assert records[0].status == "interrupted"
    assert service.execute(workflow.id, engine=ExecutionEngine()).status == "success"
