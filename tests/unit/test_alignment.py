from transcrever_app.alignment.speakers import align_speakers
from transcrever_app.core.models import SpeakerSegment, TranscriptionSegment, TranscriptionWord

EXPECTED_SPLIT_SEGMENTS = 2


def test_align_speakers_uses_largest_overlap() -> None:
    transcriptions = (
        TranscriptionSegment(start=0.0, end=5.0, text="first"),
        TranscriptionSegment(start=5.0, end=10.0, text="second"),
    )
    speakers = (
        SpeakerSegment(start=0.0, end=4.0, speaker="Falante 1"),
        SpeakerSegment(start=4.0, end=10.0, speaker="Falante 2"),
    )

    result = align_speakers(transcriptions, speakers)

    assert result[0].speaker == "Falante 1"
    assert result[1].speaker == "Falante 2"


def test_align_speakers_splits_segment_with_word_timestamps() -> None:
    transcriptions = (
        TranscriptionSegment(
            start=0.0,
            end=4.0,
            text="Hello there. Hi friend.",
            words=(
                TranscriptionWord(start=0.0, end=0.8, text="Hello"),
                TranscriptionWord(start=0.8, end=1.4, text=" there."),
                TranscriptionWord(start=2.2, end=2.7, text=" Hi"),
                TranscriptionWord(start=2.7, end=3.4, text=" friend."),
            ),
        ),
    )
    speakers = (
        SpeakerSegment(start=0.0, end=1.6, speaker="Falante 1"),
        SpeakerSegment(start=2.0, end=4.0, speaker="Falante 2"),
    )

    result = align_speakers(transcriptions, speakers)

    assert len(result) == EXPECTED_SPLIT_SEGMENTS
    assert result[0].speaker == "Falante 1"
    assert result[0].text == "Hello there."
    assert result[1].speaker == "Falante 2"
    assert result[1].text == "Hi friend."


def test_align_speakers_splits_segment_by_estimated_word_timing() -> None:
    transcriptions = (
        TranscriptionSegment(
            start=0.0,
            end=4.0,
            text="one two three four",
        ),
    )
    speakers = (
        SpeakerSegment(start=0.0, end=2.0, speaker="Falante 1"),
        SpeakerSegment(start=2.0, end=4.0, speaker="Falante 2"),
    )

    result = align_speakers(transcriptions, speakers)

    assert len(result) == EXPECTED_SPLIT_SEGMENTS
    assert result[0].speaker == "Falante 1"
    assert result[0].text == "one two"
    assert result[1].speaker == "Falante 2"
    assert result[1].text == "three four"


def test_align_speakers_keeps_word_gap_with_current_speaker() -> None:
    transcriptions = (
        TranscriptionSegment(
            start=0.0,
            end=3.0,
            text="Hello there again.",
            words=(
                TranscriptionWord(start=0.0, end=0.5, text="Hello"),
                TranscriptionWord(start=0.9, end=1.2, text=" there"),
                TranscriptionWord(start=1.8, end=2.2, text=" again."),
            ),
        ),
    )
    speakers = (SpeakerSegment(start=0.0, end=0.7, speaker="Falante 1"),)

    result = align_speakers(transcriptions, speakers)

    assert len(result) == 1
    assert result[0].speaker == "Falante 1"
    assert result[0].text == "Hello there again."


def test_align_speakers_merges_short_orphan_fragment_into_next_segment() -> None:
    transcriptions = (
        TranscriptionSegment(
            start=0.0,
            end=4.0,
            text="Fala aí galera",
        ),
    )
    speakers = (
        SpeakerSegment(start=0.0, end=0.6, speaker="Falante 1"),
        SpeakerSegment(start=0.6, end=4.0, speaker="Falante 2"),
    )

    result = align_speakers(transcriptions, speakers)

    assert len(result) == 1
    assert result[0].speaker == "Falante 2"
    assert result[0].text == "Fala aí galera"


def test_align_speakers_keeps_short_terminal_fragment() -> None:
    transcriptions = (
        TranscriptionSegment(
            start=0.0,
            end=4.0,
            text="Caraca! Vamos lá",
        ),
    )
    speakers = (
        SpeakerSegment(start=0.0, end=1.0, speaker="Falante 1"),
        SpeakerSegment(start=1.0, end=4.0, speaker="Falante 2"),
    )

    result = align_speakers(transcriptions, speakers)

    assert len(result) == EXPECTED_SPLIT_SEGMENTS
    assert result[0].speaker == "Falante 1"
    assert result[0].text == "Caraca!"
    assert result[1].speaker == "Falante 2"
    assert result[1].text == "Vamos lá"
