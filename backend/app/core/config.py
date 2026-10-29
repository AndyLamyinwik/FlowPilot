from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.http_policy import normalize_host

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLOWPILOT_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_path: Path = PROJECT_ROOT / "data" / "flowpilot.db"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "backend"]
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Reserved feature intent only: Phase 08A installs no live adapter or AI route.
    ai_enabled: bool = False
    execution_max_nodes: int = Field(default=256, ge=1)
    execution_max_output_bytes: int = Field(default=1_048_576, ge=1)
    http_allowed_hosts: list[str] = Field(default_factory=list)
    http_allow_insecure: bool = False
    http_max_request_bytes: int = Field(default=65_536, ge=1)
    http_max_response_bytes: int = Field(default=262_144, ge=1)
    scheduler_enabled: bool = True
    scheduler_workers: int = Field(default=4, ge=1, le=32)
    store_execution_outputs: bool = False
    history_retention_days: int = Field(default=30, ge=1, le=3650)
    history_max_record_bytes: int = Field(default=262_144, ge=16_384, le=16_777_216)

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("Allowed hosts must contain at least one exact hostname or IP")
        try:
            hosts = [normalize_host(value) for value in values]
        except ValueError:
            raise ValueError(
                "Allowed hosts must be exact hostnames or IPs without URLs, ports or wildcards"
            ) from None
        # HTTP Host syntax retains brackets around IPv6 literals.
        return list(dict.fromkeys(f"[{host}]" if ":" in host else host for host in hosts))

    @field_validator("http_allowed_hosts")
    @classmethod
    def validate_http_allowed_hosts(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_host(value) for value in values))

    @field_validator("database_path")
    @classmethod
    def normalize_database_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without a path")
            # Accessing port also validates malformed or out-of-range ports.
            parsed.port
        return values

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()
