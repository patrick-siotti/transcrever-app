"""faster-whisper adapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from threading import Lock
from typing import Protocol

from transcrever_app.core.exceptions import TranscriptionError
from transcrever_app.core.models import TranscriptionOutput, TranscriptionSegment, TranscriptionWord
from transcrever_app.runtime.cuda import prepare_cuda_dll_search_path


class _WhisperWord(Protocol):
    start: float
    end: float
    word: str


class _WhisperSegment(Protocol):
    start: float
    end: float
    text: str
    words: Iterable[_WhisperWord] | None


class _WhisperModel(Protocol):
    def transcribe(
        self,
        audio: str,
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
        word_timestamps: bool,
        condition_on_previous_text: bool,
    ) -> tuple[Iterable[_WhisperSegment], object]:
        """Transcribe audio using the adapter-compatible API."""
        ...


class ASRModelRegistry:
    """Lazy, thread-safe registry for reusable faster-whisper models."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._models: dict[tuple[str, str, str], _WhisperModel] = {}
        self._lock = Lock()

    def get(
        self,
        *,
        model_name: str,
        device: str,
        compute_type: str,
        model_type: Callable[..., _WhisperModel],
    ) -> _WhisperModel:
        """Return one model per effective runtime configuration."""
        key = (model_name, device, compute_type)
        with self._lock:
            model = self._models.get(key)
            if model is None:
                model = model_type(model_name, device=device, compute_type=compute_type)
                self._models[key] = model
            return model

    def close(self) -> None:
        """Release registry references so native resources can be reclaimed."""
        with self._lock:
            self._models.clear()


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str = "large-v3",
    language: str = "pt",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    vad_filter: bool = True,
    condition_on_previous_text: bool = True,
    word_timestamps: bool = False,
) -> tuple[TranscriptionSegment, ...]:
    """Transcribe a WAV file with faster-whisper.

    Args:
        audio_path: Normalized audio path.
        model_name: faster-whisper model name.
        language: Expected spoken language.
        device: `auto`, `cuda` or `cpu`.
        compute_type: CTranslate2 compute type.
        beam_size: Beam search size.
        vad_filter: Whether to filter silence before transcription.
        condition_on_previous_text: Whether ASR should condition on previous text.
        word_timestamps: Whether to include word-level timestamps.

    Returns:
        Transcription segments with timestamps.

    Raises:
        TranscriptionError: If faster-whisper is missing or transcription fails.

    """
    output = transcribe_audio_with_details(
        audio_path,
        model_name=model_name,
        language=language,
        device=device,
        compute_type=compute_type,
        beam_size=beam_size,
        vad_filter=vad_filter,
        condition_on_previous_text=condition_on_previous_text,
        word_timestamps=word_timestamps,
    )
    return output.segments


def transcribe_audio_with_details(
    audio_path: Path,
    *,
    model_name: str = "large-v3",
    language: str = "pt",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    vad_filter: bool = True,
    condition_on_previous_text: bool = True,
    word_timestamps: bool = False,
    model_registry: ASRModelRegistry | None = None,
) -> TranscriptionOutput:
    """Transcribe a WAV file and report the runtime configuration used.

    Args:
        audio_path: Normalized audio path.
        model_name: faster-whisper model name.
        language: Expected spoken language.
        device: `auto`, `cuda` or `cpu`.
        compute_type: CTranslate2 compute type.
        beam_size: Beam search size.
        vad_filter: Whether to filter silence before transcription.
        condition_on_previous_text: Whether ASR should condition on previous text.
        word_timestamps: Whether to include word-level timestamps.
        model_registry: Optional registry used to reuse heavy model instances.

    Returns:
        Transcription output with segments and runtime details.

    Raises:
        TranscriptionError: If faster-whisper is missing or transcription fails.

    """
    prepare_cuda_dll_search_path()

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        message = "faster-whisper não está instalado."
        raise TranscriptionError(message) from exc

    requested_device = device
    device, compute_type = _resolve_auto_runtime(device=device, compute_type=compute_type)

    try:
        return _run_transcription(
            audio_path,
            model_name=model_name,
            language=language,
            device=device,
            compute_type=compute_type,
            beam_size=beam_size,
            vad_filter=vad_filter,
            condition_on_previous_text=condition_on_previous_text,
            word_timestamps=word_timestamps,
            whisper_model_type=WhisperModel,
            model_registry=model_registry,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        if requested_device == "auto" and _is_cuda_runtime_error(exc):
            fallback = _run_transcription(
                audio_path,
                model_name=model_name,
                language=language,
                device="cpu",
                compute_type="int8",
                beam_size=beam_size,
                vad_filter=vad_filter,
                condition_on_previous_text=condition_on_previous_text,
                word_timestamps=word_timestamps,
                whisper_model_type=WhisperModel,
                model_registry=model_registry,
            )
            return TranscriptionOutput(
                segments=fallback.segments,
                device=fallback.device,
                compute_type=fallback.compute_type,
                fallback_reason=str(exc),
            )
        message = f"Falha na transcrição: {exc}"
        raise TranscriptionError(message) from exc


def _resolve_auto_runtime(*, device: str, compute_type: str) -> tuple[str, str]:
    if device != "auto" or not _has_cuda_device():
        return device, compute_type
    resolved_compute_type = "float16" if compute_type == "auto" else compute_type
    return "cuda", resolved_compute_type


def _has_cuda_device() -> bool:
    try:
        import ctranslate2
    except ImportError:
        return False
    return int(ctranslate2.get_cuda_device_count()) > 0


def _run_transcription(
    audio_path: Path,
    *,
    model_name: str,
    language: str,
    device: str,
    compute_type: str,
    beam_size: int,
    vad_filter: bool,
    condition_on_previous_text: bool,
    word_timestamps: bool,
    whisper_model_type: Callable[..., _WhisperModel],
    model_registry: ASRModelRegistry | None = None,
) -> TranscriptionOutput:
    model = (
        model_registry.get(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            model_type=whisper_model_type,
        )
        if model_registry is not None
        else whisper_model_type(model_name, device=device, compute_type=compute_type)
    )
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        word_timestamps=word_timestamps,
        condition_on_previous_text=condition_on_previous_text,
    )
    return TranscriptionOutput(
        segments=tuple(_convert_segments(segments)),
        device=device,
        compute_type=compute_type,
    )


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in ("cuda", "cublas", "cudnn"))


def _convert_segments(segments: Iterable[_WhisperSegment]) -> Iterable[TranscriptionSegment]:
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        words = tuple(_convert_words(segment.words or ()))
        yield TranscriptionSegment(
            start=float(segment.start),
            end=float(segment.end),
            text=text,
            words=words,
        )


def _convert_words(words: Iterable[_WhisperWord]) -> Iterable[TranscriptionWord]:
    for word in words:
        text = word.word.strip()
        if not text:
            continue
        yield TranscriptionWord(start=float(word.start), end=float(word.end), text=word.word)
