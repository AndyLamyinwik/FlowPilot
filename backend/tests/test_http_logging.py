import logging

import httpx2

from app.core.http_policy import HTTPPolicy
from app.core.logging import configure_logging
from app.services.execution.safe_http import SafeHttpClient


def test_application_debug_does_not_enable_http_url_or_header_traces(capsys) -> None:
    url_marker = "private-url-query-marker"
    header_marker = "private-response-header-marker"
    configure_logging("DEBUG")
    try:
        client = SafeHttpClient(
            HTTPPolicy(allowed_hosts=("example.test",)),
            resolver=lambda host, port: ["93.184.216.34"],
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(
                    200,
                    json={"ok": True},
                    headers={"X-Remote-Secret": header_marker},
                )
            ),
        )
        assert client.request("GET", f"https://example.test/?note={url_marker}")["body"] == {"ok": True}
        assert logging.getLogger("httpx2").getEffectiveLevel() == logging.WARNING
        assert logging.getLogger("httpcore2.connection").getEffectiveLevel() == logging.WARNING
        output = capsys.readouterr()
        assert url_marker not in output.out + output.err
        assert header_marker not in output.out + output.err
    finally:
        configure_logging("INFO")
