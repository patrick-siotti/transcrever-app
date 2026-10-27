"""Logical folder use cases."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from transcrever_app.server.persistence.models import Folder
from transcrever_app.server.persistence.repositories.folders import FolderRepository
from transcrever_app.server.persistence.repositories.transcriptions import TranscriptionRepository
from transcrever_app.server.services.transcription_service import (
    InvalidTranscriptionStateError,
    TranscriptionService,
)


class FolderNotFoundError(LookupError):
    """Raised when a folder is not visible."""


class FolderConflictError(ValueError):
    """Raised for duplicate names or cyclic moves."""


class FolderService:
    """Own folder hierarchy invariants."""

    def __init__(self, session: Session) -> None:
        """Create a service for one transaction."""
        self.repository = FolderRepository(session)

    def get(self, folder_id: str) -> Folder:
        """Return one folder or raise."""
        folder = self.repository.get(folder_id)
        if folder is None:
            raise FolderNotFoundError(folder_id)
        return folder

    def list_children(self, parent_id: str | None) -> list[Folder]:
        """List direct children, validating the requested parent."""
        if parent_id is not None:
            self.get(parent_id)
        return self.repository.list_children(parent_id)

    def list_tree(self) -> list[tuple[Folder, str]]:
        """Return all visible folders with unambiguous breadcrumb paths."""
        result: list[tuple[Folder, str]] = []
        for folder in self.repository.list_all():
            path = " / ".join(part.name for part in self.breadcrumbs(folder.id))
            result.append((folder, path))
        return sorted(result, key=lambda item: (item[1].casefold(), item[0].id))

    def breadcrumbs(self, folder_id: str | None) -> list[Folder]:
        """Build root-to-current breadcrumbs with cycle protection."""
        if folder_id is None:
            return []
        result: list[Folder] = []
        seen: set[str] = set()
        current = self.get(folder_id)
        while True:
            if current.id in seen:
                raise FolderConflictError("Ciclo detectado na hierarquia de pastas.")
            seen.add(current.id)
            result.append(current)
            if current.parent_id is None:
                break
            current = self.get(current.parent_id)
        result.reverse()
        return result

    def create(self, *, name: str, parent_id: str | None) -> Folder:
        """Create a uniquely named sibling folder."""
        clean_name, normalized = _normalize_name(name)
        if parent_id is not None:
            self.get(parent_id)
        self._ensure_unique(parent_id, normalized)
        return self.repository.add(
            Folder(
                id=str(uuid4()),
                parent_id=parent_id,
                name=clean_name,
                normalized_name=normalized,
                position=self.repository.next_position(parent_id),
            )
        )

    def patch(
        self,
        folder_id: str,
        *,
        name: str | None,
        is_pinned: bool | None,
        position: int | None,
    ) -> Folder:
        """Edit folder metadata."""
        folder = self.get(folder_id)
        if name is not None:
            clean_name, normalized = _normalize_name(name)
            existing = self.repository.find_name(folder.parent_id, normalized)
            if existing is not None and existing.id != folder.id:
                raise FolderConflictError("Já existe uma pasta com esse nome neste nível.")
            folder.name = clean_name
            folder.normalized_name = normalized
        if is_pinned is not None:
            folder.is_pinned = is_pinned
        if position is not None:
            folder.position = position
        return folder

    def move(self, folder_id: str, parent_id: str | None) -> Folder:
        """Move a folder while preventing self-parent and descendant cycles."""
        folder = self.get(folder_id)
        if parent_id == folder_id:
            raise FolderConflictError("Uma pasta não pode ser movida para dentro dela mesma.")
        if parent_id is not None:
            parent = self.get(parent_id)
            cursor: Folder | None = parent
            seen: set[str] = set()
            while cursor is not None:
                if cursor.id == folder_id:
                    raise FolderConflictError("Uma pasta não pode ser movida para uma descendente.")
                if cursor.id in seen:
                    raise FolderConflictError("Ciclo detectado na hierarquia de pastas.")
                seen.add(cursor.id)
                cursor = self.get(cursor.parent_id) if cursor.parent_id is not None else None
        self._ensure_unique(parent_id, folder.normalized_name, ignore_id=folder.id)
        folder.parent_id = parent_id
        return folder

    def delete(self, folder_id: str) -> None:
        """Soft-delete a folder tree."""
        root = self.get(folder_id)
        deleted_at = datetime.now(tz=UTC)
        pending = [root]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current.id in seen:
                continue
            seen.add(current.id)
            current.deleted_at = deleted_at
            pending.extend(self.repository.list_children(current.id))

    def delete_with_contents(self, folder_id: str, *, runs_dir: Path, data_dir: Path) -> None:
        """Move tree transcriptions to trash and compensate a partial filesystem failure."""
        folder_ids = self._tree_ids(folder_id)
        transcription_repository = TranscriptionRepository(self.repository.session)
        items = [
            item
            for current_folder_id in folder_ids
            for item in transcription_repository.list_library(current_folder_id)
        ]
        service = TranscriptionService(self.repository.session, runs_dir, data_dir)
        moved_items: list[tuple[str, str | None]] = []
        try:
            for item in items:
                service.soft_delete(item.id)
                moved_items.append((item.id, item.folder_id))
                item.folder_id = None
        except (InvalidTranscriptionStateError, OSError, ValueError) as exc:
            for moved_id, original_folder_id in reversed(moved_items):
                restored = service.restore(moved_id)
                restored.folder_id = original_folder_id
            raise FolderConflictError(str(exc)) from exc
        self.delete(folder_id)

    def _tree_ids(self, folder_id: str) -> list[str]:
        root = self.get(folder_id)
        result: list[str] = []
        pending = [root]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current.id in seen:
                continue
            seen.add(current.id)
            result.append(current.id)
            pending.extend(self.repository.list_children(current.id))
        return result

    def _ensure_unique(
        self,
        parent_id: str | None,
        normalized_name: str,
        *,
        ignore_id: str | None = None,
    ) -> None:
        existing = self.repository.find_name(parent_id, normalized_name)
        if existing is not None and existing.id != ignore_id:
            raise FolderConflictError("Já existe uma pasta com esse nome neste nível.")


def _normalize_name(name: str) -> tuple[str, str]:
    clean = " ".join(name.strip().split())
    if not clean:
        raise FolderConflictError("O nome da pasta não pode ficar vazio.")
    normalized = unicodedata.normalize("NFKC", clean).casefold()
    return clean, normalized
