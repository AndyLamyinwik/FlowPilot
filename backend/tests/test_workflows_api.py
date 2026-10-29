from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def node(node_id: str, node_type: str = "utility.logger") -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 0, "y": 100},
        "config": {},
    }


def definition() -> dict:
    return {
        "schema_version": 1,
        "nodes": [node("start", "trigger.manual"), node("log")],
        "edges": [{"id": "start-log", "source": "start", "target": "log"}],
    }


def payload() -> dict:
    return {"name": "Example workflow", "description": "A saved definition", "definition": definition()}


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_workflow_crud_and_utc_metadata(client: TestClient) -> None:
    assert client.get("/api/workflows").json() == []
    response = client.post("/api/workflows", json=payload())
    assert response.status_code == 201
    created = response.json()
    assert UUID(created["id"]).version == 4
    assert response.headers["location"] == f"/api/workflows/{created['id']}"
    assert created["name"] == "Example workflow"
    assert created["definition"]["schema_version"] == 1
    created_at = datetime.fromisoformat(created["created_at"])
    assert created_at.tzinfo == UTC
    assert created["created_at"] == created["updated_at"]

    resource = f"/api/workflows/{created['id']}"
    assert client.get(resource).json() == created
    assert client.get("/api/workflows").json() == [created]

    update = {"name": "Renamed", "definition": {"schema_version": 1, "nodes": [], "edges": []}}
    response = client.put(resource, json=update)
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert datetime.fromisoformat(updated["updated_at"]) >= created_at
    assert updated["name"] == "Renamed"
    assert updated["description"] is None
    assert updated["definition"] == update["definition"]
    assert client.get(resource).json() == updated

    response = client.delete(resource)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(resource).status_code == 404
    assert client.get("/api/workflows").json() == []


@pytest.mark.parametrize("draft", [
    {"name": "New draft"},
    {"name": "New draft", "definition": {"schema_version": 1, "nodes": [], "edges": []}},
])
def test_blank_draft_can_be_saved_and_has_separate_readiness(client: TestClient, draft: dict) -> None:
    response = client.post("/api/workflows", json=draft)
    assert response.status_code == 201
    workflow = response.json()
    assert workflow["definition"] == {"schema_version": 1, "nodes": [], "edges": []}
    report = client.post(f"/api/workflows/{workflow['id']}/validate").json()
    assert report["can_save"] is True
    assert report["structural"]["valid"] is True
    assert report["execution_readiness"]["valid"] is False
    assert "MISSING_TRIGGER" in {error["code"] for error in report["execution_readiness"]["errors"]}


def test_dag_passes_future_readiness_without_executing_nodes(client: TestClient) -> None:
    workflow = client.post("/api/workflows", json=payload()).json()
    response = client.post(f"/api/workflows/{workflow['id']}/validate")
    assert response.status_code == 200
    assert response.json() == {
        "can_save": True,
        "structural": {"valid": True, "errors": [], "warnings": []},
        "execution_readiness": {"valid": True, "errors": [], "warnings": []},
    }


def test_cycle_can_be_saved_as_draft_but_is_not_ready(client: TestClient) -> None:
    workflow_payload = payload()
    workflow_payload["definition"]["edges"].append({"id": "log-start", "source": "log", "target": "start"})
    response = client.post("/api/workflows", json=workflow_payload)
    assert response.status_code == 201
    workflow = response.json()
    report = client.post(f"/api/workflows/{workflow['id']}/validate").json()
    assert report["can_save"] is True
    assert report["structural"]["valid"] is True
    assert report["execution_readiness"]["valid"] is False
    assert "CYCLE_DETECTED" in {error["code"] for error in report["execution_readiness"]["errors"]}


@pytest.mark.parametrize("case,code", [
    ("duplicate_node", "DUPLICATE_NODE_ID"),
    ("duplicate_edge", "DUPLICATE_EDGE_ID"),
    ("missing_reference", "INVALID_NODE_REFERENCE"),
    ("unknown_type", "UNREGISTERED_NODE_TYPE"),
    ("self_loop", "SELF_LOOP"),
])
def test_integrity_errors_are_rejected_before_saving(client: TestClient, case: str, code: str) -> None:
    workflow_payload = payload()
    graph = workflow_payload["definition"]
    if case == "duplicate_node":
        graph["nodes"].append(deepcopy(graph["nodes"][0]))
    elif case == "duplicate_edge":
        graph["edges"].append(deepcopy(graph["edges"][0]))
    elif case == "missing_reference":
        graph["edges"][0]["target"] = "missing"
    elif case == "unknown_type":
        graph["nodes"][0]["type"] = "not.registered"
    elif case == "self_loop":
        graph["edges"][0]["target"] = "start"
    response = client.post("/api/workflows", json=workflow_payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_WORKFLOW_STRUCTURE"
    assert code in {error["code"] for error in response.json()["detail"]["errors"]}
    assert client.get("/api/workflows").json() == []


@pytest.mark.parametrize("invalid_payload", [
    {"name": "   "},
    {"name": "Draft", "definition": {"schema_version": 2, "nodes": [], "edges": []}},
    {"name": "Draft", "definition": {"schema_version": True, "nodes": [], "edges": []}},
    {"name": "Draft", "definition": {"nodes": [], "edges": []}},
    {"name": "Draft", "definition": {"schema_version": 1, "nodes": [{}], "edges": []}},
])
def test_invalid_schema_returns_422_and_does_not_save(client: TestClient, invalid_payload: dict) -> None:
    response = client.post("/api/workflows", json=invalid_payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])
    assert client.get("/api/workflows").json() == []


def test_put_requires_complete_definition(client: TestClient) -> None:
    created = client.post("/api/workflows", json=payload()).json()
    resource = f"/api/workflows/{created['id']}"
    assert client.put(resource, json={"name": "Metadata only"}).status_code == 422
    assert client.get(resource).json() == created


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("PUT", ""), ("DELETE", ""), ("POST", "/validate")])
def test_missing_workflows_return_404(client: TestClient, method: str, suffix: str) -> None:
    resource = f"/api/workflows/{uuid4()}{suffix}"
    options = {"json": payload()} if method == "PUT" else {}
    response = client.request(method, resource, **options)
    assert response.status_code == 404
    assert response.json() == {"detail": "Workflow not found"}


def test_malformed_uuid_is_an_input_error(client: TestClient) -> None:
    response = client.get("/api/workflows/not-a-uuid")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_definitions_survive_application_restart(settings: Settings) -> None:
    with TestClient(create_app(settings)) as first_client:
        created = first_client.post("/api/workflows", json=payload()).json()
    with TestClient(create_app(settings)) as restarted_client:
        assert restarted_client.get(f"/api/workflows/{created['id']}").json() == created
        assert restarted_client.get("/api/workflows").json() == [created]
        assert restarted_client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_cors_preflight_supports_workflow_writes(client: TestClient, method: str) -> None:
    response = client.options("/api/workflows", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert method in response.headers["access-control-allow-methods"]


def test_registered_node_types_are_metadata_only(client: TestClient) -> None:
    response = client.get("/api/node-types")
    assert response.status_code == 200
    entries = response.json()
    assert {entry["type"] for entry in entries} == {
        "trigger.manual", "trigger.schedule", "action.http_request", "logic.condition",
        "data.transform", "action.webhook", "utility.logger",
    }
    assert all(set(entry) == {"type", "display_name", "category", "description"} for entry in entries)


def test_openapi_preserves_health_and_describes_workflow_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/health" in paths
    assert {"get", "post"} <= paths["/api/workflows"].keys()
    assert {"get", "put", "delete"} <= paths["/api/workflows/{workflow_id}"].keys()
    assert "post" in paths["/api/workflows/{workflow_id}/validate"]
    assert "get" in paths["/api/node-types"]


def test_openapi_documents_schema_and_structural_422_responses(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    def resolve(schema: dict) -> dict:
        if "$ref" in schema:
            return document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
        return schema

    for path, method in [("/api/workflows", "post"), ("/api/workflows/{workflow_id}", "put")]:
        response = document["paths"][path][method]["responses"]["422"]
        schema = resolve(response["content"]["application/json"]["schema"])
        variants = [resolve(variant) for variant in schema["properties"]["detail"]["anyOf"]]
        request_errors = next(variant for variant in variants if variant.get("type") == "array")
        assert set(resolve(request_errors["items"])["required"]) == {"type", "loc", "msg"}
        structure_error = next(variant for variant in variants if variant.get("type") == "object")
        assert structure_error["properties"]["code"]["const"] == "INVALID_WORKFLOW_STRUCTURE"
        assert {"code", "errors"} == set(structure_error["required"])
