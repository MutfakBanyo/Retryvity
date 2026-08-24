"""Singleton lifecycle management for the Corona Doctor dock panel.

Calling the launch entry point repeatedly must focus/show the existing
instance rather than creating duplicates. This module owns that single
module-level reference; nothing else should hold its own copy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from corona_doctor.logging.logger import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QDockWidget

_logger = get_logger("lifecycle")

_instance: "QDockWidget | None" = None


def get_instance() -> "QDockWidget | None":
    return _instance


def set_instance(dock_widget: "QDockWidget") -> None:
    global _instance
    _instance = dock_widget


def clear_instance() -> None:
    global _instance
    _instance = None


def show_or_focus_existing() -> bool:
    """Return True if an existing instance was shown/focused (no new one needed)."""

    if _instance is None:
        return False
    try:
        _instance.show()
        _instance.raise_()
        _instance.activateWindow()
        widget = _instance.widget()
        if widget is not None:
            widget.setFocus()
        _logger.info("Reused existing Corona Doctor instance.")
        return True
    except RuntimeError:
        # The underlying C++ object was already destroyed (Max closed the
        # dock without going through our close handler); treat as gone.
        _logger.warning("Stale Corona Doctor instance reference cleared.")
        clear_instance()
        return False
