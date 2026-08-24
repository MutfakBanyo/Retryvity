"""The Diagnostics screen: the findings list.

Uses Qt Model/View (QListView + FindingsModel + FindingDelegate) rather
than one widget per finding, per the UI performance rules.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListView, QVBoxLayout, QWidget

from corona_doctor.core.models import Finding
from corona_doctor.ui.components.section_header import SectionHeader
from corona_doctor.ui.delegates.finding_delegate import FindingDelegate
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.models.findings_model import FindingsModel


class DiagnosticsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(SectionHeader("Diagnostics", parent=self))

        self._empty_label = QLabel("No scan has been performed yet.", self)
        self._empty_label.setObjectName("Caption")
        root.addWidget(self._empty_label)

        self._model = FindingsModel(parent=self)
        self._list_view = QListView(self)
        self._list_view.setModel(self._model)
        self._list_view.setItemDelegate(FindingDelegate(self._list_view))
        self._list_view.setUniformItemSizes(True)
        self._list_view.setMouseTracking(True)
        self._list_view.hide()
        root.addWidget(self._list_view, stretch=1)

    def set_findings(self, findings: list[Finding]) -> None:
        self._model.set_findings(findings)
        has_findings = bool(findings)
        self._list_view.setVisible(has_findings)
        self._empty_label.setVisible(not has_findings)

    def clear(self) -> None:
        self.set_findings([])
