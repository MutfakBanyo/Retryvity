"""Wraps EnvironmentAdapter as a single-stage scanner.

This scanner never produces Findings against the scene — it only reports
on the host environment itself, which is why it is surfaced through a
dedicated Environment view rather than the findings list.
"""

from __future__ import annotations

from typing import Iterator

from corona_doctor.adapters.environment_adapter import EnvironmentAdapter
from corona_doctor.core.models import EnvironmentReport
from corona_doctor.scanners.base import BaseScanner, ScanBatch


class EnvironmentScanner(BaseScanner):
    id = "environment"
    name = "Environment Probe"

    def __init__(self, adapter: EnvironmentAdapter | None = None) -> None:
        self._adapter = adapter or EnvironmentAdapter()
        self.last_report: EnvironmentReport | None = None

    def is_available(self) -> bool:
        return True

    def scan(self) -> Iterator[ScanBatch]:
        self.last_report = self._adapter.probe()
        yield ("environment", 1, 1, [])
