from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NodeTypeMetadata(BaseModel):
    """Descriptive registration only; no node execution behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: NonBlankString
    display_name: NonBlankString
    category: NonBlankString
    description: NonBlankString
