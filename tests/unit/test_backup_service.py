from pathlib import Path

import pytest

from transcrever_app.server.backup_service import create_backup, restore_backup
from transcrever_app.server.config import AppSettings
from transcrever_app.server.persistence.database import create_sqlite_engine, upgrade_schema


def test_backup_restore_round_trip_preserves_database_and_artifacts(tmp_path: Path) -> None:
    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs")
    engine = create_sqlite_engine(settings.database_path)
    upgrade_schema(engine)
    engine.dispose()
    artifact = settings.runs_dir / "job" / "outputs" / "transcript.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("original", encoding="utf-8")
    backup = create_backup(settings)
    artifact.write_text("changed", encoding="utf-8")

    rollback = restore_backup(settings, backup)

    assert artifact.read_text(encoding="utf-8") == "original"
    assert (rollback / "runs" / "job" / "outputs" / "transcript.txt").read_text(
        encoding="utf-8"
    ) == "changed"


def test_restore_rejects_zip_slip_before_writing_state(tmp_path: Path) -> None:
    import zipfile

    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs")
    backup = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(backup, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="inseguro"):
        restore_backup(settings, backup)
    assert not (tmp_path / "outside.txt").exists()
