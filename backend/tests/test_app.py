import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_and_startup_initialize_empty_workflows_table(settings: Settings) -> None:
    application = create_app(settings)
    assert not settings.database_path.exists()
    with TestClient(application) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert settings.database_path.is_file()
        with application.state.database.connect() as connection:
            assert tuple(connection.execute("PRAGMA foreign_keys").fetchone()) == (1,)
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            assert {row["name"] for row in tables} == {
                "workflows", "workflow_schedules", "workflow_executions"
            }
            assert connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 0


def test_database_persists_across_app_restarts(settings: Settings) -> None:
    application = create_app(settings)
    with TestClient(application):
        with application.state.database.connect() as connection:
            connection.execute("PRAGMA user_version = 7")
    restarted = create_app(settings)
    with TestClient(restarted):
        with restarted.state.database.connect() as connection:
            assert tuple(connection.execute("PRAGMA user_version").fetchone()) == (7,)


def test_cors_allows_configured_origin_and_rejects_other_origins(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-credentials" not in response.headers
        response = client.options(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code == 200
        response = client.options(
            "/api/health",
            headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


def test_unhandled_errors_do_not_expose_internal_details(settings: Settings) -> None:
    application = create_app(settings)

    @application.get("/_test/error")
    def fail() -> None:
        raise RuntimeError("sensitive diagnostic")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/error", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_routes_return_json_404(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/missing")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


def test_unusable_database_path_fails_startup(settings: Settings, tmp_path: Path) -> None:
    directory = tmp_path / "directory.db"
    directory.mkdir()
    invalid_settings = settings.model_copy(update={"database_path": directory})
    with pytest.raises(sqlite3.OperationalError):
        with TestClient(create_app(invalid_settings)):
            pass
