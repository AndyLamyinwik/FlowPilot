import json
from uuid import uuid4

import httpx2
import pytest

from app.core.http_policy import HTTPPolicy
from app.services.execution.context import NodeExecutionContext
from app.services.execution.executor import NodeExecutionError
from app.services.execution.http_nodes import HttpRequestExecutor, WebhookExecutor
from app.services.execution.safe_http import SafeHttpClient
from app.services.execution import safe_http


def context(config, inputs=None):
    return NodeExecutionContext(uuid4(), uuid4(), "node", config, inputs or {})


def secured(handler, **limits):
    return SafeHttpClient(
        HTTPPolicy(allowed_hosts=("api.example.test",), **limits),
        transport=httpx2.MockTransport(handler), resolver=lambda host, port: ["93.184.216.34"],
    )


def test_http_get_returns_json_and_custom_non_sensitive_headers():
    def handler(request):
        assert request.method == "GET"
        assert request.headers["Accept"] == "application/json"
        return httpx2.Response(200, json={"message": "success"})
    executor = HttpRequestExecutor(secured(handler))
    config = {"url": "https://api.example.test", "headers": {"Accept": "application/json"}}
    executor.validate_config(config, set())
    assert executor.execute(context(config)) == {"status_code": 200, "body": {"message": "success"}}


def test_http_post_sends_json_and_returns_text():
    def handler(request):
        assert request.method == "POST"
        assert json.loads(request.content) == {"message": "Hello FlowPilot"}
        assert request.headers["Content-Type"] == "application/json"
        return httpx2.Response(201, text="Created")
    output = HttpRequestExecutor(secured(handler)).execute(context({
        "method": "POST", "url": "https://api.example.test", "body": {"message": "Hello FlowPilot"},
    }))
    assert output == {"status_code": 201, "body": "Created"}


def test_lowercase_json_content_type_is_preserved_without_duplicate_header():
    def handler(request):
        assert request.headers.get_list("Content-Type") == ["application/json"]
        return httpx2.Response(200, text="ok")
    HttpRequestExecutor(secured(handler)).execute(context({
        "method": "POST", "url": "https://api.example.test", "body": {"x": 1},
        "headers": {"content-type": "application/json"},
    }))


def test_json_body_cannot_be_mislabeled_as_non_json():
    with pytest.raises(NodeExecutionError) as raised:
        HttpRequestExecutor(secured(lambda request: pytest.fail("Request must not be sent"))).validate_config({
            "method": "POST", "url": "https://api.example.test", "body": {},
            "headers": {"Content-Type": "text/plain"},
        }, set())
    assert raised.value.code == "HTTP_INVALID_HEADERS"


@pytest.mark.parametrize("body", [float("nan"), {"x": object()}])
def test_non_json_request_body_cannot_reach_transport(body):
    with pytest.raises(NodeExecutionError) as raised:
        secured(lambda request: pytest.fail("Request must not be sent")).request(
            "POST", "https://api.example.test", body=body,
        )
    assert raised.value.code == "HTTP_INVALID_BODY"


@pytest.mark.parametrize("status", [301, 302, 307, 404, 500])
def test_redirects_and_http_errors_fail_without_following_or_leaking_body(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(status, text="private-response-value", headers={"Location": "http://127.0.0.1"})
    with pytest.raises(NodeExecutionError) as raised:
        HttpRequestExecutor(secured(handler)).execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == ("HTTP_REDIRECT_BLOCKED" if status < 400 else "HTTP_STATUS_ERROR")
    assert "private-response-value" not in str(raised.value)
    assert len(calls) == 1


@pytest.mark.parametrize("error,code", [(httpx2.ReadTimeout, "HTTP_TIMEOUT"), (httpx2.ConnectError, "HTTP_CONNECTION_ERROR"), (httpx2.RemoteProtocolError, "HTTP_REQUEST_FAILED")])
def test_http_transport_errors_are_safe(error, code):
    def handler(request):
        raise error("internal secret diagnostic", request=request)
    with pytest.raises(NodeExecutionError) as raised:
        HttpRequestExecutor(secured(handler)).execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == code
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("config", [
    {}, {"url": "https://api.example.test", "method": "DELETE"},
    {"url": "https://api.example.test", "timeout": 0},
    {"url": "https://api.example.test", "timeout": True},
    {"url": "https://api.example.test", "timeout": 61},
    {"url": "https://api.example.test", "body": {}},
    {"url": "https://api.example.test", "unknown": 1},
])
def test_invalid_config_rejected_before_dns_or_request(config):
    def unexpected(*args):
        pytest.fail("Readiness performed network I/O")
    executor = HttpRequestExecutor(SafeHttpClient(HTTPPolicy(allowed_hosts=("api.example.test",)), resolver=unexpected))
    with pytest.raises(NodeExecutionError):
        executor.validate_config(config, set())


def test_valid_readiness_is_pure_without_dns_or_http():
    def unexpected(*args):
        pytest.fail("Readiness performed network I/O")
    executor = HttpRequestExecutor(SafeHttpClient(HTTPPolicy(allowed_hosts=("api.example.test",)), resolver=unexpected))
    executor.validate_config({"url": "https://api.example.test", "timeout": 10}, set())


def test_request_body_limit_is_checked_before_transport():
    def unexpected(request):
        pytest.fail("Oversized request reached network")
    executor = HttpRequestExecutor(secured(unexpected, max_request_bytes=4))
    with pytest.raises(NodeExecutionError) as raised:
        executor.validate_config({"url": "https://api.example.test", "method": "POST", "body": "long"}, set())
    assert raised.value.code == "HTTP_REQUEST_TOO_LARGE"


def test_response_stream_limit_applies_without_content_length_and_closes_stream():
    closed = []
    class Chunks(httpx2.SyncByteStream):
        def __iter__(self):
            yield b"123"
            yield b"456"
            pytest.fail("Stream read beyond bounded response")
        def close(self):
            closed.append(True)
    executor = HttpRequestExecutor(secured(lambda request: httpx2.Response(200, stream=Chunks()), max_response_bytes=5))
    with pytest.raises(NodeExecutionError) as raised:
        executor.execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == "HTTP_RESPONSE_TOO_LARGE"
    assert closed


def test_slow_drip_response_obeys_monotonic_budget_and_closes(monkeypatch):
    now = [0.0]
    closed = []
    monkeypatch.setattr(safe_http, "monotonic", lambda: now[0])
    class SlowChunks(httpx2.SyncByteStream):
        def __iter__(self):
            now[0] = 4
            yield b"a"
            now[0] = 8
            yield b"b"
            now[0] = 12
            yield b"c"
            pytest.fail("Timed-out response continued reading")
        def close(self):
            closed.append(True)
    executor = HttpRequestExecutor(secured(lambda request: httpx2.Response(200, stream=SlowChunks())))
    with pytest.raises(NodeExecutionError) as raised:
        executor.execute(context({"url": "https://api.example.test", "timeout": 10}))
    assert raised.value.code == "HTTP_TIMEOUT"
    assert closed


def test_dns_consuming_entire_budget_prevents_http_send(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(safe_http, "monotonic", lambda: now[0])
    def resolver(host, port):
        now[0] = 11
        return ["93.184.216.34"]
    client = SafeHttpClient(
        HTTPPolicy(allowed_hosts=("api.example.test",)),
        transport=httpx2.MockTransport(lambda request: pytest.fail("DNS budget expired before HTTP send")),
        resolver=resolver,
    )
    with pytest.raises(NodeExecutionError) as raised:
        client.request("GET", "https://api.example.test", timeout=10)
    assert raised.value.code == "HTTP_TIMEOUT"


def test_declared_oversized_response_is_rejected_before_reading():
    class Unread(httpx2.SyncByteStream):
        def __iter__(self):
            pytest.fail("Declared oversized response was read")
            yield b""
    executor = HttpRequestExecutor(secured(lambda request: httpx2.Response(200, headers={"Content-Length": "9999"}, stream=Unread()), max_response_bytes=10))
    with pytest.raises(NodeExecutionError) as raised:
        executor.execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == "HTTP_RESPONSE_TOO_LARGE"


def test_compressed_response_is_rejected_before_decompression():
    class Unread(httpx2.SyncByteStream):
        def __iter__(self):
            pytest.fail("Compressed payload was read")
            yield b""
    executor = HttpRequestExecutor(secured(lambda request: httpx2.Response(200, headers={"Content-Encoding": "gzip"}, stream=Unread())))
    with pytest.raises(NodeExecutionError) as raised:
        executor.execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == "HTTP_RESPONSE_ENCODING_UNSUPPORTED"


@pytest.mark.parametrize("content", [b"invalid json", b'{"value":NaN}'])
def test_invalid_or_nonfinite_json_response_fails_safely(content):
    executor = HttpRequestExecutor(secured(lambda request: httpx2.Response(200, headers={"Content-Type": "application/json"}, content=content)))
    with pytest.raises(NodeExecutionError) as raised:
        executor.execute(context({"url": "https://api.example.test"}))
    assert raised.value.code == "HTTP_INVALID_RESPONSE"


def test_webhook_uses_shared_client_and_posts_selected_source_json():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        assert json.loads(request.content) == {"username": "Andy", "points": 95}
        return httpx2.Response(200, json={"ignored": "response"})
    executor = WebhookExecutor(secured(handler))
    config = {"url": "https://api.example.test/hook", "source_node_id": "transform"}
    executor.validate_config(config, {"transform"})
    assert executor.execute(context(config, {"transform": {"username": "Andy", "points": 95}})) == {"status_code": 200, "delivered": True}
    assert len(calls) == 1


def test_webhook_supports_nested_source_path_and_does_not_mutate_input():
    inputs = {"transform": {"body": {"message": "ok"}}}
    def handler(request):
        assert json.loads(request.content) == {"message": "ok"}
        return httpx2.Response(204)
    executor = WebhookExecutor(secured(handler))
    output = executor.execute(context({"url": "https://api.example.test", "source_node_id": "transform", "path": "body"}, inputs))
    assert output == {"status_code": 204, "delivered": True}
    assert inputs == {"transform": {"body": {"message": "ok"}}}


@pytest.mark.parametrize("case", ["unauthorized", "invalid_source", "timeout", "status", "request_size"])
def test_webhook_inherits_security_errors_and_limits(case):
    def handler(request):
        if case == "timeout":
            raise httpx2.ReadTimeout("private diagnostic", request=request)
        return httpx2.Response(500)
    executor = WebhookExecutor(secured(handler, **({"max_request_bytes": 1} if case == "request_size" else {})))
    config = {"url": "https://not-allowed.example" if case == "unauthorized" else "https://api.example.test", "source_node_id": "source"}
    with pytest.raises(NodeExecutionError) as raised:
        if case in {"unauthorized", "invalid_source"}:
            executor.validate_config(config, set() if case == "invalid_source" else {"source"})
        else:
            executor.execute(context(config, {"source": {"message": "ok"}}))
    expected = {"unauthorized": "HTTP_HOST_NOT_ALLOWED", "invalid_source": "INVALID_DATA_SOURCE", "timeout": "HTTP_TIMEOUT", "status": "HTTP_STATUS_ERROR", "request_size": "HTTP_REQUEST_TOO_LARGE"}
    assert raised.value.code == expected[case]
