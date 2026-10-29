from collections.abc import Iterable

from app.schemas.node_type import NodeTypeMetadata


class NodeTypeRegistry:
    """Small metadata catalog, deliberately independent of node executors."""

    def __init__(self, node_types: Iterable[NodeTypeMetadata] = ()) -> None:
        self._node_types: dict[str, NodeTypeMetadata] = {}
        for metadata in node_types:
            self.register(metadata)

    def register(self, metadata: NodeTypeMetadata) -> None:
        if metadata.type in self._node_types:
            raise ValueError(f"Node type already registered: {metadata.type}")
        self._node_types[metadata.type] = metadata

    def get(self, type_name: str) -> NodeTypeMetadata | None:
        return self._node_types.get(type_name)

    def list_all(self) -> list[NodeTypeMetadata]:
        return list(self._node_types.values())

    def __contains__(self, type_name: str) -> bool:
        return type_name in self._node_types


NODE_TYPE_REGISTRY = NodeTypeRegistry(
    [
        NodeTypeMetadata(
            type="trigger.manual",
            display_name="Manual Trigger",
            category="trigger",
            description="Start a workflow manually",
        ),
        NodeTypeMetadata(
            type="trigger.schedule",
            display_name="Schedule Trigger",
            category="trigger",
            description="Start a workflow on a schedule",
        ),
        NodeTypeMetadata(
            type="action.http_request",
            display_name="HTTP Request",
            category="action",
            description="Make an HTTP request",
        ),
        NodeTypeMetadata(
            type="logic.condition",
            display_name="Condition",
            category="logic",
            description="Choose a branch based on a condition",
        ),
        NodeTypeMetadata(
            type="data.transform",
            display_name="Transform Data",
            category="data",
            description="Transform input data",
        ),
        NodeTypeMetadata(
            type="action.webhook",
            display_name="Webhook",
            category="action",
            description="Send an outgoing webhook notification",
        ),
        NodeTypeMetadata(
            type="utility.logger",
            display_name="Logger",
            category="utility",
            description="Record workflow data",
        ),
    ]
)
