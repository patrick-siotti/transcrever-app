from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings


def test_upload_is_persisted_and_visible_in_library(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/transcriptions",
            files={"file": ("meeting.mkv", b"media", "video/x-matroska")},
            data={"title": "Reunião importante", "diarization_mode": "auto"},
        )
        library = client.get("/api/v1/library")

    created_status = 201
    assert response.status_code == created_status
    item = response.json()
    assert item["status"] == "queued"
    assert item["title"] == "Reunião importante"
    success_status = 200
    assert library.status_code == success_status
    assert library.json()["transcriptions"][0]["id"] == item["id"]
    stored_source = next(settings.runs_dir.glob("*/source/meeting.mkv"))
    assert stored_source.read_bytes() == b"media"


def test_upload_rejects_invalid_diarization_mode(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/transcriptions",
            files={"file": ("meeting.mkv", b"media", "video/x-matroska")},
            data={"title": "Reunião", "diarization_mode": "invalid"},
        )

    validation_status = 422
    assert response.status_code == validation_status
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Revise os dados informados."
    assert response.json()["request_id"]


def test_upload_rejects_unconfigured_pyannote_before_creating_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    monkeypatch.setattr(
        "transcrever_app.server.api.routes.transcriptions.is_pyannote_configured",
        lambda: False,
    )
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/transcriptions",
            files={"file": ("meeting.mkv", b"media", "video/x-matroska")},
            data={"title": "Reunião", "diarization_mode": "pyannote"},
        )

    validation_status = 422
    assert response.status_code == validation_status
    assert response.json()["message"] == (
        "Pyannote não está configurado. Use Automática ou Agrupamento local."
    )
    assert list(settings.runs_dir.glob("*")) == []


def test_upload_limit_rejects_file_and_removes_partial_job(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
        max_upload_bytes=4,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/transcriptions",
            files={"file": ("large.wav", b"12345", "audio/wav")},
            data={"title": "Too large", "diarization_mode": "off"},
        )
        library = client.get("/api/v1/library")

    too_large_status = 413
    assert response.status_code == too_large_status
    assert response.json()["code"] == "payload_too_large"
    assert library.json()["transcriptions"] == []
    assert list(settings.runs_dir.glob("**/*.part")) == []
    assert list(settings.runs_dir.iterdir()) == []
