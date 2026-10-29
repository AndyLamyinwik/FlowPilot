"""Provider configuration and errors never initialize a client or need keys."""

import json
import socket

import pytest
from pydantic import ValidationError

from app.ai.config import AIProviderConfig
from app.ai.exceptions import (
    AIProviderConfigurationError, AIProviderError, AIProviderNotFoundError,
    AIProviderRateLimitError, AIProviderResponseError, AIProviderTimeoutError,
)


def test_provider_config_defaults_are_disabled_without_a_model_or_credentials():
    item = AIProviderConfig(provider_id="mock")
    assert item.enabled is False
    assert item.default_model is None and item.base_url is None
    assert item.timeout == 30
    public = json.loads(item.model_dump_json())
    assert set(public) == {"provider_id", "default_model", "enabled", "timeout", "base_url"}
    assert not any("key" in field or "credential" in field for field in public)


@pytest.mark.parametrize("field,value", [
    ("provider_id", ""), ("provider_id", "Bad Provider"), ("default_model", " "),
    ("enabled", "true"), ("enabled", 1), ("timeout", 0), ("timeout", -1),
    ("timeout", 301), ("timeout", float("nan")), ("timeout", float("inf")),
    ("timeout", True), ("timeout", "30"),
])
def test_invalid_provider_configuration_is_rejected(field, value):
    with pytest.raises(ValidationError):
        AIProviderConfig.model_validate({"provider_id": "mock", field: value})


@pytest.mark.parametrize("url", [
    "https://api.example.test/v1", "http://127.0.0.1:11434", "http://[::1]:11434/v1",
    "https://例子.測試/v1", "https://api.example.test:443/v1/",
])
def test_base_url_validation_is_syntactic_and_performs_no_dns(monkeypatch, url):
    def no_network(*args, **kwargs):
        pytest.fail("Configuration must not access DNS or sockets")
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    config = AIProviderConfig(provider_id="custom", default_model=" model ", base_url=url, timeout=300)
    assert config.base_url == url
    assert config.default_model == "model"
    assert config.enabled is False


@pytest.mark.parametrize("url", [
    "", " ", "api.example.test", "file:///tmp/private", "ftp://example.test/file",
    "https://user:fixture-password@example.test/v1", "https://example.test?api_key=fixture-key",
    "https://example.test#fragment", "https://example.test?", "https://example.test#",
    "https://example.test\\private", "https://example.test/\n", "https://example.test:0",
    "https://example.test:99999", "https://example.test:bad", "https://", "https://bad_host/v1",
    "http://[::1", "https://example.test%25/v1",
])
def test_base_url_rejects_credentials_queries_and_malformed_origins(url):
    with pytest.raises(ValidationError) as caught:
        AIProviderConfig(provider_id="custom", base_url=url)
    assert "fixture-password" not in str(caught.value)
    assert "fixture-key" not in str(caught.value)


@pytest.mark.parametrize("field", ["api_key", "credentials", "authorization", "headers"])
def test_credentials_cannot_become_serialized_provider_configuration(field):
    with pytest.raises(ValidationError) as caught:
        AIProviderConfig.model_validate({"provider_id": "mock", field: "fixture-sensitive-key"})
    assert "fixture-sensitive-key" not in str(caught.value)
    assert field not in AIProviderConfig.model_json_schema()["properties"]


@pytest.mark.parametrize("error_type", [
    AIProviderError, AIProviderConfigurationError, AIProviderNotFoundError,
    AIProviderTimeoutError, AIProviderRateLimitError, AIProviderResponseError,
])
def test_provider_errors_have_safe_fixed_messages_and_no_payload_arguments(error_type):
    error = error_type()
    assert isinstance(error, AIProviderError)
    assert error.code.startswith("AI_PROVIDER_")
    assert str(error) == error.public_message
    assert error.args == (error.public_message,)
    with pytest.raises(TypeError):
        error_type("fixture-sensitive-key")
