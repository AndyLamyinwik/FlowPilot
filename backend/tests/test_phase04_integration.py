import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api.executions import get_engine
from app.core.config import Settings
from app.core.http_policy import HTTPPolicy
from app.main import create_app
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import create_default_executor_registry
from app.services.execution.safe_http import SafeHttpClient


def node(node_id: str, node_type: str = "utility.logger", config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge(source: str, target: str, handle: str | None = None) -> dict:
    return {"id": f"{source}-{target}", "source": source, "target": target, "source_handle": handle}


def definition(nodes: list[dict], edges: list[dict]) -> dict:
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def engine_with_http(handler, allowed_hosts=("api.example.test", "hook.example.test")) -> ExecutionEngine:
    policy = HTTPPolicy(allowed_hosts=allowed_hosts)
    http_client = SafeHttpClient(
        policy,
        transport=httpx2.MockTransport(handler),
        resolver=lambda hostname, port: ["93.184.216.34"],
    )
    return ExecutionEngine(registry=create_default_executor_registry(http_client=http_client))


def save(client: TestClient, graph: dict) -> dict:
    response = client.post("/api/workflows", json={"name": "Phase 04 integration", "definition": graph})
    assert response.status_code == 201, response.text
    return response.json()


def by_id(result: dict) -> dict:
    return {item["node_id"]: item for item in result["node_results"]}


def http_graph() -> dict:
    return definition(
        [node("manual", "trigger.manual"), node("http", "action.http_request", {
            "method": "GET", "url": "https://api.example.test/user",
        }), node("logger")],
        [edge("manual", "http"), edge("http", "logger")],
    )


def test_manual_http_logger_uses_existing_execute_api_and_preserves_workflow(settings: Settings) -> None:
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "api.example.test"
        assert request.extensions["sni_hostname"] == "api.example.test"
        return httpx2.Response(200, json={"message": "success"})

    engine = engine_with_http(handler)
    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        workflow = save(client, http_graph())
        resource = f"/api/workflows/{workflow['id']}"
        response = client.post(resource + "/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert by_id(result)["http"]["output"] == {"status_code": 200, "body": {"message": "success"}}
        assert by_id(result)["logger"]["output"] == {"http": {"status_code": 200, "body": {"message": "success"}}}
        assert len(requests) == 1
        assert client.get(resource).json() == workflow
        assert client.get("/api/health").json() == {"status": "ok"}
        with app.state.database.connect() as connection:
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert {row["name"] for row in tables} == {
            "workflows", "workflow_schedules", "workflow_executions"
        }


def test_manual_transform_logger_reads_manual_output_and_static_values() -> None:
    graph = definition(
        [node("manual", "trigger.manual"), node("transform", "data.transform", {
            "mapping": {
                "origin": {"source_node_id": "manual", "path": "trigger"},
                "source": {"value": "FlowPilot"},
            },
        }), node("logger")],
        [edge("manual", "transform"), edge("transform", "logger")],
    )
    snapshot = deepcopy(graph)
    result = ExecutionEngine().execute(uuid4(), graph)
    assert result.status == "success"
    assert result.node_results[1].output == {"origin": "manual", "source": "FlowPilot"}
    assert result.node_results[2].output == {"transform": {"origin": "manual", "source": "FlowPilot"}}
    assert graph == snapshot


@pytest.mark.parametrize("remote_status", ["success", "rejected"])
def test_http_condition_transform_webhook_uses_successful_ancestor_data(
    settings: Settings, remote_status: str,
) -> None:
    deliveries = []
    requests = []

    def handler(request):
        requests.append(request)
        if request.headers["host"] == "api.example.test":
            assert request.method == "GET"
            return httpx2.Response(200, json={
                "status": remote_status, "user": {"name": "Andy", "score": 95},
            })
        assert request.headers["host"] == "hook.example.test"
        assert request.method == "POST"
        deliveries.append(json.loads(request.content))
        return httpx2.Response(200, json={"accepted": True})

    engine = engine_with_http(handler)
    graph = definition(
        [node("manual", "trigger.manual"), node("http", "action.http_request", {
            "url": "https://api.example.test/user", "method": "GET",
        }), node("condition", "logic.condition", {
            "source_node_id": "http", "field": "body.status", "operator": "equals", "value": "success",
        }), node("transform", "data.transform", {
            "mapping": {
                "username": {"source_node_id": "http", "path": "body.user.name"},
                "points": {"source_node_id": "http", "path": "body.user.score"},
                "source": {"value": "FlowPilot"},
            },
        }), node("webhook", "action.webhook", {
            "url": "https://hook.example.test/notify", "source_node_id": "transform",
        }), node("fallback")],
        [edge("manual", "http"), edge("http", "condition"),
         edge("condition", "transform", "true"), edge("transform", "webhook"),
         edge("condition", "fallback", "false")],
    )
    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        workflow = save(client, graph)
        response = client.post(f"/api/workflows/{workflow['id']}/execute")
        assert response.status_code == 200
        result = response.json()
        entries = by_id(result)
        assert result["status"] == "success"
        if remote_status == "success":
            expected = {"username": "Andy", "points": 95, "source": "FlowPilot"}
            assert entries["transform"]["output"] == expected
            assert deliveries == [expected]
            assert entries["webhook"]["output"] == {"status_code": 200, "delivered": True}
            assert entries["fallback"]["status"] == "skipped"
            assert len(requests) == 2
        else:
            assert deliveries == [] and len(requests) == 1
            assert entries["transform"]["status"] == entries["webhook"]["status"] == "skipped"
            assert entries["fallback"]["status"] == "success"


@pytest.mark.parametrize("status", [404, 500])
def test_http_failure_returns_failed_execution_and_stops_following_nodes(settings: Settings, status: int) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(status, text="private-remote-error-body")

    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine_with_http(handler)
    with TestClient(app) as client:
        workflow = save(client, http_graph())
        response = client.post(f"/api/workflows/{workflow['id']}/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "failed"
        assert [entry["status"] for entry in result["node_results"]] == ["success", "failed", "skipped"]
        assert len(calls) == 1
        assert "private-remote-error-body" not in response.text and "Traceback" not in response.text
        assert client.get("/api/health").json() == {"status": "ok"}


def test_new_node_readiness_finishes_before_any_executor_or_network_request(monkeypatch) -> None:
    calls = []
    engine = engine_with_http(lambda request: calls.append("http") or httpx2.Response(200, json={}))
    manual = engine.registry.get("trigger.manual")
    original = manual.execute

    def record_manual(context):
        calls.append("manual")
        return original(context)

    monkeypatch.setattr(manual, "execute", record_manual)
    graph = http_graph()
    graph["nodes"][-1] = node("logger", "data.transform", {
        "mapping": {"value": {"source_node_id": "not-in-this-workflow", "path": "body"}},
    })
    from app.services.execution.validation import ExecutionValidationError

    with pytest.raises(ExecutionValidationError) as raised:
        engine.execute(uuid4(), graph)
    assert "INVALID_DATA_SOURCE" in {issue.code for issue in raised.value.errors}
    assert calls == []


def test_draft_with_unconfigured_nodes_can_save_but_execution_rejects_without_dns(
    settings: Settings, monkeypatch,
) -> None:
    def forbidden_dns(*args, **kwargs):
        raise AssertionError("Readiness must not perform DNS")

    monkeypatch.setattr("socket.getaddrinfo", forbidden_dns)
    app = create_app(settings)
    with TestClient(app) as client:
        graph = http_graph()
        graph["nodes"][1]["config"] = {}
        workflow = save(client, graph)
        resource = f"/api/workflows/{workflow['id']}"
        report = client.post(resource + "/validate").json()
        assert report["can_save"] and report["structural"]["valid"]
        response = client.post(resource + "/execute")
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "WORKFLOW_NOT_EXECUTABLE"
        assert client.get(resource).json() == workflow


def test_each_run_keeps_http_outputs_isolated_from_returned_result_mutation() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json={"items": [{"name": "original"}]})

    engine = engine_with_http(handler)
    first = engine.execute(uuid4(), http_graph())
    first.node_results[1].output["body"]["items"][0]["name"] = "changed-client-copy"
    second = engine.execute(uuid4(), http_graph())
    assert first.execution_id != second.execution_id
    assert second.node_results[1].output == {"status_code": 200, "body": {"items": [{"name": "original"}]}}
    assert len(calls) == 2


def test_reference_to_skipped_ancestor_fails_instead_of_reading_inactive_data() -> None:
    graph = definition(
        [node("manual", "trigger.manual"), node("condition", "logic.condition", {
            "source_node_id": "manual", "field": "trigger", "operator": "equals", "value": "not-manual",
        }), node("left", "data.transform", {"mapping": {"value": {"value": "left"}}}),
         node("right", "data.transform", {"mapping": {"value": {"value": "right"}}}),
         node("join", "data.transform", {"mapping": {"value": {"source_node_id": "left", "path": "value"}}})],
        [edge("manual", "condition"), edge("condition", "left", "true"),
         edge("condition", "right", "false"), edge("left", "join"), edge("right", "join")],
    )
    result = ExecutionEngine().execute(uuid4(), graph)
    entries = {entry.node_id: entry for entry in result.node_results}
    assert result.status == "failed"
    assert entries["left"].status == "skipped" and entries["right"].status == "success"
    assert entries["join"].error.code == "DATA_SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("header", ["Authorization", "Cookie", "Proxy-Authorization"])
def test_sensitive_http_headers_cannot_be_persisted_in_workflow_json(settings: Settings, header: str) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        graph = http_graph()
        graph["nodes"][1]["config"]["headers"] = {header: "private-header-value"}
        response = client.post("/api/workflows", json={"name": "Unsafe credential", "definition": graph})
        assert response.status_code == 422
        assert "private-header-value" not in response.text
        assert client.get("/api/workflows").json() == []


@pytest.mark.parametrize("filename", ["http-logger.json", "core-automation.json"])
def test_documented_automation_examples_execute_via_api_with_mock_transport(
    settings: Settings, filename: str,
) -> None:
    requests = []
    payloads = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "httpbin.org"
        if request.url.path == "/json":
            return httpx2.Response(200, json={"slideshow": {"title": "Example title"}})
        assert request.method == "POST" and request.url.path == "/post"
        payloads.append(json.loads(request.content))
        return httpx2.Response(200, json={"accepted": True})

    engine = engine_with_http(handler, allowed_hosts=("httpbin.org",))
    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine
    example_path = Path(__file__).resolve().parents[2] / "docs/examples" / filename
    example = json.loads(example_path.read_text(encoding="utf-8"))
    with TestClient(app) as client:
        created = client.post("/api/workflows", json=example)
        assert created.status_code == 201
        workflow = created.json()
        response = client.post(f"/api/workflows/{workflow['id']}/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert len(result["node_results"]) == len(example["definition"]["nodes"])
        if filename == "core-automation.json":
            assert payloads == [{"title": "Example title", "source": "FlowPilot"}]
            assert by_id(result)["no_title"]["status"] == "skipped"
            assert by_id(result)["join"]["output"] == {"webhook": {"status_code": 200, "delivered": True}}
            assert len(requests) == 2
        else:
            assert payloads == [] and len(requests) == 1
