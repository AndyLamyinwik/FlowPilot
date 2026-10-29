import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.execution import NodeExecutionResult, WorkflowExecutionResult
from app.services.execution.context import ExecutionLimits, NodeExecutionContext
from app.services.execution.executor import (
    ExecutorRegistry,
    LoggerExecutor,
    MAX_OUTPUT_DEPTH,
    ManualTriggerExecutor,
    NodeExecutionError,
    create_default_executor_registry,
    normalize_output,
)


def context(**changes) -> NodeExecutionContext:
    values = {
        "execution_id": uuid4(),
        "workflow_id": uuid4(),
        "node_id": "logger",
        "node_config": {},
        "input_data": {},
    }
    values.update(changes)
    return NodeExecutionContext(**values)


def test_manual_trigger_returns_fresh_json_without_reading_config_or_input() -> None:
    executor = ManualTriggerExecutor()
    invocation = context(node_config={"ignored": "config"}, input_data={"ignored": []})
    first = executor.execute(invocation)
    assert first == {"trigger": "manual"}
    first["mutated"] = True
    assert executor.execute(invocation) == {"trigger": "manual"}


@pytest.mark.parametrize("input_data", [{}, {"source": None}, {"left": {"n": 1}, "right": [2]}])
def test_logger_passes_json_input_through_without_mutating_it(input_data: dict) -> None:
    invocation = context(input_data=input_data)
    output = LoggerExecutor().execute(invocation)
    assert output is input_data


def test_logger_logs_identifiers_without_payload_config_or_environment(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "test-only-secret-must-not-be-logged"
    monkeypatch.setenv("FLOWPILOT_TEST_SECRET", secret)
    invocation = context(
        node_id="logger\nforged-event",
        node_config={"message": secret},
        input_data={"upstream": {"payload": secret}},
        metadata={"ignored": secret},
    )
    with caplog.at_level(logging.INFO, logger="flowpilot.execution"):
        output = LoggerExecutor().execute(invocation)
    assert output == invocation.input_data
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert str(invocation.execution_id) in message
    assert str(invocation.workflow_id) in message
    assert "logger\\nforged-event" in message
    assert "\n" not in message
    assert secret not in message
    assert "payload" not in message and "message=" not in message


def test_default_registries_are_fresh_and_support_core_node_types() -> None:
    first = create_default_executor_registry()
    second = create_default_executor_registry()
    assert isinstance(first.get("trigger.manual"), ManualTriggerExecutor)
    assert isinstance(first.get("utility.logger"), LoggerExecutor)
    assert first.get("utility.logger") is not second.get("utility.logger")
    for implemented in (
        "action.http_request", "logic.condition", "data.transform", "action.webhook", "trigger.schedule",
    ):
        assert implemented in first
        assert first.get(implemented) is not second.get(implemented)
    for unsupported in ("ai.summarize",):
        assert unsupported not in first
        assert first.get(unsupported) is None

    first.register("utility.test", LoggerExecutor())
    assert "utility.test" in first and "utility.test" not in second


def test_registry_rejects_duplicates_without_overwriting_original_executor() -> None:
    registry = ExecutorRegistry()
    original = LoggerExecutor()
    registry.register("utility.logger", original)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("utility.logger", ManualTriggerExecutor())
    assert registry.get("utility.logger") is original


@pytest.mark.parametrize("type_name", ["", " ", " utility.logger", "utility.logger "])
def test_registry_requires_an_explicit_nonblank_identifier(type_name: str) -> None:
    with pytest.raises(ValueError):
        ExecutorRegistry().register(type_name, LoggerExecutor())


def test_registry_rejects_objects_without_an_executor_method() -> None:
    with pytest.raises(TypeError, match="execute method"):
        ExecutorRegistry().register("utility.invalid", object())


@pytest.mark.parametrize("value", [None, True, False, 7, -3, 1.5, "資料", [], {}, {"upstream": [1, False, None, "☃"]}])
def test_output_normalizer_accepts_finite_json_and_counts_exact_utf8_bytes(value) -> None:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    normalized, size = normalize_output(value, len(encoded))
    assert normalized == value
    assert size == len(encoded)


def test_output_normalizer_detaches_nested_objects_from_executor_references() -> None:
    original = {"source": {"items": [1, {"value": "first"}]}}
    normalized, _ = normalize_output(original, 1_000)
    original["source"]["items"][1]["value"] = "changed"
    original["source"]["items"].append("new item")
    assert normalized == {"source": {"items": [1, {"value": "first"}]}}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), (1, 2), {1, 2}, b"bytes", {1: "invalid key"}, {"nested": object()}])
def test_output_normalizer_rejects_non_json_or_nonfinite_values_without_echoing_them(value) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        normalize_output(value, 1_000)
    assert caught.value.code == "INVALID_NODE_OUTPUT"
    assert caught.value.public_message == "Node output must contain only finite JSON values"


@pytest.mark.parametrize("kind", ["list", "dict"])
def test_output_normalizer_rejects_reference_cycles_without_hanging(kind: str) -> None:
    if kind == "list":
        circular = []
        circular.append(circular)
    else:
        circular = {}
        circular["self"] = circular
    with pytest.raises(NodeExecutionError) as caught:
        normalize_output(circular, 10_000)
    assert caught.value.code == "INVALID_NODE_OUTPUT"


def test_output_normalizer_handles_shared_but_acyclic_values() -> None:
    shared = {"value": [1, 2]}
    normalized, _ = normalize_output({"left": shared, "right": shared}, 1_000)
    assert normalized == {"left": {"value": [1, 2]}, "right": {"value": [1, 2]}}
    assert normalized["left"] is not normalized["right"]


def test_output_normalizer_returns_controlled_error_for_excessive_nesting() -> None:
    value = None
    for _ in range(2_000):
        value = [value]
    with pytest.raises(NodeExecutionError) as caught:
        normalize_output(value, 100_000)
    assert caught.value.code == "INVALID_NODE_OUTPUT"


def test_supported_output_nesting_boundary_remains_serializable_in_api_results() -> None:
    value = None
    for _ in range(MAX_OUTPUT_DEPTH):
        value = [value]
    normalized, _ = normalize_output(value, 100_000)
    result = WorkflowExecutionResult(
        execution_id=uuid4(), workflow_id=uuid4(), started_at=datetime.now(UTC),
        node_results=[NodeExecutionResult(node_id="nested", status="success", output=normalized)],
    )
    assert json.loads(result.model_dump_json())["node_results"][0]["output"] == value
    with pytest.raises(NodeExecutionError) as caught:
        normalize_output([value], 100_000)
    assert caught.value.code == "INVALID_NODE_OUTPUT"
    assert "nesting depth" in caught.value.public_message


@pytest.mark.parametrize("value,budget", [(None, 0), ("hello", 4), ({"too-long-key": None}, 4), (list(range(100)), 10), ("資料", 7)])
def test_output_normalizer_enforces_output_budget_including_unicode(value, budget: int) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        normalize_output(value, budget)
    assert caught.value.code == "OUTPUT_LIMIT_EXCEEDED"
    assert caught.value.public_message == "Execution output size limit exceeded"


@pytest.mark.parametrize("budget", [-1, True, 1.5])
def test_output_normalizer_rejects_invalid_internal_budget_configuration(budget) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        normalize_output({}, budget)


@pytest.mark.parametrize("field", ["max_nodes", "max_output_bytes"])
@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_execution_limits_must_be_positive_integers(field: str, invalid) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        ExecutionLimits(**{field: invalid})


def test_context_metadata_defaults_are_not_shared_and_deadline_is_optional() -> None:
    first, second = context(), context()
    first.metadata["test"] = "first invocation"
    assert second.metadata == {}
    assert first.deadline is None


def test_execution_results_use_aware_utc_timestamps_and_independent_node_lists() -> None:
    offset = timezone(timedelta(hours=8))
    started = datetime(2026, 10, 28, 12, tzinfo=offset)
    node = NodeExecutionResult(node_id="manual", status="success", started_at=started, finished_at=started)
    result = WorkflowExecutionResult(execution_id=uuid4(), workflow_id=uuid4(), started_at=started, node_results=[node])
    assert node.started_at.tzinfo == UTC
    assert node.finished_at.tzinfo == UTC
    assert result.started_at == started.astimezone(UTC)
    second = WorkflowExecutionResult(execution_id=uuid4(), workflow_id=uuid4(), started_at=started)
    result.node_results.append(NodeExecutionResult(node_id="other"))
    assert second.node_results == []
    with pytest.raises(ValidationError):
        NodeExecutionResult(node_id="invalid", started_at=started.replace(tzinfo=None))
