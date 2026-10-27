"""Alembic environment for the embedded SQLite database."""

from __future__ import annotations

from alembic import context
from sqlalchemy.engine import Connection

from transcrever_app.server.persistence.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations using the connection owned by the application."""
    connection = context.config.attributes.get("connection")
    if not isinstance(connection, Connection):
        raise TypeError("A migration requires an application-owned database connection.")
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
