import ipaddress
import json
import math
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from urllib.parse import parse_qsl, urlsplit

import httpx2
from pydantic import JsonValue

from app.core.http_policy import HTTPPolicy, normalize_host, public_address
from app.services.execution.executor import NodeExecutionError, normalize_output

Resolver = Callable[[str, int], list[str]]
NO_BODY = object()
SENSITIVE_NAMES = frozenset({
    "authorization", "proxyauthorization", "cookie", "setcookie", "apikey",
    "xapikey", "password", "passwd", "pwd", "secret", "clientsecret",
    "accesstoken", "refreshtoken", "authtoken", "xauthtoken", "bearertoken",
    "token", "privatekey",
})
MANAGED_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "keep-alive",
    "proxy-connection", "te", "trailer", "upgrade", "accept-encoding",
})


def _error(code: str, message: str) -> NodeExecutionError:
    return NodeExecutionError(code, message)


def _resolve(host: str, port: int) -> list[str]:
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    return list(dict.fromkeys(answer[4][0] for answer in answers))


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _error("HTTP_TIMEOUT", "HTTP request timed out")
    return remaining


@dataclass(frozen=True)
class Target:
    url: httpx2.URL
    host: str
    port: int


class SafeHttpClient:
    """Bounded, allowlisted HTTP with runtime DNS checks and IP pinning.

    An injected transport/resolver is a trusted testing seam. Production connects
    to the checked numeric IP, preserving the domain Host and TLS SNI. This relies
    on the pinned HTTPX2/httpcore2 sni_hostname extension, not a second DNS lookup.
    """

    def __init__(
        self,
        policy: HTTPPolicy,
        *,
        transport: httpx2.BaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self.policy = policy
        self.transport = transport
        self.resolver = resolver if resolver is not None else _resolve

    def validate_target(self, url: str) -> Target:
        if not isinstance(url, str) or not url or len(url) > 8192 or "\\" in url:
            raise _error("HTTP_INVALID_URL", "HTTP URL is invalid")
        if any(ord(character) <= 32 or ord(character) == 127 for character in url):
            raise _error("HTTP_INVALID_URL", "HTTP URL is invalid")
        try:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError
            if parts.username is not None or parts.password is not None or parts.fragment:
                raise ValueError
            host = normalize_host(parts.hostname)
            port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
            if not 1 <= port <= 65535:
                raise ValueError
            if any(
                "".join(c for c in key.casefold() if c.isalnum()) in SENSITIVE_NAMES
                for key, _ in parse_qsl(parts.query, keep_blank_values=True)
            ):
                raise ValueError
            target_url = httpx2.URL(url).copy_with(host=host)
        except (ValueError, UnicodeError, httpx2.InvalidURL):
            raise _error("HTTP_INVALID_URL", "HTTP URL is invalid or contains credentials") from None
        if parts.scheme == "http" and not self.policy.allow_insecure:
            raise _error("HTTP_HTTPS_REQUIRED", "HTTP requests require HTTPS")
        if host == "localhost" or host.endswith(".localhost") or host in {
            "metadata", "metadata.google.internal", "instance-data.ec2.internal",
        }:
            raise _error("HTTP_TARGET_BLOCKED", "HTTP target is not a public address")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not public_address(str(address)):
            raise _error("HTTP_TARGET_BLOCKED", "HTTP target is not a public address")
        if host not in self.policy.allowed_hosts:
            raise _error("HTTP_HOST_NOT_ALLOWED", "HTTP target is not in the host allowlist")
        return Target(target_url, host, port)

    def validate_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {}
        if not isinstance(headers, dict):
            raise _error("HTTP_INVALID_HEADERS", "HTTP headers are invalid")
        checked: dict[str, str] = {}
        seen: set[str] = set()
        size = 0
        for key, value in headers.items():
            if (
                type(key) is not str or type(value) is not str
                or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
                or any(ord(character) < 32 or ord(character) > 126 for character in value)
            ):
                raise _error("HTTP_INVALID_HEADERS", "HTTP headers are invalid")
            normalized = "".join(c for c in key.casefold() if c.isalnum())
            if key.casefold() in seen:
                raise _error("HTTP_INVALID_HEADERS", "HTTP header names must be unique")
            seen.add(key.casefold())
            if normalized in SENSITIVE_NAMES or key.lower() in MANAGED_HEADERS or key.lower().startswith("proxy-"):
                raise _error("HTTP_FORBIDDEN_HEADER", "HTTP header is sensitive or managed by the client")
            size += len(key) + len(value)
            if size > 8192:
                raise _error("HTTP_INVALID_HEADERS", "HTTP headers exceed the supported size")
            checked[key] = value
        return checked

    def encode_body(self, body: object) -> bytes | None:
        if body is NO_BODY:
            return None
        try:
            normalized, _ = normalize_output(body, self.policy.max_request_bytes)
        except NodeExecutionError as error:
            if error.code == "OUTPUT_LIMIT_EXCEEDED":
                raise _error("HTTP_REQUEST_TOO_LARGE", "HTTP request body exceeds the size limit") from None
            raise _error("HTTP_INVALID_BODY", "HTTP request body must be finite JSON") from None
        return json.dumps(normalized, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")

    def validate_request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        timeout: float = 10, body: object = NO_BODY,
    ) -> tuple[Target, dict[str, str], bytes | None]:
        if method not in {"GET", "POST"}:
            raise _error("HTTP_UNSUPPORTED_METHOD", "HTTP method is not supported")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise _error("HTTP_INVALID_TIMEOUT", "HTTP timeout must be greater than zero and at most 60 seconds")
        if method == "GET" and body is not NO_BODY:
            raise _error("HTTP_INVALID_BODY", "GET requests cannot have a JSON body")
        target = self.validate_target(url)
        checked_headers = self.validate_headers(headers)
        content = self.encode_body(body)
        content_type = next(
            (value for key, value in checked_headers.items() if key.lower() == "content-type"),
            None,
        )
        if content is not None and content_type is not None:
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type != "application/json" and not (
                media_type.startswith("application/") and media_type.endswith("+json")
            ):
                raise _error("HTTP_INVALID_HEADERS", "HTTP request body requires a JSON Content-Type")
        return target, checked_headers, content

    def _pinned_address(self, target: Target) -> str:
        try:
            literal = ipaddress.ip_address(target.host)
        except ValueError:
            literal = None
        try:
            addresses = [str(literal)] if literal is not None else self.resolver(target.host, target.port)
        except (OSError, ValueError):
            raise _error("HTTP_DNS_ERROR", "HTTP target could not be resolved") from None
        if not addresses:
            raise _error("HTTP_DNS_ERROR", "HTTP target could not be resolved")
        if any(not public_address(address) for address in addresses):
            raise _error("HTTP_TARGET_BLOCKED", "HTTP target is not a public address")
        return str(ipaddress.ip_address(addresses[0]))

    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        timeout: float = 10, body: object = NO_BODY,
    ) -> dict[str, JsonValue]:
        target, checked_headers, content = self.validate_request(
            method, url, headers=headers, timeout=timeout, body=body
        )
        deadline = monotonic() + timeout
        pinned = self._pinned_address(target)
        _remaining(deadline)
        authority = f"[{target.host}]" if ":" in target.host else target.host
        default_port = 443 if target.url.scheme == "https" else 80
        if target.port != default_port:
            authority += f":{target.port}"
        checked_headers["Host"] = authority
        checked_headers["Accept-Encoding"] = "identity"
        if content is not None and not any(key.lower() == "content-type" for key in checked_headers):
            checked_headers.setdefault("Content-Type", "application/json")
        try:
            # A fresh client prevents response cookies from reaching another node.
            with httpx2.Client(
                transport=self.transport, trust_env=False, verify=True, http2=False,
                follow_redirects=False, timeout=_remaining(deadline), auth=None,
            ) as client:
                with client.stream(
                    method, target.url.copy_with(host=pinned), headers=checked_headers,
                    content=content, timeout=_remaining(deadline),
                    extensions={"sni_hostname": target.host},
                ) as response:
                    _remaining(deadline)
                    if 300 <= response.status_code < 400:
                        raise _error("HTTP_REDIRECT_BLOCKED", "HTTP redirects are not supported")
                    if not 200 <= response.status_code < 300:
                        raise _error("HTTP_STATUS_ERROR", f"HTTP request returned status {response.status_code}")
                    if response.headers.get("Content-Encoding", "identity").strip().lower() not in {"", "identity"}:
                        raise _error("HTTP_RESPONSE_ENCODING_UNSUPPORTED", "Compressed HTTP responses are not supported")
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            declared_length = int(content_length)
                        except ValueError:
                            raise _error("HTTP_INVALID_RESPONSE", "HTTP response is invalid") from None
                        if declared_length < 0:
                            raise _error("HTTP_INVALID_RESPONSE", "HTTP response is invalid")
                        if declared_length > self.policy.max_response_bytes:
                            raise _error("HTTP_RESPONSE_TOO_LARGE", "HTTP response body exceeds the size limit")
                    data = bytearray()
                    chunks = (response.content,) if response.is_stream_consumed else response.iter_raw()
                    iterator = iter(chunks)
                    while True:
                        # HTTPcore reads this timeout extension between receives.
                        # Monotonic checks also cover injected transports and
                        # servers which keep sending tiny chunks before timeout.
                        response.request.extensions["timeout"]["read"] = _remaining(deadline)
                        try:
                            chunk = next(iterator)
                        except StopIteration:
                            break
                        _remaining(deadline)
                        if len(data) + len(chunk) > self.policy.max_response_bytes:
                            raise _error("HTTP_RESPONSE_TOO_LARGE", "HTTP response body exceeds the size limit")
                        data.extend(chunk)
                    media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    text = bytes(data).decode(response.encoding or "utf-8", errors="replace")
                    if media_type == "application/json" or media_type.endswith("+json"):
                        try:
                            parsed = json.loads(text)
                            parsed, _ = normalize_output(parsed, self.policy.max_response_bytes)
                        except (ValueError, RecursionError, NodeExecutionError):
                            raise _error("HTTP_INVALID_RESPONSE", "HTTP response must contain finite JSON") from None
                        body_value = parsed
                    else:
                        body_value = text
                    _remaining(deadline)
                    return {"status_code": response.status_code, "body": body_value}
        except NodeExecutionError:
            raise
        except httpx2.TimeoutException:
            raise _error("HTTP_TIMEOUT", "HTTP request timed out") from None
        except httpx2.ConnectError:
            raise _error("HTTP_CONNECTION_ERROR", "HTTP connection failed") from None
        except (httpx2.HTTPError, OSError, UnicodeError, LookupError):
            raise _error("HTTP_REQUEST_FAILED", "HTTP request failed") from None
