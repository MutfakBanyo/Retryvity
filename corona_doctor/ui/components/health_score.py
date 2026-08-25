"""A lightweight scene health indicator: a QPainter arc, not a chart library.

No animation loop runs continuously — the widget only repaints when its
score changes.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.typography import FONT_FAMILY, Typography


def _score_color(score: int | None) -> str:
    if score is None:
        return Color.TEXT_MUTED
    if score >= 80:
        return Color.SUCCESS
    if score >= 50:
        return Color.WARNING
    return Color.CRITICAL


class HealthScoreWidget(QWidget):
    """Displays either "—" (no scan yet) or an arc + numeric score."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._score: int | None = None
        self.setMinimumSize(96, 96)

    def set_score(self, score: int | None) -> None:
        if score != self._score:
            self._score = score
            self.update()

    def sizeHint(self):  # noqa: N802 - Qt override naming
        from PySide6.QtCore import QSize

        return QSize(112, 112)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        margin = 8
        rect = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )

        track_pen = QPen(QColor(Color.SURFACE_RAISED))
        track_pen.setWidth(8)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._score is not None:
            arc_pen = QPen(QColor(_score_color(self._score)))
            arc_pen.setWidth(8)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            span = int(360 * 16 * (self._score / 100))
            painter.drawArc(rect, 90 * 16, -span)

        painter.setPen(QColor(Color.TEXT_PRIMARY if self._score is not None else Color.TEXT_MUTED))
        font = QFont(FONT_FAMILY.split(",")[0].strip())
        font.setPixelSize(Typography.DISPLAY.size)
        font.setBold(True)
        painter.setFont(font)
        label = str(self._score) if self._score is not None else "—"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()
