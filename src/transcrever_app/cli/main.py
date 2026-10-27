"""Command line interface for Transcrever App."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from threading import Thread
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from transcrever_app.core.exceptions import TranscreverAppError
from transcrever_app.evaluation.comparison import (
    ReferenceCoverage,
    compare_runs,
    find_reference_gaps,
    measure_reference_coverage,
)
from transcrever_app.evaluation.quality_report import (
    MetricDelta,
    QualityReport,
    build_quality_report,
    compare_quality_reports,
    evaluate_quality_gate,
    evaluate_quality_improvement,
)
from transcrever_app.evaluation.reference_review import (
    ReviewStatus,
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
from transcrever_app.evaluation.speakers import (
    ReferenceSpeakerSegment,
    evaluate_speakers,
    load_predicted_result,
    load_reference,
)
from transcrever_app.evaluation.transcription import (
    evaluate_transcription,
    load_text_reference,
    load_transcript_result,
)
from transcrever_app.media.ffmpeg import extract_audio_clip, inspect_media
from transcrever_app.pipeline import DiarizationMethod, process_media
from transcrever_app.server.backup_service import create_backup, restore_backup
from transcrever_app.server.config import AppSettings
from transcrever_app.server.desktop import run_desktop_app
from transcrever_app.server.instance_lock import InstanceAlreadyRunningError, InstanceLock

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("backup")
def backup_command(destination: Path | None = None) -> None:
    """Create a verified offline backup of the local library."""
    settings = AppSettings()
    lock = InstanceLock(settings.data_dir)
    try:
        lock.acquire()
        backup_path = create_backup(settings, destination)
    except (FileNotFoundError, OSError, ValueError, InstanceAlreadyRunningError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        lock.release()
    console.print(f"[green]Backup criado:[/green] {backup_path}")


@app.command("restore-backup")
def restore_backup_command(backup_path: Path) -> None:
    """Restore an offline backup and preserve the current state for rollback."""
    settings = AppSettings()
    lock = InstanceLock(settings.data_dir)
    try:
        lock.acquire()
        rollback_dir = restore_backup(settings, backup_path)
    except (FileNotFoundError, OSError, ValueError, InstanceAlreadyRunningError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        lock.release()
    console.print(f"[green]Backup restaurado.[/green] Estado anterior: {rollback_dir}")


@app.command()
def web(
    port: int = typer.Option(8765, "--port", min=1024, max=65535, help="Porta local."),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
        help="Abrir o navegador após iniciar.",
    ),
) -> None:
    """Start the complete local web application."""
    import uvicorn

    from transcrever_app.server.app import create_app
    from transcrever_app.server.config import AppSettings

    preferred_url = f"http://127.0.0.1:{port}"
    if _transcrever_is_healthy(preferred_url):
        console.print(f"[bold]Transcrever App já está aberto:[/bold] {preferred_url}")
        if open_browser:
            webbrowser.open(preferred_url)
        return
    available_port = _find_available_port("127.0.0.1", port)
    settings = AppSettings(port=available_port)
    url = f"http://{settings.host}:{settings.port}"
    if open_browser:
        Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    console.print(f"[bold]Transcrever App:[/bold] {url}")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, workers=1)


@app.command()
def desktop(
    port: int = typer.Option(8765, "--port", min=1024, max=65535, help="Porta local."),
) -> None:
    """Start the local application in a dedicated desktop window."""
    from transcrever_app.server.app import create_app

    preferred_url = f"http://127.0.0.1:{port}"
    if _transcrever_is_healthy(preferred_url):
        console.print("[yellow]O Transcrever já está aberto.[/yellow]")
        return
    available_port = _find_available_port("127.0.0.1", port)
    settings = AppSettings(port=available_port)
    try:
        run_desktop_app(create_app(settings), settings, _transcrever_is_healthy)
    except RuntimeError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _transcrever_is_healthy(url: str) -> bool:
    if not url.startswith("http://127.0.0.1:"):
        return False
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL is restricted to loopback above.
            f"{url}/api/v1/system/health",
            timeout=0.5,
        ) as response:
            payload = cast("dict[str, object]", json.loads(response.read().decode("utf-8")))
        success_status = 200
        return response.status == success_status and payload.get("api") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _find_available_port(host: str, preferred_port: int) -> int:
    for candidate in range(preferred_port, min(preferred_port + 20, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise RuntimeError("Não há uma porta local livre próxima da porta solicitada.")


def _open_browser_when_ready(url: str) -> None:
    for _attempt in range(100):
        if _transcrever_is_healthy(url):
            webbrowser.open(url)
            return
        time.sleep(0.1)


@app.command()
def inspect(path: Path) -> None:
    """Inspect an audio or video file and list audio streams."""
    try:
        media = inspect_media(path)
    except TranscreverAppError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Arquivo:[/bold] {media.path}")
    console.print(f"[bold]Formato:[/bold] {media.format_name}")
    console.print(f"[bold]Duração:[/bold] {media.duration_seconds:.2f}s")
    console.print(f"[bold]Tamanho:[/bold] {media.size_bytes / 1024 / 1024:.2f} MB")

    table = Table(title="Trilhas de áudio")
    table.add_column("Relativa")
    table.add_column("Stream")
    table.add_column("Codec")
    table.add_column("Canais")
    table.add_column("Sample rate")
    table.add_column("Título")
    for stream in media.audio_streams:
        table.add_row(
            str(stream.relative_index),
            str(stream.index),
            stream.codec_name,
            str(stream.channels),
            str(stream.sample_rate),
            stream.title or "",
        )
    console.print(table)


@app.command()
def transcribe(
    path: Path,
    audio_stream: int = typer.Option(
        0,
        "--audio-stream",
        "-a",
        help="Índice relativo da trilha de áudio.",
    ),
    language: str = typer.Option("pt", "--language", "-l", help="Idioma esperado no áudio."),
    model: str = typer.Option("large-v3", "--model", "-m", help="Modelo faster-whisper."),
    device: str = typer.Option("auto", "--device", help="Dispositivo: auto, cuda ou cpu."),
    compute_type: str = typer.Option(
        "auto",
        "--compute-type",
        help="Compute type do CTranslate2.",
    ),
    beam_size: int = typer.Option(5, "--beam-size", help="Beam size para priorizar qualidade."),
    vad_filter: bool = typer.Option(
        True,
        "--vad-filter/--no-vad-filter",
        help="Ativar ou desativar o filtro de silêncio do ASR.",
    ),
    condition_on_previous_text: bool = typer.Option(
        True,
        "--condition-on-previous-text/--no-condition-on-previous-text",
        help="Condicionar o ASR no texto anterior.",
    ),
    diarize: bool = typer.Option(False, "--diarize", help="Tentar separar falantes com pyannote."),
    diarization_method: str = typer.Option(
        "auto",
        "--diarization-method",
        help="Método: auto, pyannote ou clustering.",
    ),
    speaker_count: int | None = typer.Option(
        None,
        "--speaker-count",
        help="Número exato de falantes quando conhecido.",
    ),
    min_speakers: int | None = typer.Option(
        None,
        "--min-speakers",
        help="Número mínimo de falantes para pyannote.",
    ),
    max_speakers: int | None = typer.Option(
        None,
        "--max-speakers",
        help="Número máximo de falantes para pyannote ou clustering.",
    ),
    word_timestamps: bool = typer.Option(
        False,
        "--word-timestamps",
        help="Ativar timestamps de palavras do ASR para alinhamento experimental.",
    ),
) -> None:
    """Transcribe an audio or video file."""
    try:
        console.print("[bold]Preparando e transcrevendo arquivo...[/bold]")
        if diarization_method not in {"auto", "pyannote", "clustering"}:
            console.print("[red]Erro:[/red] método de diarização inválido.")
            raise typer.Exit(code=1)
        result, paths = process_media(
            path,
            audio_stream=audio_stream,
            language=language,
            model_name=model,
            device=device,
            compute_type=compute_type,
            beam_size=beam_size,
            vad_filter=vad_filter,
            condition_on_previous_text=condition_on_previous_text,
            diarize=diarize,
            diarization_method=cast("DiarizationMethod", diarization_method),
            speaker_count=speaker_count,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            word_timestamps=word_timestamps,
        )
    except TranscreverAppError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Concluído:[/green] {result.job_id}")
    console.print(f"Modo: {result.mode}")
    console.print(f"ASR: {result.model_name} em {result.asr_device}/{result.asr_compute_type}")
    if result.fallback_reason:
        console.print("[yellow]Fallback:[/yellow] CUDA indisponível; usado CPU/int8.")
    console.print(f"Segmentos: {len(result.segments)}")
    console.print(f"TXT: {paths.transcript_txt}")
    console.print(f"JSON: {paths.result_json}")
    console.print(f"SRT: {paths.transcript_srt}")
    console.print(f"VTT: {paths.transcript_vtt}")


@app.command("evaluate-speakers")
def evaluate_speakers_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json gerado pela pipeline."),
    ],
    reference_json: Annotated[
        Path,
        typer.Argument(help="Arquivo JSON com referência manual."),
    ],
    collar_seconds: float = typer.Option(
        0.0,
        "--collar-seconds",
        help="Segundos ignorados em cada borda dos trechos de referência.",
    ),
) -> None:
    """Evaluate speaker labels against a manual reference."""
    predicted = load_predicted_result(result_json)
    reference = load_reference(reference_json)
    evaluation = evaluate_speakers(predicted, reference, collar_seconds=collar_seconds)

    console.print(f"Acurácia temporal: {evaluation.accuracy:.2%}")
    console.print(f"Segundos corretos: {evaluation.matched_seconds:.2f}")
    console.print(f"Segundos de referência: {evaluation.reference_seconds:.2f}")
    console.print(f"Collar: {collar_seconds:.2f}s")

    table = Table(title="Mapeamento ótimo")
    table.add_column("Previsto")
    table.add_column("Referência")
    for predicted_speaker, reference_speaker in sorted(evaluation.mapping.items()):
        table.add_row(predicted_speaker, reference_speaker)
    console.print(table)

    segment_table = Table(title="Acurácia por trecho")
    segment_table.add_column("Início")
    segment_table.add_column("Fim")
    segment_table.add_column("Ref")
    segment_table.add_column("Acurácia")
    segment_table.add_column("Nota")
    for segment in evaluation.segments:
        segment_table.add_row(
            f"{segment.start:.2f}",
            f"{segment.end:.2f}",
            segment.speaker,
            f"{segment.accuracy:.2%}",
            segment.note,
        )
    console.print(segment_table)


@app.command("evaluate-transcription")
def evaluate_transcription_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json gerado pela pipeline."),
    ],
    reference_json: Annotated[
        Path,
        typer.Argument(help="Arquivo JSON com referência textual manual."),
    ],
) -> None:
    """Evaluate transcript text against a manual reference."""
    predicted = load_transcript_result(result_json)
    reference = load_text_reference(reference_json)
    evaluation = evaluate_transcription(predicted, reference)

    console.print(f"WER: {evaluation.wer:.2%}")
    console.print(f"Erros: {evaluation.edit_distance}")
    console.print(f"Palavras de referência: {evaluation.word_count}")

    table = Table(title="WER por trecho")
    table.add_column("Início")
    table.add_column("Fim")
    table.add_column("WER")
    table.add_column("Erros")
    for segment in evaluation.segments:
        table.add_row(
            f"{segment.start:.2f}",
            f"{segment.end:.2f}",
            f"{segment.wer:.2%}",
            str(segment.edit_distance),
        )
    console.print(table)


@app.command("compare-runs")
def compare_runs_command(
    baseline_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json base."),
    ],
    candidate_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json candidato."),
    ],
) -> None:
    """Compare two runs to distinguish quality changes from segmentation changes."""
    baseline = load_predicted_result(baseline_json)
    candidate = load_predicted_result(candidate_json)
    comparison = compare_runs(baseline, candidate)

    console.print(f"Segmentos base: {comparison.baseline_segments}")
    console.print(f"Segmentos candidato: {comparison.candidate_segments}")
    console.print(f"Palavras base: {comparison.baseline_words}")
    console.print(f"Palavras candidato: {comparison.candidate_words}")
    console.print(f"Distância textual: {comparison.text_edit_distance}")
    console.print(f"Taxa de mudança textual: {comparison.text_change_rate:.2%}")
    speaker_agreement = (
        f"{comparison.speaker_agreement:.2%}"
        if comparison.speaker_agreement is not None
        else "não aplicável"
    )
    console.print(f"Concordância temporal de falantes: {speaker_agreement}")
    console.print(
        f"Só segmentação mudou: {'sim' if comparison.only_segmentation_changed else 'não'}",
    )


@app.command("reference-coverage")
def reference_coverage_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json usado para obter a duração da mídia."),
    ],
    speaker_reference_json: Annotated[
        Path | None,
        typer.Option("--speaker-reference", help="Referência manual de falantes."),
    ] = None,
    text_reference_json: Annotated[
        Path | None,
        typer.Option("--text-reference", help="Referência manual de transcrição."),
    ] = None,
) -> None:
    """Show how much of the media has reviewed reference coverage."""
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    console.print(f"Duração: {duration_seconds:.2f}s")

    if speaker_reference_json is not None:
        speaker_reference = load_reference(speaker_reference_json)
        speaker_intervals = tuple((segment.start, segment.end) for segment in speaker_reference)
        speaker_coverage = measure_reference_coverage(speaker_intervals, duration_seconds)
        console.print(
            "Cobertura de falantes: "
            f"{speaker_coverage.covered_seconds:.2f}s "
            f"({speaker_coverage.coverage:.2%})",
        )

    if text_reference_json is not None:
        text_reference = load_text_reference(text_reference_json)
        text_intervals = tuple((segment.start, segment.end) for segment in text_reference)
        text_coverage = measure_reference_coverage(text_intervals, duration_seconds)
        console.print(
            "Cobertura de transcrição: "
            f"{text_coverage.covered_seconds:.2f}s "
            f"({text_coverage.coverage:.2%})",
        )


@app.command("quality-report")
def quality_report_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json gerado pela pipeline."),
    ],
    text_reference_json: Annotated[
        Path | None,
        typer.Option("--text-reference", help="Referência manual de transcrição."),
    ] = None,
    speaker_reference_json: Annotated[
        Path | None,
        typer.Option("--speaker-reference", help="Referência manual de falantes."),
    ] = None,
    speaker_collar_seconds: float = typer.Option(
        0.0,
        "--speaker-collar-seconds",
        help="Segundos ignorados em cada borda dos trechos de falante.",
    ),
    min_text_coverage: float | None = typer.Option(
        None,
        "--min-text-coverage",
        help="Cobertura textual mínima exigida, de 0 a 1.",
    ),
    max_wer: float | None = typer.Option(
        None,
        "--max-wer",
        help="WER máximo aceito, de 0 a 1.",
    ),
    min_speaker_coverage: float | None = typer.Option(
        None,
        "--min-speaker-coverage",
        help="Cobertura mínima de falantes exigida, de 0 a 1.",
    ),
    min_speaker_accuracy: float | None = typer.Option(
        None,
        "--min-speaker-accuracy",
        help="Acurácia mínima de falantes exigida, de 0 a 1.",
    ),
) -> None:
    """Show combined coverage, WER and speaker accuracy for a run."""
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    predicted = load_predicted_result(result_json)
    text_reference = (
        load_text_reference(text_reference_json) if text_reference_json is not None else None
    )
    speaker_reference = (
        load_reference(speaker_reference_json) if speaker_reference_json is not None else None
    )
    report = build_quality_report(
        predicted=predicted,
        duration_seconds=duration_seconds,
        text_reference=text_reference,
        speaker_reference=speaker_reference,
        speaker_collar_seconds=speaker_collar_seconds,
    )

    console.print(f"Duração: {report.duration_seconds:.2f}s")
    if report.text_coverage is not None and report.transcription is not None:
        console.print(
            "Transcrição: "
            f"cobertura {report.text_coverage.covered_seconds:.2f}s "
            f"({report.text_coverage.coverage:.2%}), "
            f"WER {report.transcription.wer:.2%}, "
            f"erros {report.transcription.edit_distance}, "
            f"palavras {report.transcription.word_count}",
        )
    if report.speaker_coverage is not None and report.speakers is not None:
        console.print(
            "Falantes: "
            f"cobertura {report.speaker_coverage.covered_seconds:.2f}s "
            f"({report.speaker_coverage.coverage:.2%}), "
            f"acurácia {report.speakers.accuracy:.2%}, "
            f"collar {speaker_collar_seconds:.2f}s",
        )
    gate = evaluate_quality_gate(
        report,
        min_text_coverage=min_text_coverage,
        max_wer=max_wer,
        min_speaker_coverage=min_speaker_coverage,
        min_speaker_accuracy=min_speaker_accuracy,
    )
    if not gate.configured:
        console.print("Gate: NOT CONFIGURED")
        return
    if gate.passed:
        console.print("Gate: PASS")
        return

    console.print("[red]Gate: FAIL[/red]")
    for failure in gate.failures:
        console.print(f"- {failure}")
    raise typer.Exit(code=1)


@app.command("quality-compare")
def quality_compare_command(
    baseline_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json base."),
    ],
    candidate_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json candidato."),
    ],
    text_reference_json: Annotated[
        Path | None,
        typer.Option("--text-reference", help="Referência manual de transcrição."),
    ] = None,
    speaker_reference_json: Annotated[
        Path | None,
        typer.Option("--speaker-reference", help="Referência manual de falantes."),
    ] = None,
    speaker_collar_seconds: float = typer.Option(
        0.0,
        "--speaker-collar-seconds",
        help="Segundos ignorados em cada borda dos trechos de falante.",
    ),
    min_text_coverage: float | None = typer.Option(
        None,
        "--min-text-coverage",
        help="Cobertura textual mínima exigida para aceitar melhoria real.",
    ),
    min_speaker_coverage: float | None = typer.Option(
        None,
        "--min-speaker-coverage",
        help="Cobertura mínima de falantes exigida para aceitar melhoria real.",
    ),
    require_improvement: bool = typer.Option(
        False,
        "--require-improvement",
        help="Falhar com exit code 1 quando a melhoria real não for comprovada.",
    ),
) -> None:
    """Compare quality metrics for two runs using the same references."""
    baseline_report = _build_quality_report_from_files(
        baseline_json,
        text_reference_json=text_reference_json,
        speaker_reference_json=speaker_reference_json,
        speaker_collar_seconds=speaker_collar_seconds,
    )
    candidate_report = _build_quality_report_from_files(
        candidate_json,
        text_reference_json=text_reference_json,
        speaker_reference_json=speaker_reference_json,
        speaker_collar_seconds=speaker_collar_seconds,
    )
    comparison = compare_quality_reports(baseline_report, candidate_report)

    table = Table(title="Comparativo de qualidade")
    table.add_column("Métrica")
    table.add_column("Base")
    table.add_column("Candidato")
    table.add_column("Delta")
    table.add_column("Status")
    rows = (
        ("Cobertura textual", comparison.text_coverage, True),
        ("WER", comparison.wer, False),
        ("Cobertura falantes", comparison.speaker_coverage, True),
        ("Acurácia falantes", comparison.speaker_accuracy, True),
    )
    for label, delta, higher_is_better in rows:
        table.add_row(
            label,
            _format_optional_percent(delta.baseline),
            _format_optional_percent(delta.candidate),
            _format_delta_percent(delta.delta),
            _metric_status(delta, higher_is_better=higher_is_better),
        )
    console.print(table)

    gate = evaluate_quality_improvement(
        comparison,
        min_text_coverage=min_text_coverage,
        min_speaker_coverage=min_speaker_coverage,
    )
    if gate.proven:
        console.print("Melhoria real: sim")
        return
    console.print("Melhoria real: não comprovada")
    if gate.evidence_failures:
        console.print("Evidência insuficiente:")
        for failure in gate.evidence_failures:
            console.print(f"- {failure}")
    if gate.regressed_metrics:
        console.print("Regressões:")
        for metric in gate.regressed_metrics:
            console.print(f"- {metric}")
    if require_improvement:
        raise typer.Exit(code=1)


def _build_quality_report_from_files(
    result_json: Path,
    *,
    text_reference_json: Path | None,
    speaker_reference_json: Path | None,
    speaker_collar_seconds: float,
) -> QualityReport:
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    predicted = load_predicted_result(result_json)
    text_reference = (
        load_text_reference(text_reference_json) if text_reference_json is not None else None
    )
    speaker_reference = (
        load_reference(speaker_reference_json) if speaker_reference_json is not None else None
    )
    return build_quality_report(
        predicted=predicted,
        duration_seconds=duration_seconds,
        text_reference=text_reference,
        speaker_reference=speaker_reference,
        speaker_collar_seconds=speaker_collar_seconds,
    )


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "indisponível"
    return f"{value:.2%}"


def _format_delta_percent(value: float | None) -> str:
    if value is None:
        return "indisponível"
    return f"{value:+.2%}"


def _metric_status(delta: MetricDelta, *, higher_is_better: bool) -> str:
    if delta.delta is None:
        return "indisponível"
    if delta.delta == 0:
        return "igual"
    if delta.improved:
        return "melhorou"
    direction = "maior" if higher_is_better else "menor"
    return f"piorou; {direction} seria melhor"


def _build_speaker_legend(
    reference: tuple[ReferenceSpeakerSegment, ...],
) -> list[dict[str, object]]:
    legend: list[dict[str, object]] = []
    seen: set[str] = set()
    for segment in reference:
        if segment.speaker in seen:
            continue
        seen.add(segment.speaker)
        legend.append(
            {
                "speaker": segment.speaker,
                "start": segment.start,
                "end": segment.end,
                "note": segment.note,
            }
        )
    return legend


@app.command("prepare-reference-review")
def prepare_reference_review_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json usado como candidato de revisão."),
    ],
    text_reference_json: Annotated[
        Path,
        typer.Argument(help="Referência manual de transcrição existente."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Diretório onde os clipes e o manifesto serão gerados.",
        ),
    ] = Path("evaluation/review"),
    min_gap_seconds: Annotated[
        float,
        typer.Option(
            "--min-gap-seconds",
            help="Menor lacuna exportada para revisão.",
        ),
    ] = 1.0,
) -> None:
    """Prepare audio clips for manual review of unreferenced transcript gaps."""
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    audio_path = Path(str(payload["audio_file"]))
    if not audio_path.is_absolute():
        audio_path = Path.cwd() / audio_path
    if not audio_path.exists():
        source_path = Path(str(payload["source_file"]))
        audio_path = source_path if source_path.exists() else audio_path

    predicted = load_transcript_result(result_json)
    text_reference = load_text_reference(text_reference_json)
    intervals = tuple((segment.start, segment.end) for segment in text_reference)
    gaps = find_reference_gaps(
        intervals,
        duration_seconds,
        min_gap_seconds=min_gap_seconds,
    )

    job_dir = output_dir / str(payload["job_id"])
    clips_dir = job_dir / "clips"
    manifest_entries = []
    for index, gap in enumerate(gaps, start=1):
        clip_path = clips_dir / f"gap-{index:02d}-{gap.start:.2f}-{gap.end:.2f}.wav"
        extract_audio_clip(
            source_path=audio_path,
            output_path=clip_path,
            start_seconds=gap.start,
            end_seconds=gap.end,
        )
        candidate_segments = [
            segment
            for segment in predicted
            if gap.start <= ((segment.start + segment.end) / 2) <= gap.end
        ]
        manifest_entries.append(
            {
                "clip": str(clip_path),
                "start": gap.start,
                "end": gap.end,
                "duration_seconds": gap.duration_seconds,
                "candidate_text": " ".join(segment.text for segment in candidate_segments),
                "reviewed_text": "",
                "review_note": "",
                "skip": False,
                "candidate_segments": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "speaker": segment.speaker,
                        "text": segment.text,
                    }
                    for segment in candidate_segments
                ],
            }
        )

    manifest_path = job_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "result_json": str(result_json),
        "text_reference_json": str(text_reference_json),
        "audio_file": str(audio_path),
        "duration_seconds": duration_seconds,
        "min_gap_seconds": min_gap_seconds,
        "gaps": manifest_entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review_markdown_path = write_review_markdown(manifest, job_dir / "review.md")

    console.print(f"Lacunas exportadas: {len(gaps)}")
    console.print(f"Manifesto: {manifest_path}")
    console.print(f"Folha de revisão: {review_markdown_path}")
    console.print(f"Clipes: {clips_dir}")


@app.command("prepare-speaker-reference-review")
def prepare_speaker_reference_review_command(
    result_json: Annotated[
        Path,
        typer.Argument(help="Arquivo result.json usado como candidato de revisão."),
    ],
    speaker_reference_json: Annotated[
        Path,
        typer.Argument(help="Referência manual de falantes existente."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Diretório onde os clipes e o manifesto serão gerados.",
        ),
    ] = Path("evaluation/review"),
    min_gap_seconds: Annotated[
        float,
        typer.Option(
            "--min-gap-seconds",
            help="Menor lacuna exportada para revisão.",
        ),
    ] = 1.0,
) -> None:
    """Prepare audio clips for manual review of unreferenced speaker gaps."""
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    audio_path = Path(str(payload["audio_file"]))
    if not audio_path.is_absolute():
        audio_path = Path.cwd() / audio_path
    if not audio_path.exists():
        source_path = Path(str(payload["source_file"]))
        audio_path = source_path if source_path.exists() else audio_path

    predicted = load_predicted_result(result_json)
    speaker_reference = load_reference(speaker_reference_json)
    speaker_evaluation = evaluate_speakers(predicted, speaker_reference)
    speaker_mapping = speaker_evaluation.mapping
    speaker_legend = _build_speaker_legend(speaker_reference)
    intervals = tuple((segment.start, segment.end) for segment in speaker_reference)
    gaps = find_reference_gaps(
        intervals,
        duration_seconds,
        min_gap_seconds=min_gap_seconds,
    )

    job_dir = output_dir / f"{payload['job_id']}-speakers"
    clips_dir = job_dir / "clips"
    manifest_entries = []
    for index, gap in enumerate(gaps, start=1):
        clip_path = clips_dir / f"speaker-gap-{index:02d}-{gap.start:.2f}-{gap.end:.2f}.wav"
        extract_audio_clip(
            source_path=audio_path,
            output_path=clip_path,
            start_seconds=gap.start,
            end_seconds=gap.end,
        )
        candidate_segments = [
            segment
            for segment in predicted
            if gap.start <= ((segment.start + segment.end) / 2) <= gap.end
        ]
        manifest_entries.append(
            {
                "clip": str(clip_path),
                "start": gap.start,
                "end": gap.end,
                "duration_seconds": gap.duration_seconds,
                "reviewed_speaker": "",
                "review_note": "",
                "skip": False,
                "candidate_segments": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "speaker": segment.speaker,
                        "suggested_reference_speaker": (
                            speaker_mapping.get(segment.speaker)
                            if segment.speaker is not None
                            else None
                        ),
                        "text": segment.text,
                    }
                    for segment in candidate_segments
                ],
            }
        )

    manifest_path = job_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "result_json": str(result_json),
        "speaker_reference_json": str(speaker_reference_json),
        "audio_file": str(audio_path),
        "duration_seconds": duration_seconds,
        "min_gap_seconds": min_gap_seconds,
        "speaker_mapping": speaker_mapping,
        "speaker_legend": speaker_legend,
        "gaps": manifest_entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review_markdown_path = write_speaker_review_markdown(manifest, job_dir / "review.md")

    console.print(f"Lacunas de falantes exportadas: {len(gaps)}")
    console.print(f"Manifesto: {manifest_path}")
    console.print(f"Folha de revisão: {review_markdown_path}")
    console.print(f"Clipes: {clips_dir}")


@app.command("apply-reference-review")
def apply_reference_review_command(
    review_file: Annotated[
        Path,
        typer.Argument(
            help="Manifesto JSON ou folha Markdown gerada por prepare-reference-review.",
        ),
    ],
    output_json: Annotated[
        Path,
        typer.Option("--output", help="Arquivo de referência textual atualizado."),
    ],
    allow_pending: bool = typer.Option(
        False,
        "--allow-pending",
        help="Permitir aplicar mesmo com lacunas vazias pendentes.",
    ),
) -> None:
    """Apply reviewed text from a JSON manifest or Markdown worksheet."""
    try:
        if review_file.suffix.casefold() == ".md":
            result = apply_text_review_markdown(
                review_file,
                output_json,
                allow_pending=allow_pending,
            )
        else:
            result = apply_text_review_manifest(
                review_file,
                output_json,
                allow_pending=allow_pending,
            )
    except ValueError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Referência atualizada: {result.output_path}")
    console.print(f"Trechos adicionados: {result.added_segments}")
    console.print(f"Lacunas ignoradas: {result.skipped_gaps}")
    console.print(f"Total de trechos: {result.total_segments}")


@app.command("apply-speaker-reference-review")
def apply_speaker_reference_review_command(
    review_file: Annotated[
        Path,
        typer.Argument(
            help="Manifesto JSON ou folha Markdown gerada por prepare-speaker-reference-review.",
        ),
    ],
    output_json: Annotated[
        Path,
        typer.Option("--output", help="Arquivo de referência de falantes atualizado."),
    ],
    allow_pending: bool = typer.Option(
        False,
        "--allow-pending",
        help="Permitir aplicar mesmo com lacunas vazias pendentes.",
    ),
) -> None:
    """Apply reviewed speaker gaps from a JSON manifest or Markdown worksheet."""
    try:
        if review_file.suffix.casefold() == ".md":
            result = apply_speaker_review_markdown(
                review_file,
                output_json,
                allow_pending=allow_pending,
            )
        else:
            result = apply_speaker_review_manifest(
                review_file,
                output_json,
                allow_pending=allow_pending,
            )
    except ValueError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Referência de falantes atualizada: {result.output_path}")
    console.print(f"Trechos adicionados: {result.added_segments}")
    console.print(f"Lacunas ignoradas: {result.skipped_gaps}")
    console.print(f"Total de trechos: {result.total_segments}")


@app.command("review-status")
def review_status_command(
    review_file: Annotated[
        Path,
        typer.Argument(help="Manifesto JSON ou folha Markdown de revisão."),
    ],
    require_ready: bool = typer.Option(
        False,
        "--require-ready",
        help="Falhar com exit code 1 quando houver lacunas pendentes.",
    ),
    prioritize: bool = typer.Option(
        False,
        "--prioritize",
        help="Listar pendências por maior duração primeiro.",
    ),
    target_coverage: float | None = typer.Option(
        None,
        "--target-coverage",
        help="Mostrar quais lacunas revisar para atingir esta cobertura.",
    ),
    require_target_coverage: bool = typer.Option(
        False,
        "--require-target-coverage",
        help="Falhar com exit code 1 quando a cobertura alvo não for atingível.",
    ),
) -> None:
    """Show whether a review file is ready to apply."""
    try:
        if review_file.suffix.casefold() == ".md":
            manifest = parse_review_markdown(review_file)
        else:
            manifest = json.loads(review_file.read_text(encoding="utf-8-sig"))
        status = summarize_review_data(manifest)
    except ValueError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Lacunas totais: {status.total_gaps}")
    console.print(f"Revisadas: {status.reviewed_gaps}")
    console.print(f"Ignoradas: {status.skipped_gaps}")
    console.print(f"Pendentes: {status.pending_gaps}")
    console.print(f"Segundos revisados: {status.reviewed_seconds:.2f}s")
    console.print(f"Segundos ignorados: {status.skipped_seconds:.2f}s")
    console.print(f"Segundos pendentes: {status.pending_seconds:.2f}s")
    _print_pending_review_items(status, prioritize=prioritize)
    if require_target_coverage and target_coverage is None:
        console.print("[red]Erro:[/red] --require-target-coverage exige --target-coverage.")
        raise typer.Exit(code=1)
    target_reachable = True
    if target_coverage is not None:
        try:
            target_reachable = _print_review_coverage_plan(
                manifest,
                status,
                target_coverage=target_coverage,
                reference_kind="text",
            )
        except ValueError as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            raise typer.Exit(code=1) from exc
    console.print(f"Pronto para aplicar: {'sim' if status.ready else 'não'}")
    if require_target_coverage and not target_reachable:
        raise typer.Exit(code=1)
    if require_ready and not status.ready:
        raise typer.Exit(code=1)


@app.command("speaker-review-status")
def speaker_review_status_command(
    review_file: Annotated[
        Path,
        typer.Argument(help="Manifesto JSON ou folha Markdown de revisão de falantes."),
    ],
    require_ready: bool = typer.Option(
        False,
        "--require-ready",
        help="Falhar com exit code 1 quando houver lacunas pendentes.",
    ),
    prioritize: bool = typer.Option(
        False,
        "--prioritize",
        help="Listar pendências por maior duração primeiro.",
    ),
    target_coverage: float | None = typer.Option(
        None,
        "--target-coverage",
        help="Mostrar quais lacunas revisar para atingir esta cobertura.",
    ),
    require_target_coverage: bool = typer.Option(
        False,
        "--require-target-coverage",
        help="Falhar com exit code 1 quando a cobertura alvo não for atingível.",
    ),
) -> None:
    """Show whether a speaker review file is ready to apply."""
    try:
        if review_file.suffix.casefold() == ".md":
            manifest = parse_speaker_review_markdown(review_file)
        else:
            manifest = json.loads(review_file.read_text(encoding="utf-8-sig"))
        status = summarize_speaker_review_data(manifest)
    except ValueError as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Lacunas totais: {status.total_gaps}")
    console.print(f"Revisadas: {status.reviewed_gaps}")
    console.print(f"Ignoradas: {status.skipped_gaps}")
    console.print(f"Pendentes: {status.pending_gaps}")
    console.print(f"Segundos revisados: {status.reviewed_seconds:.2f}s")
    console.print(f"Segundos ignorados: {status.skipped_seconds:.2f}s")
    console.print(f"Segundos pendentes: {status.pending_seconds:.2f}s")
    _print_pending_review_items(status, prioritize=prioritize)
    if require_target_coverage and target_coverage is None:
        console.print("[red]Erro:[/red] --require-target-coverage exige --target-coverage.")
        raise typer.Exit(code=1)
    target_reachable = True
    if target_coverage is not None:
        try:
            target_reachable = _print_review_coverage_plan(
                manifest,
                status,
                target_coverage=target_coverage,
                reference_kind="speaker",
            )
        except ValueError as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            raise typer.Exit(code=1) from exc
    console.print(f"Pronto para aplicar: {'sim' if status.ready else 'não'}")
    if require_target_coverage and not target_reachable:
        raise typer.Exit(code=1)
    if require_ready and not status.ready:
        raise typer.Exit(code=1)


@app.command("review-diagnostics")
def review_diagnostics_command(
    text_review_file: Annotated[
        Path | None,
        typer.Option("--text-review", help="Folha Markdown ou manifesto de revisão textual."),
    ] = None,
    speaker_review_file: Annotated[
        Path | None,
        typer.Option(
            "--speaker-review",
            help="Folha Markdown ou manifesto de revisão de falantes.",
        ),
    ] = None,
    text_target_coverage: float | None = typer.Option(
        None,
        "--text-target-coverage",
        help="Cobertura textual alvo para planejar revisão.",
    ),
    speaker_target_coverage: float | None = typer.Option(
        None,
        "--speaker-target-coverage",
        help="Cobertura de falantes alvo para planejar revisão.",
    ),
    require_targets: bool = typer.Option(
        False,
        "--require-targets",
        help="Falhar com exit code 1 quando alguma meta configurada não for atingível.",
    ),
) -> None:
    """Show one consolidated diagnostic for pending review work."""
    if text_review_file is None and speaker_review_file is None:
        console.print("[red]Erro:[/red] informe --text-review, --speaker-review ou ambos.")
        raise typer.Exit(code=1)
    if require_targets and text_target_coverage is None and speaker_target_coverage is None:
        console.print("[red]Erro:[/red] --require-targets exige pelo menos uma meta de cobertura.")
        raise typer.Exit(code=1)

    targets_reachable = True
    if text_review_file is not None:
        console.print("[bold]Transcrição[/bold]")
        try:
            manifest, status = _load_text_review_status(text_review_file)
            _print_review_status_summary(status)
            _print_pending_review_items(status, prioritize=True)
            if text_target_coverage is not None:
                targets_reachable = (
                    _print_review_coverage_plan(
                        manifest,
                        status,
                        target_coverage=text_target_coverage,
                        reference_kind="text",
                    )
                    and targets_reachable
                )
        except ValueError as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if speaker_review_file is not None:
        console.print("[bold]Falantes[/bold]")
        try:
            manifest, status = _load_speaker_review_status(speaker_review_file)
            _print_review_status_summary(status)
            _print_pending_review_items(status, prioritize=True)
            if speaker_target_coverage is not None:
                targets_reachable = (
                    _print_review_coverage_plan(
                        manifest,
                        status,
                        target_coverage=speaker_target_coverage,
                        reference_kind="speaker",
                    )
                    and targets_reachable
                )
        except ValueError as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if require_targets and not targets_reachable:
        raise typer.Exit(code=1)


def _load_text_review_status(review_file: Path) -> tuple[dict[str, object], ReviewStatus]:
    if review_file.suffix.casefold() == ".md":
        manifest = parse_review_markdown(review_file)
    else:
        manifest = json.loads(review_file.read_text(encoding="utf-8-sig"))
    return manifest, summarize_review_data(manifest)


def _load_speaker_review_status(review_file: Path) -> tuple[dict[str, object], ReviewStatus]:
    if review_file.suffix.casefold() == ".md":
        manifest = parse_speaker_review_markdown(review_file)
    else:
        manifest = json.loads(review_file.read_text(encoding="utf-8-sig"))
    return manifest, summarize_speaker_review_data(manifest)


def _print_review_status_summary(status: ReviewStatus) -> None:
    console.print(f"Lacunas totais: {status.total_gaps}")
    console.print(f"Revisadas: {status.reviewed_gaps}")
    console.print(f"Ignoradas: {status.skipped_gaps}")
    console.print(f"Pendentes: {status.pending_gaps}")
    console.print(f"Segundos revisados: {status.reviewed_seconds:.2f}s")
    console.print(f"Segundos ignorados: {status.skipped_seconds:.2f}s")
    console.print(f"Segundos pendentes: {status.pending_seconds:.2f}s")
    console.print(f"Pronto para aplicar: {'sim' if status.ready else 'não'}")


def _print_pending_review_items(status: ReviewStatus, *, prioritize: bool) -> None:
    if not status.pending_items:
        return
    pending_items = status.pending_items
    if prioritize:
        pending_items = tuple(
            sorted(
                pending_items,
                key=lambda item: item.duration_seconds,
                reverse=True,
            ),
        )
    console.print("Pendências:")
    for item in pending_items:
        console.print(f"- {item.range_label} ({item.duration_seconds:.2f}s)")


def _print_review_coverage_plan(
    manifest: dict[str, object],
    status: ReviewStatus,
    *,
    target_coverage: float,
    reference_kind: str,
) -> bool:
    coverage = _review_manifest_coverage(manifest, reference_kind=reference_kind)
    plan = build_review_coverage_plan(
        status,
        current_covered_seconds=coverage.covered_seconds,
        duration_seconds=coverage.duration_seconds,
        target_coverage=target_coverage,
    )
    console.print(
        f"Plano de cobertura: atual {plan.current_coverage:.2%}, alvo {plan.target_coverage:.2%}",
    )
    if not plan.steps:
        console.print("Meta já atingida." if plan.reachable else "Meta não atingível.")
        return plan.reachable
    for step in plan.steps:
        console.print(
            f"- revisar {step.item.range_label} ({step.item.duration_seconds:.2f}s) "
            f"-> {step.projected_coverage:.2%}",
        )
    if not plan.reachable:
        console.print("Meta não atingível com as lacunas pendentes listadas.")
    return plan.reachable


def _review_manifest_coverage(
    manifest: dict[str, object],
    *,
    reference_kind: str,
) -> ReferenceCoverage:
    result_value = str(manifest.get("result_json") or "")
    if not result_value:
        message = "Folha de revisão sem result_json para calcular cobertura."
        raise ValueError(message)
    result_json = Path(result_value)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    duration_seconds = float(payload["duration_seconds"])
    if reference_kind == "text":
        reference_path = Path(str(manifest["text_reference_json"]))
        text_reference = load_text_reference(reference_path)
        intervals = tuple((segment.start, segment.end) for segment in text_reference)
        return measure_reference_coverage(intervals, duration_seconds)
    reference_path = Path(str(manifest["speaker_reference_json"]))
    speaker_reference = load_reference(reference_path)
    intervals = tuple((segment.start, segment.end) for segment in speaker_reference)
    return measure_reference_coverage(intervals, duration_seconds)
