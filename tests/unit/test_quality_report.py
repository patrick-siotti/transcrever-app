from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.quality_report import (
    MetricDelta,
    QualityComparison,
    build_quality_report,
    compare_quality_reports,
    evaluate_quality_gate,
    evaluate_quality_improvement,
)
from transcrever_app.evaluation.speakers import ReferenceSpeakerSegment
from transcrever_app.evaluation.transcription import ReferenceTextSegment

HALF_DURATION_COVERAGE = 0.5


def test_build_quality_report_combines_text_and_speaker_metrics() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=5.0, text="olá mundo", speaker="Falante 1"),
        TranscriptSegment(start=5.0, end=10.0, text="segundo trecho", speaker="Falante 2"),
    )
    text_reference = (
        ReferenceTextSegment(start=0.0, end=5.0, text="olá mundo"),
    )
    speaker_reference = (
        ReferenceSpeakerSegment(start=0.0, end=5.0, speaker="S1"),
        ReferenceSpeakerSegment(start=5.0, end=10.0, speaker="S2"),
    )

    report = build_quality_report(
        predicted=predicted,
        duration_seconds=10.0,
        text_reference=text_reference,
        speaker_reference=speaker_reference,
    )

    assert report.text_coverage is not None
    assert report.speaker_coverage is not None
    assert report.transcription is not None
    assert report.speakers is not None
    assert report.text_coverage.coverage == HALF_DURATION_COVERAGE
    assert report.speaker_coverage.coverage == 1.0
    assert report.transcription.wer == 0.0
    assert report.speakers.accuracy == 1.0


def test_build_quality_report_allows_missing_references() -> None:
    report = build_quality_report(
        predicted=(),
        duration_seconds=10.0,
    )

    assert report.text_coverage is None
    assert report.speaker_coverage is None
    assert report.transcription is None
    assert report.speakers is None


def test_evaluate_quality_gate_passes_when_thresholds_are_met() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=10.0, text="olá mundo", speaker="Falante 1"),
    )
    text_reference = (
        ReferenceTextSegment(start=0.0, end=10.0, text="olá mundo"),
    )
    report = build_quality_report(
        predicted=predicted,
        duration_seconds=10.0,
        text_reference=text_reference,
    )

    gate = evaluate_quality_gate(report, min_text_coverage=1.0, max_wer=0.0)

    assert gate.configured is True
    assert gate.passed is True
    assert gate.failures == ()


def test_evaluate_quality_gate_fails_when_text_coverage_is_low() -> None:
    predicted = (
        TranscriptSegment(start=0.0, end=5.0, text="olá mundo", speaker=None),
    )
    text_reference = (
        ReferenceTextSegment(start=0.0, end=5.0, text="olá mundo"),
    )
    report = build_quality_report(
        predicted=predicted,
        duration_seconds=10.0,
        text_reference=text_reference,
    )

    gate = evaluate_quality_gate(report, min_text_coverage=1.0)

    assert gate.configured is True
    assert gate.passed is False
    assert gate.failures == ("cobertura textual 50.00% < 100.00%",)


def test_evaluate_quality_gate_is_unconfigured_without_thresholds() -> None:
    report = build_quality_report(predicted=(), duration_seconds=10.0)

    gate = evaluate_quality_gate(report)

    assert gate.configured is False
    assert gate.passed is True
    assert gate.failures == ()


def test_evaluate_quality_gate_rejects_threshold_outside_zero_to_one() -> None:
    report = build_quality_report(predicted=(), duration_seconds=10.0)

    gate = evaluate_quality_gate(report, min_text_coverage=1.2)

    assert gate.configured is True
    assert gate.passed is False
    assert gate.failures == ("min-text-coverage fora da faixa 0..1: 1.2",)


def test_compare_quality_reports_marks_improvement_by_metric_direction() -> None:
    baseline = build_quality_report(
        predicted=(
            TranscriptSegment(start=0.0, end=10.0, text="ola mundo errado", speaker="Falante 1"),
        ),
        duration_seconds=10.0,
        text_reference=(
            ReferenceTextSegment(start=0.0, end=10.0, text="ola mundo"),
        ),
        speaker_reference=(
            ReferenceSpeakerSegment(start=0.0, end=10.0, speaker="S1"),
        ),
    )
    candidate = build_quality_report(
        predicted=(
            TranscriptSegment(start=0.0, end=10.0, text="ola mundo", speaker="Falante 1"),
        ),
        duration_seconds=10.0,
        text_reference=(
            ReferenceTextSegment(start=0.0, end=10.0, text="ola mundo"),
        ),
        speaker_reference=(
            ReferenceSpeakerSegment(start=0.0, end=10.0, speaker="S1"),
        ),
    )

    comparison = compare_quality_reports(baseline, candidate)

    assert comparison.text_coverage.improved is False
    assert comparison.wer.improved is True
    assert comparison.wer.delta is not None
    assert comparison.wer.delta < 0
    assert comparison.speaker_coverage.improved is False
    assert comparison.speaker_accuracy.improved is False


def test_compare_quality_reports_keeps_missing_metrics_unavailable() -> None:
    baseline = build_quality_report(predicted=(), duration_seconds=10.0)
    candidate = build_quality_report(predicted=(), duration_seconds=10.0)

    comparison = compare_quality_reports(baseline, candidate)

    assert comparison.text_coverage.improved is None
    assert comparison.wer.improved is None
    assert comparison.speaker_coverage.improved is None
    assert comparison.speaker_accuracy.improved is None


def test_evaluate_quality_improvement_accepts_clean_improvement() -> None:
    comparison = QualityComparison(
        text_coverage=MetricDelta(0.5, 0.5, 0.0, False),
        wer=MetricDelta(0.2, 0.1, -0.1, True),
        speaker_coverage=MetricDelta(0.8, 0.8, 0.0, False),
        speaker_accuracy=MetricDelta(0.9, 0.9, 0.0, False),
    )

    gate = evaluate_quality_improvement(comparison)

    assert gate.proven is True
    assert gate.improved_metrics == ("WER",)
    assert gate.regressed_metrics == ()
    assert gate.evidence_failures == ()


def test_evaluate_quality_improvement_rejects_low_text_coverage() -> None:
    comparison = QualityComparison(
        text_coverage=MetricDelta(0.5, 0.5, 0.0, False),
        wer=MetricDelta(0.2, 0.1, -0.1, True),
        speaker_coverage=MetricDelta(0.8, 0.8, 0.0, False),
        speaker_accuracy=MetricDelta(0.9, 0.9, 0.0, False),
    )

    gate = evaluate_quality_improvement(comparison, min_text_coverage=0.9)

    assert gate.proven is False
    assert gate.improved_metrics == ("WER",)
    assert gate.regressed_metrics == ()
    assert gate.evidence_failures == ("cobertura textual 50.00% < 90.00%",)


def test_evaluate_quality_improvement_rejects_invalid_coverage_threshold() -> None:
    comparison = QualityComparison(
        text_coverage=MetricDelta(0.5, 0.5, 0.0, False),
        wer=MetricDelta(0.2, 0.1, -0.1, True),
        speaker_coverage=MetricDelta(0.8, 0.8, 0.0, False),
        speaker_accuracy=MetricDelta(0.9, 0.9, 0.0, False),
    )

    gate = evaluate_quality_improvement(comparison, min_speaker_coverage=1.2)

    assert gate.proven is False
    assert gate.improved_metrics == ("WER",)
    assert gate.regressed_metrics == ()
    assert gate.evidence_failures == ("min-speaker-coverage fora da faixa 0..1: 1.2",)


def test_evaluate_quality_improvement_rejects_no_improvement() -> None:
    comparison = QualityComparison(
        text_coverage=MetricDelta(0.5, 0.5, 0.0, False),
        wer=MetricDelta(0.0, 0.0, 0.0, False),
        speaker_coverage=MetricDelta(0.8, 0.8, 0.0, False),
        speaker_accuracy=MetricDelta(1.0, 1.0, 0.0, False),
    )

    gate = evaluate_quality_improvement(comparison)

    assert gate.proven is False
    assert gate.improved_metrics == ()
    assert gate.regressed_metrics == ()


def test_evaluate_quality_improvement_rejects_regression() -> None:
    comparison = QualityComparison(
        text_coverage=MetricDelta(0.5, 0.6, 0.1, True),
        wer=MetricDelta(0.0, 0.1, 0.1, False),
        speaker_coverage=MetricDelta(0.8, 0.8, 0.0, False),
        speaker_accuracy=MetricDelta(1.0, 1.0, 0.0, False),
    )

    gate = evaluate_quality_improvement(comparison)

    assert gate.proven is False
    assert gate.improved_metrics == ("cobertura textual",)
    assert gate.regressed_metrics == ("WER",)
