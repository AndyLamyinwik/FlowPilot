from collections import deque

from app.schemas.workflow import (
    ValidationIssue,
    ValidationResult,
    WorkflowDefinition,
    WorkflowValidationReport,
)
from app.services.node_registry import NODE_TYPE_REGISTRY, NodeTypeRegistry


def validate_workflow(
    definition: WorkflowDefinition,
    registry: NodeTypeRegistry = NODE_TYPE_REGISTRY,
) -> WorkflowValidationReport:
    """Validate integrity and future graph readiness without executing nodes.

    Pydantic validates the input shape/schema version before this graph service.
    Multi-node cycles can be saved as drafts; self-links are invalid connections.
    """
    structural_errors: list[ValidationIssue] = []
    node_ids: set[str] = set()
    for node in definition.nodes:
        if node.id in node_ids:
            structural_errors.append(
                ValidationIssue(
                    code="DUPLICATE_NODE_ID",
                    message="Node IDs must be unique within a workflow",
                    node_id=node.id,
                )
            )
        node_ids.add(node.id)
        if node.type not in registry:
            structural_errors.append(
                ValidationIssue(
                    code="UNREGISTERED_NODE_TYPE",
                    message="Node type is not registered",
                    node_id=node.id,
                )
            )

    edge_ids: set[str] = set()
    for edge in definition.edges:
        if edge.id in edge_ids:
            structural_errors.append(
                ValidationIssue(
                    code="DUPLICATE_EDGE_ID",
                    message="Edge IDs must be unique within a workflow",
                    edge_id=edge.id,
                )
            )
        edge_ids.add(edge.id)
        if edge.source not in node_ids or edge.target not in node_ids:
            structural_errors.append(
                ValidationIssue(
                    code="INVALID_NODE_REFERENCE",
                    message="Edge endpoints must reference existing nodes",
                    edge_id=edge.id,
                )
            )
        if edge.source == edge.target:
            structural_errors.append(
                ValidationIssue(
                    code="SELF_LOOP",
                    message="An edge cannot connect a node to itself",
                    node_id=edge.source,
                    edge_id=edge.id,
                )
            )

    structural = ValidationResult(valid=not structural_errors, errors=structural_errors)
    if structural_errors:
        return WorkflowValidationReport(
            can_save=False,
            structural=structural,
            execution_readiness=ValidationResult(
                valid=False,
                errors=[
                    ValidationIssue(
                        code="STRUCTURAL_VALIDATION_FAILED",
                        message="Fix structural errors before checking execution readiness",
                    )
                ],
            ),
        )

    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree = dict.fromkeys(node_ids, 0)
    connected: set[str] = set()
    for edge in definition.edges:
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1
        connected.update((edge.source, edge.target))

    triggers = {
        node.id
        for node in definition.nodes
        if (metadata := registry.get(node.type)) is not None
        and metadata.category == "trigger"
    }
    readiness_errors: list[ValidationIssue] = []
    if not triggers:
        readiness_errors.append(
            ValidationIssue(
                code="MISSING_TRIGGER", message="Workflow requires a trigger node"
            )
        )

    if len(node_ids) > 1:
        for node in definition.nodes:
            if node.id not in connected:
                readiness_errors.append(
                    ValidationIssue(
                        code="DISCONNECTED_NODE",
                        message="Node is not connected to another node",
                        node_id=node.id,
                    )
                )

    reachable = set(triggers)
    pending = deque(triggers)
    while pending:
        for target in outgoing[pending.popleft()]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    for node in definition.nodes:
        if node.id not in reachable:
            readiness_errors.append(
                ValidationIssue(
                    code="UNREACHABLE_NODE",
                    message="Node cannot be reached from a trigger",
                    node_id=node.id,
                )
            )

    # Kahn's algorithm checks the complete directed graph, including unreachable
    # components. Iteration avoids recursion limits on large editor documents.
    roots = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
    visited = 0
    while roots:
        visited += 1
        for target in outgoing[roots.popleft()]:
            indegree[target] -= 1
            if indegree[target] == 0:
                roots.append(target)
    if visited != len(node_ids):
        readiness_errors.append(
            ValidationIssue(
                code="CYCLE_DETECTED", message="Workflow contains a directed cycle"
            )
        )

    return WorkflowValidationReport(
        can_save=True,
        structural=structural,
        execution_readiness=ValidationResult(valid=not readiness_errors, errors=readiness_errors),
    )
