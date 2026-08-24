"""Creates and docks the Corona Doctor QDockWidget inside 3ds Max.

Falls back to a plain top-level window when qtmax/the Max main window is
unavailable (e.g. running the shell outside 3ds Max for manual UI
testing), so the same code path can be exercised in both contexts.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QWidget

from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.app.lifecycle import clear_instance
from corona_doctor.core.constants import APP_NAME
from corona_doctor.logging.logger import get_logger

_logger = get_logger("dock_manager")
_OBJECT_NAME = "CoronaDoctorDock"


class _CoronaDoctorDock(QDockWidget):
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        clear_instance()
        super().closeEvent(event)


def create_docked_panel(content: QWidget) -> QDockWidget:
    dock = _CoronaDoctorDock(APP_NAME)
    dock.setObjectName(_OBJECT_NAME)
    dock.setWidget(content)
    dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetClosable
        | QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )
    dock.setMinimumWidth(280)

    max_window = MaxAdapter().get_max_main_window()
    if max_window is not None:
        try:
            max_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            _logger.info("Docked Corona Doctor into the 3ds Max main window.")
        except Exception:  # noqa: BLE001 - fall back to a floating window
            _logger.warning("Could not dock into 3ds Max main window; showing as floating window.", exc_info=True)
            dock.setParent(None)
    else:
        _logger.info("3ds Max main window unavailable; showing Corona Doctor as a standalone window.")

    return dock
