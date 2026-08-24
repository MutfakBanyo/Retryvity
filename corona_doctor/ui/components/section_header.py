"""A consistent title (+ optional trailing widget) row used atop sections."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from corona_doctor.ui.design.metrics import Spacing


class SectionHeader(QWidget):
    def __init__(self, title: str, trailing: QWidget | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        label = QLabel(title, self)
        label.setObjectName("Title")
        layout.addWidget(label)
        layout.addStretch(1)

        if trailing is not None:
            layout.addWidget(trailing)
