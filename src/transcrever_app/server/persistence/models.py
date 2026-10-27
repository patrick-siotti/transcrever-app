"""SQLAlchemy models for local library state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp."""
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    """Declarative model base."""


class Folder(Base):
    """Logical library folder."""

    __tablename__ = "folders"
    __table_args__ = (Index("ix_folders_parent_position", "parent_id", "position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent: Mapped[Folder | None] = relationship(remote_side="Folder.id", back_populates="children")
    children: Mapped[list[Folder]] = relationship(back_populates="parent")


class Transcription(Base):
    """Persistent job and library item."""

    __tablename__ = "transcriptions"
    __table_args__ = (
        Index("ix_transcriptions_queue", "status", "created_at"),
        Index("ix_transcriptions_folder_position", "folder_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    original_filename: Mapped[str] = mapped_column(String(260))
    source_path: Mapped[str] = mapped_column(Text)
    job_root: Mapped[str] = mapped_column(Text)
    outputs_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    processed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), default="large-v3")
    diarization_mode: Mapped[str] = mapped_column(String(40), default="auto")
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    folder: Mapped[Folder | None] = relationship()


class AppSetting(Base):
    """Small JSON-encoded local preference."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
