"""Loads rule definitions from rules/definitions.

Empty in the bootstrap phase — no production rules ship yet. This module
exists so future rule files under ``rules/definitions/`` have a single,
predictable place to be discovered from instead of ad-hoc imports.
"""

from __future__ import annotations

from corona_doctor.core.rules import Rule


def load_rules() -> list[Rule]:
    """Return every registered rule. Currently always empty."""

    return []
