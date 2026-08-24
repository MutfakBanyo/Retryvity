"""Corona Doctor version metadata."""

from __future__ import annotations

__version__ = "0.1.0-bootstrap"
__stage__ = "architectural-foundation"

MIN_3DS_MAX_VERSION = (2026, 2)
MIN_CORONA_VERSION = 15
REQUIRED_PYTHON = (3, 11)
REQUIRED_QT_MAJOR = 6


def version_string() -> str:
    return __version__
