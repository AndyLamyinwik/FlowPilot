import pytest
from pydantic import ValidationError

from app.schemas.node_type import NodeTypeMetadata
from app.services.node_registry import NODE_TYPE_REGISTRY, NodeTypeRegistry


def test_default_registry_contains_exactly_seven_metadata_only_types() -> None:
    items = NODE_TYPE_REGISTRY.list_all()
    assert {item.type for item in items} == {
        "trigger.manual", "trigger.schedule", "action.http_request",
        "logic.condition", "data.transform", "action.webhook", "utility.logger",
    }
    assert len(items) == 7
    assert all(set(item.model_dump()) == {"type", "display_name", "category", "description"} for item in items)


def test_registry_can_be_extended_without_changing_node_schema() -> None:
    registry = NodeTypeRegistry()
    metadata = NodeTypeMetadata(type="utility.custom", display_name="Custom", category="utility", description="A test registration")
    registry.register(metadata)
    assert registry.get("utility.custom") == metadata
    assert "utility.custom" in registry
    assert registry.get("missing") is None
    assert "missing" not in registry


def test_duplicate_registration_cannot_replace_existing_metadata() -> None:
    metadata = NODE_TYPE_REGISTRY.get("trigger.manual")
    assert metadata is not None
    registry = NodeTypeRegistry([metadata])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(metadata.model_copy(update={"description": "Replacement"}))
    assert registry.get("trigger.manual") == metadata


def test_registry_returns_a_copy_of_the_catalog_and_immutable_metadata() -> None:
    metadata = NODE_TYPE_REGISTRY.get("trigger.manual")
    assert metadata is not None
    with pytest.raises(ValidationError):
        metadata.category = "action"
    listed = NODE_TYPE_REGISTRY.list_all()
    listed.clear()
    assert len(NODE_TYPE_REGISTRY.list_all()) == 7


def test_metadata_rejects_blank_identifiers() -> None:
    with pytest.raises(ValidationError):
        NodeTypeMetadata(type=" ", display_name="Name", category="utility", description="Description")
