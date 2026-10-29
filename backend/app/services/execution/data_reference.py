from copy import deepcopy

from pydantic import JsonValue

from app.services.execution.context import NodeExecutionContext
from app.services.execution.executor import NodeExecutionError

_MISSING = object()


def _path_parts(path: str | None) -> list[str]:
    """Parse literal dotted keys; this is not an expression language."""
    if path is None or path == "":
        return []
    if not isinstance(path, str):
        raise NodeExecutionError(
            "INVALID_DATA_PATH", "Data paths must be dot-separated object keys or list indices"
        )
    parts = path.split(".")
    if any(
        not part
        or part != part.strip()
        or any(character in part for character in "[]$")
        or (part.startswith("-") and part[1:].isdecimal())
        for part in parts
    ):
        raise NodeExecutionError(
            "INVALID_DATA_PATH", "Data paths must be dot-separated object keys or list indices"
        )
    return parts


def validate_reference(
    source_node_id: str, path: str | None, upstream_ids: set[str]
) -> None:
    """Validate a reference using graph ancestry, without reading any data."""
    if (
        not isinstance(source_node_id, str)
        or not source_node_id
        or source_node_id != source_node_id.strip()
        or source_node_id not in upstream_ids
    ):
        raise NodeExecutionError(
            "INVALID_DATA_SOURCE", "Data source must be an upstream node in this workflow"
        )
    _path_parts(path)


def _read_reference(
    context: NodeExecutionContext, source_node_id: str, path: str | None
) -> object:
    parts = _path_parts(path)
    # Phase 04 provides successful ancestors along activated paths. Immediate
    # inputs remain a fallback for direct executor calls and Phase 03 contexts.
    ancestors = getattr(context, "ancestor_outputs", {})
    if source_node_id in ancestors:
        value = ancestors[source_node_id]
    elif source_node_id in context.input_data:
        value = context.input_data[source_node_id]
    else:
        raise NodeExecutionError(
            "DATA_SOURCE_UNAVAILABLE",
            "Referenced upstream output is not available in this execution",
        )

    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isascii() and part.isdecimal():
            # Reject impossible indices before integer conversion, including
            # strings beyond Python's defensive integer digit limit.
            canonical_index = part.lstrip("0") or "0"
            if len(canonical_index) > len(str(len(value))):
                return _MISSING
            index = int(canonical_index)
            if index >= len(value):
                return _MISSING
            value = value[index]
        else:
            return _MISSING
    return value


def resolve_reference(
    context: NodeExecutionContext,
    source_node_id: str,
    path: str | None = None,
    *,
    default: object = _MISSING,
) -> JsonValue:
    """Read only this invocation's visible outputs and return a detached value.

    An explicit default applies to missing fields, never to unavailable sources.
    A present JSON null is data and does not trigger the default.
    """
    value = _read_reference(context, source_node_id, path)
    if value is _MISSING:
        if default is _MISSING:
            raise NodeExecutionError(
                "DATA_FIELD_NOT_FOUND", "Referenced data field was not found"
            )
        value = default
    return deepcopy(value)


def reference_exists(
    context: NodeExecutionContext, source_node_id: str, path: str | None = None
) -> bool:
    return _read_reference(context, source_node_id, path) is not _MISSING
