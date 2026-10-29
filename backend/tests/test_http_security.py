import socket
import ssl

import httpx2
import pytest
from httpcore2._backends.mock import MockBackend, MockStream
from pydantic import ValidationError

from app.core.config import Settings
from app.core.http_policy import HTTPPolicy, normalize_host
from app.services.execution.executor import NodeExecutionError
from app.services.execution.safe_http import SafeHttpClient

PUBLIC_IP = "93.184.216.34"


def client(handler=None, *, policy=None, resolver=None):
    return SafeHttpClient(
        policy or HTTPPolicy(allowed_hosts=("api.example.test",)),
        transport=httpx2.MockTransport(handler or (lambda request: httpx2.Response(200, json={"ok": True}))),
        resolver=resolver or (lambda host, port: [PUBLIC_IP]),
    )


def test_default_policy_does_not_allow_any_host_or_resolve_dns():
    def unexpected(*args):
        pytest.fail("Policy must reject before DNS or network")
    with pytest.raises(NodeExecutionError, match="allowlist") as raised:
        client(policy=HTTPPolicy(), resolver=unexpected).request("GET", "https://api.example.test")
    assert raised.value.code == "HTTP_HOST_NOT_ALLOWED"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://api.example.test/file", "javascript:alert(1)",
    "https://user:secret@api.example.test", "https://api.example.test/#fragment",
    "https://api.example.test/?api_key=do-not-leak", "https://api.example.test/?Authorization=x",
    "https://api.example.test:0/", "https://api.example.test:99999/", "https://api.example.test\\@127.0.0.1/",
    " https://api.example.test/", "https://api.example.test/\n", "https://[fe80::1%eth0]/",
])
def test_invalid_or_credential_urls_fail_with_safe_errors(url):
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", url)
    assert raised.value.code == "HTTP_INVALID_URL"
    assert "do-not-leak" not in str(raised.value)
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("host", [
    "localhost", "a.localhost", "127.0.0.1", "0.0.0.0", "10.0.0.1", "172.16.1.1",
    "192.168.1.1", "169.254.169.254", "100.100.100.200", "168.63.129.16",
    "[::1]", "[::]", "[fd00:ec2::254]", "[fe80::1]", "[::ffff:127.0.0.1]",
    "[::ffff:8.8.8.8]", "[64:ff9b::7f00:1]", "[2002:7f00:1::]",
    "metadata.google.internal",
])
def test_protected_literal_and_metadata_targets_blocked_even_if_allowed(host):
    policy = HTTPPolicy(allowed_hosts=(host,))
    with pytest.raises(NodeExecutionError) as raised:
        client(policy=policy).request("GET", f"https://{host}/")
    assert raised.value.code == "HTTP_TARGET_BLOCKED"


@pytest.mark.parametrize("addresses", [
    ["127.0.0.1"], ["10.0.0.1"], [PUBLIC_IP, "192.168.1.1"],
    ["::ffff:127.0.0.1"], ["64:ff9b::a00:1"], ["not-an-ip"], ["2606:4700::1111%eth0"],
])
def test_every_dns_answer_must_be_public_before_any_transport_call(addresses):
    def unexpected(request):
        pytest.fail("Blocked DNS answer reached HTTP transport")
    with pytest.raises(NodeExecutionError) as raised:
        client(unexpected, resolver=lambda host, port: addresses).request("GET", "https://api.example.test")
    assert raised.value.code == "HTTP_TARGET_BLOCKED"


def test_dns_is_resolved_once_and_connection_url_is_pinned_with_original_host_and_sni():
    calls = []
    def resolver(host, port):
        calls.append((host, port))
        return [PUBLIC_IP] if len(calls) == 1 else ["127.0.0.1"]
    def handler(request):
        assert request.url.host == PUBLIC_IP
        assert request.url.path == "/resource"
        assert request.headers["Host"] == "api.example.test"
        assert request.extensions["sni_hostname"] == "api.example.test"
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx2.Response(200, json={"ok": True})
    assert client(handler, resolver=resolver).request("GET", "https://api.example.test/resource")["body"] == {"ok": True}
    assert calls == [("api.example.test", 443)]


def test_public_ipv6_answer_is_pinned_without_changing_logical_host():
    address = "2606:4700:4700::1111"
    def handler(request):
        assert request.url.host == address
        assert request.headers["Host"] == "api.example.test"
        return httpx2.Response(200, text="ok")
    assert client(handler, resolver=lambda host, port: [address]).request(
        "GET", "https://api.example.test"
    )["body"] == "ok"


def test_allowlist_uses_exact_host_matches_not_suffixes():
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", "https://api.example.test.attacker.test")
    assert raised.value.code == "HTTP_HOST_NOT_ALLOWED"


def test_header_names_are_unique_without_case_ambiguity():
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", "https://api.example.test", headers={"Accept": "a", "accept": "b"})
    assert raised.value.code == "HTTP_INVALID_HEADERS"


def test_real_httpcore_transport_uses_checked_numeric_ip_and_original_tls_server_name():
    events = {}
    class RecordingStream(MockStream):
        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            events["sni"] = server_hostname
            assert ssl_context.check_hostname
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
            return self
        def write(self, buffer, timeout=None):
            events.setdefault("wire", bytearray()).extend(buffer)
    class RecordingBackend(MockBackend):
        def connect_tcp(self, host, port, **kwargs):
            events["target"] = (host, port)
            return RecordingStream([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"])
    transport = httpx2.HTTPTransport(trust_env=False, verify=True, http2=False)
    transport._pool._network_backend = RecordingBackend([])
    secured = SafeHttpClient(
        HTTPPolicy(allowed_hosts=("api.example.test",)), transport=transport,
        resolver=lambda host, port: [PUBLIC_IP],
    )
    assert secured.request("GET", "https://api.example.test/") == {"status_code": 200, "body": "OK"}
    assert events["target"] == (PUBLIC_IP, 443)
    assert events["sni"] == "api.example.test"
    assert b"Host: api.example.test\r\n" in events["wire"]


def test_https_is_default_and_http_requires_explicit_deployer_setting():
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", "http://api.example.test")
    assert raised.value.code == "HTTP_HTTPS_REQUIRED"
    policy = HTTPPolicy(allowed_hosts=("api.example.test",), allow_insecure=True)
    assert client(policy=policy).request("GET", "http://api.example.test")["status_code"] == 200


@pytest.mark.parametrize("name", [
    "Authorization", "Cookie", "Proxy-Authorization", "X-API-Key", "Host", "Content-Length",
    "Transfer-Encoding", "Connection", "Accept-Encoding", "Proxy-Connection",
])
def test_sensitive_and_managed_headers_rejected(name):
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", "https://api.example.test", headers={name: "hidden-value"})
    assert raised.value.code == "HTTP_FORBIDDEN_HEADER"
    assert "hidden-value" not in str(raised.value)


@pytest.mark.parametrize("headers", [{"Accept": "x\r\nCookie: secret"}, {"Bad Header": "x"}, {"X-Test": 4}])
def test_invalid_headers_cannot_inject_request_lines(headers):
    with pytest.raises(NodeExecutionError) as raised:
        client().validate_request("GET", "https://api.example.test", headers=headers)
    assert raised.value.code == "HTTP_INVALID_HEADERS"


def test_environment_proxies_and_response_cookies_do_not_reach_another_request(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("SSL_CERT_FILE", "not-a-real-certificate-file")
    calls = []
    def handler(request):
        assert "Cookie" not in request.headers
        calls.append(request)
        return httpx2.Response(200, text="ok", headers={"Set-Cookie": "session=private"})
    secured = client(handler)
    secured.request("GET", "https://api.example.test/one")
    secured.request("GET", "https://api.example.test/two")
    assert len(calls) == 2


@pytest.mark.parametrize("entry", ["*", "*.example.com", "https://example.com", "example.com:443", "x@y", " example.com", "bad_host"])
def test_allowlist_is_exact_hosts_only(entry):
    with pytest.raises(ValueError):
        HTTPPolicy(allowed_hosts=(entry,))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, http_allowed_hosts=[entry])


def test_settings_load_and_normalize_explicit_http_policy(monkeypatch):
    monkeypatch.setenv("FLOWPILOT_HTTP_ALLOWED_HOSTS", '["API.Example.Test.","api.example.test"]')
    monkeypatch.setenv("FLOWPILOT_HTTP_ALLOW_INSECURE", "true")
    settings = Settings(_env_file=None)
    assert settings.http_allowed_hosts == ["api.example.test"]
    assert settings.http_allow_insecure
    assert normalize_host("例子.测试") == "xn--fsqu00a.xn--0zwm56d"


@pytest.mark.parametrize("kwargs", [
    {"allowed_hosts": "api.example.test"}, {"max_request_bytes": 0},
    {"max_response_bytes": True}, {"allow_insecure": "true"},
])
def test_invalid_deployment_policy_fails_closed(kwargs):
    with pytest.raises(ValueError):
        HTTPPolicy(**kwargs)


def test_dns_failures_are_controlled_and_do_not_echo_resolver_errors():
    def unavailable(host, port):
        raise socket.gaierror("internal diagnostic with credential")
    with pytest.raises(NodeExecutionError) as raised:
        client(resolver=unavailable).request("GET", "https://api.example.test")
    assert raised.value.code == "HTTP_DNS_ERROR"
    assert "credential" not in str(raised.value)
