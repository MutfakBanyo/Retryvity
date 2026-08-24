"""Spacing and radius tokens, expressed in logical pixels.

Qt automatically scales logical pixels for the active DPI, so widget code
should size things in these units rather than hard-coded device pixels.
"""

from __future__ import annotations


class Radius:
    SMALL = 4
    MEDIUM = 8
    LARGE = 12


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Breakpoint:
    """Logical-pixel width thresholds for the responsive layout states."""

    COMPACT_MAX = 420
    STANDARD_MAX = 720
