"""Type scale tokens — the single source of truth for every font size/weight
used anywhere in the UI (QSS templates, painted delegates, QFont objects).

Never hardcode a pixel font size directly in a widget, delegate, or QSS
file — add/use a semantic token here instead, so the whole UI stays
readable and consistent by construction. See docs/ARCHITECTURE.md,
"Typography".

Font family falls back through the platform's standard UI faces; Corona
Doctor does not bundle a custom font in this phase.

Sizes were raised for v0.2 after real-host testing showed the original
scale (9-12px body/caption text) was uncomfortably small to read at
normal viewing distance inside 3ds Max, then raised again by a further
flat +4px across every token per direct user request. Readability takes
priority over fitting more information on screen — see
docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT_FAMILY = "Segoe UI, -apple-system, Helvetica Neue, Arial, sans-serif"


@dataclass(frozen=True)
class TypeStyle:
    size: int
    weight: int
    letter_spacing: float = 0.0  # not applied via QSS (unsupported there); for manual QFont use only


class Typography:
    """Semantic type scale. Pick the token that matches the text's role,
    not a size that happens to fit — see each token's usage note."""

    # Panel-level branding text: the About screen's product name. Not used
    # for ordinary section headers — see SECTION_TITLE for those.
    DISPLAY = TypeStyle(size=28, weight=700)

    # Major/top-level titles.
    TITLE = TypeStyle(size=23, weight=700)

    # Section headers atop every screen (SectionHeader component) and
    # prominent in-panel headings (e.g. a details pane's title row).
    SECTION_TITLE = TypeStyle(size=20, weight=600)

    # Ordinary readable body text — the UI default (see QWidget in dark.qss).
    BODY = TypeStyle(size=17, weight=400)
    BODY_EMPHASIS = TypeStyle(size=17, weight=600)

    # Secondary/supporting text: field labels, subordinate descriptions.
    SECONDARY = TypeStyle(size=16, weight=400)

    # Genuinely secondary information only (empty states, timestamps,
    # per-tile labels) — never body copy.
    CAPTION = TypeStyle(size=15, weight=500)

    BUTTON = TypeStyle(size=17, weight=600)

    # Table/list cell text (texture table, finding rows).
    TABLE = TypeStyle(size=16, weight=400)

    # Small status pills (severity/state badges).
    BADGE = TypeStyle(size=15, weight=700, letter_spacing=0.3)
