import json
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings
from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.worker.state_machine import JobStatus


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )


def _upload(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/transcriptions",
        files={"file": ("meeting.wav", b"media", "audio/wav")},
        data={"title": "Reunião", "diarization_mode": "off"},
    )
    created_status = 201
    assert response.status_code == created_status
    return cast("dict[str, object]", response.json())


def test_queued_job_can_be_cancelled_and_cannot_be_retried(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])

        cancelled = client.post(f"/api/v1/transcriptions/{item_id}/cancel")
        retry = client.post(f"/api/v1/transcriptions/{item_id}/retry")

    success_status = 200
    conflict_status = 409
    assert cancelled.status_code == success_status
    assert cancelled.json()["status"] == JobStatus.CANCELLED.value
    assert retry.status_code == conflict_status


def test_failed_job_can_be_requeued_and_clears_transient_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])
        with app.state.session_factory() as session:
            item = session.get(Transcription, item_id)
            assert item is not None
            item.status = JobStatus.FAILED.value
            item.stage = JobStatus.FAILED.value
            item.progress = 0.7
            item.error_code = "transcription_failed"
            item.error_message = "failure"
            session.commit()

        response = client.post(f"/api/v1/transcriptions/{item_id}/retry")

    success_status = 200
    assert response.status_code == success_status
    payload = response.json()
    assert payload["status"] == JobStatus.QUEUED.value
    assert payload["progress"] == 0.0
    assert payload["error_code"] is None


def test_retry_switches_unconfigured_pyannote_job_to_automatic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    monkeypatch.setattr(
        "transcrever_app.server.api.routes.transcriptions.is_pyannote_configured",
        lambda: False,
    )
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])
        with app.state.session_factory() as session:
            item = session.get(Transcription, item_id)
            assert item is not None
            item.status = JobStatus.FAILED.value
            item.stage = JobStatus.FAILED.value
            item.diarization_mode = "pyannote"
            item.config_json = json.dumps(
                {"model_name": "large-v3", "diarization_mode": "pyannote"}
            )
            session.commit()

        response = client.post(f"/api/v1/transcriptions/{item_id}/retry")

    success_status = 200
    assert response.status_code == success_status
    assert response.json()["diarization_mode"] == "auto"
    with app.state.session_factory() as session:
        item = session.get(Transcription, item_id)
        assert item is not None
        assert json.loads(item.config_json)["diarization_mode"] == "auto"


def test_result_is_loaded_from_artifact_and_marked_viewed(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])
        with app.state.session_factory() as session:
            item = session.get(Transcription, item_id)
            assert item is not None
            result_path = Path(item.outputs_path) / "result.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(
                    {
                        "job_id": item_id,
                        "duration_seconds": 3.5,
                        "segments": [
                            {"start": 0.0, "end": 3.5, "text": "Olá", "speaker": "Falante 1"}
                        ],
                        "speakers": ["Falante 1"],
                        "mode": "diarized",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            item.status = JobStatus.COMPLETED.value
            item.stage = JobStatus.COMPLETED.value
            session.commit()

        result = client.get(f"/api/v1/transcriptions/{item_id}/result")
        viewed = client.post(f"/api/v1/transcriptions/{item_id}/mark-viewed")

    success_status = 200
    assert result.status_code == success_status
    assert result.json()["segments"][0]["speaker"] == "Falante 1"
    assert viewed.status_code == success_status
    assert viewed.json()["viewed_at"] is not None


def test_terminal_job_moves_to_trash_and_restores_without_duplication(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])
        active_root = settings.runs_dir / item_id

        deleted = client.delete(f"/api/v1/transcriptions/{item_id}")
        library_after_delete = client.get("/api/v1/library")
        restored = client.post(f"/api/v1/transcriptions/{item_id}/restore")

    no_content_status = 204
    success_status = 200
    assert deleted.status_code == no_content_status
    assert library_after_delete.json()["transcriptions"] == []
    assert restored.status_code == success_status
    assert restored.json()["id"] == item_id
    assert active_root.is_dir()
    assert not (settings.data_dir / "trash" / item_id).exists()


def test_trash_lists_and_permanently_deletes_item(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        created = _upload(client)
        item_id = str(created["id"])
        client.delete(f"/api/v1/transcriptions/{item_id}")

        trash = client.get("/api/v1/trash")
        removed = client.delete(f"/api/v1/trash/{item_id}")
        trash_after = client.get("/api/v1/trash")
        restore_after = client.post(f"/api/v1/transcriptions/{item_id}/restore")

    success_status = 200
    no_content_status = 204
    not_found_status = 404
    assert trash.status_code == success_status
    assert [item["id"] for item in trash.json()] == [item_id]
    assert removed.status_code == no_content_status
    assert trash_after.json() == []
    assert restore_after.status_code == not_found_status
