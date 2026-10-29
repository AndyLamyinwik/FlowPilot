import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.schemas.workflow import WorkflowDefinition
from app.services.execution.context import ExecutionLimits, NodeExecutionContext
from app.services.execution.engine import ExecutionEngine
from app.services.execution.executor import (
    ExecutorRegistry,
    LoggerExecutor,
    ManualTriggerExecutor,
    NodeExecutionError,
)
from app.services.execution.validation import ExecutionValidationError


def node(node_id: str, node_type: str = "utility.logger", **extra) -> dict:
    return {
        "id": node_id, "type": node_type, "name": node_id,
        "position": {"x": 0, "y": 0}, "config": {}, **extra,
    }


def graph(nodes: list[dict], links: list[tuple[str, str]]) -> dict:
    return {
        "schema_version": 1,
        "nodes": nodes,
        "edges": [
            {"id": str(index), "source": source, "target": target}
            for index, (source, target) in enumerate(links)
        ],
    }


def linear(*ids: str) -> dict:
    nodes = [node(ids[0], "trigger.manual"), *[node(name) for name in ids[1:]]]
    return graph(nodes, list(zip(ids, ids[1:])))


def registry(logger_executor, manual_executor=None) -> ExecutorRegistry:
    result = ExecutorRegistry()
    result.register("trigger.manual", manual_executor or ManualTriggerExecutor())
    result.register("utility.logger", logger_executor)
    return result


class RecordingExecutor:
    def __init__(self):
        self.contexts: list[NodeExecutionContext] = []

    def execute(self, context: NodeExecutionContext):
        self.contexts.append(context)
        return {"node": context.node_id, "upstream": context.input_data}


def test_single_manual_trigger_executes_with_uuid_and_utc_results() -> None:
    workflow_id = uuid4()
    result = ExecutionEngine().execute(workflow_id, linear("start"))
    assert result.status == "success"
    assert isinstance(result.execution_id, UUID) and result.execution_id.version == 4
    assert result.workflow_id == workflow_id
    assert result.started_at.tzinfo == UTC
    assert result.finished_at >= result.started_at
    assert result.error is None
    assert result.node_results[0].output == {"trigger": "manual"}
    assert result.node_results[0].status == "success"
    assert result.node_results[0].finished_at >= result.node_results[0].started_at


@pytest.mark.parametrize("ids", [("start", "a"), ("start", "a", "b")])
def test_linear_workflow_passes_complete_upstream_output(ids: tuple[str]) -> None:
    result = ExecutionEngine().execute(uuid4(), linear(*ids))
    assert [node.node_id for node in result.node_results] == list(ids)
    assert all(node.status == "success" for node in result.node_results)
    expected = {"trigger": "manual"}
    for index, node_result in enumerate(result.node_results):
        if index:
            expected = {ids[index - 1]: expected}
        assert node_result.output == expected


def test_branch_join_waits_for_all_parents_and_executes_each_node_once() -> None:
    recorder = RecordingExecutor()
    definition = graph(
        [node("start", "trigger.manual"), node("a"), node("b"), node("c"), node("join")],
        [("start", "a"), ("a", "b"), ("a", "c"), ("b", "join"), ("c", "join")],
    )
    result = ExecutionEngine(registry(recorder)).execute(uuid4(), definition)
    assert result.status == "success"
    assert [item.node_id for item in recorder.contexts] == ["a", "b", "c", "join"]
    outputs = {item.node_id: item.output for item in result.node_results}
    assert recorder.contexts[-1].input_data == {"b": outputs["b"], "c": outputs["c"]}
    assert len({item.node_id for item in result.node_results}) == 5


def test_ready_node_ties_follow_definition_order_without_ignoring_dependencies() -> None:
    definition = graph(
        [node("b"), node("start", "trigger.manual"), node("z"), node("a"), node("end")],
        [("start", "a"), ("start", "z"), ("a", "b"), ("z", "end"), ("b", "end")],
    )
    result = ExecutionEngine().execute(uuid4(), definition)
    assert [item.node_id for item in result.node_results] == ["start", "z", "a", "b", "end"]


def test_parallel_plain_edges_do_not_repeat_a_node_or_its_input() -> None:
    recorder = RecordingExecutor()
    definition = graph(
        [node("start", "trigger.manual"), node("logger")],
        [("start", "logger"), ("start", "logger")],
    )
    result = ExecutionEngine(registry(recorder)).execute(uuid4(), definition)
    assert result.status == "success"
    assert len(recorder.contexts) == 1
    assert recorder.contexts[0].input_data == {"start": {"trigger": "manual"}}


def test_run_contexts_configs_inputs_and_returned_outputs_do_not_share_mutable_state() -> None:
    class MutatingExecutor:
        def __init__(self):
            self.contexts = []
            self.returned = []

        def execute(self, context):
            assert "changed" not in context.metadata
            assert context.node_config == {"items": []}
            assert context.input_data == {"start": {"trigger": "manual"}}
            self.contexts.append(context)
            context.metadata["changed"] = True
            context.node_config["items"].append("changed")
            context.input_data["start"]["trigger"] = "changed"
            output = {"items": []}
            self.returned.append(output)
            return output

    custom = MutatingExecutor()
    definition = graph(
        [node("start", "trigger.manual"), node("a", config={"items": []}), node("b", config={"items": []})],
        [("start", "a"), ("start", "b")],
    )
    original = deepcopy(definition)
    engine = ExecutionEngine(registry(custom))
    first = engine.execute(uuid4(), definition)
    second = engine.execute(uuid4(), definition)
    assert first.execution_id != second.execution_id
    assert {context.execution_id for context in custom.contexts} == {
        first.execution_id, second.execution_id
    }
    assert first.node_results[0].output == {"trigger": "manual"}
    assert second.node_results[0].output == {"trigger": "manual"}
    custom.returned[0]["items"].append("after return")
    assert first.node_results[1].output == {"items": []}
    assert second.node_results[1].output == {"items": []}
    assert definition == original


def test_deadline_is_forwarded_but_environment_is_not_exposed(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_TEST_SECRET", "not-for-nodes")
    recorder = RecordingExecutor()
    deadline = datetime.now(UTC) + timedelta(minutes=1)
    result = ExecutionEngine(registry(recorder)).execute(
        uuid4(), linear("start", "logger"), deadline=deadline
    )
    context = recorder.contexts[0]
    assert context.deadline == deadline
    assert set(context.metadata) == {"workflow_started_at"}
    assert "not-for-nodes" not in result.model_dump_json()
    assert "SYSTEM_TEST_SECRET" not in repr(context)


def test_controlled_node_failure_preserves_results_and_skips_every_remaining_node() -> None:
    class FailingExecutor:
        def __init__(self):
            self.called = []

        def execute(self, context):
            self.called.append(context.node_id)
            if context.node_id == "bad":
                raise NodeExecutionError("TEST_FAILURE", "The test node failed")
            return context.input_data

    failing = FailingExecutor()
    definition = graph(
        [node("start", "trigger.manual"), node("good"), node("bad"), node("after"), node("independent")],
        [("start", "good"), ("good", "bad"), ("bad", "after"), ("start", "independent")],
    )
    result = ExecutionEngine(registry(failing)).execute(uuid4(), definition)
    assert result.status == "failed"
    assert result.error.code == "TEST_FAILURE" and result.error.node_id == "bad"
    assert failing.called == ["good", "bad"]
    assert [item.status for item in result.node_results] == [
        "success", "success", "failed", "skipped", "skipped"
    ]
    assert result.node_results[1].output == {"start": {"trigger": "manual"}}
    assert result.node_results[2].output is None
    for skipped in result.node_results[3:]:
        assert skipped.started_at is None
        assert skipped.finished_at is not None
        assert skipped.output is None
    assert result.finished_at >= result.started_at


def test_unexpected_errors_do_not_disclose_exception_text_or_tracebacks(caplog) -> None:
    class UnexpectedFailure:
        def execute(self, context):
            raise RuntimeError("hidden-system-secret\nTraceback diagnostic")

    result = ExecutionEngine(registry(UnexpectedFailure())).execute(
        uuid4(), linear("start", "logger", "after")
    )
    assert result.status == "failed"
    assert result.error.code == "NODE_EXECUTION_FAILED"
    assert "hidden-system-secret" not in result.model_dump_json()
    assert "Traceback" not in result.model_dump_json()
    assert "hidden-system-secret" not in caplog.text


@pytest.mark.parametrize("output", [float("nan"), object(), ("not", "json")])
def test_invalid_node_output_becomes_a_structured_failure(output: object) -> None:
    class InvalidOutput:
        def execute(self, context):
            return output

    result = ExecutionEngine(registry(InvalidOutput())).execute(
        uuid4(), linear("start", "logger", "after")
    )
    assert result.status == "failed"
    assert result.error.code == "INVALID_NODE_OUTPUT"
    assert result.node_results[-1].status == "skipped"


def test_aggregate_output_budget_preserves_successful_results_and_fails_fast() -> None:
    manual_size = len(json.dumps({"trigger": "manual"}, separators=(",", ":")).encode())
    result = ExecutionEngine(limits=ExecutionLimits(max_output_bytes=manual_size + 1)).execute(
        uuid4(), linear("start", "a", "b")
    )
    assert result.status == "failed" and result.error.code == "OUTPUT_LIMIT_EXCEEDED"
    assert [item.status for item in result.node_results] == ["success", "failed", "skipped"]
    assert result.node_results[0].output == {"trigger": "manual"}


@pytest.mark.parametrize("invalid_kind", ["unsupported", "cycle", "handles", "node_limit"])
def test_preflight_finishes_before_any_executor_is_invoked(invalid_kind: str) -> None:
    class CountingManual:
        calls = 0

        def execute(self, context):
            self.calls += 1
            return {"trigger": "manual"}

    manual = CountingManual()
    definition = linear("start", "a", "b")
    limits = ExecutionLimits()
    if invalid_kind == "unsupported":
        definition["nodes"][-1]["type"] = "logic.condition"
    elif invalid_kind == "cycle":
        definition["edges"].append({"id": "cycle", "source": "b", "target": "a"})
    elif invalid_kind == "handles":
        definition["edges"][-1]["source_handle"] = "true"
    elif invalid_kind == "node_limit":
        limits = ExecutionLimits(max_nodes=2)
    with pytest.raises(ExecutionValidationError):
        ExecutionEngine(registry(LoggerExecutor(), manual), limits).execute(uuid4(), definition)
    assert manual.calls == 0


def test_engine_revalidates_mutated_models_instead_of_executing_invalid_snapshots() -> None:
    definition = WorkflowDefinition.model_validate(linear("start", "a"))
    definition.schema_version = 99
    with pytest.raises(ExecutionValidationError) as raised:
        ExecutionEngine().execute(uuid4(), definition)
    assert raised.value.errors[0].code == "INVALID_WORKFLOW_DEFINITION"


def test_long_chain_stops_at_output_depth_limit_with_a_serializable_failure() -> None:
    ids = ["start", *[f"n{index}" for index in range(1, 256)]]
    result = ExecutionEngine().execute(uuid4(), linear(*ids))
    assert result.status == "failed"
    assert result.error.code == "INVALID_NODE_OUTPUT"
    assert all(item.status == "success" for item in result.node_results[:64])
    assert result.node_results[64].status == "failed"
    assert all(item.status == "skipped" for item in result.node_results[65:])
    assert json.loads(result.model_dump_json())["execution_id"] == str(result.execution_id)
