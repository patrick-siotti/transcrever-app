"""Authoritative transcription state transitions."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Persistent states exposed to the application."""

    QUEUED = "queued"
    PREPARING = "preparing"
    LOADING_MODEL = "loading_model"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    ALIGNING = "aligning"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNING = "completed_with_warning"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.PREPARING, JobStatus.CANCELLED}),
    JobStatus.PREPARING: frozenset(
        {
            JobStatus.LOADING_MODEL,
            JobStatus.TRANSCRIBING,
            JobStatus.FAILED,
            JobStatus.CANCEL_REQUESTED,
        }
    ),
    JobStatus.LOADING_MODEL: frozenset(
        {JobStatus.TRANSCRIBING, JobStatus.FAILED, JobStatus.CANCEL_REQUESTED}
    ),
    JobStatus.TRANSCRIBING: frozenset(
        {JobStatus.DIARIZING, JobStatus.ALIGNING, JobStatus.FAILED, JobStatus.CANCEL_REQUESTED}
    ),
    JobStatus.DIARIZING: frozenset(
        {
            JobStatus.ALIGNING,
            JobStatus.COMPLETED_WITH_WARNING,
            JobStatus.FAILED,
            JobStatus.CANCEL_REQUESTED,
        }
    ),
    JobStatus.ALIGNING: frozenset(
        {JobStatus.EXPORTING, JobStatus.FAILED, JobStatus.CANCEL_REQUESTED}
    ),
    JobStatus.EXPORTING: frozenset(
        {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNING, JobStatus.FAILED}
    ),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.CANCELLED}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.INTERRUPTED: frozenset({JobStatus.QUEUED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.COMPLETED_WITH_WARNING: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    """Return whether a state transition is legal."""
    return target in ALLOWED_TRANSITIONS[current]
