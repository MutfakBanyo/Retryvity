"""The Environment screen: capability probe results and system status."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from corona_doctor.core.models import EnvironmentReport
from corona_doctor.ui.components.section_header import SectionHeader
from corona_doctor.ui.components.status_badge import StatusBadge
from corona_doctor.ui.design.metrics import Spacing


class EnvironmentView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        root.addWidget(SectionHeader("Environment", parent=self))

        surface = QWidget(self)
        surface.setObjectName("Surface")
        self._form = QFormLayout(surface)
        self._form.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._form.setSpacing(Spacing.SM)

        self._max_label = self._add_row("3ds Max")
        self._corona_label = self._add_row("Corona")
        self._python_label = self._add_row("Python")
        self._qt_label = self._add_row("Qt")

        root.addWidget(surface)

        root.addWidget(SectionHeader("System Status", parent=self))
        self._status_badge = StatusBadge("Ready", severity="healthy", parent=self)
        root.addWidget(self._status_badge)

        root.addStretch(1)

        self.show_probing()

    def _add_row(self, label_text: str) -> QLabel:
        label = QLabel(label_text, self)
        label.setObjectName("Secondary")
        value = QLabel("—", self)
        self._form.addRow(label, value)
        return value

    def show_probing(self) -> None:
        for label in (self._max_label, self._corona_label, self._python_label, self._qt_label):
            label.setText("probing…")
        self._status_badge.setText("Probing")
        self._status_badge.set_severity("info")

    def show_report(self, report: EnvironmentReport) -> None:
        self._max_label.setText(report.max_version)
        self._corona_label.setText(
            "Detected" if report.corona_detected else ("Not detected" if report.corona_detected is False else "unknown")
        )
        self._python_label.setText(report.python_version)
        self._qt_label.setText(report.qt_version)

        if report.errors:
            self._status_badge.setText("Partial")
            self._status_badge.set_severity("warning")
        else:
            self._status_badge.setText("Ready")
            self._status_badge.set_severity("healthy")
