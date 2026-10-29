from collections import deque
from copy import deepcopy
from typing import Literal

from pydantic import ValidationError

from app.schemas.workflow import ValidationIssue, ValidationResult, WorkflowDefinition
from app.services.execution.context import ExecutionLimits
from app.services.execution.executor import ExecutorRegistry, NodeExecutionError
from app.services.workflow_validation import validate_workflow


class ExecutionValidationError(Exception):
    """A workflow rejected before any executor has been called."""

    def __init__(self, errors: list[ValidationIssue]) -> None:
        super().__init__("Workflow is not executable")
        self.errors = errors


def prepare_definition(definition: WorkflowDefinition | dict) -> WorkflowDefinition:
    """Validate a detached snapshot, even when a caller passes a mutable model."""
    try:
        raw = (
            definition.model_dump(mode="python", warnings=False)
            if isinstance(definition, WorkflowDefinition)
            else deepcopy(definition)
        )
        return WorkflowDefinition.model_validate(raw)
    except (ValidationError, ValueError, TypeError, RecursionError, OverflowError):
        raise ExecutionValidationError(
            [
                ValidationIssue(
                    code="INVALID_WORKFLOW_DEFINITION",
                    message="Workflow definition is invalid",
                )
            ]
        ) from None


def validate_execution_readiness(
    definition: WorkflowDefinition,
    registry: ExecutorRegistry,
    limits: ExecutionLimits,
    *,
    trigger_type: Literal["manual", "schedule"] = "manual",
) -> ValidationResult:
    """Apply execution-only rules without changing Phase 02 draft validation."""
    if len(definition.nodes) > limits.max_nodes:
        return ValidationResult(
            valid=False,
            errors=[
                ValidationIssue(
                    code="EXECUTION_NODE_LIMIT_EXCEEDED",
                    message="Workflow exceeds the execution node limit",
                )
            ],
        )
    report = validate_workflow(definition)
    errors = list(report.structural.errors)
    if not report.structural.valid:
        return ValidationResult(valid=False, errors=errors)

    # Phase 02 checks the complete graph, including disconnected cycle components.
    # Trigger count/reachability below are stricter than its metadata-only rules.
    errors.extend(
        issue
        for issue in report.execution_readiness.errors
        if issue.code in {"CYCLE_DETECTED", "DISCONNECTED_NODE"}
    )
    if trigger_type not in {"manual", "schedule"}:
        raise ValueError("Unsupported execution trigger type")
    triggers = [
        node for node in definition.nodes if node.type == f"trigger.{trigger_type}"
    ]
    label = trigger_type.upper()
    if not triggers:
        errors.append(
            ValidationIssue(
                code=f"MISSING_{label}_TRIGGER",
                message=f"Workflow requires exactly one {trigger_type} trigger",
            )
        )
    elif len(triggers) > 1:
        errors.append(
            ValidationIssue(
                code=f"MULTIPLE_{label}_TRIGGERS",
                message=f"Workflow requires exactly one {trigger_type} trigger",
            )
        )

    for node in definition.nodes:
        if node.type.startswith("trigger.") and node.type != f"trigger.{trigger_type}":
            errors.append(
                ValidationIssue(
                    code="TRIGGER_TYPE_MISMATCH",
                    message=f"This execution requires only a {trigger_type} trigger",
                    node_id=node.id,
                )
            )
        if registry.get(node.type) is None:
            errors.append(
                ValidationIssue(
                    code="UNSUPPORTED_NODE_EXECUTOR",
                    message="Node type has no implemented executor",
                    node_id=node.id,
                )
            )

    outgoing: dict[str, list[str]] = {node.id: [] for node in definition.nodes}
    parents: dict[str, set[str]] = {node.id: set() for node in definition.nodes}
    node_types = {node.id: node.type for node in definition.nodes}
    for edge in definition.edges:
        outgoing[edge.source].append(edge.target)
        parents[edge.target].add(edge.source)
        if node_types[edge.source] == "logic.condition":
            if edge.source_handle not in {"true", "false"}:
                errors.append(
                    ValidationIssue(
                        code="INVALID_BRANCH_HANDLE",
                        message="Condition edges require a true or false source handle",
                        edge_id=edge.id,
                    )
                )
        elif edge.source_handle is not None:
            errors.append(
                ValidationIssue(
                    code="UNSUPPORTED_EDGE_HANDLE",
                    message="Only Condition nodes can use source handles",
                    edge_id=edge.id,
                )
            )
        if edge.target_handle is not None:
            errors.append(
                ValidationIssue(
                    code="UNSUPPORTED_EDGE_HANDLE",
                    message="Target handles are not supported for execution",
                    edge_id=edge.id,
                )
            )

    for trigger in triggers:
        incoming = next(
            (edge for edge in definition.edges if edge.target == trigger.id), None
        )
        if incoming is not None:
            errors.append(
                ValidationIssue(
                    code=f"{label}_TRIGGER_HAS_UPSTREAM",
                    message=f"{trigger_type.capitalize()} trigger cannot have upstream nodes",
                    node_id=trigger.id,
                    edge_id=incoming.id,
                )
            )

    if len(triggers) == 1:
        trigger_id = triggers[0].id
        reachable = {trigger_id}
        pending = deque([trigger_id])
        while pending:
            for target in outgoing[pending.popleft()]:
                if target not in reachable:
                    reachable.add(target)
                    pending.append(target)
        errors.extend(
            ValidationIssue(
                code="UNREACHABLE_NODE",
                message=f"Node cannot be reached from the {trigger_type} trigger",
                node_id=node.id,
            )
            for node in definition.nodes
            if node.id not in reachable
        )

    # Configuration checks use declared graph ancestry only. They never read
    # runtime fields, resolve DNS, or make requests; missing data is checked by
    # executors later against the successful activated ancestry of this run.
    for node in definition.nodes:
        executor = registry.get(node.type)
        validator = getattr(executor, "validate_config", None)
        if not callable(validator):
            continue
        ancestors: set[str] = set()
        pending_ancestors = list(parents[node.id])
        while pending_ancestors:
            source = pending_ancestors.pop()
            if source not in ancestors:
                ancestors.add(source)
                pending_ancestors.extend(parents[source] - ancestors)
        ancestors.discard(node.id)
        try:
            validator(deepcopy(node.config), ancestors)
        except NodeExecutionError as error:
            errors.append(
                ValidationIssue(
                    code=error.code,
                    message=error.public_message,
                    node_id=node.id,
                )
            )
        except Exception:
            errors.append(
                ValidationIssue(
                    code="INVALID_NODE_CONFIG",
                    message="Node configuration is invalid",
                    node_id=node.id,
                )
            )

    return ValidationResult(valid=not errors, errors=errors)
