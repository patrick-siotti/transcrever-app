"""Local job directory management."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class JobPaths:
    """Filesystem paths for a processing job."""

    job_id: str
    root: Path
    audio_dir: Path
    output_dir: Path
    audio_wav: Path
    result_json: Path
    transcript_txt: Path
    transcript_srt: Path
    transcript_vtt: Path
    metadata_json: Path
    source_dir: Path | None = None
    source_file: Path | None = None


def create_job_paths(source_path: Path, *, runs_dir: Path = Path("runs")) -> JobPaths:
    """Create a new local job directory for a source file.

    Args:
        source_path: Source media path.
        runs_dir: Base directory for local runs.

    Returns:
        All relevant job paths.

    """
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    stem = _slugify(source_path.stem)
    job_id = f"{timestamp}-{stem}-{uuid4().hex[:8]}"
    root = runs_dir / job_id
    source_dir = root / "source"
    audio_dir = root / "audio"
    output_dir = root / "outputs"
    source_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return JobPaths(
        job_id=job_id,
        root=root,
        audio_dir=audio_dir,
        output_dir=output_dir,
        audio_wav=audio_dir / "audio.wav",
        result_json=output_dir / "result.json",
        transcript_txt=output_dir / "transcript.txt",
        transcript_srt=output_dir / "transcript.srt",
        transcript_vtt=output_dir / "transcript.vtt",
        metadata_json=root / "metadata.json",
        source_dir=source_dir,
        source_file=source_dir / source_path.name,
    )


def existing_job_paths(job_id: str, root: Path, source_file: Path) -> JobPaths:
    """Reconstruct paths for a job already created by the application layer."""
    audio_dir = root / "audio"
    output_dir = root / "outputs"
    return JobPaths(
        job_id=job_id,
        root=root,
        audio_dir=audio_dir,
        output_dir=output_dir,
        audio_wav=audio_dir / "audio.wav",
        result_json=output_dir / "result.json",
        transcript_txt=output_dir / "transcript.txt",
        transcript_srt=output_dir / "transcript.srt",
        transcript_vtt=output_dir / "transcript.vtt",
        metadata_json=root / "metadata.json",
        source_dir=source_file.parent,
        source_file=source_file,
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "media"
