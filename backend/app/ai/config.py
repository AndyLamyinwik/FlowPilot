"""Explicit provider configuration, not a credential store or network policy."""

import ipaddress
import re
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.ai.schemas import AISchema, NonBlankString, ProviderID


class AIProviderConfig(AISchema):
    provider_id: ProviderID
    default_model: NonBlankString | None = None
    enabled: bool = False
    # Reserved for a future adapter. This schema alone enforces no I/O deadline.
    timeout: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)
    base_url: str | None = Field(default=None, repr=False)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        message = "AI provider base URL must be HTTP(S) without credentials, query or fragment"
        if not value or re.search(r"[\s\\?#\x00-\x1f\x7f]", value):
            raise ValueError(message)
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port == 0
            ):
                raise ValueError(message)
            host = parsed.hostname
            try:
                ipaddress.ip_address(host)
            except ValueError:
                ascii_host = host.rstrip(".").encode("idna").decode("ascii")
                if len(ascii_host) > 253 or any(
                    re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) is None
                    for label in ascii_host.split(".")
                ):
                    raise ValueError(message)
        except (ValueError, UnicodeError):
            raise ValueError(message) from None
        # Syntactic validation only: no DNS/HTTP, no authorization of this
        # destination, and no exemption from a future adapter's egress policy.
        return value
