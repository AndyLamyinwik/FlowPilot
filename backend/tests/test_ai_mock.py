"""Mock results are clearly fake and never depend on credentials or network."""

import json
import os
import socket

import httpx2
import pytest

from app.ai.exceptions import AIProviderConfigurationError, AIProviderError
from app.ai.providers.mock import MockAIProvider
from app.ai.schemas import AIMessage, AIRequest, AIResponse


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Mock provider must not access network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)


def request() -> AIRequest:
    return AIRequest(model="mock-model", messages=[AIMessage(role="user", content="Private prompt marker")])


def test_mock_returns_valid_deterministic_json_without_fabricated_token_usage() -> None:
    provider = MockAIProvider()
    generated = provider.generate(request())
    assert isinstance(generated, AIResponse)
    assert generated == provider.generate(request())
    assert generated.provider == "mock"
    assert generated.model == "mock-model"
    assert generated.content == "Mock response: no AI model was called."
    assert generated.finish_reason == "stop"
    assert generated.usage is None
    assert generated.metadata == {"mock": True}
    assert json.loads(generated.model_dump_json())["usage"] is None


def test_mock_uses_requested_model_label_without_calling_real_model() -> None:
    generated = MockAIProvider().generate(AIRequest(
        model="future-model-label", messages=[{"role": "user", "content": "Text"}],
        temperature=0.5, max_output_tokens=512,
    ))
    assert generated.model == "future-model-label"
    assert generated.content == "Mock response: no AI model was called."
    assert generated.usage is None
    assert MockAIProvider().capabilities.is_mock
    assert not MockAIProvider().capabilities.supports_temperature
    assert not MockAIProvider().capabilities.supports_max_output_tokens


def test_returned_responses_and_metadata_do_not_share_mutable_state() -> None:
    provider = MockAIProvider()
    first = provider.generate(request())
    first.metadata["mock"] = False
    second = provider.generate(request())
    assert second.metadata == {"mock": True}
    assert second is not first and second.metadata is not first.metadata
    assert provider.capabilities is not provider.capabilities


def test_mock_error_uses_unified_safe_error_and_does_not_leak_prompt_or_log_payload(caplog) -> None:
    provider = MockAIProvider(simulate_error=True)
    with pytest.raises(AIProviderError) as raised:
        provider.generate(request())
    assert raised.value.code == "AI_PROVIDER_ERROR"
    assert "Private prompt marker" not in str(raised.value)
    assert "Private prompt marker" not in caplog.text
    # A separate instance is not affected by another instance's test mode.
    assert MockAIProvider().generate(request()).metadata["mock"] is True


def test_mock_does_not_echo_or_log_prompt_and_does_not_read_environment(monkeypatch, caplog) -> None:
    for name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Mock provider cannot read environment")
    with monkeypatch.context() as isolated:
        isolated.setattr(os, "getenv", forbidden)
        result = MockAIProvider().generate(request())
    assert "Private prompt marker" not in result.model_dump_json()
    assert "Private prompt marker" not in caplog.text


@pytest.mark.parametrize("value", [None, 0, 1, "false", {}, []])
def test_error_simulation_requires_developer_boolean(value) -> None:
    with pytest.raises(AIProviderConfigurationError):
        MockAIProvider(simulate_error=value)


@pytest.mark.parametrize("value", [None, {}, "prompt", 123])
def test_generate_requires_the_validated_request_contract(value) -> None:
    with pytest.raises(AIProviderConfigurationError):
        MockAIProvider().generate(value)


def test_constructed_or_mutated_invalid_requests_cannot_bypass_validation() -> None:
    provider = MockAIProvider()
    invalid = AIRequest.model_construct(model="", messages=[])
    with pytest.raises(AIProviderConfigurationError):
        provider.generate(invalid)
    edited = request()
    edited.messages.clear()
    with pytest.raises(AIProviderConfigurationError):
        provider.generate(edited)


def test_generate_does_not_mutate_input_or_retain_message_references() -> None:
    original = request()
    before = original.model_dump()
    provider = MockAIProvider()
    result = provider.generate(original)
    assert original.model_dump() == before
    original.messages.append(AIMessage(role="assistant", content="A later turn"))
    assert result.content == "Mock response: no AI model was called."
    assert result.metadata == {"mock": True}
