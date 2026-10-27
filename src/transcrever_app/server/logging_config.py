"""Local rotating application log configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_local_logging(data_dir: Path) -> logging.Logger:
    """Create one non-propagating rotating logger for the local instance."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"transcrever.local.{log_dir.resolve()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(
        log_dir / "transcrever.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    )
    logger.addHandler(handler)
    return logger


def close_local_logging(logger: logging.Logger) -> None:
    """Flush and detach handlers owned by one application instance."""
    for handler in tuple(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)
