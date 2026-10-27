"""pyannote.audio diarization adapter."""

from __future__ import annotations

import inspect
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from transcrever_app.core.exceptions import DiarizationError
from transcrever_app.core.models import SpeakerSegment

DEFAULT_PYANNOTE_MODEL = "pyannote/speaker-diarization-community-1"


def diarize_audio(
    audio_path: Path,
    *,
    model_name: str = DEFAULT_PYANNOTE_MODEL,
    token: str | None = None,
    speaker_count: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> tuple[SpeakerSegment, ...]:
    """Run speaker diarization with pyannote.audio.

    Args:
        audio_path: Normalized WAV path.
        model_name: Hugging Face model id.
        token: Hugging Face token. Falls back to `HF_TOKEN`.
        speaker_count: Exact number of speakers, when known.
        min_speakers: Minimum number of speakers.
        max_speakers: Maximum number of speakers.

    Returns:
        Speaker segments.

    Raises:
        DiarizationError: If pyannote is missing, token is missing, or inference fails.

    """
    _load_dotenv_if_available()
    auth_token = get_pyannote_token(token, allow_cached=True, model_name=model_name)

    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        message = "pyannote.audio não está instalado."
        raise DiarizationError(message) from exc

    try:
        with _ignore_lazy_import_failures_during_inspection():
            pipeline: Any = Pipeline.from_pretrained(model_name, token=auth_token)
        if pipeline is None:
            message = (
                "Não foi possível carregar o pipeline pyannote. "
                "Verifique se o token tem acesso ao modelo e se a licença foi aceita."
            )
            raise DiarizationError(message)
        diarization_output = pipeline(
            _load_audio_for_pyannote(audio_path),
            **_speaker_kwargs(
                speaker_count=speaker_count,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            ),
        )
    except (RuntimeError, OSError, ValueError) as exc:
        message = f"Falha na diarização: {exc}"
        raise DiarizationError(message) from exc

    diarization = getattr(
        diarization_output,
        "exclusive_speaker_diarization",
        diarization_output,
    )
    segments: list[SpeakerSegment] = []
    labels: dict[str, str] = {}
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        speaker_label = _speaker_name_by_first_seen(labels, str(speaker))
        segments.append(
            SpeakerSegment(
                start=float(turn.start),
                end=float(turn.end),
                speaker=speaker_label,
            )
        )
    return tuple(segments)


def get_pyannote_token(
    token: str | None = None,
    *,
    allow_cached: bool = False,
    model_name: str = DEFAULT_PYANNOTE_MODEL,
) -> str | None:
    """Get the Hugging Face token required by pyannote.

    Args:
        token: Explicit token.
        allow_cached: Allow loading an already downloaded model without a token.
        model_name: Hugging Face model id used for the cache check.

    Returns:
        Token string.

    Raises:
        DiarizationError: If no token is configured.

    """
    _load_dotenv_if_available()
    auth_token = token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not auth_token and not (allow_cached and _is_model_cached(model_name)):
        message = "Diarização pyannote exige HF_TOKEN/HUGGINGFACE_TOKEN no ambiente."
        raise DiarizationError(message)
    return auth_token


def is_pyannote_configured() -> bool:
    """Report whether Pyannote can run from credentials or the local cache."""
    _load_dotenv_if_available()
    return bool(
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
        or _is_model_cached(DEFAULT_PYANNOTE_MODEL)
    )


def _is_model_cached(model_name: str) -> bool:
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError:
        return False
    try:
        snapshot_path = snapshot_download(repo_id=model_name, local_files_only=True)
    except LocalEntryNotFoundError:
        return False
    return Path(snapshot_path).is_dir()


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _load_audio_for_pyannote(audio_path: Path) -> dict[str, Any]:
    try:
        import soundfile as sf
        import torch
    except ImportError as exc:
        message = "soundfile e torch são necessários para carregar áudio no pyannote."
        raise DiarizationError(message) from exc

    try:
        waveform, sample_rate = sf.read(str(audio_path), dtype="float32")
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)
        tensor = torch.from_numpy(waveform).unsqueeze(0)
    except (RuntimeError, OSError, ValueError) as exc:
        message = f"Falha ao carregar áudio para pyannote: {exc}"
        raise DiarizationError(message) from exc

    return {"waveform": tensor, "sample_rate": sample_rate}


def _speaker_kwargs(
    *,
    speaker_count: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> dict[str, int]:
    if speaker_count is not None:
        return {"num_speakers": speaker_count}

    kwargs: dict[str, int] = {}
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers
    return kwargs


def _speaker_name_by_first_seen(labels: dict[str, str], current_speaker: str) -> str:
    if current_speaker not in labels:
        labels[current_speaker] = f"Falante {len(labels) + 1}"
    return labels[current_speaker]


@contextmanager
def _ignore_lazy_import_failures_during_inspection() -> Iterator[None]:
    original_getmodule = inspect.getmodule

    def safe_getmodule(object_: object, _filename: str | None = None) -> ModuleType | None:
        try:
            return original_getmodule(object_, _filename)
        except ImportError:
            return None

    inspect.getmodule = safe_getmodule  # type: ignore[assignment]
    try:
        yield
    finally:
        inspect.getmodule = original_getmodule
