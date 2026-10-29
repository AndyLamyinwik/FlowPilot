import os
from pathlib import Path

import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in os.environ:
        if name.startswith("FLOWPILOT_"):
            monkeypatch.delenv(name)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    configured = Settings(_env_file=None, database_path=tmp_path / "data" / "test.db")
    # TestClient's synthetic name is explicitly allowed only by this test fixture.
    return configured.model_copy(update={"allowed_hosts": [*configured.allowed_hosts, "testserver"]})
