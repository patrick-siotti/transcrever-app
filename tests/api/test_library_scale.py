from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings
from transcrever_app.server.persistence.models import Folder, Transcription
from transcrever_app.server.worker.state_machine import JobStatus


def test_library_contract_handles_500_items_and_100_folders(tmp_path: Path) -> None:
    folder_count = 100
    transcription_count = 500
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add_all(
                Folder(
                    id=f"folder-{index:03}",
                    name=f"Folder {index:03}",
                    normalized_name=f"folder {index:03}",
                    position=index,
                )
                for index in range(folder_count)
            )
            session.add_all(
                Transcription(
                    id=f"job-{index:03}",
                    title=f"Transcription {index:03}",
                    original_filename=f"audio-{index:03}.wav",
                    source_path=str(tmp_path / "runs" / f"job-{index:03}" / "source.wav"),
                    job_root=str(tmp_path / "runs" / f"job-{index:03}"),
                    outputs_path=str(tmp_path / "runs" / f"job-{index:03}" / "outputs"),
                    status=JobStatus.COMPLETED.value,
                    stage=JobStatus.COMPLETED.value,
                    position=index,
                )
                for index in range(transcription_count)
            )
            session.commit()

        started_at = perf_counter()
        response = client.get("/api/v1/library")
        elapsed = perf_counter() - started_at

    success_status = 200
    maximum_elapsed_seconds = 3.0
    assert response.status_code == success_status
    assert len(response.json()["folders"]) == folder_count
    assert len(response.json()["transcriptions"]) == transcription_count
    assert elapsed < maximum_elapsed_seconds
