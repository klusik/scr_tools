# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/logging_setup.py
# Module Type: Operational diagnostics
# Purpose: Configure bounded local logs without recording user activity data.
# Responsibilities: Rotating output, private-data discipline and handler cleanup.
# Author: Rudolf Klusal
# License: MIT

"""Bounded diagnostics for operational errors and limited service transitions."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_MAX_BYTES: int = 512 * 1024
LOG_BACKUP_COUNT: int = 3


def setup_logging(log_directory: Path) -> None:
    """Configure UTF-8 rotating logs in a caller-resolved per-user directory.

    Callers must never pass key values, clipboard data, screenshot pixels,
    credentials, user paths or arbitrary exception text as logging arguments.

    Args:
        log_directory: Suitable per-user local application-data directory.

    Returns:
        None after replacing this application's earlier logging handlers.

    Raises:
        OSError: The log directory or file cannot be created or opened.
    """
    log_directory.mkdir(parents=True, exist_ok=True)
    handler: RotatingFileHandler = RotatingFileHandler(
        log_directory / "scr_tools.log", maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    logger: logging.Logger = logging.getLogger("scr_tools")
    for old_handler in list(logger.handlers):
        logger.removeHandler(old_handler)
        old_handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
