from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.transcription import ReferenceTextSegment, evaluate_transcription

PERFECT_WER = 0.0
HALF_WER = 0.5


def test_evaluate_transcription_returns_zero_for_exact_text() -> None:
    predicted = (TranscriptSegment(start=0.0, end=2.0, text="Olá mundo"),)
    reference = (ReferenceTextSegment(start=0.0, end=2.0, text="ola mundo"),)

    result = evaluate_transcription(predicted, reference)

    assert result.wer == PERFECT_WER
    assert result.edit_distance == 0


def test_evaluate_transcription_counts_word_errors() -> None:
    predicted = (TranscriptSegment(start=0.0, end=2.0, text="ola teste"),)
    reference = (ReferenceTextSegment(start=0.0, end=2.0, text="ola mundo"),)

    result = evaluate_transcription(predicted, reference)

    assert result.wer == HALF_WER
    assert result.edit_distance == 1


def test_evaluate_transcription_uses_segment_midpoint_for_interval_membership() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=1.0, text="fora"),
        TranscriptSegment(start=1.0, end=2.0, text="dentro"),
        TranscriptSegment(start=1.9, end=5.0, text="tambem fora"),
    )
    reference = (ReferenceTextSegment(start=1.0, end=2.0, text="dentro"),)

    result = evaluate_transcription(predicted, reference)

    assert result.wer == PERFECT_WER
