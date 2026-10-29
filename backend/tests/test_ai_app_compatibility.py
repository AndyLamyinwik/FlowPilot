"""AI must remain optional even when its package cannot be imported."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.core.config import Settings


def test_ai_feature_intent_defaults_off_and_loads_environment(monkeypatch):
    assert Settings(_env_file=None).ai_enabled is False
    monkeypatch.setenv("FLOWPILOT_AI_ENABLED", "false")
    assert Settings(_env_file=None).ai_enabled is False
    monkeypatch.setenv("FLOWPILOT_AI_ENABLED", "true")
    assert Settings(_env_file=None).ai_enabled is True


@pytest.mark.parametrize("enabled", [False, True])
def test_app_and_workflows_need_neither_ai_package_nor_keys(tmp_path: Path, enabled: bool):
    # Fresh interpreter proves startup does not merely reuse previously imported
    # AI modules. Local TestClient transport needs no external socket or DNS.
    script = r'''
import importlib.abc
import json
from pathlib import Path
import socket
import sys

class NoAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "app.ai" or fullname.startswith("app.ai."):
            raise AssertionError("V1 attempted to import optional AI")

sys.meta_path.insert(0, NoAI())
def offline(*args, **kwargs):
    raise AssertionError("Compatibility test attempted external network I/O")
socket.create_connection = offline
socket.getaddrinfo = offline

from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app

settings = Settings(_env_file=None, database_path=Path(sys.argv[1]) / "compatibility.db",
                    ai_enabled=json.loads(sys.argv[2]), log_level="WARNING")
application = create_app(settings)
expected = {"trigger.manual", "trigger.schedule", "utility.logger", "action.http_request",
            "logic.condition", "data.transform", "action.webhook"}
with TestClient(application, base_url="http://127.0.0.1") as client:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert {item["type"] for item in client.get("/api/node-types").json()} == expected
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("/ai" in path or "provider" in path for path in paths)
    payload = json.loads((Path.cwd().parent / "docs/examples/manual-logger.json").read_text())
    response = client.post("/api/workflows", json=payload)
    assert response.status_code == 201
    saved = response.json()
    path = "/api/workflows/" + saved["id"]
    assert client.get(path).json() == saved
    assert len(client.get("/api/workflows").json()) == 1
    update = {"name": "AI-independent manual workflow", "description": None,
              "definition": saved["definition"]}
    assert client.put(path, json=update).json()["definition"] == saved["definition"]
    assert client.post(path + "/validate").json()["execution_readiness"]["valid"]
    live = client.post(path + "/execute")
    assert live.status_code == 200 and live.json()["status"] == "success"
    result = live.json()
    assert all(item["status"] == "success" for item in result["node_results"])
    assert [item["node_id"] for item in result["node_results"]] == [item["id"] for item in saved["definition"]["nodes"]]
    assert client.get(path + "/executions").json()["items"][0]["execution_id"] == result["execution_id"]
    assert client.get("/api/executions/" + result["execution_id"]).json()["status"] == "success"
    forbidden = {"name": "Not an implemented node", "definition": {"schema_version": 1,
        "nodes": [{"id": "ai", "name": "AI", "type": "ai.generate",
                   "position": {"x": 0, "y": 0}, "config": {}}], "edges": []}}
    assert client.post("/api/workflows", json=forbidden).status_code == 422
    assert client.delete(path).status_code == 204
assert not any(name == "app.ai" or name.startswith("app.ai.") for name in sys.modules)
print("PASS optional AI unavailable; no keys/network; existing routes, seven nodes, CRUD/Execute/History")
'''
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("FLOWPILOT_", "OPENAI_", "ANTHROPIC_", "GEMINI_", "OLLAMA_"))
                   and key != "GOOGLE_API_KEY"}
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), "true" if enabled else "false"],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS optional AI unavailable" in result.stdout
