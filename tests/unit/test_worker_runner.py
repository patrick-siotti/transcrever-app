from collections.abc import Callable
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session, sessionmaker

from transcrever_app.core.events import PipelineEvent, PipelineStage
from transcrever_app.server.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
    upgrade_schema,
)
from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.worker.runner import LocalJobRunner
from transcrever_app.server.worker.state_machine import JobStatus


def _queued_item(tmp_path: Path) -> tuple[sessionmaker[Session], str]:
    engine = create_sqlite_engine(tmp_path / "app.sqlite3")
    upgrade_schema(engine)
    factory = create_session_factory(engine)
    root = tmp_path / "runs" / "job"
    source = root / "source" / "audio.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    (root / "outputs").mkdir()
    with factory() as session:
        session.add(
            Transcription(
                id="job",
                title="Job",
                original_filename="audio.wav",
                source_path=str(source),
                job_root=str(root),
                outputs_path=str(root / "outputs"),
                status=JobStatus.QUEUED.value,
                stage=JobStatus.QUEUED.value,
                config_json='{"model_name":"tiny","diarization_mode":"off","speaker_count":null}',
            )
        )
        session.commit()
    return factory, "job"


def test_runner_persists_progress_and_completion(tmp_path: Path) -> None:
    factory, item_id = _queued_item(tmp_path)

    def processor(_source: Path, **kwargs: object) -> object:
        callback = cast("Callable[[PipelineEvent], None]", kwargs["on_event"])
        callback(
            PipelineEvent(
                stage=PipelineStage.TRANSCRIBING,
                progress=0.6,
                message="Transcribing",
                current_seconds=6,
                total_seconds=10,
            )
        )
        return object()

    runner = LocalJobRunner(factory, processor=processor)

    assert runner.process_next() is True
    with factory() as session:
        item = session.get(Transcription, item_id)
        assert item is not None
        assert item.status == JobStatus.COMPLETED.value
        assert item.progress == 1.0
        expected_duration = 10
        assert item.duration_seconds == expected_duration
        assert item.attempt_count == 1
    runner.stop()


def test_runner_records_sanitized_failure_state(tmp_path: Path) -> None:
    factory, item_id = _queued_item(tmp_path)

    def processor(_source: Path, **_kwargs: object) -> object:
        raise RuntimeError("decoder failed")

    runner = LocalJobRunner(factory, processor=processor)

    assert runner.process_next() is True
    with factory() as session:
        item = session.get(Transcription, item_id)
        assert item is not None
        assert item.status == JobStatus.FAILED.value
        assert item.error_code == "transcription_failed"
        assert item.error_message == "decoder failed"
    runner.stop()


def test_runner_reports_empty_queue(tmp_path: Path) -> None:
    factory, _item_id = _queued_item(tmp_path)
    with factory() as session:
        item = session.get(Transcription, "job")
        assert item is not None
        item.status = JobStatus.CANCELLED.value
        session.commit()
    runner = LocalJobRunner(factory)

    assert runner.process_next() is False
    runner.stop()
