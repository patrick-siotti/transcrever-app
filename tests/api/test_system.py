from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings


def test_health_initializes_local_database_and_reports_loopback(tmp_path: Path) -> None:
    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/system/health")

    expected_status = 200
    assert response.status_code == expected_status
    assert response.json() == {
        "api": "ok",
        "database": "ok",
        "worker": "idle",
        "host": "127.0.0.1",
    }
    assert settings.database_path.exists()
    engine = create_engine(f"sqlite:///{settings.database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    engine.dispose()
    assert revision == "20260714_0001"


def test_api_errors_have_stable_envelope_and_request_id(tmp_path: Path) -> None:
    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs")

    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/folders/missing",
            headers={"X-Request-ID": "test-request-123"},
        )

    expected_status = 404
    assert response.status_code == expected_status
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.json() == {
        "code": "not_found",
        "message": "Pasta não encontrada.",
        "details": None,
        "request_id": "test-request-123",
    }
    log_text = (settings.data_dir / "logs" / "transcrever.log").read_text(encoding="utf-8")
    assert "request_id=test-request-123" in log_text
    assert "path=/api/v1/folders/missing" in log_text


def test_diagnostics_and_preferences_are_persistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "transcrever_app.server.api.routes.system.is_pyannote_configured",
        lambda: False,
    )
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        diagnostics = client.get("/api/v1/system/diagnostics")
        defaults = client.get("/api/v1/system/preferences")
        updated = client.put(
            "/api/v1/system/preferences",
            json={"default_model": "medium", "default_diarization_mode": "off"},
        )
    with TestClient(create_app(settings)) as client:
        persisted = client.get("/api/v1/system/preferences")

    success_status = 200
    assert diagnostics.status_code == success_status
    assert diagnostics.json()["worker_enabled"] is False
    assert diagnostics.json()["maintenance"] == {
        "interrupted": 0,
        "imported": 0,
        "missing_roots": 0,
        "invalid_runs": 0,
        "removed_partials": 0,
    }
    assert defaults.json()["default_model"] == "large-v3"
    assert defaults.json()["default_diarization_mode"] == "pyannote"
    assert defaults.json()["pyannote_configured"] is False
    assert updated.json()["default_diarization_mode"] == "off"
    assert persisted.json() == updated.json()
