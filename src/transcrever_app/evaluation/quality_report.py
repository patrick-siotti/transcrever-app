"""Aggregate quality report for one transcription run."""

from __future__ import annotations

from dataclasses import dataclass

from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.comparison import ReferenceCoverage, measure_reference_coverage
from transcrever_app.evaluation.speakers import (
    ReferenceSpeakerSegment,
    SpeakerEvaluation,
    evaluate_speakers,
)
from transcrever_app.evaluation.transcription import (
    ReferenceTextSegment,
    TranscriptionEvaluation,
    evaluate_transcription,
)


@dataclass(frozen=True)
class QualityReport:
    """Combined metrics that decide whether quality really improved."""

    duration_seconds: float
    text_coverage: ReferenceCoverage | None
    speaker_coverage: ReferenceCoverage | None
    transcription: TranscriptionEvaluation | None
    speakers: SpeakerEvaluation | None


@dataclass(frozen=True)
class QualityGate:
    """Pass/fail result for configured quality thresholds."""

    configured: bool
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class MetricDelta:
    """Metric value comparison between a baseline and a candidate run."""

    baseline: float | None
    candidate: float | None
    delta: float | None
    improved: bool | None


@dataclass(frozen=True)
class QualityComparison:
    """Quality deltas that must be checked before claiming real improvement."""

    text_coverage: MetricDelta
    wer: MetricDelta
    speaker_coverage: MetricDelta
    speaker_accuracy: MetricDelta


@dataclass(frozen=True)
class QualityImprovementGate:
    """Decision about whether a candidate has proven quality improvement."""

    proven: bool
    improved_metrics: tuple[str, ...]
    regressed_metrics: tuple[str, ...]
    evidence_failures: tuple[str, ...] = ()


def build_quality_report(
    *,
    predicted: tuple[TranscriptSegment, ...],
    duration_seconds: float,
    text_reference: tuple[ReferenceTextSegment, ...] | None = None,
    speaker_reference: tuple[ReferenceSpeakerSegment, ...] | None = None,
    speaker_collar_seconds: float = 0.0,
) -> QualityReport:
    """Build a combined quality report for a run."""
    text_coverage = None
    transcription = None
    if text_reference is not None:
        text_intervals = tuple((segment.start, segment.end) for segment in text_reference)
        text_coverage = measure_reference_coverage(text_intervals, duration_seconds)
        transcription = evaluate_transcription(predicted, text_reference)

    speaker_coverage = None
    speakers = None
    if speaker_reference is not None:
        speaker_intervals = tuple((segment.start, segment.end) for segment in speaker_reference)
        speaker_coverage = measure_reference_coverage(speaker_intervals, duration_seconds)
        speakers = evaluate_speakers(
            predicted,
            speaker_reference,
            collar_seconds=speaker_collar_seconds,
        )

    return QualityReport(
        duration_seconds=duration_seconds,
        text_coverage=text_coverage,
        speaker_coverage=speaker_coverage,
        transcription=transcription,
        speakers=speakers,
    )


def compare_quality_reports(
    baseline: QualityReport,
    candidate: QualityReport,
) -> QualityComparison:
    """Compare two quality reports using the same reference set."""
    return QualityComparison(
        text_coverage=_compare_metric(
            _coverage_value(baseline.text_coverage),
            _coverage_value(candidate.text_coverage),
            higher_is_better=True,
        ),
        wer=_compare_metric(
            _wer_value(baseline),
            _wer_value(candidate),
            higher_is_better=False,
        ),
        speaker_coverage=_compare_metric(
            _coverage_value(baseline.speaker_coverage),
            _coverage_value(candidate.speaker_coverage),
            higher_is_better=True,
        ),
        speaker_accuracy=_compare_metric(
            _speaker_accuracy_value(baseline),
            _speaker_accuracy_value(candidate),
            higher_is_better=True,
        ),
    )


def evaluate_quality_improvement(
    comparison: QualityComparison,
    *,
    min_text_coverage: float | None = None,
    min_speaker_coverage: float | None = None,
) -> QualityImprovementGate:
    """Decide whether the candidate improved without regressing available metrics."""
    evidence_failures: list[str] = []
    _validate_improvement_thresholds(
        evidence_failures,
        min_text_coverage=min_text_coverage,
        min_speaker_coverage=min_speaker_coverage,
    )
    if not evidence_failures:
        _check_min_metric_value(
            evidence_failures,
            label="cobertura textual",
            missing_label="cobertura textual indisponivel",
            value=comparison.text_coverage.candidate,
            threshold=min_text_coverage,
        )
        _check_min_metric_value(
            evidence_failures,
            label="cobertura de falantes",
            missing_label="cobertura de falantes indisponivel",
            value=comparison.speaker_coverage.candidate,
            threshold=min_speaker_coverage,
        )
    metrics = (
        ("cobertura textual", comparison.text_coverage),
        ("WER", comparison.wer),
        ("cobertura de falantes", comparison.speaker_coverage),
        ("acuracia de falantes", comparison.speaker_accuracy),
    )
    improved_metrics = tuple(label for label, delta in metrics if delta.improved is True)
    regressed_metrics = tuple(
        label
        for label, delta in metrics
        if delta.delta is not None and delta.delta != 0 and delta.improved is False
    )
    return QualityImprovementGate(
        proven=bool(improved_metrics) and not regressed_metrics and not evidence_failures,
        improved_metrics=improved_metrics,
        regressed_metrics=regressed_metrics,
        evidence_failures=tuple(evidence_failures),
    )


def evaluate_quality_gate(
    report: QualityReport,
    *,
    min_text_coverage: float | None = None,
    max_wer: float | None = None,
    min_speaker_coverage: float | None = None,
    min_speaker_accuracy: float | None = None,
) -> QualityGate:
    """Evaluate report metrics against configured thresholds."""
    thresholds = (
        min_text_coverage,
        max_wer,
        min_speaker_coverage,
        min_speaker_accuracy,
    )
    configured = any(threshold is not None for threshold in thresholds)
    failures: list[str] = []
    _validate_thresholds(
        failures,
        min_text_coverage=min_text_coverage,
        max_wer=max_wer,
        min_speaker_coverage=min_speaker_coverage,
        min_speaker_accuracy=min_speaker_accuracy,
    )
    if failures:
        return QualityGate(
            configured=configured,
            passed=False,
            failures=tuple(failures),
        )
    _check_min_coverage(
        failures,
        label="cobertura textual",
        missing_label="referencia textual ausente",
        coverage=report.text_coverage,
        threshold=min_text_coverage,
    )
    _check_max_wer(failures, report, max_wer)
    _check_min_coverage(
        failures,
        label="cobertura de falantes",
        missing_label="referencia de falantes ausente",
        coverage=report.speaker_coverage,
        threshold=min_speaker_coverage,
    )
    _check_min_speaker_accuracy(failures, report, min_speaker_accuracy)
    return QualityGate(
        configured=configured,
        passed=not failures,
        failures=tuple(failures),
    )


def _validate_thresholds(
    failures: list[str],
    *,
    min_text_coverage: float | None,
    max_wer: float | None,
    min_speaker_coverage: float | None,
    min_speaker_accuracy: float | None,
) -> None:
    for label, value in (
        ("min-text-coverage", min_text_coverage),
        ("max-wer", max_wer),
        ("min-speaker-coverage", min_speaker_coverage),
        ("min-speaker-accuracy", min_speaker_accuracy),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            failures.append(f"{label} fora da faixa 0..1: {value}")


def _validate_improvement_thresholds(
    failures: list[str],
    *,
    min_text_coverage: float | None,
    min_speaker_coverage: float | None,
) -> None:
    for label, value in (
        ("min-text-coverage", min_text_coverage),
        ("min-speaker-coverage", min_speaker_coverage),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            failures.append(f"{label} fora da faixa 0..1: {value}")


def _check_min_coverage(
    failures: list[str],
    *,
    label: str,
    missing_label: str,
    coverage: ReferenceCoverage | None,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    if coverage is None:
        failures.append(missing_label)
        return
    if coverage.coverage < threshold:
        failures.append(f"{label} {coverage.coverage:.2%} < {threshold:.2%}")


def _check_min_metric_value(
    failures: list[str],
    *,
    label: str,
    missing_label: str,
    value: float | None,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    if value is None:
        failures.append(missing_label)
        return
    if value < threshold:
        failures.append(f"{label} {value:.2%} < {threshold:.2%}")


def _check_max_wer(
    failures: list[str],
    report: QualityReport,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    if report.transcription is None:
        failures.append("WER indisponivel")
        return
    if report.transcription.wer > threshold:
        failures.append(f"WER {report.transcription.wer:.2%} > {threshold:.2%}")


def _check_min_speaker_accuracy(
    failures: list[str],
    report: QualityReport,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    if report.speakers is None:
        failures.append("acuracia de falantes indisponivel")
        return
    if report.speakers.accuracy < threshold:
        failures.append(f"acuracia de falantes {report.speakers.accuracy:.2%} < {threshold:.2%}")


def _compare_metric(
    baseline: float | None,
    candidate: float | None,
    *,
    higher_is_better: bool,
) -> MetricDelta:
    if baseline is None or candidate is None:
        return MetricDelta(
            baseline=baseline,
            candidate=candidate,
            delta=None,
            improved=None,
        )
    delta = candidate - baseline
    improved = delta > 0 if higher_is_better else delta < 0
    return MetricDelta(
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        improved=improved,
    )


def _coverage_value(coverage: ReferenceCoverage | None) -> float | None:
    if coverage is None:
        return None
    return coverage.coverage


def _wer_value(report: QualityReport) -> float | None:
    if report.transcription is None:
        return None
    return report.transcription.wer


def _speaker_accuracy_value(report: QualityReport) -> float | None:
    if report.speakers is None:
        return None
    return report.speakers.accuracy
