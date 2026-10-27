"""System endpoint schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Readiness of local application components."""

    api: str
    database: str
    worker: str
    host: str


class MaintenanceResponse(BaseModel):
    """Last startup maintenance counters."""

    interrupted: int
    imported: int
    missing_roots: int
    invalid_runs: int
    removed_partials: int


class DiagnosticsResponse(BaseModel):
    """Safe local operational details for troubleshooting."""

    version: str
    database_path: str
    runs_path: str
    trash_path: str
    log_path: str
    worker_enabled: bool
    maintenance: MaintenanceResponse


class PreferencesResponse(BaseModel):
    """Persistent defaults used by the upload form."""

    default_model: str = "large-v3"
    default_diarization_mode: str = "pyannote"
    pyannote_configured: bool = False


class PreferencesPatch(BaseModel):
    """Editable persistent upload defaults."""

    default_model: str
    default_diarization_mode: str
