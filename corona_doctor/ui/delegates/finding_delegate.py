"""Paints one Finding row inside a QListView.

Rule IDs are intentionally not drawn here — they belong in a technical
details pane, not the primary list (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.design.typography import FONT_FAMILY, Typography
from corona_doctor.ui.models.findings_model import FindingRole

_ROW_HEIGHT = 72
_SEVERITY_DOT = 8
_TITLE_ROW_Y = 12
_SUMMARY_ROW_Y = 38
_ROW_TEXT_HEIGHT = 20


class FindingDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), _ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802
        finding = index.data(FindingRole)
        if finding is None:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect: QRect = option.rect
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(Color.SURFACE_OVERLAY))
        elif hovered:
            painter.fillRect(rect, QColor(Color.SURFACE_RAISED))

        pad = Spacing.MD
        x = rect.left() + pad

        dot_color = QColor(Color.for_severity(finding.severity.value))
        dot_y = rect.top() + rect.height() // 2 - _SEVERITY_DOT // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(x, dot_y, _SEVERITY_DOT, _SEVERITY_DOT)
        x += _SEVERITY_DOT + Spacing.SM

        title_font = QFont(FONT_FAMILY.split(",")[0].strip())
        title_font.setPixelSize(Typography.BODY_EMPHASIS.size)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(Color.TEXT_PRIMARY))

        impact_text = f"{len(finding.affected_items)} item(s)" if finding.affected_items else ""
        metrics = QFontMetrics(title_font)
        right_reserved = metrics.horizontalAdvance(impact_text) + Spacing.MD if impact_text else 0

        title_rect = QRect(x, rect.top() + _TITLE_ROW_Y, rect.width() - x - pad - right_reserved, _ROW_TEXT_HEIGHT)
        elided_title = metrics.elidedText(finding.title, Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter, elided_title)

        summary_font = QFont(FONT_FAMILY.split(",")[0].strip())
        summary_font.setPixelSize(Typography.BODY.size)
        painter.setFont(summary_font)
        painter.setPen(QColor(Color.TEXT_SECONDARY))
        summary_metrics = QFontMetrics(summary_font)
        summary_rect = QRect(x, rect.top() + _SUMMARY_ROW_Y, rect.width() - x - pad, _ROW_TEXT_HEIGHT)
        elided_summary = summary_metrics.elidedText(finding.summary, Qt.TextElideMode.ElideRight, summary_rect.width())
        painter.drawText(summary_rect, Qt.AlignmentFlag.AlignVCenter, elided_summary)

        if impact_text:
            painter.setFont(title_font)
            painter.setPen(QColor(Color.TEXT_MUTED))
            impact_rect = QRect(rect.right() - pad - right_reserved + Spacing.MD, rect.top() + _TITLE_ROW_Y, right_reserved, _ROW_TEXT_HEIGHT)
            painter.drawText(impact_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, impact_text)

        painter.restore()
