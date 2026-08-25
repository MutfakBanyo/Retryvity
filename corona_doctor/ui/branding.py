"""Loads the Corona Doctor brand mark for in-app display.

Distinct from ``ui/icons/icon_registry.py``: that module recolors small
stroke icons on demand for the nav sidebar (many colors, many sizes,
cached per combination). The brand mark is only ever shown at a
handful of fixed spots (About screen, dock/window icon) at a fixed
accent color, so it is loaded directly with a much simpler per-size
cache. See ``assets/branding/corona_doctor_mark.svg`` and
docs/BRANDING.md.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from corona_doctor.ui.design.colors import Color

# corona_doctor/ui/branding.py -> corona_doctor/ui -> corona_doctor -> repo root
_MARK_PATH = Path(__file__).resolve().parents[2] / "assets" / "branding" / "corona_doctor_mark.svg"

_pixmap_cache: dict[tuple[int, str], QPixmap] = {}


def load_brand_pixmap(size: int, color: str = Color.ACCENT) -> QPixmap:
    """Render the brand mark at ``size`` px, tinted ``color``. Cached."""

    key = (size, color)
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached

    source = _MARK_PATH.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))

    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(0)  # transparent
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    _pixmap_cache[key] = pixmap
    return pixmap


def load_brand_icon(size: int, color: str = Color.ACCENT) -> QIcon:
    """The brand mark as a :class:`QIcon` — dock/window icon usage."""

    return QIcon(load_brand_pixmap(size, color))
