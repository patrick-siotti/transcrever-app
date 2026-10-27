"""Single-threaded persistent transcription runner."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

from transcrever_app.asr.faster_whisper import ASRModelRegistry
from transcrever_app.core.cancellation import CancellationToken
from transcrever_app.core.events import PipelineEvent
from transcrever_app.core.exceptions import ProcessingCancelledError, TranscreverAppError
from transcrever_app.jobs.manager import existing_job_paths
from transcrever_app.pipeline import process_media
from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.persistence.repositories.transcriptions import TranscriptionRepository
from transcrever_app.server.worker.state_machine import JobStatus

Processor = Callable[..., object]


class LocalJobRunner:
    """Consume exactly one persistent job at a time."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        processor: Processor = process_media,
        logger: logging.Logger | None = None,
    ) -> None:
        """Create a stopped runner."""
        self._session_factory = session_factory
        self._processor = processor
        self._logger = logger or logging.getLogger(__name__)
        self._wake_event = Event()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._models = ASRModelRegistry()
        self._cancellations: dict[str, CancellationToken] = {}
        self._cancellations_lock = Lock()

    def start(self) -> None:
        """Start the worker thread once."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run, name="transcrever-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        """Wake the worker after a queue mutation."""
        self._wake_event.set()

    def request_cancel(self, job_id: str) -> None:
        """Request cancellation for the active job when present."""
        with self._cancellations_lock:
            token = self._cancellations.get(job_id)
        if token is not None:
            token.cancel()
        self.wake()

    def stop(self) -> None:
        """Stop and join the worker cleanly."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._models.close()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            processed = self.process_next()
            if not processed:
                self._wake_event.wait(timeout=2)
                self._wake_event.clear()

    def process_next(self) -> bool:
        """Process at most one queued job and report whether one was claimed."""
        with self._session_factory() as session:
            repository = TranscriptionRepository(session)
            item = repository.claim_next()
            session.commit()
            if item is None:
                return False
            config = json.loads(item.config_json)
            self._logger.info("job_id=%s claimed status=%s", item.id, item.status)
        cancellation = CancellationToken()
        with self._cancellations_lock:
            self._cancellations[item.id] = cancellation

        def on_event(event: PipelineEvent) -> None:
            with self._session_factory() as event_session:
                event_repository = TranscriptionRepository(event_session)
                current = event_repository.get(item.id)
                if current is not None:
                    if current.status == JobStatus.CANCEL_REQUESTED.value:
                        cancellation.cancel()
                        return
                    event_repository.apply_event(current, event)
                    event_session.commit()
                    self._logger.info(
                        "job_id=%s stage=%s progress=%.3f",
                        item.id,
                        event.stage.value,
                        event.progress or 0.0,
                    )

        try:
            self._run_item(item, config, cancellation, on_event)
        except ProcessingCancelledError:
            self._record_terminal(item.id, JobStatus.CANCELLED)
        except (OSError, RuntimeError, TranscreverAppError, ValueError) as exc:
            self._record_failure(item.id, exc)
        else:
            self._record_terminal(item.id, JobStatus.COMPLETED)
        finally:
            with self._cancellations_lock:
                self._cancellations.pop(item.id, None)
        return True

    def _run_item(
        self,
        item: Transcription,
        config: dict[str, object],
        cancellation: CancellationToken,
        on_event: Callable[[PipelineEvent], None],
    ) -> None:
        source_path = Path(item.source_path)
        diarization_mode = str(config["diarization_mode"])
        speaker_count_value = config["speaker_count"]
        speaker_count = (
            int(speaker_count_value) if isinstance(speaker_count_value, (int, float, str)) else None
        )
        self._processor(
            source_path,
            job_paths=existing_job_paths(item.id, Path(item.job_root), source_path),
            model_name=str(config["model_name"]),
            diarize=diarization_mode != "off",
            diarization_method="auto" if diarization_mode == "off" else diarization_mode,
            speaker_count=speaker_count,
            on_event=on_event,
            cancellation=cancellation,
            model_registry=self._models,
        )

    def _record_terminal(self, item_id: str, status: JobStatus) -> None:
        with self._session_factory() as session:
            repository = TranscriptionRepository(session)
            current = repository.get(item_id)
            if current is None:
                return
            current.status = status.value
            current.stage = status.value
            if status == JobStatus.COMPLETED:
                current.progress = 1.0
            session.commit()

    def _record_failure(self, item_id: str, exc: BaseException) -> None:
        with self._session_factory() as session:
            repository = TranscriptionRepository(session)
            current = repository.get(item_id)
            if current is None:
                return
            current.status = JobStatus.FAILED.value
            current.stage = JobStatus.FAILED.value
            current.error_code = "transcription_failed"
            current.error_message = str(exc)
            session.commit()
            self._logger.exception(
                "job_id=%s failed error_code=transcription_failed",
                item_id,
                exc_info=exc,
            )
