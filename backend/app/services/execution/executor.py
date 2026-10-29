from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, Protocol

from pydantic import JsonValue

from app.services.execution.context import NodeExecutionContext

if TYPE_CHECKING:
    from app.services.execution.safe_http import SafeHttpClient

logger = logging.getLogger("flowpilot.execution")
MAX_OUTPUT_DEPTH = 64


class NodeExecutionError(Exception):
    """An executor's deliberate error with a safe, user-facing message."""

    def __init__(self, code: str, public_message: str) -> None:
        self.code = code
        self.public_message = public_message
        super().__init__(public_message)


class NodeExecutor(Protocol):
    def execute(self, context: NodeExecutionContext) -> JsonValue: ...


class ExecutorRegistry:
    """Explicit executor instances; independent from the metadata registry."""

    def __init__(self) -> None:
        self._executors: dict[str, NodeExecutor] = {}

    def register(self, type_name: str, executor: NodeExecutor) -> None:
        if not isinstance(type_name, str) or not type_name.strip():
            raise ValueError("Executor type must be a nonblank string")
        if type_name != type_name.strip():
            raise ValueError("Executor type cannot contain surrounding whitespace")
        if type_name in self._executors:
            raise ValueError("Executor type is already registered")
        if not callable(getattr(executor, "execute", None)):
            raise TypeError("Executor must provide an execute method")
        self._executors[type_name] = executor

    def get(self, type_name: str) -> NodeExecutor | None:
        return self._executors.get(type_name)

    def __contains__(self, type_name: str) -> bool:
        return type_name in self._executors


class ManualTriggerExecutor:
    def execute(self, context: NodeExecutionContext) -> JsonValue:
        return {"trigger": "manual"}


class LoggerExecutor:
    def execute(self, context: NodeExecutionContext) -> JsonValue:
        # Log event identifiers only. Config, payloads and environment never
        # become log fields, and repr prevents node IDs from injecting lines.
        logger.info(
            "Logger node executed execution_id=%s workflow_id=%s node_id=%r",
            context.execution_id,
            context.workflow_id,
            context.node_id[:128],
        )
        return context.input_data


def create_default_executor_registry(
    http_client: SafeHttpClient | None = None,
) -> ExecutorRegistry:
    # Local imports keep the small executor protocol independent of concrete
    # implementations that share its controlled error type.
    from app.core.http_policy import HTTPPolicy
    from app.services.execution.data_nodes import ConditionExecutor, TransformExecutor
    from app.services.execution.http_nodes import HttpRequestExecutor, WebhookExecutor
    from app.services.execution.safe_http import SafeHttpClient
    from app.services.execution.schedule_node import ScheduleTriggerExecutor

    client = http_client if http_client is not None else SafeHttpClient(HTTPPolicy())
    registry = ExecutorRegistry()
    registry.register("trigger.manual", ManualTriggerExecutor())
    registry.register("trigger.schedule", ScheduleTriggerExecutor())
    registry.register("utility.logger", LoggerExecutor())
    registry.register("action.http_request", HttpRequestExecutor(client))
    registry.register("logic.condition", ConditionExecutor())
    registry.register("data.transform", TransformExecutor())
    registry.register("action.webhook", WebhookExecutor(client))
    return registry


def _invalid_output() -> NodeExecutionError:
    return NodeExecutionError(
        "INVALID_NODE_OUTPUT", "Node output must contain only finite JSON values"
    )


def _output_limit() -> NodeExecutionError:
    return NodeExecutionError(
        "OUTPUT_LIMIT_EXCEEDED", "Execution output size limit exceeded"
    )


def _dictionary_values(value: dict, max_bytes: int) -> Iterator[object]:
    for key, child in value.items():
        if type(key) is not str:
            raise _invalid_output()
        if len(key) > max_bytes:
            raise _output_limit()
        yield child


def _check_json(value: object, max_bytes: int) -> None:
    # Iterator frames bound traversal memory by nesting depth, even when an
    # executor returns a very wide list. Active IDs detect circular containers.
    frames: list[tuple[Iterator[object], int | None]] = [(iter((value,)), None)]
    active: set[int] = set()
    visited = 0
    while frames:
        iterator, container_id = frames[-1]
        try:
            item = next(iterator)
        except StopIteration:
            frames.pop()
            if container_id is not None:
                active.remove(container_id)
            continue

        item_type = type(item)
        if item_type in {dict, list}:
            if id(item) in active:
                raise _invalid_output()
            if len(active) >= MAX_OUTPUT_DEPTH:
                raise NodeExecutionError(
                    "INVALID_NODE_OUTPUT",
                    "Node output exceeds the maximum nesting depth of 64",
                )
            active.add(id(item))
            children = (
                _dictionary_values(item, max_bytes)
                if item_type is dict
                else iter(item)
            )
            frames.append((children, id(item)))
        elif item_type is str:
            # A character needs at least one UTF-8 byte, before JSON escaping.
            # Reject huge strings before the encoder allocates its chunk.
            if len(item) > max_bytes:
                raise _output_limit()
        elif item is None or item_type in {bool, int}:
            pass
        elif item_type is float and math.isfinite(item):
            pass
        else:
            raise _invalid_output()

        visited += 1
        # Each visited JSON value requires at least one encoded byte. This
        # stops pathological wide containers before traversing every element.
        if visited > max_bytes:
            raise _output_limit()


def normalize_output(value: object, max_bytes: int) -> tuple[JsonValue, int]:
    """Return a detached finite JSON value and its compact UTF-8 byte count.

    max_bytes is the remaining per-execution output budget, so zero is valid
    and rejects every output. Serialization stops as soon as the budget is hit.
    A conservative depth cap also keeps the final API result serializable.
    """
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("Output budget must be a nonnegative integer")
    _check_json(value, max_bytes)
    encoder = json.JSONEncoder(
        ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    encoded = bytearray()
    try:
        for chunk in encoder.iterencode(value):
            chunk_bytes = chunk.encode("utf-8")
            if len(encoded) + len(chunk_bytes) > max_bytes:
                raise _output_limit()
            encoded.extend(chunk_bytes)
        normalized: JsonValue = json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise _invalid_output() from None
    return normalized, len(encoded)
