"""Helpers for applying manually reviewed transcription gaps."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REFERENCE_LINE_PATTERN = re.compile(r"^- Referencia textual: `(?P<path>.+)`$", re.MULTILINE)
_RESULT_LINE_PATTERN = re.compile(r"^- Resultado: `(?P<path>.+)`$", re.MULTILINE)
_GAP_HEADING_PATTERN = re.compile(
    r"^## Lacuna (?P<index>\d+): (?P<start>\d+(?:\.\d+)?)s-(?P<end>\d+(?:\.\d+)?)s$",
    re.MULTILINE,
)
_REVIEW_BLOCK_PATTERN = re.compile(
    r"### Revisao manual\s+"
    r"- reviewed_text:\s+```text\s*(?P<reviewed_text>.*?)\s*```\s+"
    r"- review_note:\s+```text\s*(?P<review_note>.*?)\s*```\s+"
    r"- skip:\s*(?P<skip>true|false)?",
    flags=re.DOTALL,
)
_SPEAKER_REFERENCE_LINE_PATTERN = re.compile(
    r"^- Referencia de falantes: `(?P<path>.+)`$",
    re.MULTILINE,
)
_SPEAKER_REVIEW_BLOCK_PATTERN = re.compile(
    r"### Revisao manual\s+"
    r"- reviewed_speaker:\s+```text\s*(?P<reviewed_speaker>.*?)\s*```\s+"
    r"- review_note:\s+```text\s*(?P<review_note>.*?)\s*```\s+"
    r"- skip:\s*(?P<skip>true|false)?",
    flags=re.DOTALL,
)
_SPEAKER_SEGMENT_HEADING_PATTERN = re.compile(
    r"^#### Segmento (?P<index>\d+): "
    r"(?P<start>\d+(?:\.\d+)?)s-(?P<end>\d+(?:\.\d+)?)s$",
    re.MULTILINE,
)
_SPEAKER_SEGMENT_REVIEW_BLOCK_PATTERN = re.compile(
    r"- reviewed_speaker:\s+```text\s*(?P<reviewed_speaker>.*?)\s*```\s+"
    r"- review_note:\s+```text\s*(?P<review_note>.*?)\s*```\s+"
    r"- skip:\s*(?P<skip>true|false)?",
    flags=re.DOTALL,
)


@dataclass(frozen=True)
class AppliedReview:
    """Summary of applied manual review entries."""

    output_path: Path
    added_segments: int
    skipped_gaps: int
    total_segments: int


@dataclass(frozen=True)
class PendingReviewItem:
    """One pending review range with its duration."""

    start: float
    end: float
    duration_seconds: float

    @property
    def range_label(self) -> str:
        """Human-readable time range label."""
        return f"{self.start:.2f}-{self.end:.2f}"


@dataclass(frozen=True)
class ReviewCoverageStep:
    """One pending item selected to reach a coverage target."""

    item: PendingReviewItem
    projected_coverage: float


@dataclass(frozen=True)
class ReviewCoveragePlan:
    """Projected review work needed to reach a coverage target."""

    current_coverage: float
    target_coverage: float
    selected_seconds: float
    steps: tuple[ReviewCoverageStep, ...]
    reachable: bool


@dataclass(frozen=True)
class ReviewStatus:
    """Readiness summary for a review worksheet."""

    total_gaps: int
    reviewed_gaps: int
    skipped_gaps: int
    pending_gaps: int
    pending_ranges: tuple[str, ...]
    ready: bool
    pending_items: tuple[PendingReviewItem, ...] = ()
    reviewed_seconds: float = 0.0
    skipped_seconds: float = 0.0
    pending_seconds: float = 0.0


def write_review_markdown(manifest: dict[str, Any], output_path: Path) -> Path:
    """Write a human-friendly review worksheet for a review manifest."""
    lines = [
        "# Revisao de transcricao",
        "",
        f"- Resultado: `{manifest['result_json']}`",
        f"- Referencia textual: `{manifest['text_reference_json']}`",
        f"- Audio: `{manifest['audio_file']}`",
        "",
        "Preencha `reviewed_text` no `manifest.json` ou marque `skip: true` "
        "para silencio ou trecho inutil.",
        "",
    ]
    for index, gap in enumerate(manifest.get("gaps", []), start=1):
        lines.extend(
            [
                f"## Lacuna {index:02d}: {float(gap['start']):.2f}s-{float(gap['end']):.2f}s",
                "",
                f"- Clip: `{gap['clip']}`",
                f"- Duracao: {float(gap['duration_seconds']):.2f}s",
                "",
                "### Texto candidato",
                "",
                str(gap.get("candidate_text", "")).strip() or "_sem texto candidato_",
                "",
                "### Segmentos candidatos",
                "",
            ],
        )
        candidate_segments = gap.get("candidate_segments", [])
        if not candidate_segments:
            lines.extend(["_nenhum segmento candidato_", ""])
        for segment in candidate_segments:
            speaker = segment.get("speaker") or "sem falante"
            suggested_speaker = str(segment.get("suggested_reference_speaker") or "").strip()
            suggestion_suffix = f" -> sugestao {suggested_speaker}" if suggested_speaker else ""
            lines.extend(
                [
                    f"- `{float(segment['start']):.2f}-{float(segment['end']):.2f}` "
                    f"{speaker}{suggestion_suffix}: {segment['text']}",
                ],
            )
        lines.extend(
            [
                "",
                "### Revisao manual",
                "",
                "- reviewed_text:",
                "```text",
                str(gap.get("reviewed_text", "")).strip(),
                "```",
                "- review_note:",
                "```text",
                str(gap.get("review_note", "")).strip(),
                "```",
                "- skip: false",
                "",
            ],
        )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def write_speaker_review_markdown(manifest: dict[str, Any], output_path: Path) -> Path:
    """Write a human-friendly speaker review worksheet for reference gaps."""
    lines = [
        "# Revisao de falantes",
        "",
        f"- Resultado: `{manifest['result_json']}`",
        f"- Referencia de falantes: `{manifest['speaker_reference_json']}`",
        f"- Audio: `{manifest['audio_file']}`",
        "",
        "Preencha `reviewed_speaker` usando o mesmo conjunto de nomes da referencia "
        "ou marque `skip: true` para silencio/trecho inutil.",
        "",
    ]
    speaker_legend = manifest.get("speaker_legend", [])
    if speaker_legend:
        lines.extend(
            [
                "## Legenda de falantes",
                "",
            ],
        )
        for entry in speaker_legend:
            note = str(entry.get("note", "")).strip()
            note_suffix = f" - {note}" if note else ""
            lines.append(
                f"- `{entry['speaker']}`: {float(entry['start']):.2f}-"
                f"{float(entry['end']):.2f}{note_suffix}",
            )
        lines.append("")
    for index, gap in enumerate(manifest.get("gaps", []), start=1):
        lines.extend(
            [
                f"## Lacuna {index:02d}: {float(gap['start']):.2f}s-{float(gap['end']):.2f}s",
                "",
                f"- Clip: `{gap['clip']}`",
                f"- Duracao: {float(gap['duration_seconds']):.2f}s",
                "",
                "### Segmentos candidatos",
                "",
            ],
        )
        candidate_segments = gap.get("candidate_segments", [])
        if not candidate_segments:
            lines.extend(["_nenhum segmento candidato_", ""])
        for segment in candidate_segments:
            speaker = segment.get("speaker") or "sem falante"
            suggested_speaker = str(segment.get("suggested_reference_speaker") or "").strip()
            suggestion_suffix = f" -> sugestao {suggested_speaker}" if suggested_speaker else ""
            lines.extend(
                [
                    f"- `{float(segment['start']):.2f}-{float(segment['end']):.2f}` "
                    f"{speaker}{suggestion_suffix}: {segment['text']}",
                ],
            )
        if candidate_segments:
            lines.extend(["", "### Revisao por segmento candidato", ""])
            for segment_index, segment in enumerate(candidate_segments, start=1):
                lines.extend(
                    [
                        f"#### Segmento {segment_index:02d}: "
                        f"{float(segment['start']):.2f}s-{float(segment['end']):.2f}s",
                        "",
                        "- reviewed_speaker:",
                        "```text",
                        str(segment.get("reviewed_speaker", "")).strip(),
                        "```",
                        "- review_note:",
                        "```text",
                        str(segment.get("review_note", "")).strip(),
                        "```",
                        "- skip: false",
                        "",
                    ],
                )
        lines.extend(
            [
                "",
                "### Revisao manual",
                "",
                "- reviewed_speaker:",
                "```text",
                str(gap.get("reviewed_speaker", "")).strip(),
                "```",
                "- review_note:",
                "```text",
                str(gap.get("review_note", "")).strip(),
                "```",
                "- skip: false",
                "",
            ],
        )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def apply_text_review_manifest(
    manifest_path: Path,
    output_path: Path,
    *,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed gap text to a transcription reference JSON."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    return apply_text_review_data(
        manifest,
        output_path,
        source_name=manifest_path.name,
        allow_pending=allow_pending,
    )


def apply_text_review_markdown(
    markdown_path: Path,
    output_path: Path,
    *,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed gap text from a Markdown review worksheet."""
    manifest = parse_review_markdown(markdown_path)
    return apply_text_review_data(
        manifest,
        output_path,
        source_name=markdown_path.name,
        allow_pending=allow_pending,
    )


def apply_speaker_review_manifest(
    manifest_path: Path,
    output_path: Path,
    *,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed speaker gaps to a speaker reference JSON."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    return apply_speaker_review_data(
        manifest,
        output_path,
        source_name=manifest_path.name,
        allow_pending=allow_pending,
    )


def apply_speaker_review_markdown(
    markdown_path: Path,
    output_path: Path,
    *,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed speakers from a Markdown review worksheet."""
    manifest = parse_speaker_review_markdown(markdown_path)
    return apply_speaker_review_data(
        manifest,
        output_path,
        source_name=markdown_path.name,
        allow_pending=allow_pending,
    )


def apply_text_review_data(
    manifest: dict[str, Any],
    output_path: Path,
    *,
    source_name: str,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed gap text from parsed review data."""
    status = summarize_review_data(manifest)
    if not allow_pending and not status.ready:
        pending = ", ".join(status.pending_ranges)
        raise ValueError(f"Revisao incompleta; lacunas pendentes: {pending}")

    reference_path = Path(str(manifest["text_reference_json"]))
    reference = json.loads(reference_path.read_text(encoding="utf-8-sig"))
    existing_segments = list(reference.get("segments", []))
    added_segments: list[dict[str, Any]] = []
    skipped_gaps = 0

    for gap in manifest.get("gaps", []):
        if bool(gap.get("skip", False)):
            skipped_gaps += 1
            continue
        reviewed_text = str(gap.get("reviewed_text", "")).strip()
        if not reviewed_text:
            skipped_gaps += 1
            continue
        segment = {
            "start": float(gap["start"]),
            "end": float(gap["end"]),
            "text": reviewed_text,
            "note": str(gap.get("review_note") or f"Revisao manual de {source_name}"),
        }
        _validate_no_overlap(segment, existing_segments + added_segments)
        added_segments.append(segment)

    merged_segments = sorted(
        [*existing_segments, *added_segments],
        key=lambda segment: (float(segment["start"]), float(segment["end"])),
    )
    updated_reference = {
        **reference,
        "segments": merged_segments,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(updated_reference, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return AppliedReview(
        output_path=output_path,
        added_segments=len(added_segments),
        skipped_gaps=skipped_gaps,
        total_segments=len(merged_segments),
    )


def apply_speaker_review_data(
    manifest: dict[str, Any],
    output_path: Path,
    *,
    source_name: str,
    allow_pending: bool = False,
) -> AppliedReview:
    """Apply reviewed speaker gaps from parsed review data."""
    status = summarize_speaker_review_data(manifest)
    if not allow_pending and not status.ready:
        pending = ", ".join(status.pending_ranges)
        raise ValueError(f"Revisao de falantes incompleta; lacunas pendentes: {pending}")

    reference_path = Path(str(manifest["speaker_reference_json"]))
    reference = json.loads(reference_path.read_text(encoding="utf-8-sig"))
    existing_segments = list(reference.get("segments", []))
    added_segments: list[dict[str, Any]] = []
    skipped_gaps = 0

    for gap in manifest.get("gaps", []):
        if bool(gap.get("skip", False)):
            skipped_gaps += 1
            continue
        candidate_segments = [
            segment
            for segment in gap.get("candidate_segments", [])
            if str(segment.get("reviewed_speaker", "")).strip()
        ]
        if candidate_segments:
            for reviewed_segment in candidate_segments:
                segment = {
                    "start": float(reviewed_segment["start"]),
                    "end": float(reviewed_segment["end"]),
                    "speaker": str(reviewed_segment["reviewed_speaker"]).strip(),
                    "note": str(
                        reviewed_segment.get("review_note")
                        or gap.get("review_note")
                        or f"Revisao manual de {source_name}"
                    ),
                }
                _validate_no_overlap(segment, existing_segments + added_segments)
                added_segments.append(segment)
            skipped_gaps += len(
                [
                    segment
                    for segment in gap.get("candidate_segments", [])
                    if bool(segment.get("skip", False))
                    and not str(segment.get("reviewed_speaker", "")).strip()
                ]
            )
            continue
        reviewed_speaker = str(gap.get("reviewed_speaker", "")).strip()
        if not reviewed_speaker:
            skipped_gaps += 1
            continue
        segment = {
            "start": float(gap["start"]),
            "end": float(gap["end"]),
            "speaker": reviewed_speaker,
            "note": str(gap.get("review_note") or f"Revisao manual de {source_name}"),
        }
        _validate_no_overlap(segment, existing_segments + added_segments)
        added_segments.append(segment)

    merged_segments = sorted(
        [*existing_segments, *added_segments],
        key=lambda segment: (float(segment["start"]), float(segment["end"])),
    )
    updated_reference = {
        **reference,
        "segments": merged_segments,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(updated_reference, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return AppliedReview(
        output_path=output_path,
        added_segments=len(added_segments),
        skipped_gaps=skipped_gaps,
        total_segments=len(merged_segments),
    )


def summarize_review_data(manifest: dict[str, Any]) -> ReviewStatus:
    """Summarize whether review data is ready to apply."""
    reviewed_gaps = 0
    skipped_gaps = 0
    reviewed_seconds = 0.0
    skipped_seconds = 0.0
    pending_seconds = 0.0
    pending_items: list[PendingReviewItem] = []
    gaps = manifest.get("gaps", [])
    for gap in gaps:
        duration_seconds = _entry_duration_seconds(gap)
        if bool(gap.get("skip", False)):
            skipped_gaps += 1
            skipped_seconds += duration_seconds
            continue
        if str(gap.get("reviewed_text", "")).strip():
            reviewed_gaps += 1
            reviewed_seconds += duration_seconds
            continue
        pending_items.append(_pending_item(gap))
        pending_seconds += duration_seconds
    pending_gaps = len(pending_items)
    return ReviewStatus(
        total_gaps=len(gaps),
        reviewed_gaps=reviewed_gaps,
        skipped_gaps=skipped_gaps,
        pending_gaps=pending_gaps,
        pending_ranges=tuple(item.range_label for item in pending_items),
        ready=pending_gaps == 0,
        pending_items=tuple(pending_items),
        reviewed_seconds=reviewed_seconds,
        skipped_seconds=skipped_seconds,
        pending_seconds=pending_seconds,
    )


def summarize_speaker_review_data(manifest: dict[str, Any]) -> ReviewStatus:
    """Summarize whether speaker review data is ready to apply."""
    reviewed_gaps = 0
    skipped_gaps = 0
    reviewed_seconds = 0.0
    skipped_seconds = 0.0
    pending_seconds = 0.0
    pending_items: list[PendingReviewItem] = []
    gaps = manifest.get("gaps", [])
    for gap in gaps:
        duration_seconds = _entry_duration_seconds(gap)
        if bool(gap.get("skip", False)):
            skipped_gaps += 1
            skipped_seconds += duration_seconds
            continue
        if str(gap.get("reviewed_speaker", "")).strip():
            reviewed_gaps += 1
            reviewed_seconds += duration_seconds
            continue
        candidate_segments = gap.get("candidate_segments", [])
        if candidate_segments:
            pending_segments = [
                segment
                for segment in candidate_segments
                if not bool(segment.get("skip", False))
                and not str(segment.get("reviewed_speaker", "")).strip()
            ]
            if not pending_segments:
                reviewed_gaps += 1
                reviewed_seconds += sum(
                    _entry_duration_seconds(segment)
                    for segment in candidate_segments
                    if str(segment.get("reviewed_speaker", "")).strip()
                )
                skipped_seconds += sum(
                    _entry_duration_seconds(segment)
                    for segment in candidate_segments
                    if bool(segment.get("skip", False))
                    and not str(segment.get("reviewed_speaker", "")).strip()
                )
                continue
            reviewed_seconds += sum(
                _entry_duration_seconds(segment)
                for segment in candidate_segments
                if str(segment.get("reviewed_speaker", "")).strip()
            )
            skipped_seconds += sum(
                _entry_duration_seconds(segment)
                for segment in candidate_segments
                if bool(segment.get("skip", False))
                and not str(segment.get("reviewed_speaker", "")).strip()
            )
            pending_seconds += sum(_entry_duration_seconds(segment) for segment in pending_segments)
            pending_items.extend(_pending_item(segment) for segment in pending_segments)
            continue
        pending_items.append(_pending_item(gap))
        pending_seconds += duration_seconds
    pending_gaps = len(pending_items)
    return ReviewStatus(
        total_gaps=len(gaps),
        reviewed_gaps=reviewed_gaps,
        skipped_gaps=skipped_gaps,
        pending_gaps=pending_gaps,
        pending_ranges=tuple(item.range_label for item in pending_items),
        ready=pending_gaps == 0,
        pending_items=tuple(pending_items),
        reviewed_seconds=reviewed_seconds,
        skipped_seconds=skipped_seconds,
        pending_seconds=pending_seconds,
    )


def build_review_coverage_plan(
    status: ReviewStatus,
    *,
    current_covered_seconds: float,
    duration_seconds: float,
    target_coverage: float,
) -> ReviewCoveragePlan:
    """Plan the largest pending items needed to reach a target coverage."""
    if not 0.0 <= target_coverage <= 1.0:
        raise ValueError(f"target-coverage fora da faixa 0..1: {target_coverage}")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds deve ser maior que zero")

    covered_seconds = current_covered_seconds
    selected_seconds = 0.0
    steps: list[ReviewCoverageStep] = []
    for item in sorted(
        status.pending_items,
        key=lambda pending_item: pending_item.duration_seconds,
        reverse=True,
    ):
        current_coverage = covered_seconds / duration_seconds
        if current_coverage >= target_coverage:
            break
        covered_seconds += item.duration_seconds
        selected_seconds += item.duration_seconds
        steps.append(
            ReviewCoverageStep(
                item=item,
                projected_coverage=min(covered_seconds / duration_seconds, 1.0),
            ),
        )

    return ReviewCoveragePlan(
        current_coverage=min(current_covered_seconds / duration_seconds, 1.0),
        target_coverage=target_coverage,
        selected_seconds=selected_seconds,
        steps=tuple(steps),
        reachable=(covered_seconds / duration_seconds) >= target_coverage,
    )


def parse_review_markdown(markdown_path: Path) -> dict[str, Any]:
    """Parse a Markdown review worksheet into review manifest data."""
    content = markdown_path.read_text(encoding="utf-8-sig")
    reference_match = _REFERENCE_LINE_PATTERN.search(content)
    if reference_match is None:
        raise ValueError("Folha Markdown sem linha de referencia textual.")
    result_match = _RESULT_LINE_PATTERN.search(content)

    gaps: list[dict[str, Any]] = []
    matches = list(_GAP_HEADING_PATTERN.finditer(content))
    for position, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[position + 1].start() if position + 1 < len(matches) else len(content)
        section = content[section_start:section_end]
        review_match = _REVIEW_BLOCK_PATTERN.search(section)
        if review_match is None:
            raise ValueError(f"Lacuna {match.group('index')} sem bloco de revisao valido.")
        gaps.append(
            {
                "start": float(match.group("start")),
                "end": float(match.group("end")),
                "reviewed_text": review_match.group("reviewed_text").strip(),
                "review_note": review_match.group("review_note").strip(),
                "skip": review_match.group("skip") == "true",
            }
        )

    return {
        "result_json": result_match.group("path") if result_match is not None else "",
        "text_reference_json": reference_match.group("path"),
        "gaps": gaps,
    }


def parse_speaker_review_markdown(markdown_path: Path) -> dict[str, Any]:
    """Parse a Markdown speaker review worksheet into review manifest data."""
    content = markdown_path.read_text(encoding="utf-8-sig")
    reference_match = _SPEAKER_REFERENCE_LINE_PATTERN.search(content)
    if reference_match is None:
        raise ValueError("Folha Markdown sem linha de referencia de falantes.")
    result_match = _RESULT_LINE_PATTERN.search(content)

    gaps: list[dict[str, Any]] = []
    matches = list(_GAP_HEADING_PATTERN.finditer(content))
    for position, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[position + 1].start() if position + 1 < len(matches) else len(content)
        section = content[section_start:section_end]
        review_match = _SPEAKER_REVIEW_BLOCK_PATTERN.search(section)
        if review_match is None:
            raise ValueError(f"Lacuna {match.group('index')} sem bloco de revisao valido.")
        gaps.append(
            {
                "start": float(match.group("start")),
                "end": float(match.group("end")),
                "reviewed_speaker": review_match.group("reviewed_speaker").strip(),
                "review_note": review_match.group("review_note").strip(),
                "skip": review_match.group("skip") == "true",
                "candidate_segments": _parse_speaker_segment_reviews(section),
            }
        )

    return {
        "result_json": result_match.group("path") if result_match is not None else "",
        "speaker_reference_json": reference_match.group("path"),
        "gaps": gaps,
    }


def _parse_speaker_segment_reviews(section: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    matches = list(_SPEAKER_SEGMENT_HEADING_PATTERN.finditer(section))
    for position, match in enumerate(matches):
        segment_start = match.end()
        segment_end = matches[position + 1].start() if position + 1 < len(matches) else len(section)
        segment_section = section[segment_start:segment_end]
        review_match = _SPEAKER_SEGMENT_REVIEW_BLOCK_PATTERN.search(segment_section)
        if review_match is None:
            raise ValueError(f"Segmento {match.group('index')} sem bloco de revisao valido.")
        segments.append(
            {
                "start": float(match.group("start")),
                "end": float(match.group("end")),
                "reviewed_speaker": review_match.group("reviewed_speaker").strip(),
                "review_note": review_match.group("review_note").strip(),
                "skip": review_match.group("skip") == "true",
            }
        )
    return segments


def _entry_duration_seconds(entry: dict[str, Any]) -> float:
    return float(entry["end"]) - float(entry["start"])


def _pending_item(entry: dict[str, Any]) -> PendingReviewItem:
    start = float(entry["start"])
    end = float(entry["end"])
    return PendingReviewItem(
        start=start,
        end=end,
        duration_seconds=end - start,
    )


def _validate_no_overlap(
    new_segment: dict[str, Any],
    existing_segments: list[dict[str, Any]],
) -> None:
    new_start = float(new_segment["start"])
    new_end = float(new_segment["end"])
    for existing in existing_segments:
        existing_start = float(existing["start"])
        existing_end = float(existing["end"])
        if max(new_start, existing_start) < min(new_end, existing_end):
            msg = (
                "Trecho revisado sobrepoe referencia existente: "
                f"{new_start:.2f}-{new_end:.2f} com {existing_start:.2f}-{existing_end:.2f}"
            )
            raise ValueError(msg)
