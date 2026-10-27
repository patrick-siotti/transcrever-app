"""Create the initial local-library schema."""

from __future__ import annotations

from alembic import op

from transcrever_app.server.persistence.models import Base

revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables and indexes in the initial schema."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Remove the initial schema."""
    Base.metadata.drop_all(bind=op.get_bind())
