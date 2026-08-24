"""A QAbstractListModel over Finding objects.

Per the UI performance rules, findings are never rendered as one QWidget
per row — this model backs a QListView with FindingDelegate doing the
painting.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from corona_doctor.core.models import Finding

FindingRole = Qt.ItemDataRole.UserRole + 1


class FindingsModel(QAbstractListModel):
    def __init__(self, findings: list[Finding] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._findings: list[Finding] = list(findings or [])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._findings)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or not (0 <= index.row() < len(self._findings)):
            return None
        finding = self._findings[index.row()]
        if role == FindingRole:
            return finding
        if role == Qt.ItemDataRole.DisplayRole:
            return finding.title
        return None

    def set_findings(self, findings: list[Finding]) -> None:
        self.beginResetModel()
        self._findings = list(findings)
        self.endResetModel()

    def append_finding(self, finding: Finding) -> None:
        row = len(self._findings)
        self.beginInsertRows(QModelIndex(), row, row)
        self._findings.append(finding)
        self.endInsertRows()

    def clear(self) -> None:
        self.set_findings([])

    def finding_at(self, row: int) -> Finding | None:
        if 0 <= row < len(self._findings):
            return self._findings[row]
        return None
