import json
from pathlib import Path

import pytest

from transcrever_app.evaluation.reference_review import (
    PendingReviewItem,
    apply_speaker_review_manifest,
    apply_speaker_review_markdown,
    apply_text_review_manifest,
    apply_text_review_markdown,
    build_review_coverage_plan,
    parse_review_markdown,
    parse_speaker_review_markdown,
    summarize_review_data,
    summarize_speaker_review_data,
    write_review_markdown,
    write_speaker_review_markdown,
)

TOTAL_SEGMENTS_AFTER_REVIEW = 2
TOTAL_REVIEW_GAPS = 3
TOTAL_SPEAKER_SEGMENTS_AFTER_REVIEW = 2
TOTAL_CANDIDATE_SEGMENTS_AFTER_REVIEW = 2
ONE_SECOND = 1.0
TWO_SECONDS = 2.0
EIGHT_SECONDS = 8.0
HALF_COVERAGE = 0.5
NINETY_PERCENT = 0.9


def test_apply_text_review_manifest_adds_reviewed_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps(
            {
                "source": "sample.wav",
                "segments": [
                    {"start": 0.0, "end": 5.0, "text": "primeiro", "note": "base"},
                ],
            },
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "text_reference_json": str(reference_path),
                "gaps": [
                    {
                        "start": 5.0,
                        "end": 10.0,
                        "reviewed_text": "segundo trecho",
                        "review_note": "revisado",
                    },
                    {
                        "start": 10.0,
                        "end": 12.0,
                        "skip": True,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = apply_text_review_manifest(manifest_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 1
    assert result.skipped_gaps == 1
    assert result.total_segments == TOTAL_SEGMENTS_AFTER_REVIEW
    assert payload["segments"][1] == {
        "start": 5.0,
        "end": 10.0,
        "text": "segundo trecho",
        "note": "revisado",
    }


def test_write_review_markdown_includes_clip_and_candidate_text(tmp_path: Path) -> None:
    output_path = tmp_path / "review.md"
    manifest = {
        "result_json": "runs/job/outputs/result.json",
        "text_reference_json": "evaluation/reference.json",
        "audio_file": "runs/job/audio/audio.wav",
        "gaps": [
            {
                "clip": "clips/gap.wav",
                "start": 1.0,
                "end": 3.0,
                "duration_seconds": 2.0,
                "candidate_text": "texto candidato",
                "candidate_segments": [
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "speaker": "Falante 1",
                        "suggested_reference_speaker": "S1",
                        "text": "texto",
                    },
                ],
            },
        ],
    }

    result = write_review_markdown(manifest, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert result == output_path
    assert "clips/gap.wav" in content
    assert "texto candidato" in content
    assert "reviewed_text" in content


def test_write_speaker_review_markdown_includes_candidate_segments(tmp_path: Path) -> None:
    output_path = tmp_path / "speaker-review.md"
    manifest = {
        "result_json": "runs/job/outputs/result.json",
        "speaker_reference_json": "evaluation/speakers.json",
        "audio_file": "runs/job/audio/audio.wav",
        "speaker_legend": [
            {
                "speaker": "S1",
                "start": 0.0,
                "end": 1.0,
                "note": "exemplo",
            },
        ],
        "gaps": [
            {
                "clip": "clips/gap.wav",
                "start": 1.0,
                "end": 3.0,
                "duration_seconds": 2.0,
                "candidate_segments": [
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "speaker": "Falante 1",
                        "suggested_reference_speaker": "S1",
                        "text": "texto",
                    },
                ],
            },
        ],
    }

    result = write_speaker_review_markdown(manifest, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert result == output_path
    assert "clips/gap.wav" in content
    assert "`S1`: 0.00-1.00 - exemplo" in content
    assert "Falante 1 -> sugestao S1: texto" in content
    assert "#### Segmento 01: 1.00s-2.00s" in content
    assert "reviewed_speaker" in content


def test_parse_review_markdown_reads_manual_blocks(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    reference_path = tmp_path / "reference.json"
    markdown_path = tmp_path / "review.md"
    result_path.write_text(json.dumps({"duration_seconds": 20.0}), encoding="utf-8")
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    markdown_path.write_text(
        "\n".join(
            [
                "# Revisao de transcricao",
                "",
                f"- Resultado: `{result_path}`",
                f"- Referencia textual: `{reference_path}`",
                "",
                "## Lacuna 01: 5.00s-10.00s",
                "",
                "### Revisao manual",
                "",
                "- reviewed_text:",
                "```text",
                "texto revisado",
                "```",
                "- review_note:",
                "```text",
                "nota",
                "```",
                "- skip: false",
                "",
                "## Lacuna 02: 10.00s-11.00s",
                "",
                "### Revisao manual",
                "",
                "- reviewed_text:",
                "```text",
                "",
                "```",
                "- review_note:",
                "```text",
                "",
                "```",
                "- skip: true",
            ],
        ),
        encoding="utf-8",
    )

    result = parse_review_markdown(markdown_path)

    assert result["text_reference_json"] == str(reference_path)
    assert result["result_json"] == str(result_path)
    assert result["gaps"][0]["reviewed_text"] == "texto revisado"
    assert result["gaps"][0]["review_note"] == "nota"
    assert result["gaps"][1]["skip"] is True


def test_parse_speaker_review_markdown_reads_manual_blocks(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    reference_path = tmp_path / "speakers.json"
    markdown_path = tmp_path / "speaker-review.md"
    result_path.write_text(json.dumps({"duration_seconds": 20.0}), encoding="utf-8")
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    markdown_path.write_text(
        "\n".join(
            [
                "# Revisao de falantes",
                "",
                f"- Resultado: `{result_path}`",
                f"- Referencia de falantes: `{reference_path}`",
                "",
                "## Lacuna 01: 5.00s-10.00s",
                "",
                "### Revisao por segmento candidato",
                "",
                "#### Segmento 01: 5.00s-6.00s",
                "",
                "- reviewed_speaker:",
                "```text",
                "S1",
                "```",
                "- review_note:",
                "```text",
                "segmento",
                "```",
                "- skip: false",
                "",
                "### Revisao manual",
                "",
                "- reviewed_speaker:",
                "```text",
                "",
                "```",
                "- review_note:",
                "```text",
                "",
                "```",
                "- skip: false",
                "",
                "## Lacuna 02: 10.00s-11.00s",
                "",
                "### Revisao manual",
                "",
                "- reviewed_speaker:",
                "```text",
                "",
                "```",
                "- review_note:",
                "```text",
                "",
                "```",
                "- skip: true",
            ],
        ),
        encoding="utf-8",
    )

    result = parse_speaker_review_markdown(markdown_path)

    assert result["speaker_reference_json"] == str(reference_path)
    assert result["result_json"] == str(result_path)
    assert result["gaps"][0]["reviewed_speaker"] == ""
    assert result["gaps"][0]["candidate_segments"][0]["reviewed_speaker"] == "S1"
    assert result["gaps"][0]["candidate_segments"][0]["review_note"] == "segmento"
    assert result["gaps"][1]["skip"] is True


def test_summarize_review_data_marks_pending_gaps() -> None:
    manifest = {
        "gaps": [
            {
                "start": 0.0,
                "end": 1.0,
                "reviewed_text": "texto",
                "skip": False,
            },
            {
                "start": 1.0,
                "end": 2.0,
                "reviewed_text": "",
                "skip": True,
            },
            {
                "start": 2.0,
                "end": 3.0,
                "reviewed_text": "",
                "skip": False,
            },
        ],
    }

    status = summarize_review_data(manifest)

    assert status.total_gaps == TOTAL_REVIEW_GAPS
    assert status.reviewed_gaps == 1
    assert status.skipped_gaps == 1
    assert status.pending_gaps == 1
    assert status.pending_ranges == ("2.00-3.00",)
    assert status.pending_items == (
        PendingReviewItem(start=2.0, end=3.0, duration_seconds=ONE_SECOND),
    )
    assert status.ready is False
    assert status.reviewed_seconds == ONE_SECOND
    assert status.skipped_seconds == ONE_SECOND
    assert status.pending_seconds == ONE_SECOND


def test_build_review_coverage_plan_selects_largest_pending_items() -> None:
    status = summarize_review_data(
        {
            "gaps": [
                {"start": 10.0, "end": 12.0, "reviewed_text": "", "skip": False},
                {"start": 12.0, "end": 20.0, "reviewed_text": "", "skip": False},
            ],
        },
    )

    plan = build_review_coverage_plan(
        status,
        current_covered_seconds=10.0,
        duration_seconds=20.0,
        target_coverage=NINETY_PERCENT,
    )

    assert plan.current_coverage == HALF_COVERAGE
    assert plan.target_coverage == NINETY_PERCENT
    assert plan.reachable is True
    assert plan.selected_seconds == EIGHT_SECONDS
    assert tuple(step.item.range_label for step in plan.steps) == ("12.00-20.00",)
    assert plan.steps[0].projected_coverage == NINETY_PERCENT


def test_build_review_coverage_plan_rejects_invalid_target() -> None:
    status = summarize_review_data({"gaps": []})

    with pytest.raises(ValueError, match="target-coverage fora da faixa"):
        build_review_coverage_plan(
            status,
            current_covered_seconds=0.0,
            duration_seconds=10.0,
            target_coverage=1.2,
        )


def test_summarize_speaker_review_data_marks_pending_gaps() -> None:
    manifest = {
        "gaps": [
            {
                "start": 0.0,
                "end": 1.0,
                "reviewed_speaker": "S1",
                "skip": False,
            },
            {
                "start": 1.0,
                "end": 2.0,
                "reviewed_speaker": "",
                "skip": True,
            },
            {
                "start": 2.0,
                "end": 3.0,
                "reviewed_speaker": "",
                "skip": False,
            },
        ],
    }

    status = summarize_speaker_review_data(manifest)

    assert status.total_gaps == TOTAL_REVIEW_GAPS
    assert status.reviewed_gaps == 1
    assert status.skipped_gaps == 1
    assert status.pending_gaps == 1
    assert status.pending_ranges == ("2.00-3.00",)
    assert status.pending_items == (
        PendingReviewItem(start=2.0, end=3.0, duration_seconds=ONE_SECOND),
    )
    assert status.ready is False
    assert status.reviewed_seconds == ONE_SECOND
    assert status.skipped_seconds == ONE_SECOND
    assert status.pending_seconds == ONE_SECOND


def test_summarize_speaker_review_data_tracks_pending_candidate_segments() -> None:
    manifest = {
        "gaps": [
            {
                "start": 10.0,
                "end": 14.0,
                "reviewed_speaker": "",
                "skip": False,
                "candidate_segments": [
                    {
                        "start": 10.0,
                        "end": 11.0,
                        "reviewed_speaker": "S1",
                        "skip": False,
                    },
                    {
                        "start": 11.0,
                        "end": 12.0,
                        "reviewed_speaker": "",
                        "skip": False,
                    },
                ],
            },
        ],
    }

    status = summarize_speaker_review_data(manifest)

    assert status.total_gaps == 1
    assert status.reviewed_gaps == 0
    assert status.pending_gaps == 1
    assert status.pending_ranges == ("11.00-12.00",)
    assert status.pending_items == (
        PendingReviewItem(start=11.0, end=12.0, duration_seconds=ONE_SECOND),
    )
    assert status.ready is False
    assert status.reviewed_seconds == ONE_SECOND
    assert status.skipped_seconds == 0.0
    assert status.pending_seconds == ONE_SECOND


def test_summarize_speaker_review_data_counts_ready_candidate_segments() -> None:
    manifest = {
        "gaps": [
            {
                "start": 10.0,
                "end": 14.0,
                "reviewed_speaker": "",
                "skip": False,
                "candidate_segments": [
                    {
                        "start": 10.0,
                        "end": 11.0,
                        "reviewed_speaker": "S1",
                        "skip": False,
                    },
                    {
                        "start": 11.0,
                        "end": 13.0,
                        "reviewed_speaker": "",
                        "skip": True,
                    },
                ],
            },
        ],
    }

    status = summarize_speaker_review_data(manifest)

    assert status.ready is True
    assert status.reviewed_gaps == 1
    assert status.reviewed_seconds == ONE_SECOND
    assert status.skipped_seconds == TWO_SECONDS
    assert status.pending_seconds == 0.0


def test_apply_text_review_markdown_adds_reviewed_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    markdown_path = tmp_path / "review.md"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    markdown_path.write_text(
        "\n".join(
            [
                "# Revisao de transcricao",
                "",
                f"- Referencia textual: `{reference_path}`",
                "",
                "## Lacuna 01: 5.00s-10.00s",
                "",
                "### Revisao manual",
                "",
                "- reviewed_text:",
                "```text",
                "texto revisado",
                "```",
                "- review_note:",
                "```text",
                "nota markdown",
                "```",
                "- skip: false",
            ],
        ),
        encoding="utf-8",
    )

    result = apply_text_review_markdown(markdown_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 1
    assert payload["segments"][0]["text"] == "texto revisado"
    assert payload["segments"][0]["note"] == "nota markdown"


def test_apply_speaker_review_markdown_adds_reviewed_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    markdown_path = tmp_path / "speaker-review.md"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    markdown_path.write_text(
        "\n".join(
            [
                "# Revisao de falantes",
                "",
                f"- Referencia de falantes: `{reference_path}`",
                "",
                "## Lacuna 01: 5.00s-10.00s",
                "",
                "### Revisao manual",
                "",
                "- reviewed_speaker:",
                "```text",
                "S1",
                "```",
                "- review_note:",
                "```text",
                "nota markdown",
                "```",
                "- skip: false",
            ],
        ),
        encoding="utf-8",
    )

    result = apply_speaker_review_markdown(markdown_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 1
    assert payload["segments"][0]["speaker"] == "S1"
    assert payload["segments"][0]["note"] == "nota markdown"


def test_apply_speaker_review_manifest_adds_reviewed_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    manifest_path = tmp_path / "speaker-manifest.json"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps(
            {
                "source": "sample.wav",
                "segments": [
                    {"start": 0.0, "end": 5.0, "speaker": "S0", "note": "base"},
                ],
            },
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "speaker_reference_json": str(reference_path),
                "gaps": [
                    {
                        "start": 5.0,
                        "end": 10.0,
                        "reviewed_speaker": "S1",
                        "review_note": "revisado",
                    },
                    {
                        "start": 10.0,
                        "end": 12.0,
                        "skip": True,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = apply_speaker_review_manifest(manifest_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 1
    assert result.skipped_gaps == 1
    assert result.total_segments == TOTAL_SPEAKER_SEGMENTS_AFTER_REVIEW
    assert payload["segments"][1] == {
        "start": 5.0,
        "end": 10.0,
        "speaker": "S1",
        "note": "revisado",
    }


def test_apply_speaker_review_manifest_adds_reviewed_candidate_segments(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    manifest_path = tmp_path / "speaker-manifest.json"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "speaker_reference_json": str(reference_path),
                "gaps": [
                    {
                        "start": 5.0,
                        "end": 10.0,
                        "reviewed_speaker": "",
                        "candidate_segments": [
                            {
                                "start": 5.0,
                                "end": 6.0,
                                "reviewed_speaker": "S1",
                                "review_note": "primeiro candidato",
                            },
                            {
                                "start": 6.0,
                                "end": 7.0,
                                "reviewed_speaker": "S2",
                                "review_note": "segundo candidato",
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = apply_speaker_review_manifest(manifest_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == TOTAL_CANDIDATE_SEGMENTS_AFTER_REVIEW
    assert payload["segments"] == [
        {
            "start": 5.0,
            "end": 6.0,
            "speaker": "S1",
            "note": "primeiro candidato",
        },
        {
            "start": 6.0,
            "end": 7.0,
            "speaker": "S2",
            "note": "segundo candidato",
        },
    ]


def test_apply_text_review_manifest_rejects_pending_review_by_default(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "text_reference_json": str(reference_path),
                "gaps": [{"start": 0.0, "end": 3.0, "reviewed_text": ""}],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Revisao incompleta"):
        apply_text_review_manifest(manifest_path, output_path)


def test_apply_speaker_review_manifest_rejects_pending_review_by_default(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    manifest_path = tmp_path / "speaker-manifest.json"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "speaker_reference_json": str(reference_path),
                "gaps": [{"start": 0.0, "end": 3.0, "reviewed_speaker": ""}],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Revisao de falantes incompleta"):
        apply_speaker_review_manifest(manifest_path, output_path)


def test_apply_text_review_manifest_allows_pending_review_when_explicit(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "text_reference_json": str(reference_path),
                "gaps": [{"start": 0.0, "end": 3.0, "reviewed_text": ""}],
            },
        ),
        encoding="utf-8",
    )

    result = apply_text_review_manifest(manifest_path, output_path, allow_pending=True)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 0
    assert result.skipped_gaps == 1
    assert payload["segments"] == []


def test_apply_speaker_review_manifest_allows_pending_review_when_explicit(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    manifest_path = tmp_path / "speaker-manifest.json"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "speaker_reference_json": str(reference_path),
                "gaps": [{"start": 0.0, "end": 3.0, "reviewed_speaker": ""}],
            },
        ),
        encoding="utf-8",
    )

    result = apply_speaker_review_manifest(manifest_path, output_path, allow_pending=True)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.added_segments == 0
    assert result.skipped_gaps == 1
    assert payload["segments"] == []


def test_apply_text_review_manifest_accepts_utf8_bom_manifest(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps({"source": "sample.wav", "segments": []}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "text_reference_json": str(reference_path),
                "gaps": [{"start": 0.0, "end": 3.0, "reviewed_text": "trecho"}],
            },
        ),
        encoding="utf-8-sig",
    )

    result = apply_text_review_manifest(manifest_path, output_path)

    assert result.added_segments == 1


def test_apply_text_review_manifest_rejects_overlapping_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "updated.json"
    reference_path.write_text(
        json.dumps(
            {
                "source": "sample.wav",
                "segments": [
                    {"start": 0.0, "end": 5.0, "text": "primeiro", "note": "base"},
                ],
            },
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "text_reference_json": str(reference_path),
                "gaps": [
                    {"start": 4.0, "end": 7.0, "reviewed_text": "sobreposto"},
                ],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sobrepoe"):
        apply_text_review_manifest(manifest_path, output_path)


def test_apply_speaker_review_manifest_rejects_overlapping_gap(tmp_path: Path) -> None:
    reference_path = tmp_path / "speakers.json"
    manifest_path = tmp_path / "speaker-manifest.json"
    output_path = tmp_path / "updated-speakers.json"
    reference_path.write_text(
        json.dumps(
            {
                "source": "sample.wav",
                "segments": [
                    {"start": 0.0, "end": 5.0, "speaker": "S0", "note": "base"},
                ],
            },
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "speaker_reference_json": str(reference_path),
                "gaps": [
                    {"start": 4.0, "end": 7.0, "reviewed_speaker": "S1"},
                ],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sobrepoe"):
        apply_speaker_review_manifest(manifest_path, output_path)
