"""Docks the RevisionGuard panel into 3ds Max, as a single instance.

``qtmax`` is imported here rather than in revision_guard.max because what
it returns is a QWidget - a Qt concern, not scene access. Outside 3ds Max
the panel falls back to a floating window so the UI can be eyeballed
without the host.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QWidget

from revision_guard.core.constants import APP_NAME
from revision_guard.log import log, warn

try:  # pragma: no cover - only importable inside 3ds Max
    import qtmax  # type: ignore
except ImportError:
    qtmax = None

_OBJECT_NAME = "RevisionGuardDock"
_instance: QDockWidget | None = None


def _max_main_window() -> QWidget | None:
    if qtmax is None:
        return None
    for getter in ("GetQMaxMainWindow", "GetQMaxWindow"):
        function = getattr(qtmax, getter, None)
        if function is None:
            continue
        try:
            return function()
        except Exception:  # noqa: BLE001 - try the next entry point
            continue
    return None


class _RevisionGuardDock(QDockWidget):
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        clear_instance()
        super().closeEvent(event)


def clear_instance() -> None:
    global _instance
    _instance = None


def show_panel() -> QDockWidget:
    """Show the panel, reusing the existing dock if there is one."""

    global _instance

    existing = _show_existing()
    if existing is not None:
        return existing

    from revision_guard.ui.panel import RevisionGuardPanel

    dock = _RevisionGuardDock(APP_NAME)
    dock.setObjectName(_OBJECT_NAME)
    dock.setWidget(RevisionGuardPanel())
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
    )
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetClosable
        | QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )
    dock.setMinimumWidth(270)

    main_window = _max_main_window()
    if main_window is not None:
        try:
            main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            log("Docked into the 3ds Max main window.")
        except Exception:  # noqa: BLE001 - fall back to a floating window
            warn("Could not dock into 3ds Max; showing a floating window instead.")
            dock.setParent(None)
    else:
        log("3ds Max main window unavailable; showing a standalone window.")

    _instance = dock
    dock.show()
    dock.raise_()
    return dock


def _show_existing() -> QDockWidget | None:
    """Return the live dock, re-showing it, or None if there isn't one."""

    if _instance is None:
        return None
    try:
        _instance.show()
        _instance.raise_()
        _instance.activateWindow()
        log("Reused the existing RevisionGuard panel.")
        return _instance
    except RuntimeError:
        # 3ds Max destroyed the underlying C++ widget without going through
        # our close handler; treat the reference as stale.
        warn("Stale RevisionGuard panel reference cleared.")
        clear_instance()
        return None
