import json
import math
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
)

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]

# This guard catches recognizable credential fields. Arbitrary string contents
# cannot reliably be classified as secrets; callers must use credential references.
SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "apikey",
        "xapikey",
        "secret",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "authtoken",
        "xauthtoken",
        "bearertoken",
        "authorization",
        "cookie",
        "setcookie",
        "proxyauthorization",
        "privatekey",
    }
)


class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(ApiSchema):
    x: FiniteNumber
    y: FiniteNumber


class Node(ApiSchema):
    id: NonBlankString
    type: NonBlankString
    name: NonBlankString
    position: Position
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def validate_json_config(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise ValueError("Node config must be a JSON object")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError) as error:
            raise ValueError(
                "Node config must contain finite, JSON-serializable values"
            ) from error

        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ValueError("Node config object keys must be strings")
                    normalized = "".join(
                        character for character in key.casefold() if character.isalnum()
                    )
                    if normalized in SECRET_KEYS and child is not None and child != "":
                        raise ValueError(
                            "Plaintext credentials are not allowed in config; use credential_ref"
                        )
                    pending.append(child)
            elif isinstance(item, list):
                pending.extend(item)
            elif item is None or type(item) in {str, bool, int}:
                continue
            elif type(item) is float and math.isfinite(item):
                continue
            else:
                raise ValueError("Node config must contain only JSON values")
        return value


class Edge(ApiSchema):
    id: NonBlankString
    source: NonBlankString
    target: NonBlankString
    source_handle: NonBlankString | None = None
    target_handle: NonBlankString | None = None


class WorkflowDefinition(ApiSchema):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    nodes: list[Node]
    edges: list[Edge]


def empty_definition() -> WorkflowDefinition:
    return WorkflowDefinition(schema_version=1, nodes=[], edges=[])


class WorkflowCreate(ApiSchema):
    name: NonBlankString
    description: str | None = None
    definition: WorkflowDefinition = Field(default_factory=empty_definition)


class WorkflowUpdate(ApiSchema):
    name: NonBlankString
    description: str | None = None
    definition: WorkflowDefinition


class WorkflowRead(ApiSchema):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: NonBlankString
    description: str | None
    definition: WorkflowDefinition
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class ValidationIssue(ApiSchema):
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class ValidationResult(ApiSchema):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class WorkflowValidationReport(ApiSchema):
    can_save: bool
    structural: ValidationResult
    execution_readiness: ValidationResult
