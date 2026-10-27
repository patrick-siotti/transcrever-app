"""Regression tests for local speaker embedding preparation."""

import numpy as np

from transcrever_app.core.models import TranscriptionSegment
from transcrever_app.diarization.speaker_clustering import (
    MIN_EMBEDDING_SECONDS,
    _embedding_audio_chunk,
)


def test_embedding_chunk_pads_audio_shorter_than_ecapa_minimum() -> None:
    sample_rate = 16_000
    waveform = np.ones(64, dtype=np.float32)
    segment = TranscriptionSegment(start=0.0, end=0.55, text="short file")

    chunk = _embedding_audio_chunk(waveform, sample_rate, segment)

    assert len(chunk) == round(MIN_EMBEDDING_SECONDS * sample_rate)
    np.testing.assert_array_equal(chunk[:64], waveform)
    assert np.all(chunk[64:] == 0)


def test_embedding_chunk_expands_segment_truncated_at_end_of_file() -> None:
    sample_rate = 100
    waveform = np.arange(100, dtype=np.float32)
    segment = TranscriptionSegment(start=0.95, end=1.55, text="tail")

    chunk = _embedding_audio_chunk(waveform, sample_rate, segment)

    assert len(chunk) == round(MIN_EMBEDDING_SECONDS * sample_rate)
    np.testing.assert_array_equal(chunk, waveform[-len(chunk) :])
