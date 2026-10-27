"""Logical folder routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from transcrever_app.server.api.dependencies import DBSession
from transcrever_app.server.schemas.folder import (
    FolderCreate,
    FolderMove,
    FolderPatch,
    FolderResponse,
    FolderTreeResponse,
)
from transcrever_app.server.services.folder_service import (
    FolderConflictError,
    FolderNotFoundError,
    FolderService,
)

router = APIRouter(prefix="/api/v1/folders", tags=["folders"])


def _folder_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FolderNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada.")
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, session: DBSession) -> FolderResponse:
    """Create a logical folder."""
    try:
        folder = FolderService(session).create(name=payload.name, parent_id=payload.parent_id)
    except (FolderConflictError, FolderNotFoundError) as exc:
        raise _folder_error(exc) from exc
    return FolderResponse.model_validate(folder)


@router.get("/tree")
def get_folder_tree(session: DBSession) -> list[FolderTreeResponse]:
    """Return all folders with full logical paths for move controls."""
    return [
        FolderTreeResponse(
            **FolderResponse.model_validate(folder).model_dump(),
            path=path,
        )
        for folder, path in FolderService(session).list_tree()
    ]


@router.get("/{folder_id}")
def get_folder(folder_id: str, session: DBSession) -> FolderResponse:
    """Return one logical folder."""
    try:
        folder = FolderService(session).get(folder_id)
    except FolderNotFoundError as exc:
        raise _folder_error(exc) from exc
    return FolderResponse.model_validate(folder)


@router.patch("/{folder_id}")
def patch_folder(folder_id: str, payload: FolderPatch, session: DBSession) -> FolderResponse:
    """Edit logical folder metadata."""
    try:
        folder = FolderService(session).patch(
            folder_id,
            name=payload.name,
            is_pinned=payload.is_pinned,
            position=payload.position,
        )
    except (FolderConflictError, FolderNotFoundError) as exc:
        raise _folder_error(exc) from exc
    return FolderResponse.model_validate(folder)


@router.post("/{folder_id}/move")
def move_folder(folder_id: str, payload: FolderMove, session: DBSession) -> FolderResponse:
    """Move a folder to a new logical parent."""
    try:
        folder = FolderService(session).move(folder_id, payload.parent_id)
    except (FolderConflictError, FolderNotFoundError) as exc:
        raise _folder_error(exc) from exc
    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str, session: DBSession, request: Request) -> None:
    """Soft-delete a logical folder tree."""
    try:
        settings = request.app.state.settings
        FolderService(session).delete_with_contents(
            folder_id,
            runs_dir=settings.runs_dir,
            data_dir=settings.data_dir,
        )
    except (FolderConflictError, FolderNotFoundError) as exc:
        raise _folder_error(exc) from exc
