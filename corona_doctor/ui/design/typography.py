"""Type scale tokens.

Font family falls back through the platform's standard UI faces; Corona
Doctor does not bundle a custom font in this phase.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT_FAMILY = "Segoe UI, -apple-system, Helvetica Neue, Arial, sans-serif"


@dataclass(frozen=True)
class TypeStyle:
    size: int
    weight: int
    letter_spacing: float = 0.0


class Typography:
    CAPTION = TypeStyle(size=10, weight=400)
    BODY = TypeStyle(size=12, weight=400)
    BODY_STRONG = TypeStyle(size=12, weight=600)
    TITLE = TypeStyle(size=15, weight=600)
    DISPLAY = TypeStyle(size=28, weight=700)
