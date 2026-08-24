"""Base scanner contract.

A scanner returns domain objects (Findings) — never widgets, never Qt
objects. ``scan()`` is a generator yielding
``(stage_name, completed, total, findings_batch)`` tuples so callers can
surface incremental progress without freezing the host UI.
"""

from __future__ import annotations

from typing import Iterator

from corona_doctor.core.models import Finding

ScanBatch = tuple[str, int, int, list[Finding]]


class BaseScanner:
    id: str = "base"
    name: str = "Base Scanner"

    def is_available(self) -> bool:
        """Whether this scanner's prerequisites are met right now."""

        raise NotImplementedError

    def scan(self) -> Iterator[ScanBatch]:
        raise NotImplementedError
