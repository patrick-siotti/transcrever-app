from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.speakers import ReferenceSpeakerSegment, evaluate_speakers

HALF_ACCURACY = 0.5
COLLARED_REFERENCE_SECONDS = 9.0


def test_evaluate_speakers_maps_arbitrary_labels_by_overlap() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=10.0, text="a", speaker="Falante 3"),
        TranscriptSegment(start=10.0, end=20.0, text="b", speaker="Falante 1"),
    )
    reference = (
        ReferenceSpeakerSegment(start=0.0, end=10.0, speaker="S1"),
        ReferenceSpeakerSegment(start=10.0, end=20.0, speaker="S2"),
    )

    result = evaluate_speakers(predicted, reference)

    assert result.accuracy == 1.0
    assert result.mapping == {"Falante 3": "S1", "Falante 1": "S2"}
    assert tuple(segment.accuracy for segment in result.segments) == (1.0, 1.0)


def test_evaluate_speakers_penalizes_wrong_speaker_overlap() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=10.0, text="a", speaker="Falante 1"),
        TranscriptSegment(start=10.0, end=20.0, text="b", speaker="Falante 1"),
    )
    reference = (
        ReferenceSpeakerSegment(start=0.0, end=10.0, speaker="S1"),
        ReferenceSpeakerSegment(start=10.0, end=20.0, speaker="S2"),
    )

    result = evaluate_speakers(predicted, reference)

    assert result.accuracy == HALF_ACCURACY
    assert tuple(segment.accuracy for segment in result.segments) == (1.0, 0.0)


def test_evaluate_speakers_ignores_reference_boundaries_with_collar() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=0.5, text="edge", speaker="Falante 2"),
        TranscriptSegment(start=0.5, end=9.5, text="center", speaker="Falante 1"),
        TranscriptSegment(start=9.5, end=10.0, text="edge", speaker="Falante 2"),
    )
    reference = (ReferenceSpeakerSegment(start=0.0, end=10.0, speaker="S1"),)

    result = evaluate_speakers(predicted, reference, collar_seconds=0.5)

    assert result.accuracy == 1.0
    assert result.reference_seconds == COLLARED_REFERENCE_SECONDS
