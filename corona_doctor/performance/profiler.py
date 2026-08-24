"""A tiny developer-only profiler for startup and scan timing.

Not exposed in the normal UI. When ``FeatureFlags.developer_mode`` is on,
the developer panel may surface these measurements; otherwise they only
go to the log.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from corona_doctor.logging.logger import get_logger

_logger = get_logger("performance")


@dataclass
class Profiler:
    """Records named timing measurements for one session."""

    measurements: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def measure(self, label: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.measurements[label] = elapsed_ms
            _logger.info("perf: %s took %.1f ms", label, elapsed_ms)

    def report(self) -> dict[str, float]:
        return dict(self.measurements)
