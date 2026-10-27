"""Export transcript results to local files."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from transcrever_app.core.models import TranscriptResult, TranscriptSegment


def write_json(result: TranscriptResult, path: Path) -> Path:
    """Write the full transcript result as JSON.

    Args:
        result: Transcript result.
        path: Output path.

    Returns:
        Output path.

    """
    payload = asdict(result)
    payload["source_file"] = str(result.source_file)
    payload["audio_file"] = str(result.audio_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_txt(result: TranscriptResult, path: Path) -> Path:
    """Write a readable transcript text file.

    Args:
        result: Transcript result.
        path: Output path.

    Returns:
        Output path.

    """
    lines = [_format_text_segment(segment) for segment in result.segments]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_srt(result: TranscriptResult, path: Path) -> Path:
    """Write transcript as SRT subtitles.

    Args:
        result: Transcript result.
        path: Output path.

    Returns:
        Output path.

    """
    blocks = []
    for index, segment in enumerate(result.segments, start=1):
        label = f"{segment.speaker}: " if segment.speaker else ""
        blocks.append(
            f"{index}\n"
            f"{_format_srt_time(segment.start)} --> {_format_srt_time(segment.end)}\n"
            f"{label}{segment.text}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def write_vtt(result: TranscriptResult, path: Path) -> Path:
    """Write transcript as WebVTT subtitles.

    Args:
        result: Transcript result.
        path: Output path.

    Returns:
        Output path.

    """
    blocks = ["WEBVTT\n"]
    for segment in result.segments:
        label = f"{segment.speaker}: " if segment.speaker else ""
        blocks.append(
            f"{_format_vtt_time(segment.start)} --> {_format_vtt_time(segment.end)}\n"
            f"{label}{segment.text}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def _format_text_segment(segment: TranscriptSegment) -> str:
    timestamp = _format_clock_time(segment.start)
    label = f" {segment.speaker}:" if segment.speaker else ""
    return f"[{timestamp}]{label} {segment.text}"


def _format_clock_time(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    return _format_srt_time(seconds).replace(",", ".")
