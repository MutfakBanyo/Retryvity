"""Centralized product identity/authorship metadata.

Single source of truth for anything the UI shows about *what this
product is* and *who made it* — the About screen, window/dock titles,
and any future export/report header all read from here instead of each
hardcoding their own copy, so name/version/author text can never drift
out of sync between widgets (see docs/BRANDING.md).

``PRODUCT_VERSION`` is the full internal/build version string (may carry
a pre-release suffix) — keep it out of primary user-facing UI; use
``PRODUCT_VERSION_DISPLAY`` there instead. Internal diagnostics
(``host_validation.py``, logs) may still use the full string.
"""

from __future__ import annotations

from corona_doctor.version import __version__


def _display_version(raw: str) -> str:
    """"0.2.0" -> "v0.2"; degrades gracefully for any unexpected shape."""

    parts = raw.split(".")
    major_minor = ".".join(parts[:2]) if len(parts) >= 2 else raw
    return f"v{major_minor}"


PRODUCT_NAME = "Corona Doctor"
PRODUCT_TAGLINE = "Scene diagnostics for 3ds Max + Corona"

PRODUCT_VERSION = __version__
PRODUCT_VERSION_DISPLAY = _display_version(__version__)

AUTHOR_NAME = "Murat Yüksel"
AUTHOR_WEBSITE_LABEL = "yukselmurat.com"
AUTHOR_WEBSITE_URL = "https://yukselmurat.com"
AUTHOR_INSTAGRAM_LABEL = "@yuxelmurat"
AUTHOR_INSTAGRAM_URL = "https://instagram.com/yuxelmurat"
