"""A small colored pill/label used for severity and status indicators."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.metrics import Radius, Spacing


class StatusBadge(QLabel):
    def __init__(self, text: str, severity: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_severity(severity)

    def set_severity(self, severity: str) -> None:
        fg = Color.for_severity(severity)
        bg = Color.muted_for_severity(severity)
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: {Radius.SMALL}px; "
            f"padding: 2px {Spacing.SM}px; font-weight: 600; font-size: 10px;"
        )
