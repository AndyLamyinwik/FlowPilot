import json
import sqlite3
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _node(node_id: str, node_type: str = "utility.logger") -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 100, "y": 200},
        "config": {},
    }


def _payload() -> dict:
    return {
        "name": "Branch and join",
        "definition": {
            "schema_version": 1,
            "nodes": [
                _node("start", "trigger.manual"),
                _node("branch", "logic.condition"),
                _node("left"),
                _node("right", "data.transform"),
                _node("join"),
            ],
            "edges": [
                {"id": "start-branch", "source": "start", "target": "branch"},
                {"id": "true", "source": "branch", "target": "left", "source_handle": "true"},
                {"id": "false", "source": "branch", "target": "right", "source_handle": "false"},
                {"id": "left-join-a", "source": "left", "target": "join", "target_handle": "a"},
                {"id": "left-join-b", "source": "left", "target": "join", "target_handle": "b"},
                {"id": "right-join", "source": "right", "target": "join", "target_handle": "c"},
            ],
        },
    }


def test_branch_join_and_parallel_edges_round_trip_without_a_false_cycle(settings: Settings) -> None:
    payload = _payload()
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json=payload)
        assert response.status_code == 201
        workflow = response.json()
        loaded = client.get(f"/api/workflows/{workflow['id']}").json()
        assert loaded["definition"] == workflow["definition"]
        assert loaded["definition"]["edges"][1]["source_handle"] == "true"
        assert loaded["definition"]["edges"][3]["target_handle"] == "a"
        assert loaded["definition"]["edges"][4]["target_handle"] == "b"
        report = client.post(f"/api/workflows/{workflow['id']}/validate").json()
        assert report["can_save"] is True
        assert report["structural"]["valid"] is True
        assert report["execution_readiness"]["valid"] is True


def test_hostile_sql_text_is_saved_as_literal_metadata(settings: Settings) -> None:
    name = "Robert'); DROP TABLE workflows; --"
    description = "中文 ' quoted metadata; DELETE FROM workflows; ☃"
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json={"name": name, "description": description})
        assert response.status_code == 201
        workflow = response.json()
        assert workflow["name"] == name
        assert workflow["description"] == description
        assert client.get("/api/workflows").json() == [workflow]
        assert client.get("/api/health").json() == {"status": "ok"}


def test_initialization_preserves_existing_unrelated_data(settings: Settings) -> None:
    settings.database_path.parent.mkdir(parents=True)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("CREATE TABLE existing_data (value TEXT NOT NULL)")
        connection.execute("INSERT INTO existing_data (value) VALUES (?)", ("keep me",))
        connection.execute("PRAGMA user_version = 42")

    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/workflows").json() == []
        with sqlite3.connect(settings.database_path) as connection:
            assert connection.execute("SELECT value FROM existing_data").fetchall() == [("keep me",)]
            assert connection.execute("PRAGMA user_version").fetchone() == (42,)


@pytest.mark.parametrize("field", ["id", "created_at", "updated_at"])
def test_client_cannot_override_immutable_workflow_metadata(settings: Settings, field: str) -> None:
    value = str(uuid4()) if field == "id" else "2000-01-01T00:00:00Z"
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json={"name": "Draft", field: value})
        assert response.status_code == 422
        assert client.get("/api/workflows").json() == []


def test_rejected_updates_leave_the_entire_saved_workflow_unchanged(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        original = client.post("/api/workflows", json=_payload()).json()
        invalid = _payload()
        invalid["name"] = "Must not overwrite"
        invalid["definition"]["edges"][0]["target"] = "missing-node"
        response = client.put(f"/api/workflows/{original['id']}", json=invalid)
        assert response.status_code == 422
        assert client.get(f"/api/workflows/{original['id']}").json() == original

        immutable = deepcopy(_payload())
        immutable["created_at"] = "2000-01-01T00:00:00Z"
        assert client.put(f"/api/workflows/{original['id']}", json=immutable).status_code == 422
        assert client.get(f"/api/workflows/{original['id']}").json() == original


@pytest.mark.parametrize("secret_key", ["password", "API-Key", "Authorization", "X-Api-Key"])
def test_nested_plaintext_credentials_are_rejected_without_echoing_values(
    settings: Settings, secret_key: str
) -> None:
    secret = "review-only-sensitive-value"
    payload = _payload()
    payload["definition"]["nodes"][0]["config"] = {"nested": [{secret_key: secret}]}
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json=payload)
        assert response.status_code == 422
        assert secret not in response.text
        assert client.get("/api/workflows").json() == []


def test_nonfinite_json_config_is_rejected_with_json_error_response(settings: Settings) -> None:
    payload = _payload()
    payload["definition"]["nodes"][0]["config"] = {"number": float("nan")}
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/workflows", content=json.dumps(payload), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
        assert client.get("/api/workflows").json() == []

