"""Loads dark.qss with design tokens substituted in.

The QSS file is a template, not the source of truth for values — that
remains ui/design/colors.py, metrics.py and typography.py so nothing
drifts between the two.

Every ``{TOKEN}`` placeholder in dark.qss MUST have a matching entry in
``build_theme_tokens()`` below — see
``corona_doctor/tests/test_theme_tokens.py``, which enumerates every
placeholder actually present in the .qss file and asserts each one
resolves, so a template/token drift (a placeholder added to the .qss
without a matching token, or vice versa) fails CI instead of only
surfacing as a real-host ``KeyError`` at launch.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.metrics import Radius, Spacing
from corona_doctor.ui.design.typography import FONT_FAMILY, Typography

_QSS_PATH = Path(__file__).parent / "dark.qss"
_TOKEN_PATTERN = re.compile(r"\{([A-Z_]+)\}")


def build_theme_tokens() -> dict[str, Any]:
    """The full substitution map for dark.qss's ``{TOKEN}`` placeholders.

    Kept as its own function (rather than inlined in ``load_dark_theme``)
    so tests can import it directly and compare its key set against every
    placeholder dark.qss actually references.
    """

    return {
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
        "SPACING_XS": Spacing.XS,
        "SPACING_SM": Spacing.SM,
        "SPACING_MD": Spacing.MD,
        "SPACING_LG": Spacing.LG,
    }


def _substitute_token(match: re.Match[str], tokens: dict[str, Any]) -> str:
    name = match.group(1)
    if name not in tokens:
        raise KeyError(
            f"dark.qss references undefined theme token '{{{name}}}' — add it to "
            f"build_theme_tokens() in ui/themes/__init__.py (or remove/rename the "
            f"placeholder in dark.qss if it was a typo)."
        )
    return str(tokens[name])


def load_dark_theme() -> str:
    template = _QSS_PATH.read_text(encoding="utf-8")
    tokens = build_theme_tokens()
    try:
        return _TOKEN_PATTERN.sub(lambda m: _substitute_token(m, tokens), template)
    except KeyError as exc:
        # This exact class of failure has hit a real host twice already
        # while the checked-in dark.qss/__init__.py pair on disk were
        # already consistent (see test_theme_tokens.py — the two sides
        # are asserted identical on every test run). That means the
        # process actually executing this code was running a stale
        # cached copy of this module (old bytecode / a module already
        # imported in a long-running 3ds Max session before the fix
        # landed on disk) — not a real token mismatch. Surface enough to
        # tell the two apart on sight instead of a bare KeyError.
        raise KeyError(
            f"{exc.args[0]} — this module loaded from {__file__!r} "
            f"(dark.qss at {_QSS_PATH!r}, last modified {_qss_mtime_str()}). "
            "If that file's content on disk already contains this token, "
            "3ds Max is running a stale cached copy: restart 3ds Max (clears "
            "Python's in-memory module cache), or delete "
            "corona_doctor/ui/themes/__pycache__ and corona_doctor/ui/design/__pycache__."
        ) from exc


def _qss_mtime_str() -> str:
    try:
        import datetime

        return datetime.datetime.fromtimestamp(_QSS_PATH.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return "unknown"
