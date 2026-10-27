from pathlib import Path

import pytest

from transcrever_app.core.exceptions import DiarizationError
from transcrever_app.core.models import (
    AudioStream,
    MediaInfo,
    SpeakerSegment,
    TranscriptionOutput,
    TranscriptionSegment,
)
from transcrever_app.jobs.manager import JobPaths
from transcrever_app.media.ffmpeg import AudioStreamLevel
from transcrever_app.pipeline import _diarize, process_media


def test_clustering_receives_max_speakers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, int | None]] = []

    def fake_cluster(
        _audio_path: Path,
        _transcriptions: tuple[TranscriptionSegment, ...],
        *,
        speaker_count: int | None = None,
        max_speakers: int = 8,
    ) -> tuple[SpeakerSegment, ...]:
        calls.append({"speaker_count": speaker_count, "max_speakers": max_speakers})
        return (SpeakerSegment(start=0.0, end=1.0, speaker="Falante 1"),)

    monkeypatch.setattr("transcrever_app.pipeline.cluster_transcription_speakers", fake_cluster)

    result = _diarize(
        audio_path=Path("audio.wav"),
        transcriptions=(TranscriptionSegment(start=0.0, end=1.0, text="hello"),),
        method="clustering",
        speaker_count=None,
        min_speakers=None,
        max_speakers=3,
    )

    assert result == (SpeakerSegment(start=0.0, end=1.0, speaker="Falante 1"),)
    assert calls == [{"speaker_count": None, "max_speakers": 3}]


def test_auto_fallback_clustering_receives_max_speakers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, int | None]] = []

    def fake_diarize(
        _audio_path: Path,
        *,
        speaker_count: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> tuple[SpeakerSegment, ...]:
        _ = (speaker_count, min_speakers, max_speakers)
        raise DiarizationError("pyannote unavailable")

    def fake_cluster(
        _audio_path: Path,
        _transcriptions: tuple[TranscriptionSegment, ...],
        *,
        speaker_count: int | None = None,
        max_speakers: int = 8,
    ) -> tuple[SpeakerSegment, ...]:
        calls.append({"speaker_count": speaker_count, "max_speakers": max_speakers})
        return (SpeakerSegment(start=0.0, end=1.0, speaker="Falante 1"),)

    monkeypatch.setattr("transcrever_app.pipeline.diarize_audio", fake_diarize)
    monkeypatch.setattr("transcrever_app.pipeline.cluster_transcription_speakers", fake_cluster)

    _diarize(
        audio_path=Path("audio.wav"),
        transcriptions=(TranscriptionSegment(start=0.0, end=1.0, text="hello"),),
        method="auto",
        speaker_count=None,
        min_speakers=None,
        max_speakers=4,
    )

    assert calls == [{"speaker_count": None, "max_speakers": 4}]


def test_process_media_passes_vad_filter_to_asr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, bool]] = []
    source_path = tmp_path / "sample.wav"
    source_path.write_bytes(b"media")
    job_paths = JobPaths(
        job_id="job",
        root=tmp_path / "runs" / "job",
        audio_dir=tmp_path / "runs" / "job" / "audio",
        output_dir=tmp_path / "runs" / "job" / "outputs",
        audio_wav=tmp_path / "runs" / "job" / "audio" / "audio.wav",
        result_json=tmp_path / "runs" / "job" / "outputs" / "result.json",
        transcript_txt=tmp_path / "runs" / "job" / "outputs" / "transcript.txt",
        transcript_srt=tmp_path / "runs" / "job" / "outputs" / "transcript.srt",
        transcript_vtt=tmp_path / "runs" / "job" / "outputs" / "transcript.vtt",
        metadata_json=tmp_path / "runs" / "job" / "metadata.json",
    )

    def fake_transcribe(
        _audio_path: Path,
        *,
        model_name: str,
        language: str,
        device: str,
        compute_type: str,
        beam_size: int,
        vad_filter: bool,
        condition_on_previous_text: bool,
        word_timestamps: bool,
    ) -> TranscriptionOutput:
        _ = (model_name, language, device, compute_type, beam_size, word_timestamps)
        calls.append(
            {
                "vad_filter": vad_filter,
                "condition_on_previous_text": condition_on_previous_text,
            },
        )
        return TranscriptionOutput(
            segments=(TranscriptionSegment(start=0.0, end=1.0, text="hello"),),
            device="cpu",
            compute_type="int8",
        )

    monkeypatch.setattr(
        "transcrever_app.pipeline.inspect_media",
        lambda path: MediaInfo(
            path=path,
            duration_seconds=1.0,
            format_name="wav",
            size_bytes=5,
            audio_streams=(
                AudioStream(
                    index=0,
                    relative_index=0,
                    codec_name="pcm",
                    channels=1,
                    sample_rate=16000,
                ),
            ),
        ),
    )

    def fake_create_job_paths(_source_path: Path, *, runs_dir: Path = Path("runs")) -> JobPaths:
        _ = runs_dir
        return job_paths

    def fake_extract_audio(
        *,
        source_path: Path,
        output_path: Path,
        audio_streams: tuple[int, ...],
    ) -> Path:
        _ = (source_path, output_path, audio_streams)
        return job_paths.audio_wav

    monkeypatch.setattr("transcrever_app.pipeline.create_job_paths", fake_create_job_paths)
    monkeypatch.setattr(
        "transcrever_app.pipeline.measure_audio_stream_levels",
        lambda _source, _streams: (
            AudioStreamLevel(relative_index=0, mean_db=-20.0, max_db=-1.0),
        ),
    )
    monkeypatch.setattr("transcrever_app.pipeline.extract_audio", fake_extract_audio)
    monkeypatch.setattr("transcrever_app.pipeline.transcribe_audio_with_details", fake_transcribe)

    process_media(source_path, vad_filter=False, condition_on_previous_text=False)

    metadata = job_paths.metadata_json.read_text(encoding="utf-8")
    assert calls == [{"vad_filter": False, "condition_on_previous_text": False}]
    assert '"vad_filter": false' in metadata
    assert '"condition_on_previous_text": false' in metadata
