"""Persistence operations for transcription jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select, update

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.orm import Session

from transcrever_app.core.events import PipelineEvent
from transcrever_app.server.persistence.models import Transcription
from transcrever_app.server.worker.state_machine import JobStatus, can_transition


class TranscriptionRepository:
    """Repository owning transcription queries and state writes."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to one short-lived session."""
        self.session = session

    def add(self, transcription: Transcription) -> Transcription:
        """Persist a new transcription."""
        self.session.add(transcription)
        self.session.flush()
        return transcription

    def get(self, transcription_id: str) -> Transcription | None:
        """Get a non-deleted transcription by id."""
        return self.session.scalar(
            select(Transcription).where(
                Transcription.id == transcription_id,
                Transcription.deleted_at.is_(None),
            )
        )

    def get_including_deleted(self, transcription_id: str) -> Transcription | None:
        """Get a transcription regardless of its trash state."""
        return self.session.get(Transcription, transcription_id)

    def list_library(self, folder_id: str | None = None) -> list[Transcription]:
        """List visible items in deterministic library order."""
        folder_filter = (
            Transcription.folder_id.is_(None)
            if folder_id is None
            else Transcription.folder_id == folder_id
        )
        return list(
            self.session.scalars(
                select(Transcription)
                .where(Transcription.deleted_at.is_(None), folder_filter)
                .order_by(
                    Transcription.is_pinned.desc(),
                    Transcription.position.asc(),
                    Transcription.updated_at.desc(),
                    Transcription.id.asc(),
                )
            ).all()
        )

    def list_deleted(self) -> list[Transcription]:
        """List trash items newest-first."""
        return list(
            self.session.scalars(
                select(Transcription)
                .where(Transcription.deleted_at.is_not(None))
                .order_by(Transcription.deleted_at.desc(), Transcription.id.asc())
            ).all()
        )

    def next_position(self, folder_id: str | None) -> int:
        """Return the next stable position in a logical folder."""
        folder_filter = (
            Transcription.folder_id.is_(None)
            if folder_id is None
            else Transcription.folder_id == folder_id
        )
        maximum = self.session.scalar(
            select(func.max(Transcription.position)).where(
                folder_filter,
                Transcription.deleted_at.is_(None),
            )
        )
        return int(maximum if maximum is not None else -1) + 1

    def claim_next(self) -> Transcription | None:
        """Atomically claim the oldest queued job in this process."""
        candidate_id = self.session.scalar(
            select(Transcription.id)
            .where(Transcription.status == JobStatus.QUEUED.value)
            .order_by(Transcription.created_at.asc(), Transcription.id.asc())
            .limit(1)
        )
        if candidate_id is None:
            return None
        result = cast(
            "CursorResult[object]",
            self.session.execute(
                update(Transcription)
                .where(
                    Transcription.id == candidate_id,
                    Transcription.status == JobStatus.QUEUED.value,
                )
                .values(
                    status=JobStatus.PREPARING.value,
                    stage=JobStatus.PREPARING.value,
                    started_at=datetime.now(tz=UTC),
                    attempt_count=Transcription.attempt_count + 1,
                )
            ),
        )
        if result.rowcount != 1:
            return None
        self.session.flush()
        return self.session.get(Transcription, candidate_id)

    def transition(self, item: Transcription, target: JobStatus) -> None:
        """Apply one validated state transition."""
        current = JobStatus(item.status)
        if current != target and not can_transition(current, target):
            message = f"Transição inválida: {current.value} -> {target.value}"
            raise ValueError(message)
        item.status = target.value
        item.stage = target.value
        item.updated_at = datetime.now(tz=UTC)

    def apply_event(self, item: Transcription, event: PipelineEvent) -> None:
        """Persist one monotonic progress event."""
        target = JobStatus(event.stage.value)
        current = JobStatus(item.status)
        if current != target:
            self.transition(item, target)
        if event.progress is not None:
            item.progress = max(item.progress, event.progress)
        item.stage = event.stage.value
        item.processed_seconds = event.current_seconds
        if event.total_seconds is not None:
            item.duration_seconds = event.total_seconds
        item.updated_at = datetime.now(tz=UTC)
