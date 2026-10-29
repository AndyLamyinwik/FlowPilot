"""One synchronous contract, independent of workflow and HTTP infrastructure."""

from typing import Protocol, runtime_checkable

from app.ai.schemas import AIProviderCapabilities, AIRequest, AIResponse


@runtime_checkable
class AIProvider(Protocol):
    """Trusted adapters must keep identity stable and raise safe provider errors.

    Capability flags describe supported optional request parameters; adapters
    decide how to handle provider-specific differences. No async or streaming
    contract is introduced in this phase.
    """

    @property
    def provider_id(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def capabilities(self) -> AIProviderCapabilities: ...

    def generate(self, request: AIRequest) -> AIResponse: ...
