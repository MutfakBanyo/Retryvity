"""Concise logging for RevisionGuard.

Everything is prefixed with ``[RevisionGuard]`` and goes to stdout, which
is the 3ds Max listener when running inside the host. Deliberately tiny:
V0.1 logs a handful of lines per operation, never per vertex.
"""

from __future__ import annotations

import sys

from revision_guard.core.constants import LOG_PREFIX

_verbose = False


def set_verbose(enabled: bool) -> None:
    """Enable per-object diagnostics. Off by default - it is noisy."""

    global _verbose
    _verbose = enabled


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}")


def warn(message: str) -> None:
    print(f"{LOG_PREFIX} WARNING: {message}", file=sys.stderr)


def debug(message: str) -> None:
    if _verbose:
        print(f"{LOG_PREFIX} {message}")
