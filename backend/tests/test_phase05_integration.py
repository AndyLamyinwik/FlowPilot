"""API-level scheduler/history checks with isolated SQLite and no external I/O."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event
from uuid import UUID, uuid4

import pytest
import httpx2
from fastapi.testclient import TestClient

from app.api.executions import get_engine
from app.core.config import Settings
from app.core.http_policy import HTTPPolicy
from app.main import create_app
from app.schemas.workflow import WorkflowDefinition
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import (
    ExecutorRegistry,
    ManualTriggerExecutor,
    NodeExecutionError,
    create_default_executor_registry,
)
from app.services.execution.safe_http import SafeHttpClient
from app.services.execution.validation import ExecutionValidationError


def node(identifier: str, kind: str = "utility.logger", config: dict | None = None) -> dict:
    return {
        "id": identifier,
        "name": identifier,
        "type": kind,
        "position": {"x": 0, "y": 0},
        "config": {} if config is None else config,
    }


def workflow(*, scheduled: bool = False, cron: str = "0 0 1 1 *") -> dict:
    start = node(
        "start", "trigger.schedule", {"cron": cron, "timezone": "UTC"}
    ) if scheduled else node("start", "trigger.manual")
    return {
        "name": "Isolated API integration",
        "definition": {
            "schema_version": 1,
            "nodes": [start, node("log")],
            "edges": [{"id": "start-log", "source": "start", "target": "log"}],
        },
    }


def save(client: TestClient, payload: dict | None = None) -> dict:
    response = client.post("/api/workflows", json=workflow() if payload is None else payload)
    assert response.status_code == 201, response.text
    return response.json()


def history(client: TestClient, workflow_id: str, **parameters) -> dict:
    response = client.get(f"/api/workflows/{workflow_id}/executions", params=parameters)
    assert response.status_code == 200, response.text
    return response.json()


def detail(client: TestClient, execution_id: str) -> dict:
    response = client.get(f"/api/executions/{execution_id}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def quiet_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"scheduler_enabled": False})


@pytest.fixture
def client(quiet_settings: Settings):
    with TestClient(create_app(quiet_settings)) as connection:
        yield connection


def test_manual_api_persists_matching_id_and_safe_node_metadata(client: TestClient) -> None:
    saved = save(client)
    response = client.post(f"/api/workflows/{saved['id']}/execute")
    assert response.status_code == 200
    live = response.json()
    assert live["status"] == "success"
    assert live["node_results"][1]["output"] == {"start": {"trigger": "manual"}}
    page = history(client, saved["id"])
    assert (page["total"], page["limit"], page["offset"]) == (1, 20, 0)
    recorded = detail(client, live["execution_id"])
    for name in ("execution_id", "workflow_id", "status", "started_at", "finished_at"):
        assert recorded[name] == live[name]
    assert recorded["trigger_type"] == "manual"
    assert recorded["outputs_stored"] is False
    assert len(recorded["definition_hash"]) == 64
    assert recorded["duration_ms"] >= 0
    assert [item["node_id"] for item in recorded["node_results"]] == ["start", "log"]
    for item in recorded["node_results"]:
        assert item["output"] is None
        assert item["error"] is None
        assert item["duration_ms"] >= 0
        assert datetime.fromisoformat(item["started_at"]).tzinfo == UTC
        assert datetime.fromisoformat(item["finished_at"]).tzinfo == UTC
    assert client.get(f"/api/workflows/{saved['id']}").json() == saved


def test_preflight_rejection_creates_no_running_or_completed_history(client: TestClient) -> None:
    saved = save(client, {"name": "Empty Draft"})
    assert client.post(f"/api/workflows/{saved['id']}/execute").status_code == 422
    assert history(client, saved["id"])["total"] == 0


def test_history_survives_restart_and_does_not_rerun_workflow(quiet_settings: Settings) -> None:
    with TestClient(create_app(quiet_settings)) as first:
        saved = save(first)
        live = first.post(f"/api/workflows/{saved['id']}/execute").json()
        recorded = detail(first, live["execution_id"])
    with TestClient(create_app(quiet_settings)) as restarted:
        assert detail(restarted, live["execution_id"]) == recorded
        assert history(restarted, saved["id"])["total"] == 1


def test_history_pagination_filter_and_workflow_isolation(client: TestClient) -> None:
    first, second = save(client), save(client)
    ids = []
    for _ in range(3):
        live = client.post(f"/api/workflows/{first['id']}/execute").json()
        ids.append(live["execution_id"])
    client.post(f"/api/workflows/{second['id']}/execute")
    failing = deepcopy(first)
    failing["definition"]["nodes"][1] = node(
        "log", "data.transform", {"mapping": {"value": {"source_node_id": "start", "path": "missing"}}}
    )
    assert client.put(
        f"/api/workflows/{first['id']}",
        json={"name": failing["name"], "definition": failing["definition"]},
    ).status_code == 200
    failed = client.post(f"/api/workflows/{first['id']}/execute")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    page = history(client, first["id"], limit=2, offset=1)
    assert (page["total"], page["limit"], page["offset"]) == (4, 2, 1)
    assert [item["execution_id"] for item in page["items"]] == [ids[2], ids[1]]
    assert all(item["workflow_id"] == first["id"] for item in page["items"])
    assert history(client, second["id"])["total"] == 1
    failures = history(client, first["id"], status="failed")
    assert failures["total"] == 1
    assert failures["items"][0]["execution_id"] == failed.json()["execution_id"]
    assert history(client, first["id"], status="success")["total"] == 3
    assert history(client, first["id"], offset=100)["items"] == []


@pytest.mark.parametrize("parameters", [
    {"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "not-a-status"},
])
def test_history_rejects_invalid_query_values(client: TestClient, parameters: dict) -> None:
    saved = save(client)
    response = client.get(f"/api/workflows/{saved['id']}/executions", params=parameters)
    assert response.status_code == 422


@pytest.mark.parametrize("path", [
    "/api/executions/{id}", "/api/workflows/{id}/executions", "/api/workflows/{id}/schedule",
])
def test_history_and_schedule_missing_ids_return_404(client: TestClient, path: str) -> None:
    assert client.get(path.format(id=uuid4())).status_code == 404


def test_disabled_scheduler_allows_persistent_enable_and_idempotent_disable(client: TestClient) -> None:
    saved = save(client, workflow(scheduled=True))
    path = f"/api/workflows/{saved['id']}/schedule"
    initial = client.get(path).json()
    assert initial["enabled"] is False
    assert initial["cron"] == "0 0 1 1 *"
    enabled = client.put(path, json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["scheduler_running"] is False
    assert enabled.json()["next_run_at"] is None
    assert client.app.state.scheduler.scheduler.running is False
    client.app.state.scheduler.run_workflow(UUID(saved["id"]))
    assert history(client, saved["id"])["total"] == 0
    for _ in range(2):
        disabled = client.put(path, json={"enabled": False})
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        assert disabled.json()["next_run_at"] is None


@pytest.mark.parametrize("config", [
    {"cron": "not cron", "timezone": "UTC"},
    {"cron": "60 * * * *", "timezone": "UTC"},
    {"cron": "* * * * * *", "timezone": "UTC"},
    {"cron": "0 9 * * *", "timezone": "Invalid/Nowhere"},
    {},
])
def test_invalid_schedule_config_still_saves_draft_but_cannot_enable(
    client: TestClient, config: dict,
) -> None:
    payload = workflow(scheduled=True)
    payload["definition"]["nodes"][0]["config"] = config
    saved = save(client, payload)
    path = f"/api/workflows/{saved['id']}/schedule"
    assert client.put(path, json={"enabled": True}).status_code == 422
    assert client.get(path).json()["enabled"] is False
    assert history(client, saved["id"])["total"] == 0


def test_manual_execute_does_not_run_schedule_workflow(client: TestClient) -> None:
    saved = save(client, workflow(scheduled=True))
    response = client.post(f"/api/workflows/{saved['id']}/execute")
    assert response.status_code == 422
    assert history(client, saved["id"])["total"] == 0
    manual = save(client)
    assert client.put(f"/api/workflows/{manual['id']}/schedule", json={"enabled": True}).status_code == 422


def test_enabled_schedule_rejects_cycles_and_multiple_entry_points(client: TestClient) -> None:
    cyclic = workflow(scheduled=True)
    cyclic["definition"]["edges"].append({"id": "back", "source": "log", "target": "start"})
    mixed = workflow(scheduled=True)
    mixed["definition"]["nodes"].append(node("manual", "trigger.manual"))
    mixed["definition"]["edges"].append({"id": "mixed", "source": "manual", "target": "log"})
    for payload in (cyclic, mixed):
        saved = save(client, payload)
        assert client.put(f"/api/workflows/{saved['id']}/schedule", json={"enabled": True}).status_code == 422


def test_scheduler_restore_update_disable_and_deletion(settings: Settings) -> None:
    active_settings = settings.model_copy(update={"scheduler_enabled": True})
    application = create_app(active_settings)
    with TestClient(application) as first:
        enabled = save(first, workflow(scheduled=True))
        disabled = save(first, workflow(scheduled=True))
        path = f"/api/workflows/{enabled['id']}/schedule"
        response = first.put(path, json={"enabled": True})
        assert response.status_code == 200, response.text
        schedule = response.json()
        assert schedule["scheduler_running"] is True
        assert datetime.fromisoformat(schedule["next_run_at"]).tzinfo == UTC
        scheduler = first.app.state.scheduler
        job_id = f"workflow:{enabled['id']}"
        assert scheduler.scheduler.get_job(job_id) is not None
        scheduler.start()
        scheduler.reconcile()
        assert sum(job.id == job_id for job in scheduler.scheduler.get_jobs()) == 1
        changed = workflow(scheduled=True, cron="0 12 1 1 *")
        assert first.put(f"/api/workflows/{enabled['id']}", json=changed).status_code == 200
        assert first.get(path).json()["cron"] == "0 12 1 1 *"
        assert sum(job.id == job_id for job in scheduler.scheduler.get_jobs()) == 1
    assert application.state.scheduler.scheduler.running is False
    with TestClient(create_app(active_settings)) as restarted:
        scheduler = restarted.app.state.scheduler
        job_id = f"workflow:{enabled['id']}"
        assert scheduler.scheduler.get_job(job_id) is not None
        assert scheduler.scheduler.get_job(f"workflow:{disabled['id']}") is None
        assert restarted.delete(f"/api/workflows/{enabled['id']}").status_code == 204
        assert scheduler.scheduler.get_job(job_id) is None
        scheduler.reconcile()
        assert scheduler.scheduler.get_job(job_id) is None


def test_enabled_workflow_becomes_draft_and_cannot_continue_old_job(settings: Settings) -> None:
    active = settings.model_copy(update={"scheduler_enabled": True})
    with TestClient(create_app(active)) as client:
        saved = save(client, workflow(scheduled=True))
        path = f"/api/workflows/{saved['id']}/schedule"
        assert client.put(path, json={"enabled": True}).status_code == 200
        assert client.put(
            f"/api/workflows/{saved['id']}",
            json={"name": "Now a draft", "definition": {"schema_version": 1, "nodes": [], "edges": []}},
        ).status_code == 200
        disabled = client.get(path).json()
        assert disabled["enabled"] is False
        assert disabled["last_error"]
        assert disabled["next_run_at"] is None
        assert client.app.state.scheduler.scheduler.get_job(f"workflow:{saved['id']}") is None
        client.app.state.scheduler.run_workflow(UUID(saved["id"]))
        assert history(client, saved["id"])["total"] == 0


def test_scheduled_success_and_failure_use_same_history_flow(settings: Settings) -> None:
    active = settings.model_copy(update={"scheduler_enabled": True})
    with TestClient(create_app(active)) as client:
        for fail in (False, True):
            payload = workflow(scheduled=True)
            if fail:
                payload["definition"]["nodes"][1] = node(
                    "log", "data.transform",
                    {"mapping": {"value": {"source_node_id": "start", "path": "missing"}}},
                )
            saved = save(client, payload)
            assert client.put(f"/api/workflows/{saved['id']}/schedule", json={"enabled": True}).status_code == 200
            client.app.state.scheduler.run_workflow(UUID(saved["id"]))
            page = history(client, saved["id"])
            assert page["total"] == 1
            recorded = detail(client, page["items"][0]["execution_id"])
            assert recorded["trigger_type"] == "schedule"
            assert recorded["status"] == ("failed" if fail else "success")
            assert recorded["node_results"][0]["status"] == "success"
            assert recorded["node_results"][0]["output"] is None
            assert recorded["node_results"][1]["status"] == ("failed" if fail else "success")
            assert recorded["duration_ms"] >= 0


def test_delete_cascades_execution_history_and_schedule_metadata(client: TestClient) -> None:
    saved = save(client)
    live = client.post(f"/api/workflows/{saved['id']}/execute").json()
    assert client.put(f"/api/workflows/{saved['id']}/schedule", json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/workflows/{saved['id']}").status_code == 204
    assert client.get(f"/api/executions/{live['execution_id']}").status_code == 404
    with client.app.state.database.connect() as connection:
        for table in ("workflow_schedules", "workflow_executions"):
            assert connection.execute(f"SELECT count(*) FROM {table} WHERE workflow_id = ?", (saved["id"],)).fetchone()[0] == 0


def test_active_execution_rejects_duplicate_and_delete_but_other_workflow_runs(
    quiet_settings: Settings,
) -> None:
    entered, release = Event(), Event()

    class BlockingLogger:
        def execute(self, context):
            entered.set()
            assert release.wait(5), "Test must release the controlled executor"
            return context.input_data

    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("utility.logger", BlockingLogger())
    application = create_app(quiet_settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    with TestClient(application) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = save(client)
        other = save(client, {"name": "Independent manual", "definition": {
            "schema_version": 1, "nodes": [node("start", "trigger.manual")], "edges": [],
        }})
        future = pool.submit(client.post, f"/api/workflows/{first['id']}/execute")
        try:
            assert entered.wait(5)
            running = history(client, first["id"], status="running")
            assert running["total"] == 1
            assert running["items"][0]["finished_at"] is None
            assert client.post(f"/api/workflows/{first['id']}/execute").status_code == 409
            assert client.delete(f"/api/workflows/{first['id']}").status_code == 409
            assert client.post(f"/api/workflows/{other['id']}/execute").status_code == 200
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200
        assert history(client, first["id"])["total"] == 1
        assert client.delete(f"/api/workflows/{first['id']}").status_code == 204


def test_running_execution_uses_original_snapshot_during_workflow_update(
    quiet_settings: Settings,
) -> None:
    entered, release = Event(), Event()

    class BlockingLogger:
        def execute(self, context):
            entered.set()
            assert release.wait(5)
            return context.input_data

    from app.services.execution.data_nodes import TransformExecutor

    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("utility.logger", BlockingLogger())
    registry.register("data.transform", TransformExecutor())
    application = create_app(quiet_settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    payload = workflow()
    payload["definition"]["nodes"].append(node("transform", "data.transform", {"mapping": {"value": {"value": "original"}}}))
    payload["definition"]["edges"].append({"id": "last", "source": "log", "target": "transform"})
    with TestClient(application) as client, ThreadPoolExecutor(max_workers=1) as pool:
        saved = save(client, payload)
        future = pool.submit(client.post, f"/api/workflows/{saved['id']}/execute")
        try:
            assert entered.wait(5)
            changed = deepcopy(payload)
            changed["definition"]["nodes"][2]["config"]["mapping"]["value"]["value"] = "updated"
            assert client.put(f"/api/workflows/{saved['id']}", json=changed).status_code == 200
        finally:
            release.set()
        live = future.result(timeout=5).json()
        assert live["status"] == "success"
        assert live["node_results"][-1]["output"] == {"value": "original"}
        assert client.get(f"/api/workflows/{saved['id']}").json()["definition"] == WorkflowDefinition.model_validate(changed["definition"]).model_dump(mode="json")


def test_output_opt_in_redacts_recognizable_fields_but_preserves_live_response(
    quiet_settings: Settings,
) -> None:
    class OutputExecutor:
        def execute(self, context):
            return {"Authorization": "credential-marker", "nested": {"Cookie": "cookie-marker", "value": "safe"}}

    registry = ExecutorRegistry()
    registry.register("trigger.manual", OutputExecutor())
    opted_in = quiet_settings.model_copy(update={"store_execution_outputs": True})
    application = create_app(opted_in)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    with TestClient(application) as client:
        saved = save(client, {"name": "Output persistence", "definition": {
            "schema_version": 1, "nodes": [node("start", "trigger.manual")], "edges": [],
        }})
        response = client.post(f"/api/workflows/{saved['id']}/execute")
        assert response.status_code == 200
        assert "credential-marker" in response.text
        recorded_response = client.get(f"/api/executions/{response.json()['execution_id']}")
        assert recorded_response.status_code == 200
        assert "credential-marker" not in recorded_response.text
        assert "cookie-marker" not in recorded_response.text
        assert recorded_response.json()["outputs_stored"] is True
        assert recorded_response.json()["node_results"][0]["output"]["nested"]["value"] == "safe"


def test_failed_execution_releases_guard_and_history_error_has_safe_summary(
    quiet_settings: Settings,
) -> None:
    class FailingLogger:
        def execute(self, context):
            raise NodeExecutionError("TEST_NODE_FAILURE", "sensitive-error-marker")

    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("utility.logger", FailingLogger())
    application = create_app(quiet_settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    with TestClient(application) as client:
        saved = save(client)
        for _ in range(2):
            response = client.post(f"/api/workflows/{saved['id']}/execute")
            assert response.status_code == 200
            assert response.json()["status"] == "failed"
            recorded = client.get(f"/api/executions/{response.json()['execution_id']}")
            assert recorded.status_code == 200
            assert "sensitive-error-marker" not in recorded.text
            assert recorded.json()["status"] == "failed"
            assert recorded.json()["node_results"][0]["status"] == "success"
            assert recorded.json()["node_results"][1]["status"] == "failed"
        assert history(client, saved["id"], status="failed")["total"] == 2


def test_startup_recovers_only_running_history_without_reexecution(quiet_settings: Settings) -> None:
    interrupted_id = uuid4()
    with TestClient(create_app(quiet_settings)) as client:
        saved = save(client)
        successful = client.post(f"/api/workflows/{saved['id']}/execute").json()
        completed = detail(client, successful["execution_id"])
        client.app.state.execution_service.history.repository.create_running(
            interrupted_id, UUID(saved["id"]), "schedule",
            datetime.now(UTC) - timedelta(minutes=10), "0" * 64,
        )
    with TestClient(create_app(quiet_settings)) as restarted:
        interrupted = detail(restarted, str(interrupted_id))
        assert interrupted["status"] == "interrupted"
        assert interrupted["finished_at"] is not None
        assert interrupted["duration_ms"] >= 600_000
        assert interrupted["error"]["code"] == "EXECUTION_INTERRUPTED"
        assert detail(restarted, successful["execution_id"]) == completed
        assert history(restarted, saved["id"])["total"] == 2
        assert history(restarted, saved["id"], status="interrupted")["total"] == 1


def test_openapi_describes_schedule_history_and_manual_conflict(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "put"} <= paths["/api/workflows/{workflow_id}/schedule"].keys()
    assert "get" in paths["/api/workflows/{workflow_id}/executions"]
    assert "get" in paths["/api/executions/{execution_id}"]
    assert "409" in paths["/api/workflows/{workflow_id}/execute"]["post"]["responses"]
    assert client.get("/api/health").json() == {"status": "ok"}


def test_overlapping_application_owner_is_rejected_and_released(quiet_settings: Settings) -> None:
    with TestClient(create_app(quiet_settings)) as first:
        with pytest.raises(RuntimeError, match="one backend process"):
            with TestClient(create_app(quiet_settings)):
                pytest.fail("A second backend must not own the same database")
        assert first.get("/api/health").json() == {"status": "ok"}
    with TestClient(create_app(quiet_settings)) as restarted:
        assert restarted.get("/api/health").json() == {"status": "ok"}


def test_database_instance_lock_excludes_another_process(quiet_settings: Settings) -> None:
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from app.core.instance import InstanceLock\n"
        "owner = InstanceLock(Path(sys.argv[1]))\n"
        "try:\n"
        "    owner.acquire()\n"
        "except RuntimeError:\n"
        "    sys.exit(23)\n"
        "owner.release()\n"
    )

    def attempt() -> int:
        result = subprocess.run(
            [sys.executable, "-c", code, str(quiet_settings.database_path)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=10,
        )
        assert not result.stderr, result.stderr
        return result.returncode

    with TestClient(create_app(quiet_settings)):
        assert attempt() == 23
    assert attempt() == 0


@pytest.mark.parametrize("trigger_type,scheduled", [("manual", True), ("schedule", False)])
def test_engine_rejects_wrong_entry_mode(trigger_type: str, scheduled: bool) -> None:
    with pytest.raises(ExecutionValidationError) as rejected:
        ExecutionEngine().execute(
            uuid4(), workflow(scheduled=scheduled)["definition"], trigger_type=trigger_type,
        )
    assert "TRIGGER_TYPE_MISMATCH" in {error.code for error in rejected.value.errors}


def test_schedule_mode_preserves_execution_identity_and_utc_trigger_data() -> None:
    engine = ExecutionEngine()
    execution_id = uuid4()
    scheduled = datetime.fromisoformat("2026-10-28T09:00:00+08:00")
    started = datetime.now(UTC)
    result = engine.execute(
        uuid4(), workflow(scheduled=True)["definition"],
        trigger_type="schedule", execution_id=execution_id,
        started_at=started, scheduled_at=scheduled,
    )
    assert result.status == "success"
    assert result.execution_id == execution_id
    assert result.started_at == started
    expected = {"trigger": "schedule", "scheduled_at": "2026-10-28T01:00:00Z"}
    assert result.node_results[0].output == expected
    assert result.node_results[1].output == {"start": expected}


def test_history_start_write_failure_returns_safe_503_before_any_node_runs(
    quiet_settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class RecordingManual:
        def execute(self, context):
            calls.append(context.node_id)
            return {"trigger": "manual"}

    registry = ExecutorRegistry()
    registry.register("trigger.manual", RecordingManual())
    application = create_app(quiet_settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    with TestClient(application) as client:
        saved = save(client, {"name": "No effects without history", "definition": {
            "schema_version": 1, "nodes": [node("start", "trigger.manual")], "edges": [],
        }})
        repository = client.app.state.execution_service.history.repository
        original = repository.create_running

        def fail_write(*args, **kwargs):
            raise sqlite3.OperationalError("sensitive-db-failure-marker")

        monkeypatch.setattr(repository, "create_running", fail_write)
        failed = client.post(f"/api/workflows/{saved['id']}/execute")
        assert failed.status_code == 503
        assert "sensitive-db-failure-marker" not in failed.text
        assert calls == []
        monkeypatch.setattr(repository, "create_running", original)
        assert client.post(f"/api/workflows/{saved['id']}/execute").status_code == 200
        assert calls == ["start"]
        assert history(client, saved["id"])["total"] == 1


def test_history_final_write_failure_does_not_retry_effects_and_recovers_on_restart(
    quiet_settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class RecordingManual:
        def execute(self, context):
            calls.append(context.node_id)
            return {"trigger": "manual"}

    registry = ExecutorRegistry()
    registry.register("trigger.manual", RecordingManual())
    application = create_app(quiet_settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(registry=registry)
    with TestClient(application) as client:
        saved = save(client, {"name": "Do not retry unknown delivery", "definition": {
            "schema_version": 1, "nodes": [node("start", "trigger.manual")], "edges": [],
        }})
        repository = client.app.state.execution_service.history.repository

        def fail_finalization(*args, **kwargs):
            raise sqlite3.OperationalError("sensitive-finalize-marker")

        monkeypatch.setattr(repository, "finish", fail_finalization)
        response = client.post(f"/api/workflows/{saved['id']}/execute")
        assert response.status_code == 503
        assert "sensitive-finalize-marker" not in response.text
        assert calls == ["start"]
        running = history(client, saved["id"], status="running")
        assert running["total"] == 1
        execution_id = running["items"][0]["execution_id"]
    with TestClient(create_app(quiet_settings)) as restarted:
        assert detail(restarted, execution_id)["status"] == "interrupted"
        assert history(restarted, saved["id"])["total"] == 1
    assert calls == ["start"]


def load_example(filename: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "docs" / "examples" / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_documented_schedule_logger_can_enable_execute_and_store_history(settings: Settings) -> None:
    configured = settings.model_copy(update={"scheduler_enabled": True, "store_execution_outputs": True})
    with TestClient(create_app(configured)) as client:
        # Real cron calculations remain enabled; tests invoke only the controlled callback.
        service = client.app.state.scheduler
        service.scheduler.pause()
        service.clock = lambda: datetime(2026, 10, 28, 9, 5, tzinfo=UTC)
        saved = save(client, load_example("scheduled-logger.json"))
        path = f"/api/workflows/{saved['id']}/schedule"
        assert client.get(path).json()["enabled"] is False
        enabled = client.put(path, json={"enabled": True})
        assert enabled.status_code == 200
        assert enabled.json()["cron"] == "*/5 * * * *"
        assert enabled.json()["next_run_at"] is not None
        service.run_workflow(UUID(saved["id"]))
        page = history(client, saved["id"])
        assert page["total"] == 1
        recorded = detail(client, page["items"][0]["execution_id"])
        assert recorded["status"] == "success"
        assert recorded["trigger_type"] == "schedule"
        expected = {"trigger": "schedule", "scheduled_at": "2026-10-28T09:05:00Z"}
        assert recorded["node_results"][0]["output"] == expected
        assert recorded["node_results"][1]["output"] == {"schedule": expected}


@pytest.mark.parametrize("title_present", [True, False])
def test_documented_scheduled_http_condition_webhook_uses_safe_client(
    settings: Settings, title_present: bool,
) -> None:
    requests, notifications = [], []
    title = "FlowPilot scheduled example"

    def handler(request):
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "httpbin.org"
        assert request.extensions["sni_hostname"] == "httpbin.org"
        if request.method == "GET":
            assert request.url.path == "/json"
            return httpx2.Response(200, json={"slideshow": {"title": title} if title_present else {}})
        assert request.method == "POST"
        assert request.url.path == "/post"
        notifications.append(json.loads(request.content))
        return httpx2.Response(200, json={"delivered": True})

    client_http = SafeHttpClient(
        HTTPPolicy(allowed_hosts=("httpbin.org",)),
        transport=httpx2.MockTransport(handler),
        resolver=lambda host, port: ["93.184.216.34"],
    )
    mock_engine = ExecutionEngine(registry=create_default_executor_registry(client_http))
    configured = settings.model_copy(update={"scheduler_enabled": True})
    with TestClient(create_app(configured)) as client:
        scheduler = client.app.state.scheduler
        scheduler.scheduler.pause()
        client.app.state.execution_service.engine_factory = lambda: mock_engine
        saved = save(client, load_example("scheduled-automation.json"))
        enabled = client.put(f"/api/workflows/{saved['id']}/schedule", json={"enabled": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["timezone"] == "Asia/Singapore"
        scheduler.run_workflow(UUID(saved["id"]))
        page = history(client, saved["id"])
        assert page["total"] == 1
        recorded = detail(client, page["items"][0]["execution_id"])
        assert recorded["status"] == "success"
        assert recorded["trigger_type"] == "schedule"
        nodes = {item["node_id"]: item for item in recorded["node_results"]}
        assert [nodes[key]["status"] for key in ("schedule", "http_fetch", "has_title")] == ["success"] * 3
        assert nodes["notify"]["status"] == ("success" if title_present else "skipped")
        assert notifications == ([title] if title_present else [])
        assert len(requests) == (2 if title_present else 1)
        assert all(item["output"] is None for item in nodes.values())


def test_documented_scheduled_http_example_cannot_bypass_default_allowlist(client: TestClient) -> None:
    saved = save(client, load_example("scheduled-automation.json"))
    response = client.put(f"/api/workflows/{saved['id']}/schedule", json={"enabled": True})
    assert response.status_code == 422
    assert "HTTP_HOST_NOT_ALLOWED" in response.text
    assert history(client, saved["id"])["total"] == 0

