from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from transcrever_app.core.models import AudioStream, MediaInfo
from transcrever_app.media.ffmpeg import (
    AudioStreamLevel,
    extract_audio,
    measure_audio_stream_levels,
    select_audio_streams,
)


def _obs_media() -> MediaInfo:
    return MediaInfo(
        path=Path("recording.mkv"),
        duration_seconds=10.0,
        format_name="matroska",
        size_bytes=100,
        audio_streams=(
            AudioStream(
                index=1,
                relative_index=0,
                codec_name="aac",
                channels=2,
                sample_rate=48000,
                title="pc",
            ),
            AudioStream(
                index=2,
                relative_index=1,
                codec_name="aac",
                channels=2,
                sample_rate=48000,
                title="microfone",
            ),
        ),
    )


def test_automatic_selection_mixes_known_obs_tracks() -> None:
    levels = (
        AudioStreamLevel(relative_index=0, mean_db=-20.0, max_db=-1.0),
        AudioStreamLevel(relative_index=1, mean_db=-30.0, max_db=-5.0),
    )

    assert select_audio_streams(_obs_media(), None, levels) == (0, 1)


def test_automatic_selection_discards_silent_stream() -> None:
    levels = (
        AudioStreamLevel(relative_index=0, mean_db=-91.0, max_db=-91.0),
        AudioStreamLevel(relative_index=1, mean_db=-25.3, max_db=-0.1),
    )

    assert select_audio_streams(_obs_media(), None, levels) == (1,)


def test_explicit_selection_preserves_single_track() -> None:
    assert select_audio_streams(_obs_media(), 1) == (1,)


def test_multitrack_extraction_builds_amix_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    class Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr("transcrever_app.media.ffmpeg.ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(
        "transcrever_app.media.ffmpeg.subprocess.run",
        lambda command, **_kwargs: commands.append(command) or Completed(),
    )

    extract_audio(
        source_path=tmp_path / "recording.mkv",
        output_path=tmp_path / "audio.wav",
        audio_streams=(0, 1),
    )

    command = commands[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "[0:a:0][0:a:1]amix=inputs=2" in graph
    assert command[command.index("-map") + 1] == "[mixed]"


def test_measurement_parses_all_stream_levels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Completed:
        returncode = 0
        stderr = """
[Parsed_volumedetect_0 @ abc] mean_volume: -91.0 dB
[Parsed_volumedetect_0 @ abc] max_volume: -91.0 dB
[Parsed_volumedetect_1 @ def] mean_volume: -25.3 dB
[Parsed_volumedetect_1 @ def] max_volume: -0.1 dB
"""

    monkeypatch.setattr("transcrever_app.media.ffmpeg.ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(
        "transcrever_app.media.ffmpeg.subprocess.run",
        lambda _command, **_kwargs: Completed(),
    )

    assert measure_audio_stream_levels(tmp_path / "recording.mov", _obs_media().audio_streams) == (
        AudioStreamLevel(relative_index=0, mean_db=-91.0, max_db=-91.0),
        AudioStreamLevel(relative_index=1, mean_db=-25.3, max_db=-0.1),
    )
