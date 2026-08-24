"""Unit tests for the diagnostic engine / event flow. No 3ds Max required."""

from __future__ import annotations

import pytest

from corona_doctor.core.diagnostics import DiagnosticEngine, ScannerUnavailableError
from corona_doctor.core.events import EventBus, FindingAdded, ScanFailed, ScanFinished, ScanStarted
from corona_doctor.core.models import Finding, Severity
from corona_doctor.scanners.base import BaseScanner


class _FakeScanner(BaseScanner):
    id = "fake"
    name = "Fake Scanner"

    def is_available(self) -> bool:
        return True

    def scan(self):
        finding = Finding(id="f1", rule_id="r1", category="Test", title="t", summary="s", severity=Severity.WARNING)
        yield ("stage1", 1, 2, [finding])
        yield ("stage2", 2, 2, [])


class _UnavailableScanner(BaseScanner):
    id = "unavailable"
    name = "Unavailable Scanner"

    def is_available(self) -> bool:
        return False

    def scan(self):
        yield ("stage", 1, 1, [])


def test_run_publishes_expected_event_sequence():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: seen.append(type(e).__name__))

    engine = DiagnosticEngine(bus)
    result = engine.run(_FakeScanner())

    assert result.summary.total == 1
    assert seen[0] == "ScanStarted"
    assert "FindingAdded" in seen
    assert seen[-1] == "ScanFinished"


def test_run_raises_and_publishes_failure_for_unavailable_scanner():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: seen.append(e))

    engine = DiagnosticEngine(bus)
    with pytest.raises(ScannerUnavailableError):
        engine.run(_UnavailableScanner())

    assert any(isinstance(e, ScanFailed) for e in seen)


def test_iter_run_yields_once_per_batch():
    bus = EventBus()
    engine = DiagnosticEngine(bus)
    generator = engine.iter_run(_FakeScanner())

    next(generator)  # stage1
    next(generator)  # stage2
    with pytest.raises(StopIteration) as stop:
        next(generator)  # generator body completes, result is returned

    result = stop.value.value
    assert result.summary.total == 1
