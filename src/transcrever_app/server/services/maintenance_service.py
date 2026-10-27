"""Idempotent startup recovery and filesystem reconciliation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.worker.state_machine import JobStatus

ACTIVE_STATUSES = {
    JobStatus.PREPARING.value,
    JobStatus.LOADING_MODEL.value,
    JobStatus.TRANSCRIBING.value,
    JobStatus.DIARIZING.value,
    JobStatus.ALIGNING.value,
    JobStatus.EXPORTING.value,
    JobStatus.CANCEL_REQUESTED.value,
}


@dataclass(frozen=True)
class MaintenanceReport:
    """Counts produced by one safe maintenance pass."""

    interrupted: int = 0
    imported: int = 0
    missing_roots: int = 0
    invalid_runs: int = 0
    removed_partials: int = 0


def run_startup_maintenance(session: Session, runs_dir: Path) -> MaintenanceReport:
    """Recover interrupted work, import old runs, and flag missing storage."""
    interrupted = _recover_interrupted(session)
    imported, invalid_runs = _import_runs(session, runs_dir)
    missing_roots = _flag_missing_roots(session)
    removed_partials = _remove_abandoned_partials(runs_dir)
    session.commit()
    return MaintenanceReport(
        interrupted=interrupted,
        imported=imported,
        missing_roots=missing_roots,
        invalid_runs=invalid_runs,
        removed_partials=removed_partials,
    )


def _recover_interrupted(session: Session) -> int:
    items = session.scalars(
        select(Transcription).where(
            Transcription.deleted_at.is_(None),
            Transcription.status.in_(ACTIVE_STATUSES),
        )
    ).all()
    for item in items:
        item.status = JobStatus.INTERRUPTED.value
        item.stage = JobStatus.INTERRUPTED.value
        item.error_code = "application_restarted"
        item.error_message = "O aplicativo foi encerrado durante o processamento. Tente novamente."
    return len(items)


def _import_runs(session: Session, runs_dir: Path) -> tuple[int, int]:
    if not runs_dir.is_dir():
        return 0, 0
    known_ids = set(session.scalars(select(Transcription.id)).all())
    imported = 0
    invalid = 0
    for metadata_path in sorted(runs_dir.glob("*/metadata.json")):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            job_id = str(payload["job_id"])
            if job_id in known_ids:
                continue
            root = metadata_path.parent.resolve()
            source_path = _resolve_import_source(root, payload)
            result_path = root / "outputs" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            asr = _asr_metadata(payload)
            item = Transcription(
                id=job_id,
                title=source_path.stem,
                original_filename=source_path.name,
                source_path=str(source_path),
                job_root=str(root),
                outputs_path=str((root / "outputs").resolve()),
                status=JobStatus.COMPLETED.value,
                stage=JobStatus.COMPLETED.value,
                progress=1.0,
                duration_seconds=float(result.get("duration_seconds", 0.0)),
                model_name=str(asr.get("model_name", "unknown")),
                diarization_mode=str(payload.get("diarization_method", "off")),
                speaker_count=_optional_int(payload.get("speaker_count")),
                config_json=json.dumps(payload, ensure_ascii=False),
            )
            session.add(item)
            known_ids.add(job_id)
            imported += 1
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            invalid += 1
    return imported, invalid


def _resolve_import_source(root: Path, payload: dict[str, object]) -> Path:
    source_dir = root / "source"
    candidates = sorted(path for path in source_dir.iterdir() if path.is_file())
    if candidates:
        return candidates[0].resolve()
    source_value = payload.get("source_file") or payload.get("original_source_file")
    if not source_value:
        raise ValueError("Run without source")
    source = Path(str(source_value)).resolve()
    if not source.is_file():
        raise ValueError("Run source is missing")
    return source


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float, str)) else None


def _asr_metadata(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get("asr", {})
    if not isinstance(value, dict):
        raise TypeError("Invalid ASR metadata")
    return value


def _flag_missing_roots(session: Session) -> int:
    items = session.scalars(select(Transcription).where(Transcription.deleted_at.is_(None))).all()
    missing = 0
    for item in items:
        if Path(item.job_root).is_dir():
            continue
        item.status = JobStatus.INTERRUPTED.value
        item.stage = JobStatus.INTERRUPTED.value
        item.error_code = "storage_missing"
        item.error_message = "A pasta de arquivos desta transcrição não foi encontrada."
        missing += 1
    return missing


def _remove_abandoned_partials(runs_dir: Path) -> int:
    """Remove partial files only after exclusive startup lock has been acquired."""
    if not runs_dir.is_dir():
        return 0
    removed = 0
    for partial in runs_dir.rglob("*.part"):
        if partial.is_file():
            partial.unlink()
            removed += 1
    return removed
