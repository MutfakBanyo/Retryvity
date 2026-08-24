"""Dark theme color tokens.

Tonal surfaces rather than pure black, per the product design direction.
Every color used anywhere in the UI must come from this module — no
hex literals scattered through widget code.
"""

from __future__ import annotations


class Color:
    # Base surfaces (layered, not pure black)
    BACKGROUND = "#151719"
    SURFACE = "#1C1F22"
    SURFACE_RAISED = "#22262A"
    SURFACE_OVERLAY = "#282D32"

    # Borders / separators (low-opacity light, simulated as flat tones
    # since Qt stylesheets handle alpha poorly across nested widgets)
    BORDER = "#33383D"
    BORDER_SUBTLE = "#2A2F34"

    # Text
    TEXT_PRIMARY = "#F2F3F5"
    TEXT_SECONDARY = "#A8AFB8"
    TEXT_MUTED = "#6E7580"
    TEXT_ON_ACCENT = "#0F1113"

    # Accent / brand
    ACCENT = "#5B8CFF"
    ACCENT_HOVER = "#7AA1FF"
    ACCENT_MUTED = "#2A3550"

    # Semantic status colors
    CRITICAL = "#F0554B"
    CRITICAL_MUTED = "#3A2224"
    WARNING = "#E8A93B"
    WARNING_MUTED = "#3A3020"
    OPTIMIZATION = "#4FB0E0"
    OPTIMIZATION_MUTED = "#1F3540"
    SUCCESS = "#4CC38A"
    SUCCESS_MUTED = "#1D3329"
    INFO = "#9AA3AF"
    INFO_MUTED = "#262A2E"

    @staticmethod
    def for_severity(severity: str) -> str:
        return {
            "critical": Color.CRITICAL,
            "warning": Color.WARNING,
            "optimization": Color.OPTIMIZATION,
            "healthy": Color.SUCCESS,
            "info": Color.INFO,
        }.get(severity, Color.INFO)

    @staticmethod
    def muted_for_severity(severity: str) -> str:
        return {
            "critical": Color.CRITICAL_MUTED,
            "warning": Color.WARNING_MUTED,
            "optimization": Color.OPTIMIZATION_MUTED,
            "healthy": Color.SUCCESS_MUTED,
            "info": Color.INFO_MUTED,
        }.get(severity, Color.INFO_MUTED)
