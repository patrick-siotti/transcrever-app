"""Transcription API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from transcrever_app.server.schemas.folder import FolderResponse


class TranscriptionResponse(BaseModel):
    """Public transcription representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    folder_id: str | None
    title: str
    original_filename: str
    status: str
    stage: str | None
    progress: float
    processed_seconds: float | None
    duration_seconds: float | None
    model_name: str
    diarization_mode: str
    speaker_count: int | None
    is_pinned: bool
    position: int
    viewed_at: datetime | None
    started_at: datetime | None
    attempt_count: int
    error_code: str | None
    error_message: str | None
    warning_message: str | None
    created_at: datetime
    updated_at: datetime


class TranscriptionPatch(BaseModel):
    """Editable library metadata."""

    title: str | None = Field(default=None, min_length=1, max_length=240)
    is_pinned: bool | None = None
    folder_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class LibraryResponse(BaseModel):
    """Current library payload."""

    folder: FolderResponse | None
    breadcrumbs: list[FolderResponse]
    folders: list[FolderResponse]
    new_transcriptions: list[TranscriptionResponse]
    transcriptions: list[TranscriptionResponse]


class TranscriptSegmentResponse(BaseModel):
    """One rendered transcript segment."""

    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptionResultResponse(BaseModel):
    """Transcript result loaded from the canonical artifact."""

    job_id: str
    duration_seconds: float
    segments: list[TranscriptSegmentResponse]
    speakers: list[str]
    mode: str
