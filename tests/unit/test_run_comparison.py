from transcrever_app.core.models import TranscriptSegment
from transcrever_app.evaluation.comparison import (
    compare_runs,
    find_reference_gaps,
    measure_reference_coverage,
)

MERGED_REFERENCE_SECONDS = 25.0
MERGED_REFERENCE_COVERAGE = 0.625
FIRST_GAP_SECONDS = 5.0
SECOND_GAP_SECONDS = 10.0


def test_compare_runs_detects_only_segmentation_change() -> None:
    baseline = (
        TranscriptSegment(start=0.0, end=10.0, text="Olá mundo", speaker="Falante 1"),
    )
    candidate = (
        TranscriptSegment(start=0.0, end=5.0, text="Olá", speaker="Falante A"),
        TranscriptSegment(start=5.0, end=10.0, text="mundo", speaker="Falante A"),
    )

    result = compare_runs(baseline, candidate)

    assert result.text_edit_distance == 0
    assert result.speaker_agreement == 1.0
    assert result.only_segmentation_changed is True


def test_compare_runs_detects_text_change() -> None:
    baseline = (
        TranscriptSegment(start=0.0, end=10.0, text="Olá mundo", speaker="Falante 1"),
    )
    candidate = (
        TranscriptSegment(start=0.0, end=10.0, text="Olá pessoa", speaker="Falante 1"),
    )

    result = compare_runs(baseline, candidate)

    assert result.text_edit_distance == 1
    assert result.only_segmentation_changed is False


def test_compare_runs_marks_speaker_agreement_unavailable_without_speakers() -> None:
    baseline = (
        TranscriptSegment(start=0.0, end=10.0, text="Olá mundo", speaker=None),
    )
    candidate = (
        TranscriptSegment(start=0.0, end=10.0, text="Olá mundo", speaker=None),
    )

    result = compare_runs(baseline, candidate)

    assert result.speaker_agreement is None
    assert result.speaker_mapping == {}


def test_measure_reference_coverage_merges_overlapping_intervals() -> None:
    intervals = (
        (0.0, 10.0),
        (5.0, 15.0),
        (20.0, 30.0),
    )

    result = measure_reference_coverage(intervals, duration_seconds=40.0)

    assert result.covered_seconds == MERGED_REFERENCE_SECONDS
    assert result.coverage == MERGED_REFERENCE_COVERAGE


def test_find_reference_gaps_uses_merged_intervals() -> None:
    intervals = (
        (5.0, 10.0),
        (9.0, 20.0),
        (30.0, 40.0),
    )

    gaps = find_reference_gaps(intervals, duration_seconds=50.0, min_gap_seconds=2.0)

    assert [(gap.start, gap.end) for gap in gaps] == [
        (0.0, 5.0),
        (20.0, 30.0),
        (40.0, 50.0),
    ]
    assert gaps[0].duration_seconds == FIRST_GAP_SECONDS
    assert gaps[1].duration_seconds == SECOND_GAP_SECONDS
