"""Offline backup and rollback-safe restore for local application data."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from transcrever_app.server.config import AppSettings

BACKUP_FORMAT_VERSION = 1


def create_backup(settings: AppSettings, destination: Path | None = None) -> Path:
    """Create a consistent SQLite and artifact backup while the app is stopped."""
    if not settings.database_path.is_file():
        raise FileNotFoundError("O banco local ainda não existe.")
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    target = destination or settings.data_dir / "backups" / f"transcrever-{timestamp}.zip"
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_zip = target.with_suffix(f"{target.suffix}.part")
    with tempfile.TemporaryDirectory(prefix="transcrever-backup-") as temporary_dir:
        snapshot = Path(temporary_dir) / "transcrever.sqlite3"
        _backup_database(settings.database_path, snapshot)
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format_version": BACKUP_FORMAT_VERSION,
                        "created_at": datetime.now(tz=UTC).isoformat(),
                    },
                    indent=2,
                ),
            )
            archive.write(snapshot, "database/transcrever.sqlite3")
            _add_tree(archive, settings.runs_dir, "storage/runs")
            _add_tree(archive, settings.data_dir / "trash", "storage/trash")
    temporary_zip.replace(target)
    return target


def restore_backup(settings: AppSettings, backup_path: Path) -> Path:
    """Validate and restore a backup, keeping the previous state in a rollback directory."""
    backup_path = backup_path.resolve()
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup não encontrado: {backup_path}")
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    rollback_dir = (settings.data_dir / "restore-rollbacks" / timestamp).resolve()
    with tempfile.TemporaryDirectory(prefix="transcrever-restore-") as temporary_dir:
        extracted = Path(temporary_dir)
        _safe_extract(backup_path, extracted)
        database = extracted / "database" / "transcrever.sqlite3"
        _validate_backup(extracted, database)
        rollback_dir.mkdir(parents=True, exist_ok=False)
        _preserve_current(settings.database_path, rollback_dir / "transcrever.sqlite3")
        _preserve_current(settings.runs_dir, rollback_dir / "runs")
        _preserve_current(settings.data_dir / "trash", rollback_dir / "trash")
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, settings.database_path)
        _replace_tree(extracted / "storage" / "runs", settings.runs_dir)
        _replace_tree(extracted / "storage" / "trash", settings.data_dir / "trash")
    return rollback_dir


def _backup_database(source: Path, destination: Path) -> None:
    with (
        closing(sqlite3.connect(source)) as source_connection,
        closing(sqlite3.connect(destination)) as target,
    ):
        source_connection.backup(target)


def _add_tree(archive: zipfile.ZipFile, root: Path, prefix: str) -> None:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.endswith(".part"):
            archive.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")


def _safe_extract(backup_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(backup_path) as archive:
        for member in archive.infolist():
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("O backup contém um caminho inseguro.")
        archive.extractall(destination)


def _validate_backup(extracted: Path, database: Path) -> None:
    manifest_path = extracted / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise ValueError("Versão de backup incompatível.")
    if not database.is_file():
        raise ValueError("Backup sem banco de dados.")
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("O banco contido no backup está corrompido.")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    if not {"alembic_version", "transcriptions", "folders"}.issubset(tables):
        raise ValueError("O backup não contém o schema esperado.")


def _preserve_current(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
