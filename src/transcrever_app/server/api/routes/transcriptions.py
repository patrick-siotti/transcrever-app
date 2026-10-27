"""Transcription and library routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status

from transcrever_app.diarization.pyannote import is_pyannote_configured
from transcrever_app.server.api.dependencies import DBSession
from transcrever_app.server.schemas.folder import FolderResponse
from transcrever_app.server.schemas.transcription import (
    LibraryResponse,
    TranscriptionPatch,
    TranscriptionResponse,
    TranscriptionResultResponse,
)
from transcrever_app.server.services.explorer_service import open_transcription_folder
from transcrever_app.server.services.folder_service import FolderNotFoundError, FolderService
from transcrever_app.server.services.transcription_service import (
    InvalidTranscriptionStateError,
    TranscriptionNotFoundError,
    TranscriptionService,
    UploadTooLargeError,
)

router = APIRouter(prefix="/api/v1", tags=["transcriptions"])


def _service(request: Request, session: DBSession) -> TranscriptionService:
    settings = request.app.state.settings
    return TranscriptionService(
        session,
        settings.runs_dir,
        settings.data_dir,
        settings.max_upload_bytes,
    )


@router.get("/library")
def get_library(
    request: Request,
    session: DBSession,
    folder_id: Annotated[str | None, Query()] = None,
) -> LibraryResponse:
    """Return the visible library and unread completed items."""
    folder_service = FolderService(session)
    try:
        current_folder = folder_service.get(folder_id) if folder_id is not None else None
        folders = folder_service.list_children(folder_id)
        breadcrumbs = folder_service.breadcrumbs(folder_id)
    except FolderNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada.") from exc
    items = _service(request, session).list_library(folder_id)
    responses = [TranscriptionResponse.model_validate(item) for item in items]
    new_items = [
        item
        for item in responses
        if item.viewed_at is None and item.status in {"completed", "completed_with_warning"}
    ]
    return LibraryResponse(
        folder=(
            FolderResponse.model_validate(current_folder) if current_folder is not None else None
        ),
        breadcrumbs=[FolderResponse.model_validate(folder) for folder in breadcrumbs],
        folders=[FolderResponse.model_validate(folder) for folder in folders],
        new_transcriptions=new_items,
        transcriptions=responses,
    )


@router.get("/trash")
def get_trash(request: Request, session: DBSession) -> list[TranscriptionResponse]:
    """Return items available for restore or permanent deletion."""
    return [
        TranscriptionResponse.model_validate(item)
        for item in _service(request, session).list_trash()
    ]


@router.delete("/trash/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_transcription(
    transcription_id: str,
    request: Request,
    session: DBSession,
) -> None:
    """Permanently remove a transcription already placed in trash."""
    try:
        _service(request, session).permanently_delete(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Transcrição excluída não encontrada.",
        ) from exc


@router.post("/transcriptions", status_code=status.HTTP_201_CREATED)
def create_transcription(
    request: Request,
    session: DBSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=240)],
    model_name: Annotated[str, Form(min_length=1, max_length=120)] = "large-v3",
    diarization_mode: Annotated[str, Form(pattern="^(off|auto|pyannote|clustering)$")] = "auto",
    speaker_count: Annotated[int | None, Form(ge=1, le=20)] = None,
) -> TranscriptionResponse:
    """Stream an upload into controlled storage and enqueue it."""
    if not file.filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Arquivo sem nome.")
    if diarization_mode == "pyannote" and not is_pyannote_configured():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Pyannote não está configurado. Use Automática ou Agrupamento local.",
        )
    try:
        item = _service(request, session).create_from_upload(
            stream=file.file,
            original_filename=file.filename,
            title=title,
            model_name=model_name,
            diarization_mode=diarization_mode,
            speaker_count=speaker_count,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    runner = request.app.state.runner
    if runner is not None:
        runner.wake()
    return TranscriptionResponse.model_validate(item)


@router.get("/transcriptions/{transcription_id}")
def get_transcription(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResponse:
    """Return one transcription."""
    try:
        item = _service(request, session).get(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    return TranscriptionResponse.model_validate(item)


@router.patch("/transcriptions/{transcription_id}")
def patch_transcription(
    transcription_id: str,
    payload: TranscriptionPatch,
    request: Request,
    session: DBSession,
) -> TranscriptionResponse:
    """Edit title or pinned state."""
    try:
        item = _service(request, session).patch(
            transcription_id,
            title=payload.title,
            is_pinned=payload.is_pinned,
            folder_id=payload.folder_id,
            update_folder="folder_id" in payload.model_fields_set,
            position=payload.position,
        )
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    return TranscriptionResponse.model_validate(item)


def _state_conflict(exc: InvalidTranscriptionStateError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/transcriptions/{transcription_id}/cancel")
def cancel_transcription(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResponse:
    """Cancel a queued job or request cancellation for the active one."""
    try:
        item = _service(request, session).cancel(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    except InvalidTranscriptionStateError as exc:
        raise _state_conflict(exc) from exc
    runner = request.app.state.runner
    if runner is not None:
        runner.request_cancel(transcription_id)
    return TranscriptionResponse.model_validate(item)


@router.post("/transcriptions/{transcription_id}/retry")
def retry_transcription(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResponse:
    """Requeue a failed or interrupted job."""
    try:
        item = _service(request, session).retry(
            transcription_id,
            pyannote_configured=is_pyannote_configured(),
        )
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    except InvalidTranscriptionStateError as exc:
        raise _state_conflict(exc) from exc
    runner = request.app.state.runner
    if runner is not None:
        runner.wake()
    return TranscriptionResponse.model_validate(item)


@router.post("/transcriptions/{transcription_id}/mark-viewed")
def mark_transcription_viewed(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResponse:
    """Mark a transcription as viewed."""
    try:
        item = _service(request, session).mark_viewed(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    return TranscriptionResponse.model_validate(item)


@router.get("/transcriptions/{transcription_id}/result")
def get_transcription_result(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResultResponse:
    """Return the canonical transcript result."""
    try:
        payload = _service(request, session).get_result(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    except InvalidTranscriptionStateError as exc:
        raise _state_conflict(exc) from exc
    return TranscriptionResultResponse.model_validate(payload)


@router.post(
    "/transcriptions/{transcription_id}/open-folder",
    status_code=status.HTTP_204_NO_CONTENT,
)
def open_folder(transcription_id: str, request: Request, session: DBSession) -> None:
    """Open the controlled job output directory in the operating system."""
    try:
        item = _service(request, session).get(transcription_id)
        open_transcription_folder(
            job_root=Path(item.job_root),
            outputs_path=Path(item.outputs_path),
        )
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não foi possível abrir a pasta.") from exc


@router.delete("/transcriptions/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transcription(transcription_id: str, request: Request, session: DBSession) -> None:
    """Move a terminal transcription to the application trash."""
    try:
        _service(request, session).soft_delete(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcrição não encontrada.") from exc
    except InvalidTranscriptionStateError as exc:
        raise _state_conflict(exc) from exc


@router.post("/transcriptions/{transcription_id}/restore")
def restore_transcription(
    transcription_id: str, request: Request, session: DBSession
) -> TranscriptionResponse:
    """Restore a transcription from the application trash."""
    try:
        item = _service(request, session).restore(transcription_id)
    except TranscriptionNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Transcrição excluída não encontrada.",
        ) from exc
    except InvalidTranscriptionStateError as exc:
        raise _state_conflict(exc) from exc
    return TranscriptionResponse.model_validate(item)
