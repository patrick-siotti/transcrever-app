"""FFmpeg integration for media inspection and audio extraction."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from transcrever_app.core.exceptions import DependencyNotFoundError, MediaProcessingError
from transcrever_app.core.models import AudioStream, MediaInfo

MIN_USEFUL_AUDIO_MAX_DB = -60.0
_VOLUME_PATTERN = re.compile(
    r"Parsed_volumedetect_(?P<filter>\d+).*?"
    r"(?P<metric>mean_volume|max_volume): (?P<value>-?inf|-?\d+(?:\.\d+)?) dB"
)


@dataclass(frozen=True)
class AudioStreamLevel:
    """Measured loudness for one relative audio stream."""

    relative_index: int
    mean_db: float
    max_db: float


class _FormatData(TypedDict, total=False):
    format_name: str
    duration: str
    size: str


class _StreamTags(TypedDict, total=False):
    title: str


class _StreamData(TypedDict, total=False):
    index: int
    codec_name: str
    codec_type: str
    sample_rate: str
    channels: int
    tags: _StreamTags


class _ProbeData(TypedDict):
    streams: list[_StreamData]
    format: _FormatData


def ensure_ffmpeg_available() -> None:
    """Validate that FFmpeg and FFprobe are available in PATH.

    Raises:
        DependencyNotFoundError: If FFmpeg or FFprobe cannot be found.

    """
    missing = [binary for binary in ("ffmpeg", "ffprobe") if shutil.which(binary) is None]
    if missing:
        joined = ", ".join(missing)
        raise DependencyNotFoundError(f"Dependência ausente no PATH: {joined}")


def inspect_media(path: Path) -> MediaInfo:
    """Inspect a media file and return metadata relevant to the pipeline.

    Args:
        path: Audio or video file path.

    Returns:
        Parsed media metadata.

    Raises:
        MediaProcessingError: If the file does not exist or FFprobe fails.

    """
    if not path.exists():
        raise MediaProcessingError(f"Arquivo não encontrado: {path}")

    ensure_ffmpeg_available()
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,format_name",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise MediaProcessingError(completed.stderr.strip() or "Falha ao inspecionar mídia.")

    data = cast("_ProbeData", json.loads(completed.stdout))
    audio_streams: list[AudioStream] = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        tags = stream.get("tags", {})
        audio_streams.append(
            AudioStream(
                index=int(stream.get("index", 0)),
                relative_index=len(audio_streams),
                codec_name=str(stream.get("codec_name", "unknown")),
                channels=int(stream.get("channels", 0)),
                sample_rate=int(stream.get("sample_rate", "0")),
                title=tags.get("title"),
            )
        )

    if not audio_streams:
        raise MediaProcessingError("O arquivo não possui trilha de áudio.")

    format_data = data.get("format", {})
    return MediaInfo(
        path=path,
        duration_seconds=float(format_data.get("duration", "0") or 0),
        format_name=str(format_data.get("format_name", "unknown")),
        size_bytes=int(format_data.get("size", "0") or 0),
        audio_streams=tuple(audio_streams),
    )


def extract_audio(
    *,
    source_path: Path,
    output_path: Path,
    audio_streams: tuple[int, ...] = (0,),
    sample_rate: int = 16_000,
    normalize: bool = True,
) -> Path:
    """Extract a single audio stream into a mono WAV file.

    Args:
        source_path: Source audio or video file.
        output_path: Destination WAV file.
        audio_streams: Relative audio stream indexes to extract or mix.
        sample_rate: Output sample rate.
        normalize: Whether to apply loudness normalization.

    Returns:
        Path to the extracted WAV file.

    Raises:
        MediaProcessingError: If FFmpeg fails.

    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not audio_streams:
        raise MediaProcessingError("Nenhuma trilha de áudio foi selecionada.")
    if len(audio_streams) == 1:
        mapping = ["-map", f"0:a:{audio_streams[0]}"]
        audio_filter = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"] if normalize else []
    else:
        inputs = "".join(f"[0:a:{stream}]" for stream in audio_streams)
        normalization = ",loudnorm=I=-16:TP=-1.5:LRA=11" if normalize else ""
        filter_graph = (
            f"{inputs}amix=inputs={len(audio_streams)}:duration=longest:normalize=1"
            f",aresample={sample_rate},pan=mono|c0=c0{normalization}[mixed]"
        )
        mapping = ["-filter_complex", filter_graph, "-map", "[mixed]"]
        audio_filter = []
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        *mapping,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        *audio_filter,
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise MediaProcessingError(completed.stderr.strip() or "Falha ao extrair áudio.")
    return output_path


def measure_audio_stream_levels(
    source_path: Path,
    audio_streams: tuple[AudioStream, ...],
) -> tuple[AudioStreamLevel, ...]:
    """Measure all audio streams in one bounded FFmpeg pass."""
    ensure_ffmpeg_available()
    filters = ";".join(
        f"[0:a:{stream.relative_index}]volumedetect[level{position}]"
        for position, stream in enumerate(audio_streams)
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(source_path),
        "-filter_complex",
        filters,
    ]
    for position in range(len(audio_streams)):
        command.extend(["-map", f"[level{position}]"])
    command.extend(["-f", "null", "NUL"])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise MediaProcessingError(
            completed.stderr.strip() or "Falha ao medir as trilhas de áudio."
        )

    measurements: dict[int, dict[str, float]] = {}
    for match in _VOLUME_PATTERN.finditer(completed.stderr):
        filter_index = int(match.group("filter"))
        value = float(match.group("value"))
        measurements.setdefault(filter_index, {})[match.group("metric")] = value

    levels: list[AudioStreamLevel] = []
    for position, stream in enumerate(audio_streams):
        measurement = measurements.get(position, {})
        if "mean_volume" not in measurement or "max_volume" not in measurement:
            raise MediaProcessingError("O FFmpeg não retornou o nível de todas as trilhas.")
        levels.append(
            AudioStreamLevel(
                relative_index=stream.relative_index,
                mean_db=measurement["mean_volume"],
                max_db=measurement["max_volume"],
            )
        )
    return tuple(levels)


def select_audio_streams(
    media: MediaInfo,
    requested_stream: int | None,
    levels: tuple[AudioStreamLevel, ...] | None = None,
) -> tuple[int, ...]:
    """Select an explicit stream or every automatically detected useful stream."""
    if requested_stream is not None:
        if requested_stream < 0 or requested_stream >= len(media.audio_streams):
            raise MediaProcessingError("Trilha de áudio selecionada não existe.")
        return (requested_stream,)
    if levels is None:
        return tuple(stream.relative_index for stream in media.audio_streams)
    useful_streams = tuple(
        level.relative_index for level in levels if level.max_db > MIN_USEFUL_AUDIO_MAX_DB
    )
    if not useful_streams:
        raise MediaProcessingError("Nenhuma trilha de áudio com sinal útil foi encontrada.")
    return useful_streams


def extract_audio_clip(
    *,
    source_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
    sample_rate: int = 16_000,
) -> Path:
    """Extract a small mono WAV clip for manual review."""
    if end_seconds <= start_seconds:
        raise MediaProcessingError("Intervalo de corte inválido.")

    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-to",
        f"{end_seconds:.3f}",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise MediaProcessingError(completed.stderr.strip() or "Falha ao cortar áudio.")
    return output_path
