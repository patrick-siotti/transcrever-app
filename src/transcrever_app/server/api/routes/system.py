"""System health endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from transcrever_app import __version__
from transcrever_app.diarization.pyannote import is_pyannote_configured
from transcrever_app.server.api.dependencies import DBSession
from transcrever_app.server.persistence.models import AppSetting
from transcrever_app.server.schemas.system import (
    DiagnosticsResponse,
    HealthResponse,
    MaintenanceResponse,
    PreferencesPatch,
    PreferencesResponse,
)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health")
def health(request: Request) -> HealthResponse:
    """Report local API and database readiness."""
    settings = request.app.state.settings
    return HealthResponse(api="ok", database="ok", worker="idle", host=settings.host)


@router.get("/diagnostics")
def diagnostics(request: Request) -> DiagnosticsResponse:
    """Return non-secret paths and startup recovery information."""
    settings = request.app.state.settings
    report = request.app.state.maintenance_report
    return DiagnosticsResponse(
        version=__version__,
        database_path=str(settings.database_path.resolve()),
        runs_path=str(settings.runs_dir.resolve()),
        trash_path=str((settings.data_dir / "trash").resolve()),
        log_path=str((settings.data_dir / "logs" / "transcrever.log").resolve()),
        worker_enabled=settings.worker_enabled,
        maintenance=MaintenanceResponse(
            interrupted=report.interrupted,
            imported=report.imported,
            missing_roots=report.missing_roots,
            invalid_runs=report.invalid_runs,
            removed_partials=report.removed_partials,
        ),
    )


@router.get("/preferences")
def get_preferences(session: DBSession) -> PreferencesResponse:
    """Return persisted upload defaults or product defaults."""
    setting = session.get(AppSetting, "preferences")
    if setting is None:
        return PreferencesResponse(pyannote_configured=is_pyannote_configured())
    try:
        preferences = PreferencesPatch.model_validate_json(setting.value_json)
        return PreferencesResponse(
            **preferences.model_dump(),
            pyannote_configured=is_pyannote_configured(),
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "As preferências locais estão inválidas.",
        ) from exc


@router.put("/preferences")
def put_preferences(payload: PreferencesPatch, session: DBSession) -> PreferencesResponse:
    """Validate and persist upload defaults."""
    allowed_modes = {"off", "auto", "pyannote", "clustering"}
    if payload.default_diarization_mode not in allowed_modes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Modo de diarização inválido.")
    if not payload.default_model.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Modelo padrão inválido.")
    response = PreferencesResponse(
        default_model=payload.default_model.strip(),
        default_diarization_mode=payload.default_diarization_mode,
        pyannote_configured=is_pyannote_configured(),
    )
    stored_preferences = PreferencesPatch(
        default_model=response.default_model,
        default_diarization_mode=response.default_diarization_mode,
    )
    setting = session.get(AppSetting, "preferences")
    if setting is None:
        setting = AppSetting(key="preferences", value_json=stored_preferences.model_dump_json())
        session.add(setting)
    else:
        setting.value_json = stored_preferences.model_dump_json()
    return response
