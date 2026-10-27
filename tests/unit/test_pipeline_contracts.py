from pathlib import Path

import pytest

from transcrever_app.core.cancellation import CancellationToken
from transcrever_app.core.events import PipelineEvent, PipelineStage
from transcrever_app.core.exceptions import ProcessingCancelledError
from transcrever_app.jobs.manager import create_job_paths
from transcrever_app.pipeline import _emit, _preserve_source


def test_preserve_source_copies_original_atomically(tmp_path: Path) -> None:
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"original")
    paths = create_job_paths(source, runs_dir=tmp_path / "runs")

    copied = _preserve_source(source.resolve(), paths)

    assert copied.read_bytes() == b"original"
    assert not copied.with_suffix(f"{copied.suffix}.part").exists()


def test_progress_event_is_clamped() -> None:
    events: list[PipelineEvent] = []

    _emit(events.append, PipelineStage.PREPARING, 4.0, "test")

    assert events[0].progress == 1.0


def test_cancellation_token_raises_at_checkpoint() -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(ProcessingCancelledError):
        token.raise_if_cancelled()
