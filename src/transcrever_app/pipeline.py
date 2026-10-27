"""High-level transcription pipeline."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from transcrever_app.alignment.speakers import align_speakers, without_speakers
from transcrever_app.asr.faster_whisper import ASRModelRegistry, transcribe_audio_with_details
from transcrever_app.core.cancellation import CancellationToken
from transcrever_app.core.events import PipelineEvent, PipelineStage, ProgressCallback
from transcrever_app.core.exceptions import DiarizationError, TranscriptionError
from transcrever_app.core.models import SpeakerSegment, TranscriptionSegment, TranscriptResult
from transcrever_app.diarization.pyannote import diarize_audio, get_pyannote_token
from transcrever_app.diarization.speaker_clustering import (
    DEFAULT_MAX_SPEAKERS,
    cluster_transcription_speakers,
)
from transcrever_app.exporters.files import write_json, write_srt, write_txt, write_vtt
from transcrever_app.jobs.manager import JobPaths, create_job_paths
from transcrever_app.media.ffmpeg import (
    extract_audio,
    inspect_media,
    measure_audio_stream_levels,
    select_audio_streams,
)

DiarizationMethod = Literal["auto", "pyannote", "clustering"]


def process_media(
    source_path: Path,
    *,
    runs_dir: Path = Path("runs"),
    audio_stream: int | None = None,
    language: str = "pt",
    model_name: str = "large-v3",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    vad_filter: bool = True,
    condition_on_previous_text: bool = True,
    diarize: bool = False,
    diarization_method: DiarizationMethod = "auto",
    speaker_count: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    word_timestamps: bool = False,
    job_paths: JobPaths | None = None,
    on_event: ProgressCallback | None = None,
    cancellation: CancellationToken | None = None,
    model_registry: ASRModelRegistry | None = None,
) -> tuple[TranscriptResult, JobPaths]:
    """Run the full file-based transcription pipeline.

    Args:
        source_path: Audio or video source.
        runs_dir: Local runs directory.
        audio_stream: Explicit relative audio stream index, or automatic selection when omitted.
        language: Expected spoken language.
        model_name: faster-whisper model.
        device: ASR device.
        compute_type: ASR compute type.
        beam_size: Beam search size.
        vad_filter: Whether to filter silence before transcription.
        condition_on_previous_text: Whether ASR should condition on previous text.
        diarize: Whether to attempt speaker diarization.
        diarization_method: `auto`, `pyannote` or `clustering`.
        speaker_count: Exact speaker count when known.
        min_speakers: Minimum speaker count for pyannote.
        max_speakers: Maximum speaker count for pyannote and clustering.
        word_timestamps: Whether to request word-level ASR timestamps.
        job_paths: Pre-created job paths, when the caller owns job creation.
        on_event: Optional progress callback independent of HTTP or persistence.
        cancellation: Optional cooperative cancellation token.
        model_registry: Optional cache for reusing ASR model instances.

    Returns:
        Transcript result and job paths.

    """
    source_path = source_path.resolve()
    cancellation = cancellation or CancellationToken()
    _emit(on_event, PipelineStage.PREPARING, 0.0, "Preparando mídia")
    cancellation.raise_if_cancelled()
    if diarize and diarization_method == "pyannote":
        get_pyannote_token(allow_cached=True)
    media_info = inspect_media(source_path)
    job_paths = job_paths or create_job_paths(source_path, runs_dir=runs_dir)
    processing_source = _preserve_source(source_path, job_paths)
    cancellation.raise_if_cancelled()
    audio_stream_levels = (
        ()
        if audio_stream is not None
        else measure_audio_stream_levels(processing_source, media_info.audio_streams)
    )
    selected_audio_streams = select_audio_streams(
        media_info,
        audio_stream,
        audio_stream_levels if audio_stream is None else None,
    )
    audio_path = extract_audio(
        source_path=processing_source,
        output_path=job_paths.audio_wav,
        audio_streams=selected_audio_streams,
    )
    _emit(on_event, PipelineStage.LOADING_MODEL, 0.05, "Carregando modelo")
    cancellation.raise_if_cancelled()
    _emit(
        on_event,
        PipelineStage.TRANSCRIBING,
        0.1,
        "Transcrevendo",
        total_seconds=media_info.duration_seconds,
    )
    transcription_kwargs: dict[str, Any] = {}
    if model_registry is not None:
        transcription_kwargs["model_registry"] = model_registry
    transcription = transcribe_audio_with_details(
        audio_path,
        model_name=model_name,
        language=language,
        device=device,
        compute_type=compute_type,
        beam_size=beam_size,
        vad_filter=vad_filter,
        condition_on_previous_text=condition_on_previous_text,
        word_timestamps=word_timestamps,
        **transcription_kwargs,
    )
    if not transcription.segments:
        raise TranscriptionError(
            "Nenhuma fala foi reconhecida nas trilhas de áudio selecionadas."
        )
    _emit(
        on_event,
        PipelineStage.TRANSCRIBING,
        0.75,
        "Transcrição concluída",
        current_seconds=media_info.duration_seconds,
        total_seconds=media_info.duration_seconds,
    )
    cancellation.raise_if_cancelled()

    if diarize:
        _emit(on_event, PipelineStage.DIARIZING, 0.76, "Identificando falantes")
    speakers = (
        _diarize(
            audio_path=audio_path,
            transcriptions=transcription.segments,
            method=diarization_method,
            speaker_count=speaker_count,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        if diarize
        else ()
    )
    cancellation.raise_if_cancelled()
    _emit(on_event, PipelineStage.ALIGNING, 0.92, "Alinhando texto e falantes")
    segments = (
        align_speakers(transcription.segments, speakers)
        if speakers
        else without_speakers(transcription.segments)
    )
    result = TranscriptResult(
        job_id=job_paths.job_id,
        source_file=processing_source,
        audio_file=audio_path,
        language=language,
        model_name=model_name,
        asr_device=transcription.device,
        asr_compute_type=transcription.compute_type,
        duration_seconds=media_info.duration_seconds,
        segments=segments,
        speakers=tuple(sorted({segment.speaker for segment in segments if segment.speaker})),
        mode="diarized" if speakers else "transcription",
        fallback_reason=transcription.fallback_reason,
    )
    _emit(on_event, PipelineStage.EXPORTING, 0.97, "Gravando resultados")
    cancellation.raise_if_cancelled()
    _write_metadata(
        path=job_paths.metadata_json,
        payload={
            "job_id": job_paths.job_id,
            "source_file": str(processing_source),
            "original_source_file": str(source_path),
            "audio_stream": audio_stream,
            "audio_streams_used": list(selected_audio_streams),
            "audio_stream_levels": [asdict(level) for level in audio_stream_levels],
            "audio_mix_mode": "mixed" if len(selected_audio_streams) > 1 else "single",
            "media": {
                "duration_seconds": media_info.duration_seconds,
                "format_name": media_info.format_name,
                "size_bytes": media_info.size_bytes,
                "audio_streams": [asdict(stream) for stream in media_info.audio_streams],
            },
            "asr": {
                "requested_device": device,
                "requested_compute_type": compute_type,
                "actual_device": transcription.device,
                "actual_compute_type": transcription.compute_type,
                "model_name": model_name,
                "language": language,
                "beam_size": beam_size,
                "vad_filter": vad_filter,
                "condition_on_previous_text": condition_on_previous_text,
                "word_timestamps": word_timestamps,
                "fallback_reason": transcription.fallback_reason,
            },
            "diarize": diarize,
            "diarization_method": diarization_method,
            "speaker_count": speaker_count,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
        },
    )
    write_json(result, job_paths.result_json)
    write_txt(result, job_paths.transcript_txt)
    write_srt(result, job_paths.transcript_srt)
    write_vtt(result, job_paths.transcript_vtt)
    _emit(on_event, PipelineStage.COMPLETED, 1.0, "Transcrição concluída")
    return result, job_paths


def _write_metadata(*, path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.part")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)
    return path


def _preserve_source(source_path: Path, job_paths: JobPaths) -> Path:
    target = job_paths.source_file
    if target is None:
        return source_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if source_path != target.resolve():
        temporary_path = target.with_suffix(f"{target.suffix}.part")
        shutil.copy2(source_path, temporary_path)
        temporary_path.replace(target)
    return target.resolve()


def _emit(
    callback: ProgressCallback | None,
    stage: PipelineStage,
    progress: float,
    message: str,
    *,
    current_seconds: float | None = None,
    total_seconds: float | None = None,
) -> None:
    if callback is None:
        return
    callback(
        PipelineEvent(
            stage=stage,
            progress=max(0.0, min(1.0, progress)),
            message=message,
            current_seconds=current_seconds,
            total_seconds=total_seconds,
        )
    )


def _diarize(
    *,
    audio_path: Path,
    transcriptions: tuple[TranscriptionSegment, ...],
    method: DiarizationMethod,
    speaker_count: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> tuple[SpeakerSegment, ...]:
    if method == "pyannote":
        return diarize_audio(
            audio_path,
            speaker_count=speaker_count,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    if method == "clustering":
        return cluster_transcription_speakers(
            audio_path,
            transcriptions,
            speaker_count=speaker_count,
            max_speakers=max_speakers if max_speakers is not None else DEFAULT_MAX_SPEAKERS,
        )
    try:
        return diarize_audio(
            audio_path,
            speaker_count=speaker_count,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except DiarizationError:
        return cluster_transcription_speakers(
            audio_path,
            transcriptions,
            speaker_count=speaker_count,
            max_speakers=max_speakers if max_speakers is not None else DEFAULT_MAX_SPEAKERS,
        )
