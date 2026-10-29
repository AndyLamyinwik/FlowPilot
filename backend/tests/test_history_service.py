import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.database import Database
from app.db.executions import ExecutionRepository
from app.db.workflows import WorkflowRepository
from app.models.execution import ExecutionRecord
from app.schemas.execution import ExecutionError, NodeExecutionResult, WorkflowExecutionResult
from app.schemas.history import ExecutionHistoryDetail, ExecutionSummary
from app.services.history import HistoryService, duration_ms


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "history.db")
    database.initialize()
    return database


@pytest.fixture
def workflow(database: Database):
    return WorkflowRepository(database).create(
        "History test", None, {"schema_version": 1, "nodes": [], "edges": []},
    )


def running(repository, workflow_id, *, started=None, trigger_type="manual"):
    started = started or datetime.now(UTC)
    execution_id = uuid4()
    repository.create_running(execution_id, workflow_id, trigger_type, started, "a" * 64)
    return execution_id, started


def completed(repository, workflow_id, *, started=None, status="success", finished=True):
    execution_id, started = running(repository, workflow_id, started=started)
    record = ExecutionRecord(
        execution_id, workflow_id, "manual", status, started,
        started + timedelta(milliseconds=1234) if finished else None,
        1234 if finished else None, [], None, started, "a" * 64,
    )
    repository.finish(record)
    return record


def result_for(repository, workflow_id, *, output=None, error=None, node_id="logger", count=1):
    execution_id, started = running(repository, workflow_id)
    finished = started + timedelta(milliseconds=1250)
    return WorkflowExecutionResult(
        execution_id=execution_id, workflow_id=workflow_id,
        status="failed" if error else "success", started_at=started, finished_at=finished,
        error=error,
        node_results=[NodeExecutionResult(
            node_id=node_id + str(index), status="failed" if error else "success",
            started_at=started + timedelta(milliseconds=250), finished_at=finished,
            output=output, error=error,
        ) for index in range(count)],
    )


def test_additive_initialization_preserves_workflows_and_database_version(database, workflow):
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 19")
    database.initialize()
    database.initialize()
    assert WorkflowRepository(database).get(workflow.id) == workflow
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 19
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"workflows", "workflow_schedules", "workflow_executions"}
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_database_cascade_removes_schedule_and_history(database, workflow):
    repository = ExecutionRepository(database)
    completed(repository, workflow.id)
    with database.connect() as connection:
        now = datetime.now(UTC).isoformat()
        connection.execute(
            "INSERT INTO workflow_schedules VALUES (?, 1, ?, ?, NULL)",
            (str(workflow.id), now, now),
        )
    assert WorkflowRepository(database).delete(workflow.id)
    assert repository.list_for_workflow(workflow.id) == ([], 0)
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM workflow_schedules").fetchone()[0] == 0


def test_repository_rejects_orphan_history(database):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        running(ExecutionRepository(database), uuid4())


def test_history_keeps_engine_id_times_and_node_duration(database, workflow):
    service = HistoryService(database)
    result = result_for(service.repository, workflow.id)
    record = service.finish(result, "manual", "a" * 64)
    saved = service.repository.get(result.execution_id)
    assert saved == record
    assert saved.execution_id == result.execution_id
    assert saved.started_at == result.started_at
    assert saved.finished_at == result.finished_at
    assert saved.duration_ms == 1250
    assert saved.node_results[0]["duration_ms"] == 1000
    detail = ExecutionHistoryDetail.model_validate(saved, from_attributes=True)
    assert detail.node_results[0].started_at.utcoffset() == timedelta(0)
    summary = ExecutionSummary.model_validate(saved, from_attributes=True)
    assert "node_results" not in summary.model_dump()


def test_default_history_does_not_persist_http_payload_or_sensitive_errors(database, workflow):
    service = HistoryService(database)
    secret = "sensitive-http-body-marker"
    error = ExecutionError(code="HTTP_STATUS_ERROR", message=secret, node_id="logger")
    result = result_for(service.repository, workflow.id,
                        output={"body": secret, "Authorization": secret, "Cookie": secret}, error=error)
    service.finish(result, "manual", "c" * 64)
    saved = service.repository.get(result.execution_id)
    assert saved.status == "failed"
    assert saved.error["code"] == "HTTP_STATUS_ERROR"
    assert saved.error["message"] == "Workflow execution failed"
    assert saved.node_results[0]["output"] is None
    assert saved.outputs_stored is False
    with database.connect() as connection:
        raw = str(tuple(connection.execute(
            "SELECT * FROM workflow_executions WHERE id = ?", (str(result.execution_id),)
        ).fetchone()))
    assert secret not in raw
    # Persistence policy must not mutate the compatible live Execute API response.
    assert result.node_results[0].output["body"] == secret
    assert result.error.message == secret


def test_optin_outputs_are_recursively_redacted_without_mutating_response(database, workflow):
    service = HistoryService(database, store_outputs=True)
    output = {"public": "keep", "nested": [{
        "Authorization": "bearer-secret", "Set-Cookie": "cookie-secret",
        "api_key": "key-secret", "password": "password-secret", "token": "token-secret",
        "safe": 42,
    }]}
    result = result_for(service.repository, workflow.id, output=output)
    saved = service.finish(result, "manual", "d" * 64)
    persisted = saved.node_results[0]["output"]
    assert persisted["public"] == "keep"
    assert persisted["nested"][0]["safe"] == 42
    assert all(persisted["nested"][0][key] == "[REDACTED]"
               for key in ("Authorization", "Set-Cookie", "api_key", "password", "token"))
    assert result.node_results[0].output == output


def test_history_record_cap_drops_oversized_output(database, workflow):
    service = HistoryService(database, store_outputs=True, history_max_bytes=4096)
    result = result_for(service.repository, workflow.id, output={"body": "x" * 20_000})
    saved = service.finish(result, "manual", "e" * 64)
    assert saved.node_results[0]["output"] is None
    assert saved.history_truncated and not saved.outputs_stored
    assert len(json.dumps(asdict(saved), default=str).encode()) <= 4096
    assert len(result.node_results[0].output["body"]) == 20_000


def test_history_record_cap_also_bounds_metadata_for_many_long_ids(database, workflow):
    service = HistoryService(database, history_max_bytes=4096)
    result = result_for(service.repository, workflow.id, node_id="測" * 20_000, count=20)
    saved = service.finish(result, "manual", "f" * 64)
    encoded = json.dumps(asdict(saved), ensure_ascii=False, separators=(",", ":"), default=str).encode()
    assert len(encoded) <= 4096
    assert saved.history_truncated
    assert len(saved.node_results) < len(result.node_results)
    assert saved.status == "success" and saved.duration_ms == 1250


def test_history_preserves_distinct_long_node_ids_and_error_references(database, workflow):
    service = HistoryService(database)
    prefix = "node_" + "x" * 260
    error = ExecutionError(code="NODE_EXECUTION_FAILED", message="safe", node_id=prefix + "1")
    result = result_for(service.repository, workflow.id, node_id=prefix, count=2, error=error)

    saved = service.finish(result, "manual", "a" * 64)

    assert [node["node_id"] for node in saved.node_results] == [prefix + "0", prefix + "1"]
    assert saved.error["node_id"] == prefix + "1"
    assert all(node["error"]["node_id"] == prefix + "1" for node in saved.node_results)
    assert not saved.history_truncated
    assert service.repository.get(result.execution_id) == saved


def test_history_omits_oversized_error_reference_without_exceeding_record_cap(database, workflow):
    service = HistoryService(database, history_max_bytes=4096)
    node_id = "測" * 20_000
    error = ExecutionError(code="NODE_EXECUTION_FAILED", message="safe", node_id=node_id)
    result = result_for(service.repository, workflow.id, node_id=node_id, error=error)

    saved = service.finish(result, "manual", "a" * 64)

    encoded = json.dumps(asdict(saved), ensure_ascii=False, separators=(",", ":"), default=str).encode()
    assert len(encoded) <= 4096
    assert saved.error["node_id"] is None
    assert saved.error["code"] == "NODE_EXECUTION_FAILED"
    assert saved.node_results == []
    assert saved.history_truncated and saved.status == "failed"
    assert result.error.node_id == node_id


def test_invalid_history_error_code_is_replaced(database, workflow):
    service = HistoryService(database)
    result = result_for(service.repository, workflow.id,
                        error=ExecutionError(code="secret\ntraceback", message="never store this"))
    saved = service.finish(result, "manual", "a" * 64)
    assert saved.error["code"] == "EXECUTION_FAILED"
    assert saved.node_results[0]["error"]["code"] == "EXECUTION_FAILED"


def test_history_survives_new_database_and_service_instances(database, workflow):
    first = HistoryService(database)
    execution_id, started = running(first.repository, workflow.id, trigger_type="schedule")
    result = WorkflowExecutionResult(
        execution_id=execution_id, workflow_id=workflow.id,
        status="success", started_at=started, finished_at=started + timedelta(seconds=1),
    )
    first.finish(result, "schedule", "a" * 64)
    restarted_db = Database(database.path)
    restarted_db.initialize()
    second = HistoryService(restarted_db)
    saved = second.repository.get(result.execution_id)
    assert saved.trigger_type == "schedule" and saved.status == "success"


def test_history_pagination_filter_order_and_workflow_isolation(database, workflow):
    repository = ExecutionRepository(database)
    now = datetime.now(UTC)
    records = [completed(repository, workflow.id, started=now + timedelta(seconds=index),
                         status="failed" if index == 2 else "success") for index in range(5)]
    other = WorkflowRepository(database).create("Other", None, {})
    completed(repository, other.id, started=now + timedelta(days=1))
    page, total = repository.list_for_workflow(workflow.id, limit=2, offset=1)
    assert total == 5
    assert [item.execution_id for item in page] == [records[3].execution_id, records[2].execution_id]
    filtered, total = repository.list_for_workflow(workflow.id, status="failed")
    assert total == 1 and filtered[0].execution_id == records[2].execution_id
    assert repository.list_for_workflow(workflow.id, offset=100) == ([], 5)
    assert repository.get(uuid4()) is None


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (20, -1)])
def test_history_repository_limits_pagination(database, workflow, limit, offset):
    with pytest.raises(ValueError):
        ExecutionRepository(database).list_for_workflow(workflow.id, limit=limit, offset=offset)


def test_startup_recovery_only_interrupts_running_and_never_reexecutes(database, workflow):
    history = HistoryService(database)
    now = datetime.now(UTC)
    stale_id, _ = running(history.repository, workflow.id, started=now - timedelta(minutes=10))
    succeeded = completed(history.repository, workflow.id, started=now - timedelta(minutes=20))
    failed = completed(history.repository, workflow.id, status="failed")
    assert history.recover_interrupted(now=now) == 1
    interrupted = history.repository.get(stale_id)
    assert interrupted.status == "interrupted"
    assert interrupted.finished_at == now and interrupted.duration_ms == 600_000
    assert interrupted.error["message"] == "Execution interrupted by application restart."
    assert history.repository.get(succeeded.execution_id).status == "success"
    assert history.repository.get(failed.execution_id).status == "failed"
    assert history.recover_interrupted(now=now) == 0


def test_retention_deletes_only_old_terminal_finished_records(database, workflow):
    history = HistoryService(database, retention_days=30)
    now = datetime.now(UTC)
    old = now - timedelta(days=40)
    expired = completed(history.repository, workflow.id, started=old)
    recent = completed(history.repository, workflow.id, started=now - timedelta(days=1))
    active_id, _ = running(history.repository, workflow.id, started=old)
    unfinished = completed(history.repository, workflow.id, started=old, finished=False, status="failed")
    assert history.cleanup(now=now) == 1
    assert history.repository.get(expired.execution_id) is None
    assert history.repository.get(recent.execution_id) is not None
    assert history.repository.get(active_id).status == "running"
    assert history.repository.get(unfinished.execution_id).finished_at is None


def test_retention_uses_small_bounded_batches(database, workflow):
    history = HistoryService(database)
    now = datetime.now(UTC)
    old = now - timedelta(days=40)
    # Seed in one transaction; this tests the cap rather than 501 separate commits.
    with database.connect() as connection:
        connection.executemany(
            """INSERT INTO workflow_executions
                (id,workflow_id,trigger_type,status,started_at,finished_at,created_at,definition_hash)
                VALUES (?,?,'manual','success',?,?,?,'')""",
            [(str(uuid4()), str(workflow.id), old.isoformat(), old.isoformat(), old.isoformat())
             for _ in range(501)],
        )
    assert history.cleanup(now=now) == 500
    assert history.cleanup(now=now) == 1


def test_repository_normalizes_offsets_and_rejects_naive_times(database, workflow):
    repository = ExecutionRepository(database)
    offset_time = datetime(2026, 10, 28, 9, tzinfo=timezone(timedelta(hours=8)))
    execution_id, _ = running(repository, workflow.id, started=offset_time)
    assert repository.get(execution_id).started_at == datetime(2026, 10, 28, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        running(repository, workflow.id, started=datetime(2026, 10, 28))


@pytest.mark.parametrize("start,end,expected", [
    (None, None, None),
    (datetime(2026, 1, 1, tzinfo=UTC), None, None),
    (datetime(2026, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC), 0),
])
def test_duration_missing_or_clock_reversed(start, end, expected):
    assert duration_ms(start, end) == expected
