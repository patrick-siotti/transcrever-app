"""Local speaker clustering based on ASR segments and voice embeddings."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from transcrever_app.core.exceptions import DiarizationError
from transcrever_app.core.models import SpeakerSegment, TranscriptionSegment

MIN_EMBEDDING_SECONDS = 0.55
MIN_CLUSTER_SEGMENTS = 2
DEFAULT_MAX_SPEAKERS = 8
FloatArray = NDArray[np.float32]
IntArray = NDArray[np.int64]


def cluster_transcription_speakers(
    audio_path: Path,
    transcriptions: tuple[TranscriptionSegment, ...],
    *,
    speaker_count: int | None = None,
    max_speakers: int = DEFAULT_MAX_SPEAKERS,
) -> tuple[SpeakerSegment, ...]:
    """Cluster ASR segments into approximate speaker labels.

    Args:
        audio_path: Normalized WAV file.
        transcriptions: ASR segments used as candidate speaker turns.
        speaker_count: Fixed number of speakers. If omitted, the method estimates it.
        max_speakers: Upper bound for automatic speaker count estimation.

    Returns:
        Speaker segments aligned to ASR segment boundaries.

    Raises:
        DiarizationError: If there are not enough segments or embedding fails.

    """
    candidates = [
        segment
        for segment in transcriptions
        if segment.end - segment.start >= MIN_EMBEDDING_SECONDS
    ]
    if len(candidates) < MIN_CLUSTER_SEGMENTS:
        message = "Segmentos insuficientes para clusterização de falantes."
        raise DiarizationError(message)

    embeddings = _extract_embeddings(audio_path, tuple(candidates))
    labels = _cluster_embeddings(
        embeddings,
        speaker_count=speaker_count,
        max_speakers=max_speakers,
    )
    speaker_names = _speaker_names_by_first_seen(labels)
    candidate_speakers = {
        candidate: speaker_names[label]
        for candidate, label in zip(candidates, labels, strict=True)
    }
    return tuple(
        SpeakerSegment(
            start=segment.start,
            end=segment.end,
            speaker=candidate_speakers.get(
                segment,
                _nearest_candidate_speaker(segment, candidate_speakers),
            ),
        )
        for segment in transcriptions
    )


def _extract_embeddings(
    audio_path: Path,
    segments: tuple[TranscriptionSegment, ...],
) -> FloatArray:
    try:
        import soundfile as sf
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
    except ImportError as exc:
        message = "Dependências de clusterização de falantes não estão instaladas."
        raise DiarizationError(message) from exc

    try:
        waveform, sample_rate = sf.read(str(audio_path), dtype="float32")
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)
        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="models/speechbrain-spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )
        embeddings: list[FloatArray] = []
        for segment in segments:
            chunk = _embedding_audio_chunk(waveform, sample_rate, segment)
            tensor = torch.tensor(chunk).unsqueeze(0)
            embedding = classifier.encode_batch(tensor).detach().cpu().numpy().reshape(-1)
            embeddings.append(_normalize_vector(embedding))
    except (RuntimeError, OSError, ValueError) as exc:
        message = f"Falha ao extrair embeddings de falantes: {exc}"
        raise DiarizationError(message) from exc

    if len(embeddings) != len(segments):
        message = "Nem todos os segmentos geraram embeddings de voz."
        raise DiarizationError(message)
    return np.asarray(np.vstack(embeddings), dtype=np.float32)


def _embedding_audio_chunk(
    waveform: FloatArray,
    sample_rate: int,
    segment: TranscriptionSegment,
) -> FloatArray:
    """Return enough audio for ECAPA, including segments at file boundaries."""
    minimum_samples = max(1, round(MIN_EMBEDDING_SECONDS * sample_rate))
    center = round(((segment.start + segment.end) / 2) * sample_rate)
    start = max(0, center - (minimum_samples // 2))
    end = min(len(waveform), start + minimum_samples)
    start = max(0, end - minimum_samples)
    chunk = np.asarray(waveform[start:end], dtype=np.float32)
    if len(chunk) < minimum_samples:
        chunk = np.pad(chunk, (0, minimum_samples - len(chunk)))
    return np.asarray(chunk, dtype=np.float32)


def _cluster_embeddings(
    embeddings: np.ndarray,
    *,
    speaker_count: int | None,
    max_speakers: int,
) -> IntArray:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score

    if speaker_count is not None:
        labels = AgglomerativeClustering(
            n_clusters=speaker_count,
            metric="cosine",
            linkage="average",
        ).fit_predict(embeddings)
        return np.asarray(labels, dtype=np.int64)

    candidate_count = min(max_speakers, len(embeddings) - 1)
    best_labels: IntArray | None = None
    best_score = -1.0
    for count in range(2, candidate_count + 1):
        raw_labels = AgglomerativeClustering(
            n_clusters=count,
            metric="cosine",
            linkage="average",
        ).fit_predict(embeddings)
        labels = np.asarray(raw_labels, dtype=np.int64)
        if len(set(labels.tolist())) < MIN_CLUSTER_SEGMENTS:
            continue
        score = float(silhouette_score(embeddings, labels, metric="cosine"))
        if score > best_score:
            best_score = score
            best_labels = labels

    if best_labels is None:
        return np.zeros(len(embeddings), dtype=np.int64)
    return best_labels


def _speaker_names_by_first_seen(labels: IntArray) -> dict[int, str]:
    names: dict[int, str] = {}
    for label in labels.tolist():
        if int(label) not in names:
            names[int(label)] = f"Falante {len(names) + 1}"
    return names


def _normalize_vector(vector: FloatArray) -> FloatArray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return np.asarray(vector / norm, dtype=np.float32)


def _nearest_candidate_speaker(
    segment: TranscriptionSegment,
    candidate_speakers: dict[TranscriptionSegment, str],
) -> str:
    segment_midpoint = (segment.start + segment.end) / 2
    nearest = min(
        candidate_speakers,
        key=lambda candidate: abs(((candidate.start + candidate.end) / 2) - segment_midpoint),
    )
    return candidate_speakers[nearest]
