"""SQLite engine and session lifecycle."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def create_sqlite_engine(database_path: Path) -> Engine:
    """Create a local SQLite engine with concurrency-safe pragmas."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path.resolve().as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5.0},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def upgrade_schema(engine: Engine) -> None:
    """Upgrade the database to the packaged Alembic head revision."""
    script_location = Path(__file__).resolve().parent / "migrations"
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.attributes["connection"] = engine.connect()
    try:
        command.upgrade(config, "head")
    finally:
        config.attributes["connection"].close()


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory with explicit transaction ownership."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session and commit or roll back its transaction."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
