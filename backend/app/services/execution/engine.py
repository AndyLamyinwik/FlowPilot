import logging
from copy import deepcopy
from datetime import UTC, datetime
from heapq import heappop, heappush
from typing import Literal
from uuid import UUID, uuid4

from pydantic import JsonValue

from app.schemas.execution import (
    ExecutionError,
    NodeExecutionResult,
    WorkflowExecutionResult,
)
from app.schemas.workflow import Edge, Node, ValidationIssue, WorkflowDefinition
from app.services.execution.context import ExecutionLimits, NodeExecutionContext
from app.services.execution.executor import (
    ExecutorRegistry,
    NodeExecutionError,
    create_default_executor_registry,
    normalize_output,
)
from app.services.execution.validation import (
    ExecutionValidationError,
    prepare_definition,
    validate_execution_readiness,
)

logger = logging.getLogger("flowpilot.execution")


def _build_plan(
    definition: WorkflowDefinition,
) -> tuple[list[Node], dict[str, list[str]]]:
    """Kahn order: prefer the earliest defined node among all ready nodes."""
    positions = {node.id: index for index, node in enumerate(definition.nodes)}
    parents: dict[str, set[str]] = {node.id: set() for node in definition.nodes}
    children: dict[str, set[str]] = {node.id: set() for node in definition.nodes}
    for edge in definition.edges:
        parents[edge.target].add(edge.source)
        children[edge.source].add(edge.target)
    indegrees = {node_id: len(sources) for node_id, sources in parents.items()}
    ready: list[int] = []
    for node in definition.nodes:
        if indegrees[node.id] == 0:
            heappush(ready, positions[node.id])
    order: list[Node] = []
    while ready:
        node = definition.nodes[heappop(ready)]
        order.append(node)
        for target in children[node.id]:
            indegrees[target] -= 1
            if indegrees[target] == 0:
                heappush(ready, positions[target])
    if len(order) != len(definition.nodes):
        raise ExecutionValidationError(
            [
                ValidationIssue(
                    code="CYCLE_DETECTED",
                    message="Workflow contains a directed cycle",
                )
            ]
        )
    ordered_parents = {
        node_id: sorted(sources, key=positions.__getitem__)
        for node_id, sources in parents.items()
    }
    return order, ordered_parents


class ExecutionEngine:
    """Synchronous, single-run DAG execution with invocation-local state."""

    def __init__(
        self,
        registry: ExecutorRegistry | None = None,
        limits: ExecutionLimits | None = None,
    ) -> None:
        self.registry = (
            registry if registry is not None else create_default_executor_registry()
        )
        self.limits = limits if limits is not None else ExecutionLimits()

    def execute(
        self,
        workflow_id: UUID,
        definition: WorkflowDefinition | dict,
        *,
        deadline: datetime | None = None,
        execution_id: UUID | None = None,
        started_at: datetime | None = None,
        trigger_type: Literal["manual", "schedule"] = "manual",
        scheduled_at: datetime | None = None,
    ) -> WorkflowExecutionResult:
        snapshot = self.validate(definition, trigger_type=trigger_type)
        for timestamp in (started_at, scheduled_at):
            if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
                raise ValueError("Execution timestamps must be timezone aware")
        order, parents = _build_plan(snapshot)
        incoming: dict[str, list[Edge]] = {node.id: [] for node in order}
        outgoing: dict[str, list[Edge]] = {node.id: [] for node in order}
        for edge in snapshot.edges:
            incoming[edge.target].append(edge)
            outgoing[edge.source].append(edge)
        # Resolve the complete executor set before starting. Registry changes made
        # by an executor cannot alter the rest of an already validated run.
        executors = {node.id: self.registry.get(node.type) for node in order}
        if any(executor is None for executor in executors.values()):
            raise ExecutionValidationError(
                [
                    ValidationIssue(
                        code="UNSUPPORTED_NODE_EXECUTOR",
                        message="Node type has no implemented executor",
                    )
                ]
            )

        execution_id = execution_id if execution_id is not None else uuid4()
        started_at = started_at.astimezone(UTC) if started_at is not None else datetime.now(UTC)
        metadata = {"workflow_started_at": started_at.isoformat()}
        if trigger_type == "schedule":
            metadata["scheduled_at"] = (scheduled_at or started_at).astimezone(UTC).isoformat()
        result = WorkflowExecutionResult(
            execution_id=execution_id,
            workflow_id=workflow_id,
            status="running",
            started_at=started_at,
            node_results=[
                NodeExecutionResult(node_id=node.id, status="pending") for node in order
            ],
        )
        outputs: dict[str, JsonValue] = {}
        # Edge activation is distinct from node completion. A successful
        # Condition activates only one handle, while a skipped node activates
        # none. Topological order guarantees every parent is terminal first.
        activated_edges = dict.fromkeys((edge.id for edge in snapshot.edges), False)
        provenance: dict[str, set[str]] = {}
        positions = {node.id: index for index, node in enumerate(snapshot.nodes)}
        output_bytes = 0
        logger.info("Workflow execution started (execution_id=%s)", execution_id)

        for index, node in enumerate(order):
            node_result = result.node_results[index]
            active_sources = {
                edge.source for edge in incoming[node.id] if activated_edges[edge.id]
            }
            active_parents = [source for source in parents[node.id] if source in active_sources]
            if node.type != f"trigger.{trigger_type}" and not active_parents:
                node_result.status = "skipped"
                node_result.finished_at = datetime.now(UTC)
                continue

            visible_sources = set(active_parents)
            for source in active_parents:
                visible_sources.update(provenance[source])
            node_result.status = "running"
            node_result.started_at = datetime.now(UTC)
            try:
                context = NodeExecutionContext(
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    node_id=node.id,
                    node_config=deepcopy(node.config),
                    input_data=deepcopy(
                        {source: outputs[source] for source in active_parents}
                    ),
                    metadata=deepcopy(metadata),
                    deadline=deadline,
                    ancestor_outputs=deepcopy(
                        {
                            source: outputs[source]
                            for source in sorted(visible_sources, key=positions.__getitem__)
                        }
                    ),
                )
                executor = executors[node.id]
                output, size = normalize_output(
                    executor.execute(context),
                    self.limits.max_output_bytes - output_bytes,
                )
                if node.type == "logic.condition" and (
                    not isinstance(output, dict) or type(output.get("matched")) is not bool
                ):
                    raise NodeExecutionError(
                        "INVALID_CONDITION_OUTPUT",
                        "Condition output must contain a boolean matched value",
                    )
            except NodeExecutionError as error:
                public_error = ExecutionError(
                    code=error.code,
                    message=error.public_message,
                    node_id=node.id,
                )
            except Exception:
                # An unexpected executor error may contain secrets or traceback
                # details. Its text is never used in public errors or log events.
                public_error = ExecutionError(
                    code="NODE_EXECUTION_FAILED",
                    message="Node execution failed",
                    node_id=node.id,
                )
            else:
                node_result.status = "success"
                node_result.output = output
                node_result.finished_at = datetime.now(UTC)
                node_result.duration_ms = _duration_ms(node_result.started_at, node_result.finished_at)
                outputs[node.id] = output
                provenance[node.id] = visible_sources
                output_bytes += size
                for edge in outgoing[node.id]:
                    activated_edges[edge.id] = (
                        node.type != "logic.condition"
                        or edge.source_handle == ("true" if output["matched"] else "false")
                    )
                continue

            node_result.status = "failed"
            node_result.error = public_error
            node_result.finished_at = datetime.now(UTC)
            node_result.duration_ms = _duration_ms(node_result.started_at, node_result.finished_at)
            result.status = "failed"
            result.error = public_error
            for remaining in result.node_results[index + 1 :]:
                remaining.status = "skipped"
                remaining.finished_at = node_result.finished_at
            result.finished_at = datetime.now(UTC)
            logger.warning(
                "Workflow execution failed (execution_id=%s code=%s)",
                execution_id,
                public_error.code,
            )
            return result

        result.status = "success"
        result.finished_at = datetime.now(UTC)
        logger.info("Workflow execution succeeded (execution_id=%s)", execution_id)
        return result

    def validate(
        self,
        definition: WorkflowDefinition | dict,
        *,
        trigger_type: Literal["manual", "schedule"] = "manual",
    ) -> WorkflowDefinition:
        """Return an isolated, executable snapshot without invoking any node."""
        snapshot = prepare_definition(definition)
        readiness = validate_execution_readiness(
            snapshot, self.registry, self.limits, trigger_type=trigger_type
        )
        if not readiness.valid:
            raise ExecutionValidationError(readiness.errors)
        return snapshot


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))
