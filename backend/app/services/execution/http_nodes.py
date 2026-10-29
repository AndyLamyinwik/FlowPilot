from typing import Annotated, Literal

from pydantic import Field, JsonValue, ValidationError

from app.schemas.workflow import ApiSchema, NonBlankString
from app.services.execution.context import NodeExecutionContext
from app.services.execution.data_reference import resolve_reference, validate_reference
from app.services.execution.executor import NodeExecutionError
from app.services.execution.safe_http import NO_BODY, SafeHttpClient

Timeout = Annotated[float, Field(strict=True, gt=0, le=60, allow_inf_nan=False)]


class HttpRequestConfig(ApiSchema):
    method: Literal["GET", "POST"] = "GET"
    url: NonBlankString
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: Timeout = 10
    body: JsonValue = None


class WebhookConfig(ApiSchema):
    url: NonBlankString
    source_node_id: NonBlankString
    path: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: Timeout = 10


def _parse(schema, config):
    try:
        return schema.model_validate(config)
    except ValidationError:
        raise NodeExecutionError("INVALID_NODE_CONFIG", "HTTP node configuration is invalid") from None


class HttpRequestExecutor:
    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http_client = http_client

    def validate_config(self, config: dict, upstream_ids: set[str]) -> None:
        parsed = _parse(HttpRequestConfig, config)
        body = parsed.body if "body" in parsed.model_fields_set else NO_BODY
        self.http_client.validate_request(
            parsed.method, parsed.url, headers=parsed.headers,
            timeout=parsed.timeout, body=body,
        )

    def execute(self, context: NodeExecutionContext) -> JsonValue:
        parsed = _parse(HttpRequestConfig, context.node_config)
        body = parsed.body if "body" in parsed.model_fields_set else NO_BODY
        return self.http_client.request(
            parsed.method, parsed.url, headers=parsed.headers,
            timeout=parsed.timeout, body=body,
        )


class WebhookExecutor:
    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http_client = http_client

    def validate_config(self, config: dict, upstream_ids: set[str]) -> None:
        parsed = _parse(WebhookConfig, config)
        validate_reference(parsed.source_node_id, parsed.path, upstream_ids)
        self.http_client.validate_request(
            "POST", parsed.url, headers=parsed.headers, timeout=parsed.timeout,
        )

    def execute(self, context: NodeExecutionContext) -> JsonValue:
        parsed = _parse(WebhookConfig, context.node_config)
        payload = resolve_reference(context, parsed.source_node_id, parsed.path)
        response = self.http_client.request(
            "POST", parsed.url, headers=parsed.headers, timeout=parsed.timeout,
            body=payload,
        )
        return {"status_code": response["status_code"], "delivered": True}
