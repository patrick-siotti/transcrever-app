from pathlib import Path

from transcrever_app.jobs.manager import create_job_paths


def test_job_ids_are_unique_and_sources_have_a_dedicated_directory(tmp_path: Path) -> None:
    source = tmp_path / "same name.wav"

    first = create_job_paths(source, runs_dir=tmp_path / "runs")
    second = create_job_paths(source, runs_dir=tmp_path / "runs")

    assert first.job_id != second.job_id
    assert first.source_dir == first.root / "source"
    assert first.source_file == first.root / "source" / source.name
