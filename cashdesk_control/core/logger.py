"""Application logging configured for both source and packaged builds."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import AppPaths, app_paths


LOGGER_NAME = "cashdesk_control"


def configure_logging(paths: AppPaths | None = None) -> logging.Logger:
    """Configure rotating UTF-8 logs and return the application logger."""

    target_paths = (paths or app_paths()).ensure()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = RotatingFileHandler(
        Path(target_paths.log_file),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
