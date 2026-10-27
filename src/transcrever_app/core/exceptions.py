"""Application exception hierarchy."""


class TranscreverAppError(Exception):
    """Base exception for all application errors."""


class DependencyNotFoundError(TranscreverAppError):
    """Raised when a required external dependency is not available."""


class MediaProcessingError(TranscreverAppError):
    """Raised when media inspection or extraction fails."""


class TranscriptionError(TranscreverAppError):
    """Raised when ASR processing fails."""


class DiarizationError(TranscreverAppError):
    """Raised when speaker diarization fails."""


class ProcessingCancelledError(TranscreverAppError):
    """Raised at a safe checkpoint after cancellation was requested."""
