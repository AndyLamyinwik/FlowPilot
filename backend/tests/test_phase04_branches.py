from copy import deepcopy
from uuid import uuid4

import pytest

from app.services.execution.data_nodes import ConditionExecutor, TransformExecutor
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import (
    ExecutorRegistry,
    LoggerExecutor,
    ManualTriggerExecutor,
)


def node(node_id: str, node_type: str = "utility.logger", config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge(source: str, target: str, handle: str | None = None, *, suffix: str = "") -> dict:
    return {
        "id": f"{source}-{target}{suffix}",
        "source": source,
        "target": target,
        "source_handle": handle,
        "target_handle": None,
    }


def graph(nodes: list[dict], edges: list[dict]) -> dict:
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def base_nodes(matched: bool) -> list[dict]:
    return [
        node("manual", "trigger.manual"),
        node("seed", "data.transform", {"mapping": {"flag": {"value": matched}}}),
        node("condition", "logic.condition", {
            "source_node_id": "seed", "field": "flag", "operator": "equals", "value": True,
        }),
    ]


def base_edges() -> list[dict]:
    return [edge("manual", "seed"), edge("seed", "condition")]


def registry(condition=None) -> ExecutorRegistry:
    catalog = ExecutorRegistry()
    catalog.register("trigger.manual", ManualTriggerExecutor())
    catalog.register("utility.logger", LoggerExecutor())
    catalog.register("data.transform", TransformExecutor())
    catalog.register("logic.condition", condition if condition is not None else ConditionExecutor())
    return catalog


def execute(definition: dict, *, condition=None):
    return ExecutionEngine(registry=registry(condition)).execute(uuid4(), definition)


def results(result):
    return {item.node_id: item for item in result.node_results}


@pytest.mark.parametrize("matched", [True, False])
def test_only_selected_branch_executes_and_join_continues(matched: bool) -> None:
    definition = graph(
        [node("join"), *base_nodes(matched), node("yes"), node("no"), node("tail")],
        [
            *base_edges(), edge("condition", "yes", "true"),
            edge("condition", "no", "false"), edge("yes", "join"),
            edge("no", "join"), edge("join", "tail"),
        ],
    )
    result = execute(definition)
    by_id = results(result)
    selected, skipped = ("yes", "no") if matched else ("no", "yes")
    assert result.status == "success"
    assert by_id[selected].status == "success"
    assert by_id[skipped].status == "skipped"
    assert by_id[skipped].started_at is None
    assert by_id[skipped].output is None and by_id[skipped].error is None
    assert by_id["join"].status == by_id["tail"].status == "success"
    assert by_id["join"].output == {selected: {"condition": {"matched": matched}}}
    assert [item.node_id for item in result.node_results].count("join") == 1
    assert len({item.node_id for item in result.node_results}) == len(definition["nodes"])


@pytest.mark.parametrize("matched", [True, False])
def test_opposite_condition_handles_to_same_target_activate_it_only_once(matched: bool) -> None:
    result = execute(graph(
        [*base_nodes(matched), node("join")],
        [*base_edges(), edge("condition", "join", "true", suffix="-true"),
         edge("condition", "join", "false", suffix="-false")],
    ))
    by_id = results(result)
    assert result.status == "success"
    assert by_id["join"].status == "success"
    assert by_id["join"].output == {"condition": {"matched": matched}}
    assert [item.node_id for item in result.node_results].count("join") == 1


def test_inactive_path_skips_its_entire_descendant_chain_without_failure() -> None:
    result = execute(graph(
        [*base_nodes(False), node("first"), node("second"), node("join")],
        [*base_edges(), edge("condition", "first", "true"),
         edge("first", "second"), edge("second", "join")],
    ))
    by_id = results(result)
    assert result.status == "success" and result.error is None
    assert [by_id[name].status for name in ("first", "second", "join")] == ["skipped"] * 3
    assert all(by_id[name].started_at is None for name in ("first", "second", "join"))


def test_join_uses_only_active_edge_even_when_inactive_source_succeeded() -> None:
    result = execute(graph(
        [node("join"), *base_nodes(False)],
        [*base_edges(), edge("seed", "join"), edge("condition", "join", "true")],
    ))
    by_id = results(result)
    assert result.status == "success"
    assert by_id["condition"].status == "success"
    assert by_id["join"].output == {"seed": {"flag": False}}
    order = [item.node_id for item in result.node_results]
    assert order.index("condition") < order.index("join")


def test_successful_node_without_an_active_path_is_not_a_visible_data_source() -> None:
    join = node("join", "data.transform", {
        "mapping": {"branch": {"source_node_id": "condition", "path": "matched"}},
    })
    result = execute(graph(
        [join, *base_nodes(False)],
        [*base_edges(), edge("seed", "join"), edge("condition", "join", "true")],
    ))
    by_id = results(result)
    assert by_id["condition"].status == "success"
    assert by_id["join"].status == "failed"
    assert by_id["join"].error.code == "DATA_SOURCE_UNAVAILABLE"
    assert result.status == "failed"


def test_join_waits_for_all_skipped_parent_states_before_running() -> None:
    definition = graph(
        [node("join"), *base_nodes(True), node("fast"), node("skip_a"), node("skip_b")],
        [*base_edges(), edge("condition", "fast", "true"),
         edge("condition", "skip_a", "false"), edge("skip_a", "skip_b"),
         edge("fast", "join"), edge("skip_b", "join")],
    )
    result = execute(definition)
    by_id = results(result)
    order = [item.node_id for item in result.node_results]
    assert result.status == "success"
    assert by_id["skip_a"].status == by_id["skip_b"].status == "skipped"
    assert order.index("fast") < order.index("join")
    assert order.index("skip_b") < order.index("join")
    assert set(by_id["join"].output) == {"fast"}


def test_nested_condition_preserves_skips_and_selected_join_inputs() -> None:
    nested = node("nested", "logic.condition", {
        "source_node_id": "seed", "field": "flag", "operator": "equals", "value": False,
    })
    result = execute(graph(
        [*base_nodes(True), nested, node("outer_no"), node("nested_yes"),
         node("nested_no"), node("join")],
        [*base_edges(), edge("condition", "nested", "true"),
         edge("condition", "outer_no", "false"),
         edge("nested", "nested_yes", "true"), edge("nested", "nested_no", "false"),
         edge("outer_no", "join"), edge("nested_yes", "join"), edge("nested_no", "join")],
    ))
    by_id = results(result)
    assert result.status == "success"
    assert by_id["nested"].output == {"matched": False}
    assert by_id["outer_no"].status == by_id["nested_yes"].status == "skipped"
    assert by_id["nested_no"].status == by_id["join"].status == "success"
    assert by_id["join"].output == {"nested_no": {"nested": {"matched": False}}}


@pytest.mark.parametrize("bad_output", [{"matched": "true"}, {"matched": 1}, {}, None])
def test_invalid_condition_output_fails_instead_of_activating_a_branch(bad_output) -> None:
    class BadCondition:
        def execute(self, context):
            return deepcopy(bad_output)

    result = execute(graph(
        [*base_nodes(True), node("yes"), node("no")],
        [*base_edges(), edge("condition", "yes", "true"), edge("condition", "no", "false")],
    ), condition=BadCondition())
    by_id = results(result)
    assert result.status == "failed"
    assert by_id["condition"].status == "failed"
    assert by_id["condition"].error.code == "INVALID_CONDITION_OUTPUT"
    assert by_id["yes"].status == by_id["no"].status == "skipped"


def test_missing_condition_field_is_runtime_failure_and_keeps_completed_results() -> None:
    nodes = base_nodes(True)
    nodes[-1]["config"]["field"] = "missing"
    result = execute(graph(
        [*nodes, node("yes"), node("no")],
        [*base_edges(), edge("condition", "yes", "true"), edge("condition", "no", "false")],
    ))
    by_id = results(result)
    assert result.status == "failed"
    assert by_id["manual"].status == by_id["seed"].status == "success"
    assert by_id["condition"].error.code == "DATA_FIELD_NOT_FOUND"
    assert by_id["yes"].status == by_id["no"].status == "skipped"
