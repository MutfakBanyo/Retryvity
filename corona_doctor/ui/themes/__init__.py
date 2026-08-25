"""Loads dark.qss with design tokens substituted in.

The QSS file is a template, not the source of truth for values — that
remains ui/design/colors.py, metrics.py and typography.py so nothing
drifts between the two.
"""

from __future__ import annotations

import re
from pathlib import Path

from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.metrics import Radius, Spacing
from corona_doctor.ui.design.typography import FONT_FAMILY, Typography

_QSS_PATH = Path(__file__).parent / "dark.qss"


def load_dark_theme() -> str:
    template = _QSS_PATH.read_text(encoding="utf-8")
    tokens = {
        "BACKGROUND": Color.BACKGROUND,
        "SURFACE": Color.SURFACE,
        "SURFACE_RAISED": Color.SURFACE_RAISED,
        "SURFACE_OVERLAY": Color.SURFACE_OVERLAY,
        "BORDER": Color.BORDER,
        "BORDER_SUBTLE": Color.BORDER_SUBTLE,
        "TEXT_PRIMARY": Color.TEXT_PRIMARY,
        "TEXT_SECONDARY": Color.TEXT_SECONDARY,
        "TEXT_MUTED": Color.TEXT_MUTED,
        "TEXT_ON_ACCENT": Color.TEXT_ON_ACCENT,
        "ACCENT": Color.ACCENT,
        "ACCENT_HOVER": Color.ACCENT_HOVER,
        "ACCENT_MUTED": Color.ACCENT_MUTED,
        "FONT_FAMILY": FONT_FAMILY,
        "DISPLAY_SIZE": Typography.DISPLAY.size,
        "TITLE_SIZE": Typography.TITLE.size,
        "SECTION_TITLE_SIZE": Typography.SECTION_TITLE.size,
        "BODY_SIZE": Typography.BODY.size,
        "BODY_EMPHASIS_SIZE": Typography.BODY_EMPHASIS.size,
        "SECONDARY_SIZE": Typography.SECONDARY.size,
        "CAPTION_SIZE": Typography.CAPTION.size,
        "BUTTON_SIZE": Typography.BUTTON.size,
        "TABLE_SIZE": Typography.TABLE.size,
        "RADIUS_SMALL": Radius.SMALL,
        "RADIUS_MEDIUM": Radius.MEDIUM,
        "RADIUS_LARGE": Radius.LARGE,
        "SPACING_XS": Spacing.XS,
        "SPACING_SM": Spacing.SM,
        "SPACING_MD": Spacing.MD,
        "SPACING_LG": Spacing.LG,
    }
    return re.sub(r"\{([A-Z_]+)\}", lambda m: str(tokens[m.group(1)]), template)
