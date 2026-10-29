from fastapi import APIRouter

from app.schemas.node_type import NodeTypeMetadata
from app.services.node_registry import NODE_TYPE_REGISTRY

router = APIRouter(tags=["node-types"])


@router.get("/node-types", response_model=list[NodeTypeMetadata])
def list_node_types() -> list[NodeTypeMetadata]:
    return NODE_TYPE_REGISTRY.list_all()
