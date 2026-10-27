"""Transcription application use cases."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from transcrever_app.jobs.manager import create_job_paths
from transcrever_app.server.persistence.models import Folder, Transcription
from transcrever_app.server.persistence.repositories.transcriptions import TranscriptionRepository
from transcrever_app.server.worker.state_machine import JobStatus


class TranscriptionNotFoundError(LookupError):
    """Raised when a transcription does not exist."""


class InvalidTranscriptionStateError(ValueError):
    """Raised when an action is unavailable for the current state."""


class UploadTooLargeError(ValueError):
    """Raised when a streamed upload exceeds the configured local limit."""


class TranscriptionService:
    """Coordinate upload, persistence, and library mutations."""

    def __init__(
        self,
        session: Session,
        runs_dir: Path,
        data_dir: Path,
        max_upload_bytes: int = 20 * 1024 * 1024 * 1024,
    ) -> None:
        """Create a service for one transaction."""
        self.repository = TranscriptionRepository(session)
        self.session = session
        self.runs_dir = runs_dir
        self.data_dir = data_dir
        self.max_upload_bytes = max_upload_bytes

    def create_from_upload(
        self,
        *,
        stream: BinaryIO,
        original_filename: str,
        title: str,
        model_name: str,
        diarization_mode: str,
        speaker_count: int | None,
    ) -> Transcription:
        """Persist a streamed source and enqueue its job."""
        safe_filename = _safe_filename(original_filename)
        job_paths = create_job_paths(Path(safe_filename), runs_dir=self.runs_dir)
        if job_paths.source_file is None:
            message = "Job sem destino para o arquivo original."
            raise RuntimeError(message)
        temporary_path = job_paths.source_file.with_suffix(f"{job_paths.source_file.suffix}.part")
        try:
            _copy_stream(stream, temporary_path, max_bytes=self.max_upload_bytes)
            temporary_path.replace(job_paths.source_file)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            shutil.rmtree(job_paths.root, ignore_errors=True)
            raise
        item = Transcription(
            id=job_paths.job_id,
            title=title.strip(),
            original_filename=original_filename,
            source_path=str(job_paths.source_file.resolve()),
            job_root=str(job_paths.root.resolve()),
            outputs_path=str(job_paths.output_dir.resolve()),
            status=JobStatus.QUEUED.value,
            stage=JobStatus.QUEUED.value,
            model_name=model_name,
            diarization_mode=diarization_mode,
            speaker_count=speaker_count,
            position=self.repository.next_position(None),
            config_json=json.dumps(
                {
                    "model_name": model_name,
                    "diarization_mode": diarization_mode,
                    "speaker_count": speaker_count,
                }
            ),
        )
        return self.repository.add(item)

    def get(self, transcription_id: str) -> Transcription:
        """Return one item or raise a domain error."""
        item = self.repository.get(transcription_id)
        if item is None:
            raise TranscriptionNotFoundError(transcription_id)
        return item

    def list_library(self, folder_id: str | None = None) -> list[Transcription]:
        """Return visible library items."""
        return self.repository.list_library(folder_id)

    def list_trash(self) -> list[Transcription]:
        """Return deleted items available for restore or permanent removal."""
        return self.repository.list_deleted()

    def patch(
        self,
        transcription_id: str,
        *,
        title: str | None,
        is_pinned: bool | None,
        folder_id: str | None = None,
        update_folder: bool = False,
        position: int | None = None,
    ) -> Transcription:
        """Update editable metadata."""
        item = self.get(transcription_id)
        if title is not None:
            item.title = title.strip()
        if is_pinned is not None:
            item.is_pinned = is_pinned
        if update_folder:
            if folder_id is not None:
                folder = self.session.get(Folder, folder_id)
                if folder is None or folder.deleted_at is not None:
                    raise TranscriptionNotFoundError(f"folder:{folder_id}")
            if item.folder_id != folder_id:
                new_position = self.repository.next_position(folder_id)
                item.folder_id = folder_id
                item.position = new_position
        if position is not None:
            item.position = position
        return item

    def cancel(self, transcription_id: str) -> Transcription:
        """Cancel a queued job or request cooperative cancellation for an active job."""
        item = self.get(transcription_id)
        status = JobStatus(item.status)
        if status == JobStatus.QUEUED:
            self.repository.transition(item, JobStatus.CANCELLED)
            return item
        active = {
            JobStatus.PREPARING,
            JobStatus.LOADING_MODEL,
            JobStatus.TRANSCRIBING,
            JobStatus.DIARIZING,
            JobStatus.ALIGNING,
        }
        if status in active:
            self.repository.transition(item, JobStatus.CANCEL_REQUESTED)
            return item
        message = f"Não é possível cancelar uma transcrição em estado {status.value}."
        raise InvalidTranscriptionStateError(message)

    def retry(
        self, transcription_id: str, *, pyannote_configured: bool = True
    ) -> Transcription:
        """Requeue a failed or interrupted job."""
        item = self.get(transcription_id)
        status = JobStatus(item.status)
        if status not in {JobStatus.FAILED, JobStatus.INTERRUPTED}:
            message = f"Não é possível repetir uma transcrição em estado {status.value}."
            raise InvalidTranscriptionStateError(message)
        if item.diarization_mode == "pyannote" and not pyannote_configured:
            config = json.loads(item.config_json)
            config["diarization_mode"] = "auto"
            item.config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
            item.diarization_mode = "auto"
        self.repository.transition(item, JobStatus.QUEUED)
        item.progress = 0.0
        item.processed_seconds = None
        item.error_code = None
        item.error_message = None
        item.warning_message = None
        return item

    def mark_viewed(self, transcription_id: str) -> Transcription:
        """Mark a result as viewed."""
        item = self.get(transcription_id)
        item.viewed_at = datetime.now(tz=UTC)
        return item

    def get_result(self, transcription_id: str) -> dict[str, object]:
        """Load the canonical result artifact for a completed job."""
        item = self.get(transcription_id)
        result_path = Path(item.outputs_path) / "result.json"
        _ensure_within(Path(item.job_root), result_path)
        if not result_path.is_file():
            raise InvalidTranscriptionStateError("O resultado ainda não está disponível.")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise InvalidTranscriptionStateError("O arquivo de resultado é inválido.")
        return payload

    def soft_delete(self, transcription_id: str) -> Transcription:
        """Move a terminal job to the application trash and hide it."""
        item = self.get(transcription_id)
        if item.status == JobStatus.QUEUED.value:
            self.repository.transition(item, JobStatus.CANCELLED)
        if item.status in {
            JobStatus.PREPARING.value,
            JobStatus.LOADING_MODEL.value,
            JobStatus.TRANSCRIBING.value,
            JobStatus.DIARIZING.value,
            JobStatus.ALIGNING.value,
            JobStatus.EXPORTING.value,
            JobStatus.CANCEL_REQUESTED.value,
        }:
            raise InvalidTranscriptionStateError("Cancele o processamento antes de excluir.")
        source_root = Path(item.job_root).resolve()
        _ensure_within(self.runs_dir, source_root)
        trash_root = (self.data_dir / "trash" / item.id).resolve()
        _ensure_within(self.data_dir / "trash", trash_root)
        trash_root.parent.mkdir(parents=True, exist_ok=True)
        if source_root.exists():
            if trash_root.exists():
                shutil.rmtree(trash_root)
            source_root.replace(trash_root)
        relative_source = Path(item.source_path).resolve().relative_to(source_root)
        relative_outputs = Path(item.outputs_path).resolve().relative_to(source_root)
        item.job_root = str(trash_root)
        item.source_path = str(trash_root / relative_source)
        item.outputs_path = str(trash_root / relative_outputs)
        item.deleted_at = datetime.now(tz=UTC)
        return item

    def restore(self, transcription_id: str) -> Transcription:
        """Restore one deleted job from the application trash."""
        item = self.repository.get_including_deleted(transcription_id)
        if item is None or item.deleted_at is None:
            raise TranscriptionNotFoundError(transcription_id)
        trash_root = Path(item.job_root).resolve()
        _ensure_within(self.data_dir / "trash", trash_root)
        restored_root = (self.runs_dir / item.id).resolve()
        _ensure_within(self.runs_dir, restored_root)
        if restored_root.exists():
            raise InvalidTranscriptionStateError("Já existe uma pasta ativa para esta transcrição.")
        relative_source = Path(item.source_path).resolve().relative_to(trash_root)
        relative_outputs = Path(item.outputs_path).resolve().relative_to(trash_root)
        trash_root.replace(restored_root)
        item.job_root = str(restored_root)
        item.source_path = str(restored_root / relative_source)
        item.outputs_path = str(restored_root / relative_outputs)
        item.deleted_at = None
        return item

    def permanently_delete(self, transcription_id: str) -> None:
        """Remove one trashed job from controlled storage and persistence."""
        item = self.repository.get_including_deleted(transcription_id)
        if item is None or item.deleted_at is None:
            raise TranscriptionNotFoundError(transcription_id)
        trash_root = Path(item.job_root).resolve()
        _ensure_within(self.data_dir / "trash", trash_root)
        if trash_root.exists():
            shutil.rmtree(trash_root)
        self.session.delete(item)


def _safe_filename(filename: str) -> str:
    basename = Path(filename).name
    normalized = re.sub(r"[^\w. -]+", "_", basename, flags=re.UNICODE).strip(" .")
    return normalized or "media.bin"


def _copy_stream(stream: BinaryIO, target: Path, *, max_bytes: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as destination:
        while chunk := stream.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise UploadTooLargeError(
                    f"O arquivo excede o limite local de {max_bytes / 1024 / 1024:.0f} MB."
                )
            destination.write(chunk)


def _ensure_within(root: Path, candidate: Path) -> None:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        message = f"Caminho fora da raiz controlada: {resolved_candidate}"
        raise ValueError(message)
