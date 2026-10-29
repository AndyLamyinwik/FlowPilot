from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.workflow import (
    Edge,
    Node,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
    WorkflowUpdate,
)
from app.services.node_registry import NODE_TYPE_REGISTRY, NodeTypeRegistry
from app.services.workflow_validation import validate_workflow


def node(node_id: str, node_type: str = "utility.logger", **overrides: object) -> Node:
    return Node.model_validate({"id": node_id, "type": node_type, "name": node_id, "position": {"x": 0, "y": 0}, "config": {}, **overrides})


def definition(nodes: list[Node], edges: list[Edge] | None = None) -> WorkflowDefinition:
    return WorkflowDefinition(schema_version=1, nodes=nodes, edges=edges or [])


def codes(issues: list) -> set[str]:
    return {issue.code for issue in issues}


def test_empty_draft_can_be_saved_but_is_not_execution_ready() -> None:
    report = validate_workflow(definition([]))
    assert report.can_save
    assert report.structural.valid
    assert not report.execution_readiness.valid
    assert "MISSING_TRIGGER" in codes(report.execution_readiness.errors)
    assert report.structural.warnings == report.execution_readiness.warnings == []


def test_single_manual_trigger_has_ready_structure_without_an_executor() -> None:
    report = validate_workflow(definition([node("start", "trigger.manual")]))
    assert report.can_save and report.structural.valid and report.execution_readiness.valid


def test_valid_dag_supports_branches_joins_and_parallel_handle_edges() -> None:
    nodes = [node("start", "trigger.manual"), node("condition", "logic.condition"), node("a"), node("b"), node("end")]
    edges = [
        Edge(id="1", source="start", target="condition"),
        Edge(id="2", source="condition", target="a", source_handle="true"),
        Edge(id="3", source="condition", target="b", source_handle="false"),
        Edge(id="4", source="a", target="end", target_handle="left"),
        Edge(id="5", source="b", target="end", target_handle="right"),
        Edge(id="6", source="a", target="end", source_handle="other", target_handle="other"),
    ]
    report = validate_workflow(definition(nodes, edges))
    assert report.structural.valid and report.execution_readiness.valid


def test_duplicate_node_ids_are_structural_errors() -> None:
    report = validate_workflow(definition([node("same"), node("same")]))
    assert not report.can_save
    assert codes(report.structural.errors) == {"DUPLICATE_NODE_ID"}
    assert report.structural.errors[0].node_id == "same"
    assert codes(report.execution_readiness.errors) == {"STRUCTURAL_VALIDATION_FAILED"}


def test_duplicate_edge_ids_are_structural_errors() -> None:
    edge = Edge(id="same", source="start", target="end")
    report = validate_workflow(definition([node("start", "trigger.manual"), node("end")], [edge, edge]))
    assert not report.can_save
    assert codes(report.structural.errors) == {"DUPLICATE_EDGE_ID"}
    assert report.structural.errors[0].edge_id == "same"


@pytest.mark.parametrize("source,target", [("absent", "end"), ("start", "absent")])
def test_dangling_edge_endpoints_are_rejected(source: str, target: str) -> None:
    report = validate_workflow(definition([node("start"), node("end")], [Edge(id="edge", source=source, target=target)]))
    assert not report.can_save
    assert codes(report.structural.errors) == {"INVALID_NODE_REFERENCE"}


def test_self_link_is_an_invalid_connection() -> None:
    report = validate_workflow(definition([node("same")], [Edge(id="edge", source="same", target="same")]))
    assert not report.can_save
    assert "SELF_LOOP" in codes(report.structural.errors)


def test_unknown_node_type_is_a_structural_error() -> None:
    report = validate_workflow(definition([node("custom", "utility.unregistered")]))
    assert not report.can_save
    assert codes(report.structural.errors) == {"UNREGISTERED_NODE_TYPE"}


def test_injected_registry_is_used_for_validation() -> None:
    metadata = NODE_TYPE_REGISTRY.get("trigger.manual")
    assert metadata is not None
    registry = NodeTypeRegistry([metadata.model_copy(update={"type": "trigger.custom"})])
    report = validate_workflow(definition([node("start", "trigger.custom")]), registry)
    assert report.execution_readiness.valid


def test_missing_trigger_and_incomplete_config_do_not_block_saving() -> None:
    report = validate_workflow(definition([node("http", "action.http_request")]))
    assert report.can_save and report.structural.valid
    assert "MISSING_TRIGGER" in codes(report.execution_readiness.errors)


def test_isolated_and_unreachable_nodes_are_reported_without_blocking_draft() -> None:
    nodes = [node("start", "trigger.manual"), node("isolated"), node("orphan_a"), node("orphan_b")]
    report = validate_workflow(definition(nodes, [Edge(id="edge", source="orphan_a", target="orphan_b")]))
    assert report.can_save
    assert {issue.node_id for issue in report.execution_readiness.errors if issue.code == "DISCONNECTED_NODE"} == {"start", "isolated"}
    assert {issue.node_id for issue in report.execution_readiness.errors if issue.code == "UNREACHABLE_NODE"} == {"isolated", "orphan_a", "orphan_b"}


def test_cycle_can_be_saved_as_a_draft_but_is_never_ready() -> None:
    nodes = [node("start", "trigger.manual"), node("next")]
    edges = [Edge(id="1", source="start", target="next"), Edge(id="2", source="next", target="start")]
    report = validate_workflow(definition(nodes, edges))
    assert report.can_save and report.structural.valid
    assert not report.execution_readiness.valid
    assert codes(report.execution_readiness.errors) == {"CYCLE_DETECTED"}


def test_cycles_in_components_unreachable_from_a_trigger_are_detected() -> None:
    nodes = [node("start", "trigger.manual"), node("a"), node("b")]
    edges = [Edge(id="1", source="a", target="b"), Edge(id="2", source="b", target="a")]
    report = validate_workflow(definition(nodes, edges))
    assert "CYCLE_DETECTED" in codes(report.execution_readiness.errors)
    assert "UNREACHABLE_NODE" in codes(report.execution_readiness.errors)


def test_large_dag_does_not_depend_on_python_recursion_limit() -> None:
    nodes = [node("0", "trigger.manual"), *(node(str(i)) for i in range(1, 2000))]
    edges = [Edge(id=str(i), source=str(i - 1), target=str(i)) for i in range(1, 2000)]
    assert validate_workflow(definition(nodes, edges)).execution_readiness.valid


@pytest.mark.parametrize("version", [True, "1", 1.0, 0, 2, None])
def test_schema_version_must_be_supported_and_an_actual_integer(version: object) -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({"schema_version": version, "nodes": [], "edges": []})


def test_explicit_definition_requires_schema_version() -> None:
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({"nodes": [], "edges": []})


@pytest.mark.parametrize("coordinate", [True, "100", float("nan"), float("inf")])
def test_position_rejects_nonfinite_and_nonnumeric_coordinates(coordinate: object) -> None:
    with pytest.raises(ValidationError):
        node("node", position={"x": coordinate, "y": 0})


@pytest.mark.parametrize("config", [{"nested": [float("nan")]}, {"value": float("inf")}, {"value": {1, 2}}, {"value": (1, 2)}, {1: "value"}, []])
def test_config_contains_only_finite_json_values(config: object) -> None:
    with pytest.raises(ValidationError):
        node("node", config=config)


@pytest.mark.parametrize("key", ["password", "api_key", "apiKey", "Authorization", "X-Api-Key", "client_secret", "refresh_token", "private-key"])
def test_plaintext_secret_fields_are_rejected_even_when_nested(key: str) -> None:
    with pytest.raises(ValidationError) as error:
        node("node", config={"nested": [{key: "secret-value"}]})
    assert "secret-value" not in error.value.errors()[0]["msg"]


def test_empty_credential_fields_and_reference_can_be_saved_in_drafts() -> None:
    config = {"password": "", "api_key": None, "credential_ref": "credential-id", "nested": [True, 1, 1.5, None, {"text": "value"}]}
    assert node("node", config=config).model_dump(mode="json")["config"] == config


def test_workflow_creation_trims_name_and_has_independent_empty_draft_defaults() -> None:
    first = WorkflowCreate(name="  New workflow  ")
    second = WorkflowCreate(name="Second")
    assert first.name == "New workflow"
    assert first.definition.model_dump() == {"schema_version": 1, "nodes": [], "edges": []}
    first.definition.nodes.append(node("one"))
    assert second.definition.nodes == []


@pytest.mark.parametrize("name", ["", "   "])
def test_workflow_name_must_not_be_blank(name: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowCreate(name=name)


def test_put_schema_requires_definition_to_avoid_accidental_erasure() -> None:
    with pytest.raises(ValidationError):
        WorkflowUpdate(name="Replacement")


def test_unknown_fields_are_not_silently_dropped() -> None:
    with pytest.raises(ValidationError):
        WorkflowCreate.model_validate({"name": "Test", "unexpected": True})
    with pytest.raises(ValidationError):
        node("node", unexpected=True)


def test_response_schema_can_read_a_database_record_and_normalizes_utc() -> None:
    moment = datetime(2026, 10, 28, 10, tzinfo=timezone(timedelta(hours=8)))
    record = SimpleNamespace(id=uuid4(), name="Workflow", description=None, definition={"schema_version": 1, "nodes": [], "edges": []}, created_at=moment, updated_at=moment)
    response = WorkflowRead.model_validate(record)
    assert response.created_at.utcoffset() == timedelta(0)
    assert response.updated_at.hour == 2
    record.created_at = moment.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        WorkflowRead.model_validate(record)
