"""Central logging configuration.

Ordinary diagnostic failures must never crash the plugin or dump raw
tracebacks into the UI — they are always logged here, with the UI showing
a friendly message plus an optional "Show Details" pane sourced from the
log (see docs/ARCHITECTURE.md, "Error UX").
"""

from __future__ import annotations

import logging as _logging
import os
from pathlib import Path

from corona_doctor.core.constants import ORG_NAME, SETTINGS_NAMESPACE

_LOGGER_NAME = "corona_doctor"
_configured = False


def default_log_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "state"
    return base / ORG_NAME / f"{SETTINGS_NAMESPACE}.log"


def configure_logging(log_path: Path | None = None, level: int = _logging.INFO) -> _logging.Logger:
    """Idempotent: safe to call multiple times (e.g. on re-launch)."""

    global _configured
    logger = _logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = _logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = _logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    path = log_path or default_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = _logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # A missing/unwritable log directory must not block startup.
        pass

    _configured = True
    return logger


def get_logger(name: str | None = None) -> _logging.Logger:
    full_name = _LOGGER_NAME if not name else f"{_LOGGER_NAME}.{name}"
    return _logging.getLogger(full_name)
