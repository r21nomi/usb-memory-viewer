"""Logging to stderr and, optionally, a rotating log file."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_LOG_BYTES = 1_000_000
BACKUP_COUNT = 3


def configure_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        handlers.append(_file_handler(log_file))
    logging.basicConfig(level=level, format=LOG_FORMAT, handlers=handlers)


def _file_handler(log_file: Path) -> logging.Handler:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(
        log_file, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
