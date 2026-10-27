"""Transcription quality evaluation."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.speakers import load_predicted_result

_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True)
class ReferenceTextSegment:
    """Manually reviewed transcript interval."""

    start: float
    end: float
    text: str
    note: str = ""


@dataclass(frozen=True)
class SegmentTextEvaluation:
    """Text evaluation for one reviewed interval."""

    start: float
    end: float
    reference_text: str
    predicted_text: str
    word_count: int
    edit_distance: int
    wer: float


@dataclass(frozen=True)
class TranscriptionEvaluation:
    """Aggregate transcription evaluation."""

    word_count: int
    edit_distance: int
    wer: float
    segments: tuple[SegmentTextEvaluation, ...]


def evaluate_transcription(
    predicted: tuple[TranscriptSegment, ...],
    reference: tuple[ReferenceTextSegment, ...],
) -> TranscriptionEvaluation:
    """Evaluate predicted text against reviewed intervals using WER.

    Args:
        predicted: Predicted transcript segments.
        reference: Reviewed transcript intervals.

    Returns:
        Aggregate and per-interval word error rate.

    """
    evaluations = tuple(
        _evaluate_segment(predicted, reference_segment)
        for reference_segment in reference
    )
    word_count = sum(segment.word_count for segment in evaluations)
    edit_distance = sum(segment.edit_distance for segment in evaluations)
    wer = edit_distance / word_count if word_count else 0.0
    return TranscriptionEvaluation(
        word_count=word_count,
        edit_distance=edit_distance,
        wer=wer,
        segments=evaluations,
    )


def load_text_reference(path: Path) -> tuple[ReferenceTextSegment, ...]:
    """Load reviewed transcript intervals from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        ReferenceTextSegment(
            start=float(segment["start"]),
            end=float(segment["end"]),
            text=str(segment["text"]),
            note=str(segment.get("note", "")),
        )
        for segment in payload.get("segments", [])
    )


def load_transcript_result(path: Path) -> tuple[TranscriptSegment, ...]:
    """Load predicted transcript segments from a result JSON file."""
    return load_predicted_result(path)


def _evaluate_segment(
    predicted: tuple[TranscriptSegment, ...],
    reference: ReferenceTextSegment,
) -> SegmentTextEvaluation:
    predicted_text = _text_for_interval(predicted, reference.start, reference.end)
    reference_words = normalize_words(reference.text)
    predicted_words = normalize_words(predicted_text)
    edit_distance = word_edit_distance(reference_words, predicted_words)
    word_count = len(reference_words)
    wer = edit_distance / word_count if word_count else 0.0
    return SegmentTextEvaluation(
        start=reference.start,
        end=reference.end,
        reference_text=reference.text,
        predicted_text=predicted_text,
        word_count=word_count,
        edit_distance=edit_distance,
        wer=wer,
    )


def _text_for_interval(
    predicted: tuple[TranscriptSegment, ...],
    start: float,
    end: float,
) -> str:
    parts = [
        segment.text
        for segment in predicted
        if start <= _midpoint(segment.start, segment.end) <= end
    ]
    return " ".join(parts)


def normalize_words(text: str) -> tuple[str, ...]:
    """Normalize text into comparable words."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return tuple(match.group(0) for match in _WORD_PATTERN.finditer(without_marks))


def word_edit_distance(reference: tuple[str, ...], predicted: tuple[str, ...]) -> int:
    """Calculate word-level edit distance."""
    previous = list(range(len(predicted) + 1))
    for reference_index, reference_word in enumerate(reference, start=1):
        current = [reference_index]
        for predicted_index, predicted_word in enumerate(predicted, start=1):
            substitution_cost = 0 if reference_word == predicted_word else 1
            current.append(
                min(
                    previous[predicted_index] + 1,
                    current[predicted_index - 1] + 1,
                    previous[predicted_index - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]


def _midpoint(start: float, end: float) -> float:
    return (start + end) / 2
