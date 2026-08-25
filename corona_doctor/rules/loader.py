"""Loads rule definitions from rules/definitions.

A single, predictable place production scanners get their rules from,
instead of importing rule modules ad-hoc. Currently aggregates the
Texture Doctor rule family (TXT-00x); future rule families extend this
function the same way.
"""

from __future__ import annotations

from corona_doctor.core.rules import Rule
from corona_doctor.core.texture_models import TextureThresholds


def load_rules(texture_thresholds: TextureThresholds | None = None) -> list[Rule]:
    """Return every registered rule."""

    from corona_doctor.rules.definitions.texture_rules import build_texture_rules  # noqa: PLC0415

    return build_texture_rules(texture_thresholds)
