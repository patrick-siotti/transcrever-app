"""Cooperative cancellation primitives for long-running jobs."""

from __future__ import annotations

from threading import Event

from transcrever_app.core.exceptions import ProcessingCancelledError


class CancellationToken:
    """Thread-safe cooperative cancellation token."""

    def __init__(self) -> None:
        """Create a token with no cancellation request."""
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()

    def cancel(self) -> None:
        """Request cancellation."""
        self._event.set()

    def raise_if_cancelled(self) -> None:
        """Raise when cancellation was requested."""
        if self.is_cancelled:
            raise ProcessingCancelledError
