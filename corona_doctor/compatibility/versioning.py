"""Safe parsing/comparison helpers for version strings.

3ds Max, Python, Qt and Corona all report versions in slightly different
formats. These helpers never raise on malformed input — they return
``None`` and let the caller decide how to present "unknown".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DOTTED_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_BARE_NUMBER_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class ParsedVersion:
    major: int
    minor: int = 0
    patch: int = 0

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(raw: str | None) -> ParsedVersion | None:
    """Extract the first ``major[.minor[.patch]]`` pattern from ``raw``.

    Returns ``None`` if no numeric version could be found, instead of
    raising — callers should treat that as "unknown".
    """

    if not raw:
        return None

    match = _DOTTED_VERSION_RE.search(raw)
    if match:
        major, minor, patch = match.groups()
        return ParsedVersion(major=int(major), minor=int(minor), patch=int(patch) if patch else 0)

    # Fall back to a bare integer only when no dotted version is present
    # (e.g. Corona's major version is sometimes reported as just "15").
    bare = _BARE_NUMBER_RE.search(raw)
    if bare:
        return ParsedVersion(major=int(bare.group(1)))

    return None


def is_at_least(raw: str | None, minimum: tuple[int, ...]) -> bool | None:
    """Compare ``raw`` against a minimum version tuple.

    Returns ``None`` (uncertain) rather than ``False`` when ``raw`` cannot
    be parsed, so callers don't mistake "unknown" for "unsupported".
    """

    parsed = parse_version(raw)
    if parsed is None:
        return None
    padded_minimum = tuple(minimum) + (0,) * (3 - len(minimum))
    return parsed.as_tuple() >= padded_minimum[:3]
