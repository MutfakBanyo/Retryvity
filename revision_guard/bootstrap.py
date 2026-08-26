"""Stable entry point for the 3ds Max host.

The menu action, the installer and the listener all call
``show_revision_guard()``, so the internal package layout can change
without touching anything on the 3ds Max side.
"""

from __future__ import annotations


def show_revision_guard():
    """Show (or focus) the RevisionGuard panel. Safe to call repeatedly."""

    from revision_guard.log import log
    from revision_guard.ui.dock import show_panel
    from revision_guard.version import __version__

    log(f"RevisionGuard {__version__} starting.")
    return show_panel()


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    show_revision_guard()
