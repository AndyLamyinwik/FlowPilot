"""Provider-neutral, text-only contracts; independent of workflow internals."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator

ProviderID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
NonBlankString = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
MAX_METADATA_DEPTH = 32
# This only rejects recognizable credential fields. It cannot classify secrets
# embedded in arbitrary text, and must not be presented as a secret scanner.
_SENSITIVE_METADATA_KEYS = frozenset({
    "password", "passwd", "pwd", "apikey", "xapikey", "secret", "clientsecret",
    "accesstoken", "refreshtoken", "authtoken", "xauthtoken", "bearertoken",
    "authorization", "proxyauthorization", "cookie", "setcookie", "privatekey",
    "token", "credentials",
})


def _ensure_utf8(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("AI text must contain valid Unicode") from None


class AISchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True,
        hide_input_in_errors=True, revalidate_instances="always",
    )

    @field_validator("*")
    @classmethod
    def validate_text_encoding(cls, value: object) -> object:
        if type(value) is str:
            _ensure_utf8(value)
        return value


class AIMessage(AISchema):
    role: Literal["system", "user", "assistant"]
    content: str = Field(repr=False)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("AI message content must be nonblank text")
        # Preserve prompt whitespace; validation must not rewrite its meaning.
        return value


class AIRequest(AISchema):
    model: NonBlankString
    messages: list[AIMessage] = Field(min_length=1, repr=False)
    # None means unspecified. Adapters decide if and how a model supports a
    # supplied parameter; these are not universal vendor defaults.
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, gt=0)


class AIUsage(AISchema):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class AIResponse(AISchema):
    provider: ProviderID
    model: NonBlankString
    content: str = Field(repr=False)
    finish_reason: NonBlankString | None = None
    usage: AIUsage | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict, repr=False)

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: object) -> object:
        if type(value) is not dict:
            raise ValueError("AI response metadata must be a JSON object")
        pending = [(value, 0, frozenset())]
        while pending:
            item, depth, ancestors = pending.pop()
            if type(item) in {dict, list}:
                if depth >= MAX_METADATA_DEPTH or id(item) in ancestors:
                    raise ValueError("AI response metadata is too deep or cyclic")
                lineage = ancestors | {id(item)}
                if type(item) is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            raise ValueError("AI response metadata keys must be strings")
                        _ensure_utf8(key)
                        normalized = "".join(character for character in key.casefold() if character.isalnum())
                        if normalized in _SENSITIVE_METADATA_KEYS:
                            raise ValueError("Credentials are not allowed in AI response metadata")
                        pending.append((child, depth + 1, lineage))
                else:
                    pending.extend((child, depth + 1, lineage) for child in item)
            elif type(item) is str:
                _ensure_utf8(item)
            elif item is None or type(item) in {bool, int}:
                continue
            elif type(item) is float and math.isfinite(item):
                continue
            else:
                raise ValueError("AI response metadata must contain only finite JSON values")
        return value


class AIProviderCapabilities(AISchema):
    is_mock: bool = False
    supports_temperature: bool = False
    supports_max_output_tokens: bool = False


class AIProviderMetadata(AISchema):
    provider_id: ProviderID
    provider_name: NonBlankString
    capabilities: AIProviderCapabilities
