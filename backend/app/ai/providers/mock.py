"""Deterministic development/test provider with no network or credentials."""

from pydantic import ValidationError

from app.ai.exceptions import AIProviderConfigurationError, AIProviderError
from app.ai.schemas import AIProviderCapabilities, AIRequest, AIResponse


class MockAIProvider:
    """Fixed mock text, not real model generation or token accounting.

    Optional generation parameters are deliberately not applied. simulate_error
    belongs to test setup, never to a workflow or model request.
    """

    __slots__ = ("_simulate_error",)

    def __init__(self, *, simulate_error: bool = False) -> None:
        if type(simulate_error) is not bool:
            raise AIProviderConfigurationError()
        self._simulate_error = simulate_error

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def provider_name(self) -> str:
        return "Mock AI Provider"

    @property
    def capabilities(self) -> AIProviderCapabilities:
        return AIProviderCapabilities(is_mock=True)

    def generate(self, request: AIRequest) -> AIResponse:
        if not isinstance(request, AIRequest):
            raise AIProviderConfigurationError()
        try:
            # Revalidate instances too: model_construct/model_copy or a mutated
            # messages list must not silently bypass the shared contract.
            validated = AIRequest.model_validate(request)
        except ValidationError:
            raise AIProviderConfigurationError() from None
        if self._simulate_error:
            raise AIProviderError()
        return AIResponse(
            provider=self.provider_id,
            model=validated.model,
            content="Mock response: no AI model was called.",
            finish_reason="stop",
            usage=None,
            metadata={"mock": True},
        )
