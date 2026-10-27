"""Run comparison and reference coverage diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.speakers import (
    ReferenceSpeakerSegment,
    evaluate_speakers,
)
from transcrever_app.evaluation.transcription import normalize_words, word_edit_distance


@dataclass(frozen=True)
class RunComparison:
    """Comparison between two transcription runs."""

    baseline_segments: int
    candidate_segments: int
    baseline_words: int
    candidate_words: int
    text_edit_distance: int
    text_change_rate: float
    speaker_agreement: float | None
    speaker_mapping: dict[str, str]
    only_segmentation_changed: bool


@dataclass(frozen=True)
class ReferenceCoverage:
    """How much of a media file is covered by reviewed intervals."""

    covered_seconds: float
    duration_seconds: float
    coverage: float


@dataclass(frozen=True)
class ReferenceGap:
    """Unreviewed interval that still needs manual reference."""

    start: float
    end: float
    duration_seconds: float


def compare_runs(
    baseline: tuple[TranscriptSegment, ...],
    candidate: tuple[TranscriptSegment, ...],
) -> RunComparison:
    """Compare two runs and detect whether differences are only segmentation."""
    baseline_words = normalize_words(_joined_text(baseline))
    candidate_words = normalize_words(_joined_text(candidate))
    edit_distance = word_edit_distance(baseline_words, candidate_words)
    word_count = max(len(baseline_words), 1)
    speaker_reference = tuple(
        ReferenceSpeakerSegment(
            start=segment.start,
            end=segment.end,
            speaker=segment.speaker,
        )
        for segment in baseline
        if segment.speaker is not None
    )
    if speaker_reference and any(segment.speaker is not None for segment in candidate):
        speaker_evaluation = evaluate_speakers(candidate, speaker_reference)
        speaker_agreement: float | None = speaker_evaluation.accuracy
        speaker_mapping = speaker_evaluation.mapping
    else:
        speaker_agreement = None
        speaker_mapping = {}
    only_segmentation_changed = (
        edit_distance == 0
        and speaker_agreement == 1.0
        and len(baseline) != len(candidate)
    )
    return RunComparison(
        baseline_segments=len(baseline),
        candidate_segments=len(candidate),
        baseline_words=len(baseline_words),
        candidate_words=len(candidate_words),
        text_edit_distance=edit_distance,
        text_change_rate=edit_distance / word_count,
        speaker_agreement=speaker_agreement,
        speaker_mapping=speaker_mapping,
        only_segmentation_changed=only_segmentation_changed,
    )


def measure_reference_coverage(
    intervals: Sequence[tuple[float, float]],
    duration_seconds: float,
) -> ReferenceCoverage:
    """Measure reviewed interval coverage over a media duration."""
    covered_seconds = _covered_seconds(intervals)
    coverage = covered_seconds / duration_seconds if duration_seconds else 0.0
    return ReferenceCoverage(
        covered_seconds=covered_seconds,
        duration_seconds=duration_seconds,
        coverage=coverage,
    )


def find_reference_gaps(
    intervals: Sequence[tuple[float, float]],
    duration_seconds: float,
    *,
    min_gap_seconds: float = 1.0,
) -> tuple[ReferenceGap, ...]:
    """Find unreviewed intervals longer than the minimum gap."""
    gaps: list[ReferenceGap] = []
    cursor = 0.0
    for start, end in _merged_intervals(intervals):
        if start - cursor >= min_gap_seconds:
            gaps.append(_gap(cursor, start))
        cursor = max(cursor, end)
    if duration_seconds - cursor >= min_gap_seconds:
        gaps.append(_gap(cursor, duration_seconds))
    return tuple(gaps)


def _joined_text(segments: tuple[TranscriptSegment, ...]) -> str:
    return " ".join(segment.text for segment in segments)


def _covered_seconds(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(end - start for start, end in _merged_intervals(intervals))


def _merged_intervals(intervals: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    sorted_intervals = sorted(intervals)
    merged: list[tuple[float, float]] = []
    current_start: float | None = None
    current_end: float | None = None
    for start, end in sorted_intervals:
        if end <= start:
            continue
        if current_start is None or current_end is None:
            current_start = start
            current_end = end
            continue
        if start > current_end:
            merged.append((current_start, current_end))
            current_start = start
            current_end = end
            continue
        current_end = max(current_end, end)
    if current_start is not None and current_end is not None:
        merged.append((current_start, current_end))
    return tuple(merged)


def _gap(start: float, end: float) -> ReferenceGap:
    return ReferenceGap(
        start=start,
        end=end,
        duration_seconds=end - start,
    )
