import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.executions import get_engine
from app.core.config import Settings
from app.main import create_app
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import (
    ExecutorRegistry,
    ManualTriggerExecutor,
    NodeExecutionError,
)


def node(node_id: str, node_type: str = "utility.logger") -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 0, "y": 100},
        "config": {},
    }


def linear_payload() -> dict:
    return {
        "name": "Manual logger chain",
        "definition": {
            "schema_version": 1,
            "nodes": [
                node("logger_b"),
                node("manual", "trigger.manual"),
                node("logger_a"),
            ],
            "edges": [
                {"id": "first", "source": "manual", "target": "logger_a"},
                {"id": "second", "source": "logger_a", "target": "logger_b"},
            ],
        },
    }


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def save(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/workflows", json=payload)
    assert response.status_code == 201
    return response.json()


def issue_codes(response) -> set[str]:
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "WORKFLOW_NOT_EXECUTABLE"
    return {issue["code"] for issue in detail["errors"]}


def test_execute_saved_workflow_returns_complete_results_and_utc_times(
    client: TestClient,
) -> None:
    workflow = save(client, linear_payload())
    response = client.post(f"/api/workflows/{workflow['id']}/execute")
    assert response.status_code == 200
    result = response.json()
    assert UUID(result["execution_id"]).version == 4
    assert result["workflow_id"] == workflow["id"]
    assert result["status"] == "success"
    assert result["error"] is None
    started = datetime.fromisoformat(result["started_at"])
    finished = datetime.fromisoformat(result["finished_at"])
    assert started.tzinfo == finished.tzinfo == UTC
    assert started <= finished

    results = result["node_results"]
    assert [entry["node_id"] for entry in results] == [
        "manual", "logger_a", "logger_b"
    ]
    assert [entry["status"] for entry in results] == ["success"] * 3
    assert [entry["output"] for entry in results] == [
        {"trigger": "manual"},
        {"manual": {"trigger": "manual"}},
        {"logger_a": {"manual": {"trigger": "manual"}}},
    ]
    for entry in results:
        node_started = datetime.fromisoformat(entry["started_at"])
        node_finished = datetime.fromisoformat(entry["finished_at"])
        assert node_started.tzinfo == node_finished.tzinfo == UTC
        assert started <= node_started <= node_finished <= finished
        assert entry["error"] is None


def test_execute_preserves_workflow_and_creates_history(
    client: TestClient, settings: Settings
) -> None:
    workflow = save(client, linear_payload())
    resource = f"/api/workflows/{workflow['id']}"
    assert client.post(resource + "/execute").status_code == 200
    assert client.get(resource).json() == workflow
    assert client.get("/api/workflows").json() == [workflow]
    assert client.post(resource + "/validate").json()["can_save"] is True
    with client.app.state.database.connect() as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert {row["name"] for row in tables} == {
            "workflows", "workflow_schedules", "workflow_executions"
        }
        assert connection.execute("SELECT COUNT(*) FROM workflow_executions").fetchone()[0] == 1
    update = {"name": "Still editable", "definition": workflow["definition"]}
    assert client.put(resource, json=update).status_code == 200
    assert client.delete(resource).status_code == 204
    assert client.get(resource).status_code == 404


def test_repeated_executions_have_independent_ids_and_outputs(client: TestClient) -> None:
    workflow = save(client, linear_payload())
    execute = f"/api/workflows/{workflow['id']}/execute"
    first = client.post(execute).json()
    first["node_results"][0]["output"]["trigger"] = "modified client copy"
    second = client.post(execute).json()
    assert first["execution_id"] != second["execution_id"]
    assert second["node_results"][0]["output"] == {"trigger": "manual"}
    assert second["node_results"][2]["output"] == {
        "logger_a": {"manual": {"trigger": "manual"}}
    }


def test_execute_missing_workflow_returns_404(client: TestClient) -> None:
    response = client.post(f"/api/workflows/{uuid4()}/execute")
    assert response.status_code == 404
    assert response.json() == {"detail": "Workflow not found"}


def test_execute_invalid_uuid_returns_sanitized_422(client: TestClient) -> None:
    response = client.post("/api/workflows/not-a-uuid/execute")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert all(
        set(issue) == {"type", "loc", "msg"}
        for issue in response.json()["detail"]
    )


def test_empty_draft_remains_saveable_but_cannot_execute(client: TestClient) -> None:
    workflow = save(client, {"name": "Unfinished draft"})
    resource = f"/api/workflows/{workflow['id']}"
    assert "MISSING_MANUAL_TRIGGER" in issue_codes(
        client.post(resource + "/execute")
    )
    report = client.post(resource + "/validate").json()
    assert report["can_save"] is True
    assert report["structural"]["valid"] is True
    assert client.get(resource).json() == workflow


@pytest.mark.parametrize(
    "unsupported_type",
    ["trigger.schedule"],
)
def test_schedule_nodes_cannot_execute_as_manual_workflows(
    client: TestClient, unsupported_type: str
) -> None:
    payload = linear_payload()
    payload["definition"]["nodes"][0]["type"] = unsupported_type
    workflow = save(client, payload)
    assert "TRIGGER_TYPE_MISMATCH" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


@pytest.mark.parametrize("node_type,code", [
    ("action.http_request", "INVALID_NODE_CONFIG"),
    ("logic.condition", "INVALID_CONDITION_CONFIG"),
    ("data.transform", "INVALID_TRANSFORM_CONFIG"),
    ("action.webhook", "INVALID_NODE_CONFIG"),
])
def test_unconfigured_core_node_drafts_are_rejected_before_execution(
    client: TestClient, node_type: str, code: str,
) -> None:
    payload = linear_payload()
    payload["definition"]["nodes"][0]["type"] = node_type
    workflow = save(client, payload)
    codes = issue_codes(client.post(f"/api/workflows/{workflow['id']}/execute"))
    assert code in codes
    assert "UNSUPPORTED_NODE_EXECUTOR" not in codes
    assert client.get(f"/api/workflows/{workflow['id']}").json() == workflow


def test_multiple_manual_triggers_cannot_execute(client: TestClient) -> None:
    payload = linear_payload()
    payload["definition"]["nodes"][0]["type"] = "trigger.manual"
    workflow = save(client, payload)
    assert "MULTIPLE_MANUAL_TRIGGERS" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


def test_cycle_draft_still_saves_but_execution_returns_422(client: TestClient) -> None:
    payload = linear_payload()
    payload["definition"]["edges"].append(
        {"id": "cycle", "source": "logger_b", "target": "manual"}
    )
    workflow = save(client, payload)
    assert "CYCLE_DETECTED" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


def test_manual_trigger_with_upstream_cannot_execute(client: TestClient) -> None:
    payload = linear_payload()
    payload["definition"]["edges"] = [
        {"id": "upstream", "source": "logger_a", "target": "manual"},
        {"id": "downstream", "source": "manual", "target": "logger_b"},
    ]
    workflow = save(client, payload)
    assert "MANUAL_TRIGGER_HAS_UPSTREAM" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


def test_nodes_unreachable_from_manual_trigger_cannot_execute(client: TestClient) -> None:
    payload = linear_payload()
    payload["definition"]["edges"].pop()
    workflow = save(client, payload)
    assert "UNREACHABLE_NODE" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


@pytest.mark.parametrize("handle", ["source_handle", "target_handle"])
def test_unimplemented_handle_semantics_are_rejected(
    client: TestClient, handle: str
) -> None:
    payload = linear_payload()
    payload["definition"]["edges"][0][handle] = "conditional-branch"
    workflow = save(client, payload)
    assert "UNSUPPORTED_EDGE_HANDLE" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


@pytest.mark.parametrize("controlled", [True, False])
def test_node_failure_returns_http_200_with_fail_fast_results_and_no_traceback(
    settings: Settings, controlled: bool
) -> None:
    class FailingLogger:
        def execute(self, context):
            if controlled:
                raise NodeExecutionError("TEST_NODE_FAILURE", "Logger rejected input")
            raise RuntimeError("internal-sensitive-diagnostic")

    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("utility.logger", FailingLogger())
    application = create_app(settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(
        registry=registry
    )
    with TestClient(application) as client:
        workflow = save(client, linear_payload())
        resource = f"/api/workflows/{workflow['id']}"
        response = client.post(resource + "/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "failed"
        assert [node["status"] for node in result["node_results"]] == [
            "success", "failed", "skipped"
        ]
        error_code = "TEST_NODE_FAILURE" if controlled else "NODE_EXECUTION_FAILED"
        assert result["error"]["code"] == error_code
        assert result["node_results"][1]["error"]["code"] == error_code
        assert result["node_results"][2]["started_at"] is None
        assert result["node_results"][2]["output"] is None
        assert "Traceback" not in response.text
        assert "RuntimeError" not in response.text
        assert "internal-sensitive-diagnostic" not in response.text
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get(resource).json() == workflow


def test_configured_node_limit_rejects_before_execution(settings: Settings) -> None:
    limited = settings.model_copy(update={"execution_max_nodes": 2})
    with TestClient(create_app(limited)) as client:
        workflow = save(client, linear_payload())
        assert "EXECUTION_NODE_LIMIT_EXCEEDED" in issue_codes(
            client.post(f"/api/workflows/{workflow['id']}/execute")
        )


def test_output_limit_is_a_structured_execution_failure(settings: Settings) -> None:
    limited = settings.model_copy(update={"execution_max_output_bytes": 1})
    with TestClient(create_app(limited)) as client:
        workflow = save(client, linear_payload())
        response = client.post(f"/api/workflows/{workflow['id']}/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "failed"
        assert result["error"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
        assert [node["status"] for node in result["node_results"]] == [
            "failed", "skipped", "skipped"
        ]


def test_execution_does_not_echo_node_config_or_system_environment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment_marker = "private-system-environment"
    config_marker = "private-node-message"
    monkeypatch.setenv("FLOWPILOT_EXECUTION_TEST_SECRET", environment_marker)
    payload = linear_payload()
    payload["definition"]["nodes"][2]["config"] = {"message": config_marker}
    workflow = save(client, payload)
    response = client.post(f"/api/workflows/{workflow['id']}/execute")
    assert response.status_code == 200
    assert environment_marker not in response.text
    assert config_marker not in response.text


def test_execute_reads_and_validates_the_saved_definition(client: TestClient) -> None:
    workflow = save(client, linear_payload())
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE workflows SET definition = ? WHERE id = ?",
            ('{"schema_version":2,"nodes":[],"edges":[]}', workflow["id"]),
        )
    assert "INVALID_WORKFLOW_DEFINITION" in issue_codes(
        client.post(f"/api/workflows/{workflow['id']}/execute")
    )


def test_execute_openapi_documents_success_and_readiness_or_input_errors(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()

    def resolve(schema: dict) -> dict:
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[1]
            return document["components"]["schemas"][name]
        return schema

    operation = document["paths"]["/api/workflows/{workflow_id}/execute"]["post"]
    assert "requestBody" not in operation
    result = resolve(operation["responses"]["200"]["content"]["application/json"]["schema"])
    assert {
        "execution_id", "workflow_id", "status", "started_at", "node_results"
    } <= result["properties"].keys()
    error = resolve(operation["responses"]["422"]["content"]["application/json"]["schema"])
    variants = [resolve(item) for item in error["properties"]["detail"]["anyOf"]]
    assert any(item.get("type") == "array" for item in variants)
    readiness = next(item for item in variants if item.get("type") == "object")
    assert readiness["properties"]["code"]["const"] == "WORKFLOW_NOT_EXECUTABLE"


def test_execute_cors_allows_the_configured_browser_origin(client: TestClient) -> None:
    workflow = save(client, linear_payload())
    response = client.post(
        f"/api/workflows/{workflow['id']}/execute",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_documented_manual_logger_example_can_be_created_and_executed(
    client: TestClient,
) -> None:
    example = Path(__file__).resolve().parents[2] / "docs/examples/manual-logger.json"
    workflow = save(client, json.loads(example.read_text(encoding="utf-8")))
    response = client.post(f"/api/workflows/{workflow['id']}/execute")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "success"
    assert [entry["node_id"] for entry in result["node_results"]] == [
        "manual", "logger_a", "logger_b"
    ]
    assert result["node_results"][-1]["output"] == {
        "logger_a": {"manual": {"trigger": "manual"}}
    }


def test_execute_branch_join_and_parallel_edges_runs_each_node_once(
    client: TestClient,
) -> None:
    payload = {
        "name": "Unconditional branch and join",
        "definition": {
            "schema_version": 1,
            "nodes": [
                node("join"), node("right"),
                node("manual", "trigger.manual"), node("left"),
            ],
            "edges": [
                {"id": "left", "source": "manual", "target": "left"},
                {"id": "right", "source": "manual", "target": "right"},
                {"id": "left-join", "source": "left", "target": "join"},
                {"id": "left-join-copy", "source": "left", "target": "join"},
                {"id": "right-join", "source": "right", "target": "join"},
            ],
        },
    }
    workflow = save(client, payload)
    response = client.post(f"/api/workflows/{workflow['id']}/execute")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "success"
    assert [entry["node_id"] for entry in result["node_results"]] == [
        "manual", "right", "left", "join"
    ]
    assert result["node_results"][-1]["output"] == {
        "left": {"manual": {"trigger": "manual"}},
        "right": {"manual": {"trigger": "manual"}},
    }


def test_preflight_rejection_does_not_invoke_any_executor(settings: Settings) -> None:
    calls = []

    class RecordingExecutor:
        def execute(self, context):
            calls.append(context.node_id)
            return {}

    registry = ExecutorRegistry()
    registry.register("trigger.manual", RecordingExecutor())
    registry.register("utility.logger", RecordingExecutor())
    application = create_app(settings)
    application.dependency_overrides[get_engine] = lambda: ExecutionEngine(
        registry=registry
    )
    with TestClient(application) as client:
        payload = linear_payload()
        payload["definition"]["nodes"][0]["type"] = "action.http_request"
        workflow = save(client, payload)
        assert "UNSUPPORTED_NODE_EXECUTOR" in issue_codes(
            client.post(f"/api/workflows/{workflow['id']}/execute")
        )
    assert calls == []


def test_simultaneous_requests_do_not_share_execution_results(client: TestClient) -> None:
    workflow = save(client, linear_payload())
    path = f"/api/workflows/{workflow['id']}/execute"

    def execute_once(_):
        response = client.post(path)
        assert response.status_code in {200, 409}
        return response.json() if response.status_code == 200 else None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(execute_once, range(8)))
    results = [result for result in results if result is not None]
    assert results
    assert len({result["execution_id"] for result in results}) == len(results)
    assert all(result["status"] == "success" for result in results)
    expected = {"logger_a": {"manual": {"trigger": "manual"}}}
    assert all(result["node_results"][-1]["output"] == expected for result in results)


def test_deep_passthrough_chain_returns_a_failed_result_instead_of_http_500(
    client: TestClient,
) -> None:
    identifiers = ["manual", *[f"logger_{index}" for index in range(70)]]
    payload = {
        "name": "Deep output chain",
        "definition": {
            "schema_version": 1,
            "nodes": [
                node(identifier, "trigger.manual" if index == 0 else "utility.logger")
                for index, identifier in enumerate(identifiers)
            ],
            "edges": [
                {"id": f"edge_{index}", "source": source, "target": target}
                for index, (source, target) in enumerate(zip(identifiers, identifiers[1:]))
            ],
        },
    }
    workflow = save(client, payload)
    response = client.post(f"/api/workflows/{workflow['id']}/execute")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_NODE_OUTPUT"
    assert result["node_results"][0]["status"] == "success"
    assert sum(entry["status"] == "failed" for entry in result["node_results"]) == 1
    assert result["node_results"][-1]["status"] == "skipped"
    assert client.get("/api/health").json() == {"status": "ok"}
