from copy import deepcopy

import pytest

from app.schemas.workflow import WorkflowDefinition
from app.services.execution.context import ExecutionLimits
from app.services.execution.executor import create_default_executor_registry
from app.services.execution.validation import (
    ExecutionValidationError,
    prepare_definition,
    validate_execution_readiness,
)
from app.services.workflow_validation import validate_workflow


def node(node_id: str, node_type: str = "utility.logger") -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 0, "y": 0},
        "config": {},
    }


def graph(nodes: list[dict], edges: list[dict] | None = None) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {"schema_version": 1, "nodes": nodes, "edges": edges or []}
    )


def edge(source: str, target: str, edge_id: str = "edge", **handles) -> dict:
    return {"id": edge_id, "source": source, "target": target, **handles}


def errors(definition: WorkflowDefinition, limits: ExecutionLimits | None = None) -> set[str]:
    report = validate_execution_readiness(
        definition, create_default_executor_registry(), limits or ExecutionLimits()
    )
    return {issue.code for issue in report.errors}


def test_single_manual_trigger_is_executable() -> None:
    assert errors(graph([node("start", "trigger.manual")])) == set()


@pytest.mark.parametrize("nodes", [[], [node("logger")]])
def test_draft_without_manual_trigger_is_not_executable(nodes: list[dict]) -> None:
    definition = graph(nodes)
    assert validate_workflow(definition).can_save
    assert "MISSING_MANUAL_TRIGGER" in errors(definition)


def test_multiple_manual_triggers_are_not_executable() -> None:
    definition = graph(
        [node("first", "trigger.manual"), node("second", "trigger.manual")],
        [edge("first", "second")],
    )
    assert "MULTIPLE_MANUAL_TRIGGERS" in errors(definition)


def test_manual_trigger_cannot_have_upstream_nodes() -> None:
    definition = graph(
        [node("before"), node("start", "trigger.manual")],
        [edge("before", "start")],
    )
    assert "MANUAL_TRIGGER_HAS_UPSTREAM" in errors(definition)


def test_cycle_stays_saveable_as_a_draft_but_cannot_execute() -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("a"), node("b")],
        [edge("start", "a", "1"), edge("a", "b", "2"), edge("b", "a", "3")],
    )
    assert validate_workflow(definition).can_save
    assert "CYCLE_DETECTED" in errors(definition)


def test_dangling_reference_is_a_pre_execution_error() -> None:
    definition = graph([node("start", "trigger.manual")], [edge("start", "missing")])
    assert errors(definition) == {"INVALID_NODE_REFERENCE"}


@pytest.mark.parametrize(
    "node_type",
    ["trigger.schedule"],
)
def test_schedule_nodes_cannot_execute_in_manual_mode(node_type: str) -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("unsupported", node_type)],
        [edge("start", "unsupported")],
    )
    assert validate_workflow(definition).can_save
    assert "TRIGGER_TYPE_MISMATCH" in errors(definition)


@pytest.mark.parametrize("node_type,code", [
    ("action.http_request", "INVALID_NODE_CONFIG"),
    ("logic.condition", "INVALID_CONDITION_CONFIG"),
    ("data.transform", "INVALID_TRANSFORM_CONFIG"),
    ("action.webhook", "INVALID_NODE_CONFIG"),
])
def test_unconfigured_core_nodes_stay_saveable_but_are_not_ready(node_type: str, code: str) -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("unconfigured", node_type)],
        [edge("start", "unconfigured")],
    )
    assert validate_workflow(definition).can_save
    issue_codes = errors(definition)
    assert code in issue_codes
    assert "UNSUPPORTED_NODE_EXECUTOR" not in issue_codes


def test_nodes_must_be_reachable_from_the_manual_trigger() -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("a"), node("orphan"), node("child")],
        [edge("start", "a", "1"), edge("orphan", "child", "2")],
    )
    report = validate_execution_readiness(
        definition, create_default_executor_registry(), ExecutionLimits()
    )
    assert {issue.node_id for issue in report.errors if issue.code == "UNREACHABLE_NODE"} == {
        "orphan", "child"
    }


@pytest.mark.parametrize("handle", ["source_handle", "target_handle"])
def test_edge_handles_remain_saveable_but_are_not_executable(handle: str) -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("logger")],
        [edge("start", "logger", **{handle: "future-port"})],
    )
    assert validate_workflow(definition).can_save
    assert "UNSUPPORTED_EDGE_HANDLE" in errors(definition)


def test_execution_node_limit_does_not_change_draft_saving() -> None:
    definition = graph(
        [node("start", "trigger.manual"), node("a"), node("b")],
        [edge("start", "a", "1"), edge("a", "b", "2")],
    )
    assert validate_workflow(definition).can_save
    assert errors(definition, ExecutionLimits(max_nodes=2)) == {"EXECUTION_NODE_LIMIT_EXCEEDED"}


@pytest.mark.parametrize("case,code", [
    ("duplicate_node", "DUPLICATE_NODE_ID"),
    ("duplicate_edge", "DUPLICATE_EDGE_ID"),
    ("self_loop", "SELF_LOOP"),
    ("unknown_type", "UNREGISTERED_NODE_TYPE"),
])
def test_structural_validation_is_reused_before_execution(case: str, code: str) -> None:
    raw = {
        "schema_version": 1,
        "nodes": [node("start", "trigger.manual"), node("a")],
        "edges": [edge("start", "a")],
    }
    if case == "duplicate_node":
        raw["nodes"].append(deepcopy(raw["nodes"][0]))
    elif case == "duplicate_edge":
        raw["edges"].append(deepcopy(raw["edges"][0]))
    elif case == "self_loop":
        raw["edges"][0]["target"] = "start"
    elif case == "unknown_type":
        raw["nodes"][1]["type"] = "unknown.type"
    assert code in errors(WorkflowDefinition.model_validate(raw))


@pytest.mark.parametrize("version", [2, True, "1", None])
def test_definition_shape_and_version_are_revalidated(version: object) -> None:
    with pytest.raises(ExecutionValidationError) as raised:
        prepare_definition({"schema_version": version, "nodes": [], "edges": []})
    assert raised.value.errors[0].code == "INVALID_WORKFLOW_DEFINITION"


def test_mutated_pydantic_model_is_not_trusted_at_the_engine_boundary() -> None:
    definition = graph([node("start", "trigger.manual")])
    definition.schema_version = 2
    with pytest.raises(ExecutionValidationError):
        prepare_definition(definition)


def test_prepared_definition_is_detached_from_the_original() -> None:
    definition = graph([node("start", "trigger.manual")])
    definition.nodes[0].config = {"nested": ["original"]}
    snapshot = prepare_definition(definition)
    snapshot.nodes[0].config["nested"].append("changed")
    assert definition.nodes[0].config == {"nested": ["original"]}
