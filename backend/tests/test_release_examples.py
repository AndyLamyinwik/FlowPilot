"""Validate the exact public examples offline through existing APIs and Engine."""

import json
from pathlib import Path
import socket
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api.executions import get_engine
from app.core.config import Settings
from app.core.http_policy import HTTPPolicy
from app.main import create_app
from app.schemas.workflow import WorkflowCreate
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import create_default_executor_registry
from app.services.execution.safe_http import SafeHttpClient

EXAMPLE_DIRECTORY = Path(__file__).resolve().parents[2] / "examples" / "workflows"
EXAMPLE_FILES = ("manual-logger.json", "scheduled-logger.json", "api-condition.json")


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Release examples must not contact external services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def load_example(filename: str) -> dict:
    raw = json.loads((EXAMPLE_DIRECTORY / filename).read_text(encoding="utf-8"))
    # This also rejects unknown public fields, unsupported schema versions,
    # credential fields and non-JSON configuration values.
    WorkflowCreate.model_validate(raw)
    return raw


def save_example(client: TestClient, filename: str) -> dict:
    response = client.post("/api/workflows", json=load_example(filename))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("filename", EXAMPLE_FILES)
def test_release_example_parses_saves_and_passes_general_graph_validation(
    settings: Settings, filename: str,
) -> None:
    payload = load_example(filename)
    expected = WorkflowCreate.model_validate(payload).definition.model_dump(mode="json")
    with TestClient(create_app(settings)) as client:
        saved = save_example(client, filename)
        path = f"/api/workflows/{saved['id']}"
        assert saved["definition"] == expected
        assert client.get(path).json() == saved
        report = client.post(path + "/validate")
        assert report.status_code == 200
        assert report.json()["can_save"] is True
        assert report.json()["structural"]["valid"] is True
        assert report.json()["execution_readiness"]["valid"] is True
        assert client.get(path + "/executions").json()["total"] == 0


def test_manual_release_example_executes_offline_with_matching_history(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        saved = save_example(client, "manual-logger.json")
        path = f"/api/workflows/{saved['id']}"
        response = client.post(path + "/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["workflow_id"] == saved["id"]
        assert result["status"] == "success"
        assert [item["node_id"] for item in result["node_results"]] == ["manual", "logger_a", "logger_b"]
        assert all(item["status"] == "success" for item in result["node_results"])
        assert result["node_results"][-1]["output"] == {
            "logger_a": {"manual": {"trigger": "manual"}},
        }
        history = client.get(path + "/executions").json()
        assert history["total"] == 1
        assert history["items"][0]["execution_id"] == result["execution_id"]
        detail = client.get(f"/api/executions/{result['execution_id']}").json()
        assert detail["execution_id"] == result["execution_id"]
        assert all(item["output"] is None for item in detail["node_results"])
        assert client.get(path).json() == saved


def test_scheduled_release_example_import_is_disabled_without_a_job(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        saved = save_example(client, "scheduled-logger.json")
        path = f"/api/workflows/{saved['id']}"
        state = client.get(path + "/schedule").json()
        assert state["enabled"] is False
        assert state["next_run_at"] is None
        assert state["cron"] == "*/5 * * * *"
        assert state["timezone"] == "UTC"
        assert state["scheduler_running"] is True
        assert "enabled" not in saved["definition"]
        assert app.state.scheduler.scheduler.get_job(
            app.state.scheduler.job_id(UUID(saved["id"])),
        ) is None
        assert client.get(path + "/executions").json()["total"] == 0
        # Importing a Schedule workflow never creates a Manual Run loophole.
        assert client.post(path + "/execute").status_code == 422
        assert client.get(path + "/executions").json()["total"] == 0


def test_http_release_example_requires_allowlist_without_executing_http(
    settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Default allowlist must reject before HTTP execution")

    monkeypatch.setattr(SafeHttpClient, "request", forbidden)
    assert settings.http_allowed_hosts == []
    with TestClient(create_app(settings)) as client:
        saved = save_example(client, "api-condition.json")
        path = f"/api/workflows/{saved['id']}"
        # General graph validity is not a promise of executor readiness.
        assert client.post(path + "/validate").json()["execution_readiness"]["valid"] is True
        response = client.post(path + "/execute")
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "WORKFLOW_NOT_EXECUTABLE"
        assert "HTTP_HOST_NOT_ALLOWED" in {
            issue["code"] for issue in response.json()["detail"]["errors"]
        }
        assert client.get(path + "/executions").json()["total"] == 0


@pytest.mark.parametrize("has_title", [True, False])
def test_http_release_example_true_false_branches_use_only_controlled_transport(
    settings: Settings, has_title: bool,
) -> None:
    calls = []
    resolutions = []
    body = {"slideshow": {"title": "Release example fixture"}} if has_title else {
        "message": "No slideshow title in this fixture",
    }

    def resolver(host: str, port: int) -> list[str]:
        resolutions.append((host, port))
        return ["93.184.216.34"]

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "93.184.216.34"
        assert request.url.path == "/json"
        assert request.headers["host"] == "httpbin.org"
        assert request.extensions["sni_hostname"] == "httpbin.org"
        return httpx2.Response(200, json=body)

    http_client = SafeHttpClient(
        HTTPPolicy(allowed_hosts=("httpbin.org",)),
        transport=httpx2.MockTransport(handler), resolver=resolver,
    )
    engine = ExecutionEngine(registry=create_default_executor_registry(http_client))
    app = create_app(settings)
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        saved = save_example(client, "api-condition.json")
        path = f"/api/workflows/{saved['id']}"
        response = client.post(path + "/execute")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        nodes = {item["node_id"]: item for item in result["node_results"]}
        assert nodes["http"]["output"] == {"status_code": 200, "body": body}
        assert nodes["condition"]["output"] == {"matched": has_title}
        selected, skipped = ("logger_true", "logger_false") if has_title else ("logger_false", "logger_true")
        assert nodes[selected]["status"] == "success"
        assert nodes[selected]["output"] == {"condition": {"matched": has_title}}
        assert nodes[skipped]["status"] == "skipped"
        assert nodes[skipped]["output"] is None
        assert len(calls) == 1
        assert resolutions == [("httpbin.org", 443)]
        assert client.get(path).json() == saved
        assert client.get(path + "/executions").json()["total"] == 1
