from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings


def test_defaults_use_persistent_project_data_directory() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_path == PROJECT_ROOT / "data" / "flowpilot.db"


def test_settings_load_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "from-env.db"
    monkeypatch.setenv("FLOWPILOT_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("FLOWPILOT_CORS_ORIGINS", '["https://flowpilot.example"]')
    monkeypatch.setenv("FLOWPILOT_LOG_LEVEL", "warning")
    settings = Settings(_env_file=None)
    assert settings.database_path == database_path
    assert settings.cors_origins == ["https://flowpilot.example"]
    assert settings.log_level == "WARNING"


def test_dotenv_configuration_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'FLOWPILOT_LOG_LEVEL=debug\nFLOWPILOT_CORS_ORIGINS=["http://localhost:9000"]\nOTHER_SERVICE_VALUE=ignored\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLOWPILOT_LOG_LEVEL", "ERROR")
    settings = Settings(_env_file=env_file)
    assert settings.log_level == "ERROR"
    assert settings.cors_origins == ["http://localhost:9000"]


@pytest.mark.parametrize("origin", ["*", "http://localhost:5173/", "https://example.com/path", "https://user:password@example.com", "file:///tmp", "https://example.com:70000"])
def test_invalid_cors_origin_is_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")
