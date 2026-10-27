"""Validated local application configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Settings for one local application instance."""

    model_config = SettingsConfigDict(env_prefix="TRANSCRIBER_", extra="ignore")

    data_dir: Path = Path("data")
    runs_dir: Path = Path("runs")
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    debug: bool = False
    worker_enabled: bool = True
    max_upload_bytes: int = Field(default=20 * 1024 * 1024 * 1024, ge=1)

    @property
    def database_path(self) -> Path:
        """Return the SQLite path controlled by this instance."""
        return self.data_dir / "transcrever.sqlite3"
