from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import JsonValue


@dataclass(frozen=True)
class ExecutionLimits:
    max_nodes: int = 256
    max_output_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        for value in (self.max_nodes, self.max_output_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("Execution limits must be positive integers")


@dataclass(frozen=True)
class NodeExecutionContext:
    """One node invocation; input keys are its immediate upstream node IDs.

    The engine supplies detached dictionaries for every invocation. Deadline is
    reserved for future cooperative executors; no hard timeout is implemented.
    """

    execution_id: UUID
    workflow_id: UUID
    node_id: str
    node_config: dict[str, JsonValue]
    input_data: dict[str, JsonValue]
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    deadline: datetime | None = None
    ancestor_outputs: dict[str, JsonValue] = field(default_factory=dict)
