"""Align transcription segments with diarized speaker turns."""

from __future__ import annotations

from collections.abc import Iterable

from transcrever_app.core.models import (
    SpeakerSegment,
    TranscriptionSegment,
    TranscriptionWord,
    TranscriptSegment,
)

MIN_ALIGNMENT_OVERLAP_SECONDS = 0.05
MIN_SPLIT_TOKEN_COUNT = 2
MIN_SPLIT_SPEAKER_COUNT = 2
MAX_ORPHAN_FRAGMENT_SECONDS = 0.75
MAX_ORPHAN_FRAGMENT_WORDS = 2
MAX_ORPHAN_MERGE_GAP_SECONDS = 0.25
TERMINAL_FRAGMENT_SUFFIXES = (".", "!", "?", "…")


def align_speakers(
    transcriptions: tuple[TranscriptionSegment, ...],
    speakers: tuple[SpeakerSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    """Attach speaker labels and split ASR segments on diarized turns when possible.

    Args:
        transcriptions: ASR segments.
        speakers: Diarization segments.

    Returns:
        Final transcript segments with speaker labels when available.

    """
    aligned_segments = tuple(
        aligned_segment
        for segment in transcriptions
        for aligned_segment in _align_segment(segment, speakers)
    )
    return _merge_orphan_fragments(aligned_segments)


def without_speakers(
    transcriptions: tuple[TranscriptionSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    """Convert ASR segments to final segments without speaker labels.

    Args:
        transcriptions: ASR segments.

    Returns:
        Transcript segments without speaker labels.

    """
    return tuple(
        TranscriptSegment(start=segment.start, end=segment.end, text=segment.text)
        for segment in transcriptions
    )


def _best_speaker_for_segment(
    transcription: TranscriptionSegment,
    speakers: tuple[SpeakerSegment, ...],
) -> str | None:
    return _best_speaker_for_interval(transcription.start, transcription.end, speakers)


def _align_segment(
    transcription: TranscriptionSegment,
    speakers: tuple[SpeakerSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    segment_speaker = _best_speaker_for_segment(transcription, speakers)
    if not transcription.words:
        return _align_segment_by_estimated_words(transcription, speakers, segment_speaker)

    groups = tuple(_group_words_by_speaker(transcription.words, speakers, segment_speaker))
    if not groups:
        return (_single_transcript_segment(transcription, segment_speaker),)
    if len({speaker for speaker, _words in groups}) < MIN_SPLIT_SPEAKER_COUNT:
        return (_single_transcript_segment(transcription, segment_speaker),)
    return tuple(_word_group_to_segment(group) for group in groups)


def _align_segment_by_estimated_words(
    transcription: TranscriptionSegment,
    speakers: tuple[SpeakerSegment, ...],
    fallback_speaker: str | None,
) -> tuple[TranscriptSegment, ...]:
    tokens = tuple(transcription.text.split())
    if len(tokens) < MIN_SPLIT_TOKEN_COUNT:
        return (_single_transcript_segment(transcription, fallback_speaker),)

    estimated_words = tuple(_estimate_word_timings(transcription, tokens))
    groups = tuple(_group_words_by_speaker(estimated_words, speakers, fallback_speaker))
    if len({speaker for speaker, _words in groups}) < MIN_SPLIT_SPEAKER_COUNT:
        return (_single_transcript_segment(transcription, fallback_speaker),)
    return tuple(_word_group_to_segment(group) for group in groups)


def _single_transcript_segment(
    transcription: TranscriptionSegment,
    speaker: str | None,
) -> TranscriptSegment:
    return TranscriptSegment(
        start=transcription.start,
        end=transcription.end,
        text=transcription.text,
        speaker=speaker,
    )


def _estimate_word_timings(
    transcription: TranscriptionSegment,
    tokens: tuple[str, ...],
) -> Iterable[TranscriptionWord]:
    duration = transcription.end - transcription.start
    token_duration = duration / len(tokens)
    for index, token in enumerate(tokens):
        start = transcription.start + token_duration * index
        end = transcription.start + token_duration * (index + 1)
        prefix = "" if index == 0 else " "
        yield TranscriptionWord(start=start, end=end, text=f"{prefix}{token}")


def _group_words_by_speaker(
    words: tuple[TranscriptionWord, ...],
    speakers: tuple[SpeakerSegment, ...],
    fallback_speaker: str | None,
) -> Iterable[tuple[str | None, tuple[TranscriptionWord, ...]]]:
    current_speaker: str | None = None
    current_words: list[TranscriptionWord] = []

    for word in words:
        word_speaker = (
            _best_speaker_for_interval(word.start, word.end, speakers)
            or current_speaker
            or fallback_speaker
        )
        if current_words and word_speaker != current_speaker:
            yield current_speaker, tuple(current_words)
            current_words = []
        current_speaker = word_speaker
        current_words.append(word)

    if current_words:
        yield current_speaker, tuple(current_words)


def _word_group_to_segment(
    group: tuple[str | None, tuple[TranscriptionWord, ...]],
) -> TranscriptSegment:
    speaker, words = group
    text = "".join(word.text for word in words).strip()
    return TranscriptSegment(
        start=words[0].start,
        end=words[-1].end,
        text=text,
        speaker=speaker,
    )


def _merge_orphan_fragments(
    segments: tuple[TranscriptSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    merged: list[TranscriptSegment] = []
    index = 0
    while index < len(segments):
        current = segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        if next_segment is not None and _should_merge_into_next(current, next_segment):
            merged.append(_merge_segments(current, next_segment, speaker=next_segment.speaker))
            index += 2
            continue
        merged.append(current)
        index += 1
    return tuple(merged)


def _should_merge_into_next(current: TranscriptSegment, next_segment: TranscriptSegment) -> bool:
    duration = current.end - current.start
    gap = next_segment.start - current.end
    return (
        duration <= MAX_ORPHAN_FRAGMENT_SECONDS
        and len(current.text.split()) <= MAX_ORPHAN_FRAGMENT_WORDS
        and 0 <= gap <= MAX_ORPHAN_MERGE_GAP_SECONDS
        and not current.text.strip().endswith(TERMINAL_FRAGMENT_SUFFIXES)
    )


def _merge_segments(
    first: TranscriptSegment,
    second: TranscriptSegment,
    *,
    speaker: str | None,
) -> TranscriptSegment:
    return TranscriptSegment(
        start=first.start,
        end=second.end,
        text=_join_text(first.text, second.text),
        speaker=speaker,
    )


def _join_text(first: str, second: str) -> str:
    first = first.strip()
    second = second.strip()
    if not first:
        return second
    if not second:
        return first
    return f"{first} {second}"


def _best_speaker_for_interval(
    start: float,
    end: float,
    speakers: tuple[SpeakerSegment, ...],
) -> str | None:
    best_speaker: str | None = None
    best_overlap = 0.0
    for speaker in speakers:
        overlap = _overlap_seconds(
            start,
            end,
            speaker.start,
            speaker.end,
        )
        if overlap > best_overlap and overlap >= MIN_ALIGNMENT_OVERLAP_SECONDS:
            best_overlap = overlap
            best_speaker = speaker.speaker
    return best_speaker


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))
