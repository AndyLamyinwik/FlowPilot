"""Incoming Host boundaries are independent of outbound HTTP destination policy."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def test_allowed_hosts_default_to_local_and_compose_names_only() -> None:
    settings = Settings(_env_file=None)
    assert settings.allowed_hosts == ["localhost", "127.0.0.1", "[::1]", "backend"]
    assert "testserver" not in settings.allowed_hosts


def test_allowed_hosts_load_from_environment_and_normalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "FLOWPILOT_ALLOWED_HOSTS",
        '["LOCALHOST", "flowpilot.example.", "[0:0:0:0:0:0:0:1]", "localhost"]',
    )
    assert Settings(_env_file=None).allowed_hosts == ["localhost", "flowpilot.example", "[::1]"]


@pytest.mark.parametrize("hosts", [
    [], ["*"], ["*.example.com"], ["http://localhost"], ["localhost:8000"],
    ["user@localhost"], ["localhost/path"], [" localhost"], [""], ["[::1]:8000"],
    ["bad host"], ["localhost\r\nHost:attacker.invalid"],
])
def test_invalid_allowed_host_configuration_is_rejected(hosts: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_hosts=hosts)


@pytest.mark.parametrize("host", [
    "localhost", "LOCALHOST:8000", "127.0.0.1:8000", "[::1]", "[::1]:8000", "backend:8000",
])
def test_local_ip_and_compose_host_headers_work(settings: Settings, host: str) -> None:
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        response = client.get("/api/health", headers={"Host": host})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("host", [
    "attacker.invalid:8000", "localhost.attacker.invalid", "user@localhost",
    "localhost/path", "[::1", "localhost:invalid", "localhost,attacker.invalid",
])
def test_untrusted_or_malformed_host_is_rejected_before_side_effects(
    settings: Settings, host: str,
) -> None:
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/workflows", json={"name": "Must not be persisted"},
            headers={"Host": host, "Origin": "http://localhost:5173"},
        )
        assert response.status_code == 400
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert client.get("/api/workflows").json() == []


def test_missing_host_header_is_rejected_before_side_effects(settings: Settings) -> None:
    application = create_app(settings)
    with TestClient(application, base_url="http://127.0.0.1") as client:
        # TestClient adds Host when absent; submit the exact ASGI request instead.
        messages = []

        async def receive():
            return {"type": "http.request", "body": b'{"name":"Rejected"}', "more_body": False}

        async def send(message):
            messages.append(message)

        asyncio.run(application({
            "type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/api/workflows", "raw_path": b"/api/workflows", "query_string": b"",
            "root_path": "", "headers": [(b"content-type", b"application/json")],
            "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 50000),
        }, receive, send))
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 400
        assert client.get("/api/workflows").json() == []


def test_custom_host_is_explicit_and_does_not_enable_subdomains(settings: Settings) -> None:
    configured = settings.model_copy(update={"allowed_hosts": ["flowpilot.example"]})
    with TestClient(create_app(configured), base_url="http://flowpilot.example") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health", headers={"Host": "sub.flowpilot.example"}).status_code == 400
        assert client.get("/api/health", headers={"Host": "localhost"}).status_code == 400


def test_host_rejection_cannot_update_execute_or_override_with_forwarded_headers(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        payload = {"name": "Original", "definition": {
            "schema_version": 1,
            "nodes": [{"id": "manual", "name": "Manual", "type": "trigger.manual",
                       "position": {"x": 0, "y": 0}, "config": {}}],
            "edges": [],
        }}
        saved = client.post("/api/workflows", json=payload).json()
        path = f"/api/workflows/{saved['id']}"
        headers = {
            "Host": "rebind.example.invalid:8000", "Origin": "http://rebind.example.invalid:8000",
            "X-Forwarded-Host": "localhost", "Forwarded": "host=localhost",
        }
        assert client.put(path, json={**payload, "name": "Changed"}, headers=headers).status_code == 400
        assert client.post(path + "/execute", headers=headers).status_code == 400
        assert client.get(path).json()["name"] == "Original"
        assert client.get(path + "/executions").json()["total"] == 0
        assert client.post(path + "/execute").json()["status"] == "success"
