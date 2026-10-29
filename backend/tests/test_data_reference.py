from types import SimpleNamespace

import pytest

from app.services.execution.data_reference import (
    reference_exists,
    resolve_reference,
    validate_reference,
)
from app.services.execution.executor import NodeExecutionError


def context(input_data=None, ancestor_outputs=None):
    return SimpleNamespace(
        input_data=input_data or {}, ancestor_outputs=ancestor_outputs or {}
    )


def test_reference_reads_nested_object_array_and_literal_unicode_keys() -> None:
    invocation = context({"http": {"body": {"使用者": [{"display-name": "Andy"}]}}})
    assert resolve_reference(invocation, "http", "body.使用者.0.display-name") == "Andy"


@pytest.mark.parametrize("path", [None, ""])
def test_omitted_path_returns_a_detached_complete_output(path) -> None:
    original = {"values": [1, {"enabled": False}]}
    invocation = context({"source": original})
    resolved = resolve_reference(invocation, "source", path)
    resolved["values"][1]["enabled"] = True
    assert original == {"values": [1, {"enabled": False}]}


def test_visible_ancestors_are_available_without_adding_them_to_immediate_input() -> None:
    invocation = context(
        {"condition": {"matched": True}},
        {"http": {"body": {"score": 95}}, "condition": {"matched": True}},
    )
    assert resolve_reference(invocation, "http", "body.score") == 95
    assert invocation.input_data == {"condition": {"matched": True}}


def test_source_not_visible_to_this_execution_cannot_be_read() -> None:
    invocation = context({"selected": {"value": 1}})
    for action in (
        lambda: resolve_reference(invocation, "other-workflow", default={}),
        lambda: reference_exists(invocation, "inactive-branch", "value"),
    ):
        with pytest.raises(NodeExecutionError) as caught:
            action()
        assert caught.value.code == "DATA_SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_present_values_are_preserved_and_do_not_use_the_default(value) -> None:
    invocation = context({"source": {"value": value}})
    assert reference_exists(invocation, "source", "value") is True
    assert resolve_reference(invocation, "source", "value", default="fallback") == value


def test_missing_fields_are_distinct_from_json_null() -> None:
    invocation = context({"source": {"null": None, "items": [None]}})
    assert reference_exists(invocation, "source", "missing") is False
    assert reference_exists(invocation, "source", "items.1") is False
    assert reference_exists(invocation, "source", "null") is True
    with pytest.raises(NodeExecutionError) as caught:
        resolve_reference(invocation, "source", "missing")
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"


def test_very_large_array_index_is_a_clear_missing_field() -> None:
    invocation = context({"source": {"items": [1]}})
    path = "items." + "9" * 5_000
    assert reference_exists(invocation, "source", path) is False
    with pytest.raises(NodeExecutionError) as caught:
        resolve_reference(invocation, "source", path)
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"


def test_explicit_default_is_detached_and_only_used_for_missing_fields() -> None:
    fallback = {"nested": ["fallback"]}
    resolved = resolve_reference(context({"source": {}}), "source", "missing", default=fallback)
    resolved["nested"].append("changed")
    assert fallback == {"nested": ["fallback"]}
    assert resolve_reference(context({"source": {}}), "source", "missing", default=None) is None


@pytest.mark.parametrize("path", [".body", "body.", "body..name", "body[0]", "$.body", "body. name", "items.-1", True, 12])
def test_malformed_paths_fail_before_runtime_data_is_read(path) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        validate_reference("source", path, {"source"})
    assert caught.value.code == "INVALID_DATA_PATH"


@pytest.mark.parametrize("source", ["missing", "self", "future", " source ", ""])
def test_only_declared_graph_ancestors_are_valid_sources(source: str) -> None:
    with pytest.raises(NodeExecutionError) as caught:
        validate_reference(source, None, {"source"})
    assert caught.value.code == "INVALID_DATA_SOURCE"


def test_reference_validation_does_not_require_runtime_fields_to_exist() -> None:
    validate_reference("source", "body.not_yet_known.0", {"source"})


def test_dictionary_keys_do_not_invoke_attributes_or_expressions() -> None:
    invocation = context({"source": {"__class__": "literal", "a+b": 3}})
    assert resolve_reference(invocation, "source", "__class__") == "literal"
    assert resolve_reference(invocation, "source", "a+b") == 3
    with pytest.raises(NodeExecutionError) as caught:
        resolve_reference(context({"source": "text"}), "source", "__class__")
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"
