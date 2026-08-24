"""Loads and caches SVG icons as QIcon instances.

Icons are read from disk once per (name, color, size) combination and
cached in memory — paint events must never touch the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG_DIR = Path(__file__).parent / "svg"


class IconRegistry:
    """Caches rendered QIcon instances keyed by (name, color, size)."""

    def __init__(self) -> None:
        self._svg_cache: dict[str, str] = {}
        self._icon_cache: dict[tuple[str, str, int], QIcon] = {}

    def _load_svg_source(self, name: str) -> str:
        if name not in self._svg_cache:
            path = _SVG_DIR / f"{name}.svg"
            self._svg_cache[name] = path.read_text(encoding="utf-8")
        return self._svg_cache[name]

    def icon(self, name: str, color: str, size: int = 18) -> QIcon:
        key = (name, color, size)
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached

        svg_source = self._load_svg_source(name).replace("currentColor", color)
        renderer = QSvgRenderer(QByteArray(svg_source.encode("utf-8")))

        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(0)  # transparent
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        icon = QIcon(pixmap)
        self._icon_cache[key] = icon
        return icon


_registry: IconRegistry | None = None


def get_icon_registry() -> IconRegistry:
    global _registry
    if _registry is None:
        _registry = IconRegistry()
    return _registry
