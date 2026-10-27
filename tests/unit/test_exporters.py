from pathlib import Path

from transcrever_app.core.models import TranscriptResult, TranscriptSegment
from transcrever_app.exporters.files import write_txt


def test_write_txt_with_speaker(tmp_path: Path) -> None:
    result = TranscriptResult(
        job_id="job",
        source_file=Path("source.mp4"),
        audio_file=Path("audio.wav"),
        language="pt",
        model_name="large-v3",
        asr_device="cpu",
        asr_compute_type="int8",
        duration_seconds=2.0,
        segments=(
            TranscriptSegment(start=1.2, end=2.0, speaker="Falante 1", text="Olá mundo."),
        ),
        speakers=("Falante 1",),
        mode="diarized",
    )

    output_path = write_txt(result, tmp_path / "transcript.txt")

    assert output_path.read_text(encoding="utf-8") == "[00:00:01] Falante 1: Olá mundo.\n"
