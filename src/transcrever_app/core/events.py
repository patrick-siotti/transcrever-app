"""Progress contracts shared by CLI, worker, and pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class PipelineStage(StrEnum):
    """Stable stages emitted by the transcription pipeline."""

    PREPARING = "preparing"
    LOADING_MODEL = "loading_model"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    ALIGNING = "aligning"
    EXPORTING = "exporting"
    COMPLETED = "completed"


@dataclass(frozen=True)
class PipelineEvent:
    """One monotonic progress observation."""

    stage: PipelineStage
    progress: float | None
    message: str
    current_seconds: float | None = None
    total_seconds: float | None = None


ProgressCallback = Callable[[PipelineEvent], None]
