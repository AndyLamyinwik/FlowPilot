import math
from copy import deepcopy
from typing import Literal

from pydantic import JsonValue, ValidationError, field_validator, model_validator

from app.schemas.workflow import ApiSchema, Node, NonBlankString
from app.services.execution.context import NodeExecutionContext
from app.services.execution.data_reference import (
    reference_exists,
    resolve_reference,
    validate_reference,
)
from app.services.execution.executor import NodeExecutionError


class ConditionConfig(ApiSchema):
    source_node_id: NonBlankString
    field: str | None = None
    operator: Literal[
        "equals", "not_equals", "greater_than", "greater_than_or_equal",
        "less_than", "less_than_or_equal", "contains", "exists",
    ]
    value: JsonValue = None

    @model_validator(mode="after")
    def require_comparison_value(self) -> "ConditionConfig":
        if self.operator != "exists" and "value" not in self.model_fields_set:
            raise ValueError("Comparison operators require a value")
        return self


class StaticMapping(ApiSchema):
    value: JsonValue


class ReferenceMapping(ApiSchema):
    source_node_id: NonBlankString
    path: str | None = None
    default: JsonValue = None


class TransformConfig(ApiSchema):
    mapping: dict[str, StaticMapping | ReferenceMapping]

    @field_validator("mapping")
    @classmethod
    def validate_output_keys(
        cls, value: dict[str, StaticMapping | ReferenceMapping]
    ) -> dict[str, StaticMapping | ReferenceMapping]:
        if any(not key or key != key.strip() for key in value):
            raise ValueError("Output field names must be nonblank without surrounding whitespace")
        return value


def _condition_config(config: dict) -> ConditionConfig:
    try:
        Node.validate_json_config(config)
        return ConditionConfig.model_validate(config)
    except (ValidationError, ValueError, TypeError, RecursionError, OverflowError):
        raise NodeExecutionError(
            "INVALID_CONDITION_CONFIG", "Condition configuration is invalid"
        ) from None


def _transform_config(config: dict) -> TransformConfig:
    try:
        Node.validate_json_config(config)
        return TransformConfig.model_validate(config)
    except (ValidationError, ValueError, TypeError, RecursionError, OverflowError):
        raise NodeExecutionError(
            "INVALID_TRANSFORM_CONFIG", "Transform configuration is invalid"
        ) from None


def _json_equals(left: JsonValue, right: JsonValue) -> bool:
    number_types = {int, float}
    if type(left) in number_types and type(right) in number_types:
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equals(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equals(first, second) for first, second in zip(left, right)
        )
    return left == right


def _compare(operator: str, actual: JsonValue, expected: JsonValue) -> bool:
    if operator == "equals":
        return _json_equals(actual, expected)
    if operator == "not_equals":
        return not _json_equals(actual, expected)
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, list):
            return any(_json_equals(item, expected) for item in actual)
        if isinstance(actual, dict) and isinstance(expected, str):
            return expected in actual
    elif (
        type(actual) in {int, float}
        and type(expected) in {int, float}
        and (type(actual) is int or math.isfinite(actual))
        and (type(expected) is int or math.isfinite(expected))
    ):
        if operator == "greater_than":
            return actual > expected
        if operator == "greater_than_or_equal":
            return actual >= expected
        if operator == "less_than":
            return actual < expected
        if operator == "less_than_or_equal":
            return actual <= expected
    raise NodeExecutionError(
        "CONDITION_TYPE_MISMATCH",
        "Condition operator does not support the referenced value types",
    )


class ConditionExecutor:
    def validate_config(self, config: dict, upstream_ids: set[str]) -> None:
        parsed = _condition_config(config)
        validate_reference(parsed.source_node_id, parsed.field, upstream_ids)

    def execute(self, context: NodeExecutionContext) -> JsonValue:
        parsed = _condition_config(context.node_config)
        if parsed.operator == "exists":
            matched = reference_exists(context, parsed.source_node_id, parsed.field)
        else:
            actual = resolve_reference(context, parsed.source_node_id, parsed.field)
            matched = _compare(parsed.operator, actual, parsed.value)
        return {"matched": matched}


class TransformExecutor:
    def validate_config(self, config: dict, upstream_ids: set[str]) -> None:
        parsed = _transform_config(config)
        for rule in parsed.mapping.values():
            if isinstance(rule, ReferenceMapping):
                validate_reference(rule.source_node_id, rule.path, upstream_ids)

    def execute(self, context: NodeExecutionContext) -> JsonValue:
        parsed = _transform_config(context.node_config)
        output: dict[str, JsonValue] = {}
        for key, rule in parsed.mapping.items():
            if isinstance(rule, StaticMapping):
                output[key] = deepcopy(rule.value)
            elif "default" in rule.model_fields_set:
                output[key] = resolve_reference(
                    context, rule.source_node_id, rule.path, default=rule.default
                )
            else:
                output[key] = resolve_reference(context, rule.source_node_id, rule.path)
        return output
