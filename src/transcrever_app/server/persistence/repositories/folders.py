"""Persistence operations for logical folders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from transcrever_app.server.persistence.models import Folder


class FolderRepository:
    """Repository owning folder queries."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to one transaction."""
        self.session = session

    def add(self, folder: Folder) -> Folder:
        """Persist a folder."""
        self.session.add(folder)
        self.session.flush()
        return folder

    def get(self, folder_id: str) -> Folder | None:
        """Get a visible folder."""
        return self.session.scalar(
            select(Folder).where(Folder.id == folder_id, Folder.deleted_at.is_(None))
        )

    def list_children(self, parent_id: str | None) -> list[Folder]:
        """List visible direct children in stable order."""
        parent_filter = (
            Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
        )
        return list(
            self.session.scalars(
                select(Folder)
                .where(parent_filter, Folder.deleted_at.is_(None))
                .order_by(
                    Folder.is_pinned.desc(),
                    Folder.position.asc(),
                    Folder.updated_at.desc(),
                    Folder.id.asc(),
                )
            ).all()
        )

    def list_all(self) -> list[Folder]:
        """List every visible folder in stable name order."""
        return list(
            self.session.scalars(
                select(Folder)
                .where(Folder.deleted_at.is_(None))
                .order_by(Folder.normalized_name.asc(), Folder.id.asc())
            ).all()
        )

    def find_name(self, parent_id: str | None, normalized_name: str) -> Folder | None:
        """Find a visible sibling by normalized name."""
        parent_filter = (
            Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
        )
        return self.session.scalar(
            select(Folder).where(
                parent_filter,
                Folder.normalized_name == normalized_name,
                Folder.deleted_at.is_(None),
            )
        )

    def next_position(self, parent_id: str | None) -> int:
        """Return the next stable position among visible siblings."""
        parent_filter = (
            Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
        )
        maximum = self.session.scalar(
            select(func.max(Folder.position)).where(
                parent_filter,
                Folder.deleted_at.is_(None),
            )
        )
        return int(maximum if maximum is not None else -1) + 1
