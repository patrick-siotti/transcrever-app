import json
from pathlib import Path

from sqlalchemy.orm import Session

from transcrever_app.server.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
    upgrade_schema,
)
from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.services.maintenance_service import run_startup_maintenance
from transcrever_app.server.worker.state_machine import JobStatus


def _session(tmp_path: Path) -> tuple[Session, Path]:
    engine = create_sqlite_engine(tmp_path / "app.sqlite3")
    upgrade_schema(engine)
    return create_session_factory(engine)(), tmp_path / "runs"


def test_startup_recovers_active_job_as_interrupted(tmp_path: Path) -> None:
    session, runs_dir = _session(tmp_path)
    root = runs_dir / "active"
    root.mkdir(parents=True)
    session.add(
        Transcription(
            id="active",
            title="Active",
            original_filename="audio.wav",
            source_path=str(root / "audio.wav"),
            job_root=str(root),
            outputs_path=str(root / "outputs"),
            status=JobStatus.TRANSCRIBING.value,
        )
    )
    session.commit()

    report = run_startup_maintenance(session, runs_dir)
    item = session.get(Transcription, "active")

    assert report.interrupted == 1
    assert item is not None
    assert item.status == JobStatus.INTERRUPTED.value
    assert item.error_code == "application_restarted"
    session.close()


def test_startup_imports_completed_run_idempotently(tmp_path: Path) -> None:
    session, runs_dir = _session(tmp_path)
    root = runs_dir / "old-job"
    source = root / "source" / "meeting.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    outputs = root / "outputs"
    outputs.mkdir()
    (outputs / "result.json").write_text(json.dumps({"duration_seconds": 12.5}), encoding="utf-8")
    (root / "metadata.json").write_text(
        json.dumps({"job_id": "old-job", "asr": {"model_name": "large-v3"}}),
        encoding="utf-8",
    )

    first = run_startup_maintenance(session, runs_dir)
    second = run_startup_maintenance(session, runs_dir)

    assert first.imported == 1
    assert second.imported == 0
    assert session.get(Transcription, "old-job") is not None
    session.close()


def test_startup_flags_registered_item_with_missing_root(tmp_path: Path) -> None:
    session, runs_dir = _session(tmp_path)
    session.add(
        Transcription(
            id="missing",
            title="Missing",
            original_filename="missing.wav",
            source_path=str(runs_dir / "missing" / "source" / "missing.wav"),
            job_root=str(runs_dir / "missing"),
            outputs_path=str(runs_dir / "missing" / "outputs"),
            status=JobStatus.COMPLETED.value,
        )
    )
    session.commit()

    report = run_startup_maintenance(session, runs_dir)
    item = session.get(Transcription, "missing")

    assert report.missing_roots == 1
    assert item is not None
    assert item.error_code == "storage_missing"
    session.close()


def test_startup_removes_abandoned_partial_files(tmp_path: Path) -> None:
    session, runs_dir = _session(tmp_path)
    partial = runs_dir / "abandoned" / "source" / "audio.wav.part"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")

    report = run_startup_maintenance(session, runs_dir)

    assert report.removed_partials == 1
    assert not partial.exists()
    session.close()
