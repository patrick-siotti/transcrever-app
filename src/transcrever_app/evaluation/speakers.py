"""Speaker diarization evaluation."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from transcrever_app.core.models import TranscriptSegment


@dataclass(frozen=True)
class ReferenceSpeakerSegment:
    """Manually reviewed speaker interval."""

    start: float
    end: float
    speaker: str
    note: str = ""


@dataclass(frozen=True)
class SegmentSpeakerEvaluation:
    """Speaker evaluation for one reviewed interval."""

    start: float
    end: float
    speaker: str
    note: str
    reference_seconds: float
    matched_seconds: float
    accuracy: float


@dataclass(frozen=True)
class SpeakerEvaluation:
    """Speaker evaluation result."""

    reference_seconds: float
    matched_seconds: float
    accuracy: float
    mapping: dict[str, str]
    unmapped_predicted_speakers: tuple[str, ...]
    segments: tuple[SegmentSpeakerEvaluation, ...]


def evaluate_speakers(
    predicted: tuple[TranscriptSegment, ...],
    reference: tuple[ReferenceSpeakerSegment, ...],
    *,
    collar_seconds: float = 0.0,
) -> SpeakerEvaluation:
    """Evaluate predicted speaker labels against reviewed intervals.

    Args:
        predicted: Predicted transcript segments.
        reference: Reviewed speaker intervals.
        collar_seconds: Seconds ignored at each reference boundary.

    Returns:
        Time-weighted speaker evaluation with optimal predicted-to-reference mapping.

    """
    reference_speakers = tuple(dict.fromkeys(segment.speaker for segment in reference))
    predicted_speakers = tuple(
        dict.fromkeys(segment.speaker for segment in predicted if segment.speaker is not None)
    )
    evaluation_reference = tuple(_apply_collar(segment, collar_seconds) for segment in reference)
    overlap_by_pair = _speaker_overlap_by_pair(predicted, evaluation_reference)
    mapping = _best_speaker_mapping(
        predicted_speakers=predicted_speakers,
        reference_speakers=reference_speakers,
        overlap_by_pair=overlap_by_pair,
    )
    matched_seconds = sum(
        overlap
        for (predicted_speaker, reference_speaker), overlap in overlap_by_pair.items()
        if mapping.get(predicted_speaker) == reference_speaker
    )
    reference_seconds = sum(segment.end - segment.start for segment in evaluation_reference)
    unmapped = tuple(speaker for speaker in predicted_speakers if speaker not in mapping)
    accuracy = matched_seconds / reference_seconds if reference_seconds else 0.0
    segment_evaluations = tuple(
        _evaluate_reference_segment(predicted, reference_segment, mapping)
        for reference_segment in evaluation_reference
    )
    return SpeakerEvaluation(
        reference_seconds=reference_seconds,
        matched_seconds=matched_seconds,
        accuracy=accuracy,
        mapping=mapping,
        unmapped_predicted_speakers=unmapped,
        segments=segment_evaluations,
    )


def load_reference(path: Path) -> tuple[ReferenceSpeakerSegment, ...]:
    """Load reviewed speaker intervals from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    return tuple(
        ReferenceSpeakerSegment(
            start=float(segment["start"]),
            end=float(segment["end"]),
            speaker=str(segment["speaker"]),
            note=str(segment.get("note", "")),
        )
        for segment in segments
    )


def load_predicted_result(path: Path) -> tuple[TranscriptSegment, ...]:
    """Load predicted transcript segments from a result JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        TranscriptSegment(
            start=float(segment["start"]),
            end=float(segment["end"]),
            text=str(segment["text"]),
            speaker=segment.get("speaker"),
        )
        for segment in payload.get("segments", [])
    )


def _speaker_overlap_by_pair(
    predicted: tuple[TranscriptSegment, ...],
    reference: tuple[ReferenceSpeakerSegment, ...],
) -> dict[tuple[str, str], float]:
    overlaps: dict[tuple[str, str], float] = {}
    for predicted_segment in predicted:
        if predicted_segment.speaker is None:
            continue
        for reference_segment in reference:
            overlap = _overlap_seconds(
                predicted_segment.start,
                predicted_segment.end,
                reference_segment.start,
                reference_segment.end,
            )
            if overlap <= 0:
                continue
            key = (predicted_segment.speaker, reference_segment.speaker)
            overlaps[key] = overlaps.get(key, 0.0) + overlap
    return overlaps


def _apply_collar(
    reference: ReferenceSpeakerSegment,
    collar_seconds: float,
) -> ReferenceSpeakerSegment:
    if collar_seconds <= 0:
        return reference
    start = min(reference.end, reference.start + collar_seconds)
    end = max(start, reference.end - collar_seconds)
    return ReferenceSpeakerSegment(
        start=start,
        end=end,
        speaker=reference.speaker,
        note=reference.note,
    )


def _evaluate_reference_segment(
    predicted: tuple[TranscriptSegment, ...],
    reference: ReferenceSpeakerSegment,
    mapping: dict[str, str],
) -> SegmentSpeakerEvaluation:
    matched_seconds = 0.0
    for predicted_segment in predicted:
        if predicted_segment.speaker is None:
            continue
        if mapping.get(predicted_segment.speaker) != reference.speaker:
            continue
        matched_seconds += _overlap_seconds(
            predicted_segment.start,
            predicted_segment.end,
            reference.start,
            reference.end,
        )
    reference_seconds = reference.end - reference.start
    accuracy = matched_seconds / reference_seconds if reference_seconds else 0.0
    return SegmentSpeakerEvaluation(
        start=reference.start,
        end=reference.end,
        speaker=reference.speaker,
        note=reference.note,
        reference_seconds=reference_seconds,
        matched_seconds=matched_seconds,
        accuracy=accuracy,
    )


def _best_speaker_mapping(
    *,
    predicted_speakers: tuple[str, ...],
    reference_speakers: tuple[str, ...],
    overlap_by_pair: dict[tuple[str, str], float],
) -> dict[str, str]:
    if not predicted_speakers or not reference_speakers:
        return {}

    best_score = -1.0
    best_mapping: dict[str, str] = {}
    if len(predicted_speakers) <= len(reference_speakers):
        for reference_subset in itertools.permutations(reference_speakers, len(predicted_speakers)):
            mapping = dict(zip(predicted_speakers, reference_subset, strict=True))
            score = _mapping_score(mapping, overlap_by_pair)
            if score > best_score:
                best_score = score
                best_mapping = mapping
    else:
        for predicted_subset in itertools.permutations(predicted_speakers, len(reference_speakers)):
            mapping = dict(zip(predicted_subset, reference_speakers, strict=True))
            score = _mapping_score(mapping, overlap_by_pair)
            if score > best_score:
                best_score = score
                best_mapping = mapping
    return best_mapping


def _mapping_score(
    mapping: dict[str, str],
    overlap_by_pair: dict[tuple[str, str], float],
) -> float:
    return sum(
        overlap
        for (predicted_speaker, reference_speaker), overlap in overlap_by_pair.items()
        if mapping.get(predicted_speaker) == reference_speaker
    )


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))
