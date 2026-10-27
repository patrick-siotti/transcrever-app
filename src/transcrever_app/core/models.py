"""Domain models used across the transcription pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AudioStream:
    """Audio stream discovered in a media file."""

    index: int
    relative_index: int
    codec_name: str
    channels: int
    sample_rate: int
    title: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    """Relevant media metadata for pipeline decisions."""

    path: Path
    duration_seconds: float
    format_name: str
    size_bytes: int
    audio_streams: tuple[AudioStream, ...]


@dataclass(frozen=True)
class TranscriptionWord:
    """Word-level ASR timing."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionSegment:
    """Text segment returned by the ASR model."""

    start: float
    end: float
    text: str
    words: tuple[TranscriptionWord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TranscriptionOutput:
    """ASR output plus runtime details."""

    segments: tuple[TranscriptionSegment, ...]
    device: str
    compute_type: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class SpeakerSegment:
    """Speaker segment returned by a diarization model."""

    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class TranscriptSegment:
    """Final transcript segment after optional speaker alignment."""

    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class TranscriptResult:
    """Complete transcript result exported by the pipeline."""

    job_id: str
    source_file: Path
    audio_file: Path
    language: str
    model_name: str
    asr_device: str
    asr_compute_type: str
    duration_seconds: float
    segments: tuple[TranscriptSegment, ...]
    speakers: tuple[str, ...] = field(default_factory=tuple)
    mode: Literal["transcription", "diarized"] = "transcription"
    fallback_reason: str | None = None
