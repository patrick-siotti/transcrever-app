from pathlib import Path

import pytest

from transcrever_app.diarization.pyannote import (
    _is_model_cached,
    _speaker_name_by_first_seen,
    get_pyannote_token,
)


def test_speaker_name_by_first_seen_keeps_chronological_names() -> None:
    labels: dict[str, str] = {}

    result = [
        _speaker_name_by_first_seen(labels, "SPEAKER_03"),
        _speaker_name_by_first_seen(labels, "SPEAKER_01"),
        _speaker_name_by_first_seen(labels, "SPEAKER_03"),
    ]

    assert result == ["Falante 1", "Falante 2", "Falante 1"]


def test_cached_model_allows_pyannote_without_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        lambda **_kwargs: str(tmp_path),
    )

    assert _is_model_cached("cached/model") is True
    assert get_pyannote_token(allow_cached=True, model_name="cached/model") is None
