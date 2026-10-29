"""Provider composition stays explicit, offline and isolated from workflows."""

import importlib
import socket
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest

from app.ai.exceptions import AIProviderConfigurationError, AIProviderNotFoundError
from app.ai.provider import AIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.registry import AIProviderRegistry
from app.ai.schemas import AIProviderCapabilities, AIRequest, AIResponse


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("AI registry must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)


def test_registry_starts_empty_and_explicitly_registers_mock() -> None:
    registry = AIProviderRegistry()
    assert registry.list_providers() == []
    provider = MockAIProvider()
    registry.register(provider)
    assert registry.get("mock") is provider
    assert isinstance(provider, AIProvider)
    metadata = registry.list_providers()
    assert len(metadata) == 1
    assert metadata[0].provider_id == "mock"
    assert metadata[0].provider_name == "Mock AI Provider"
    assert metadata[0].capabilities.is_mock is True
    assert set(metadata[0].model_dump()) == {"provider_id", "provider_name", "capabilities"}


def test_duplicate_registration_is_rejected_without_replacing_provider() -> None:
    registry = AIProviderRegistry()
    original = MockAIProvider()
    registry.register(original)
    with pytest.raises(AIProviderConfigurationError):
        registry.register(MockAIProvider(simulate_error=True))
    assert registry.get("mock") is original


def test_unknown_provider_raises_safe_clear_error_without_echoing_identifier() -> None:
    with pytest.raises(AIProviderNotFoundError) as raised:
        AIProviderRegistry().get("unregistered-private-marker")
    assert raised.value.code == "AI_PROVIDER_NOT_FOUND"
    assert "unregistered-private-marker" not in str(raised.value)


@pytest.mark.parametrize("identifier", [None, [], {}, 1, True, "", " mock", "mock\n", "../module", "openai.api"])
def test_invalid_lookup_does_not_leak_values_or_unhashable_errors(identifier) -> None:
    with pytest.raises(AIProviderConfigurationError):
        AIProviderRegistry().get(identifier)


def test_registry_instances_do_not_share_registration_or_metadata() -> None:
    registry, other = AIProviderRegistry(), AIProviderRegistry()
    registry.register(MockAIProvider())
    listed = registry.list_providers()
    first = listed[0]
    listed.clear()
    assert len(registry.list_providers()) == 1
    assert registry.list_providers()[0] is not first
    assert registry.list_providers()[0].capabilities is not first.capabilities
    assert other.list_providers() == []


def test_trusted_custom_provider_uses_same_registry_without_factory_or_sdk() -> None:
    class CustomProvider:
        provider_id = "custom-local"
        provider_name = "Trusted custom test adapter"
        capabilities = AIProviderCapabilities()

        def generate(self, request: AIRequest) -> AIResponse:
            return AIResponse(provider=self.provider_id, model=request.model, content="Custom test fixture")

    provider = CustomProvider()
    registry = AIProviderRegistry()
    registry.register(provider)
    assert registry.get("custom-local") is provider
    provider.provider_name = "Changed by developer"
    provider.capabilities = AIProviderCapabilities(is_mock=True)
    # Registration captures a public snapshot, not a view of adapter internals.
    listed = registry.list_providers()[0]
    assert listed.provider_name == "Trusted custom test adapter"
    assert listed.capabilities.is_mock is False


@pytest.mark.parametrize("provider", [None, object(), {"provider_id": "mock"}])
def test_incomplete_provider_interface_is_rejected(provider) -> None:
    with pytest.raises(AIProviderConfigurationError):
        AIProviderRegistry().register(provider)


def test_invalid_metadata_and_async_generate_are_rejected_without_echoing_values() -> None:
    class InvalidProvider:
        provider_id = "invalid private marker"
        provider_name = "Test"
        capabilities = AIProviderCapabilities()
        def generate(self, request):
            raise AssertionError("Registry must never execute providers")

    class AsyncProvider(MockAIProvider):
        async def generate(self, request):
            raise AssertionError("Registry must never execute providers")

    class AsyncGeneratorProvider(MockAIProvider):
        async def generate(self, request):
            yield request

    class AsyncCall:
        async def __call__(self, request):
            raise AssertionError("Registry must never execute providers")

    class AsyncCallableProvider(MockAIProvider):
        generate = AsyncCall()

    for provider in [InvalidProvider(), AsyncProvider(), AsyncGeneratorProvider(), AsyncCallableProvider()]:
        with pytest.raises(AIProviderConfigurationError) as raised:
            AIProviderRegistry().register(provider)
        assert "private marker" not in str(raised.value)


def test_imports_do_not_register_providers_or_access_external_services() -> None:
    import app.ai.registry as module
    importlib.reload(module)
    registry = module.AIProviderRegistry()
    assert registry.list_providers() == []


def test_registration_never_calls_generate() -> None:
    class NeverGenerate(MockAIProvider):
        def generate(self, request):
            raise AssertionError("Registration cannot invoke a model")
    registry = AIProviderRegistry()
    registry.register(NeverGenerate())
    assert registry.list_providers()[0].provider_id == "mock"


def test_broken_metadata_property_becomes_safe_configuration_error() -> None:
    class BrokenProvider(MockAIProvider):
        @property
        def provider_name(self):
            raise RuntimeError("private-credential-marker")
    with pytest.raises(AIProviderConfigurationError) as raised:
        AIProviderRegistry().register(BrokenProvider())
    assert "private-credential-marker" not in str(raised.value)
    assert raised.value.__suppress_context__ is True


def test_clean_interpreter_import_and_generate_have_no_network_or_workflow_imports() -> None:
    script = """
import sys

def no_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind', 'http.client.connect', 'urllib.Request'}:
        raise AssertionError('AI import/generation attempted external I/O')

sys.addaudithook(no_network)
from app.ai.registry import AIProviderRegistry
from app.ai.providers.mock import MockAIProvider
from app.ai.schemas import AIRequest

registry = AIProviderRegistry()
registry.register(MockAIProvider())
result = registry.get('mock').generate(AIRequest(model='mock-model', messages=[{'role': 'user', 'content': 'Offline check'}]))
assert result.metadata == {'mock': True}
assert result.usage is None
for name in sys.modules:
    assert name != 'app.main'
    assert not name.startswith(('app.api', 'app.db', 'app.models', 'app.services'))
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True, capture_output=True, text=True, timeout=10,
    )
