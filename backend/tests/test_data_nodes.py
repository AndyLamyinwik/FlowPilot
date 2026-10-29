from copy import deepcopy
from uuid import uuid4

import pytest

from app.services.execution.context import NodeExecutionContext
from app.services.execution.data_nodes import ConditionExecutor, TransformExecutor
from app.services.execution.executor import NodeExecutionError


def context(config: dict, output=None) -> NodeExecutionContext:
    return NodeExecutionContext(
        execution_id=uuid4(), workflow_id=uuid4(), node_id="node",
        node_config=config, input_data={"source": output},
    )


def condition_config(operator: str, value=1, field="value") -> dict:
    return {"source_node_id": "source", "field": field, "operator": operator, "value": value}


@pytest.mark.parametrize("operator,actual,expected,matched", [
    ("equals", "success", "success", True),
    ("equals", False, 0, False),
    ("equals", {"a": [True]}, {"a": [1]}, False),
    ("equals", 1, 1.0, True),
    ("not_equals", "success", "failure", True),
    ("not_equals", None, None, False),
    ("greater_than", 95, 90, True),
    ("greater_than", 90, 95, False),
    ("greater_than_or_equal", 95, 95, True),
    ("less_than", 90, 95, True),
    ("less_than_or_equal", 95, 95, True),
    ("contains", "FlowPilot", "Pilot", True),
    ("contains", ["a", {"n": 2}], {"n": 2}, True),
    ("contains", [True], 1, False),
    ("contains", {"name": "Andy"}, "name", True),
    ("contains", {"name": "Andy"}, "missing", False),
])
def test_condition_operators_have_explicit_json_semantics(operator, actual, expected, matched) -> None:
    invocation = context(condition_config(operator, expected), {"value": actual})
    assert ConditionExecutor().execute(invocation) == {"matched": matched}


def test_condition_reads_nested_array_fields() -> None:
    invocation = context(
        condition_config("equals", "Andy", "body.users.0.name"),
        {"body": {"users": [{"name": "Andy"}]}},
    )
    assert ConditionExecutor().execute(invocation) == {"matched": True}


@pytest.mark.parametrize("output,matched", [({}, False), ({"value": None}, True), ({"value": False}, True)])
def test_exists_checks_presence_not_truthiness_and_needs_no_value(output, matched) -> None:
    invocation = context({"source_node_id": "source", "field": "value", "operator": "exists"}, output)
    assert ConditionExecutor().execute(invocation) == {"matched": matched}


def test_missing_field_is_a_clear_runtime_failure_for_comparison() -> None:
    with pytest.raises(NodeExecutionError) as caught:
        ConditionExecutor().execute(context(condition_config("equals"), {}))
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"


@pytest.mark.parametrize("operator,actual,expected", [
    ("greater_than", "95", 90), ("less_than", True, 3),
    ("contains", None, "text"), ("contains", "text", 1),
])
def test_condition_type_mismatch_is_not_silently_coerced(operator, actual, expected) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        ConditionExecutor().execute(context(condition_config(operator, expected), {"value": actual}))
    assert caught.value.code == "CONDITION_TYPE_MISMATCH"


def test_condition_can_compare_finite_integers_larger_than_float_range() -> None:
    huge = 10 ** 1000
    invocation = context(condition_config("greater_than", huge - 1), {"value": huge})
    assert ConditionExecutor().execute(invocation) == {"matched": True}


@pytest.mark.parametrize("config", [
    {}, {"source_node_id": "source", "operator": "unsupported-operator"},
    {"source_node_id": "source", "operator": "equals"},
    {"source_node_id": "source", "operator": "exists", "extra": "sensitive-value"},
])
def test_invalid_condition_configuration_is_rejected_without_input_echo(config) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        ConditionExecutor().validate_config(config, {"source"})
    assert caught.value.code == "INVALID_CONDITION_CONFIG"
    assert "sensitive-value" not in str(caught.value)


def test_condition_reference_validation_is_pure_and_checks_ancestry() -> None:
    executor = ConditionExecutor()
    executor.validate_config(condition_config("equals", 1, "future.field"), {"source"})
    with pytest.raises(NodeExecutionError) as caught:
        executor.validate_config(condition_config("equals"), {"another"})
    assert caught.value.code == "INVALID_DATA_SOURCE"


def test_transform_extracts_renames_static_and_complete_outputs_without_mutation() -> None:
    source = {"body": {"user": {"name": "Andy", "score": 95}}, "items": [1, 2]}
    config = {"mapping": {
        "username": {"source_node_id": "source", "path": "body.user.name"},
        "points": {"source_node_id": "source", "path": "body.user.score"},
        "source": {"value": "FlowPilot"},
        "full": {"source_node_id": "source"},
        "static_nested": {"value": {"enabled": False}},
    }}
    original_source, original_config = deepcopy(source), deepcopy(config)
    executor = TransformExecutor()
    executor.validate_config(config, {"source"})
    output = executor.execute(context(config, source))
    assert output["username"] == "Andy" and output["points"] == 95
    assert output["source"] == "FlowPilot" and output["full"] == source
    output["full"]["items"].append(3)
    output["static_nested"]["enabled"] = True
    assert source == original_source and config == original_config


@pytest.mark.parametrize("fallback", [None, False, 0, "", {"nested": [1]}])
def test_transform_explicit_missing_field_defaults_are_preserved(fallback) -> None:
    config = {"mapping": {"result": {"source_node_id": "source", "path": "missing", "default": fallback}}}
    assert TransformExecutor().execute(context(config, {})) == {"result": fallback}


def test_transform_missing_field_without_default_fails() -> None:
    config = {"mapping": {"result": {"source_node_id": "source", "path": "missing"}}}
    with pytest.raises(NodeExecutionError) as caught:
        TransformExecutor().execute(context(config, {}))
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"


def test_transform_default_does_not_replace_existing_null_or_missing_sources() -> None:
    config = {"mapping": {"result": {"source_node_id": "source", "path": "value", "default": "fallback"}}}
    assert TransformExecutor().execute(context(config, {"value": None})) == {"result": None}
    invocation = context(config, {})
    invocation.input_data.clear()
    with pytest.raises(NodeExecutionError) as caught:
        TransformExecutor().execute(invocation)
    assert caught.value.code == "DATA_SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("config", [
    {}, {"mapping": []}, {"mapping": {"": {"value": 1}}},
    {"mapping": {"both": {"value": 1, "source_node_id": "source"}}},
    {"mapping": {"missing": {"path": "value"}}},
    {"mapping": {"bad": {"value": float("nan")}}},
])
def test_invalid_transform_mapping_is_rejected_before_execution(config) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        TransformExecutor().validate_config(config, {"source"})
    assert caught.value.code == "INVALID_TRANSFORM_CONFIG"


def test_transform_rejects_invalid_source_and_path_during_readiness() -> None:
    executor = TransformExecutor()
    config = {"mapping": {"result": {"source_node_id": "other"}}}
    with pytest.raises(NodeExecutionError) as caught:
        executor.validate_config(config, {"source"})
    assert caught.value.code == "INVALID_DATA_SOURCE"
    config["mapping"]["result"] = {"source_node_id": "source", "path": "items[0]"}
    with pytest.raises(NodeExecutionError) as caught:
        executor.validate_config(config, {"source"})
    assert caught.value.code == "INVALID_DATA_PATH"


def test_empty_mapping_is_a_valid_empty_json_object() -> None:
    config = {"mapping": {}}
    TransformExecutor().validate_config(config, set())
    assert TransformExecutor().execute(context(config, None)) == {}
