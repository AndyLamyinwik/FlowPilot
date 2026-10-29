"""Safe public provider errors; raw vendor exceptions are never their message."""


class AIProviderError(Exception):
    code = "AI_PROVIDER_ERROR"
    public_message = "AI provider operation failed"

    def __init__(self) -> None:
        super().__init__(self.public_message)


class AIProviderNotFoundError(AIProviderError):
    code = "AI_PROVIDER_NOT_FOUND"
    public_message = "AI provider is not registered"


class AIProviderConfigurationError(AIProviderError):
    code = "AI_PROVIDER_CONFIGURATION_ERROR"
    public_message = "AI provider configuration is invalid"


class AIProviderTimeoutError(AIProviderError):
    code = "AI_PROVIDER_TIMEOUT"
    public_message = "AI provider operation timed out"


class AIProviderRateLimitError(AIProviderError):
    code = "AI_PROVIDER_RATE_LIMIT"
    public_message = "AI provider rate limit exceeded"


class AIProviderResponseError(AIProviderError):
    code = "AI_PROVIDER_RESPONSE_ERROR"
    public_message = "AI provider returned an invalid response"
