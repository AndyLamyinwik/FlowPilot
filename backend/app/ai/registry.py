"""Explicit, process-local registration of trusted provider instances."""

from inspect import isasyncgenfunction, iscoroutinefunction

from pydantic import TypeAdapter, ValidationError

from app.ai.exceptions import AIProviderConfigurationError, AIProviderNotFoundError
from app.ai.provider import AIProvider
from app.ai.schemas import AIProviderMetadata, ProviderID

_PROVIDER_ID = TypeAdapter(ProviderID)


class AIProviderRegistry:
    """Each registry starts empty and has no credential or activation settings.

    Registration is a trusted application composition step, not a plugin loader
    or a public API. It never calls generate(). Register providers before use;
    concurrent mutation is not part of this small registry's contract.
    """

    def __init__(self) -> None:
        self._providers: dict[str, tuple[AIProvider, AIProviderMetadata]] = {}

    def register(self, provider: AIProvider) -> None:
        try:
            generate = getattr(provider, "generate", None)
            if not callable(generate) or any(
                iscoroutinefunction(method) or isasyncgenfunction(method)
                for method in (generate, getattr(generate, "__call__", None))
            ):
                raise AIProviderConfigurationError()
            metadata = AIProviderMetadata(
                provider_id=provider.provider_id,
                provider_name=provider.provider_name,
                capabilities=provider.capabilities,
            )
        except AIProviderConfigurationError:
            raise
        except Exception:
            # Do not expose an invalid metadata value or provider property error.
            raise AIProviderConfigurationError() from None
        if metadata.provider_id in self._providers:
            raise AIProviderConfigurationError()
        self._providers[metadata.provider_id] = (provider, metadata.model_copy(deep=True))

    def get(self, provider_id: str) -> AIProvider:
        try:
            identifier = _PROVIDER_ID.validate_python(provider_id, strict=True)
        except (TypeError, ValueError, ValidationError):
            raise AIProviderConfigurationError() from None
        registered = self._providers.get(identifier)
        if registered is None:
            raise AIProviderNotFoundError()
        return registered[0]

    def list_providers(self) -> list[AIProviderMetadata]:
        """Return independent public metadata snapshots, never adapter internals."""
        return [metadata.model_copy(deep=True) for _, metadata in self._providers.values()]
