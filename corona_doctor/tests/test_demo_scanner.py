"""Unit tests for the deterministic demo scanner. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.core.models import Severity
from corona_doctor.scanners.demo_scanner import DemoScanner


def test_demo_scanner_is_always_available():
    assert DemoScanner().is_available() is True


def test_demo_scanner_yields_multiple_stages():
    stages = [stage for stage, *_ in DemoScanner().scan()]
    assert len(stages) > 1
    assert stages == sorted(set(stages), key=stages.index)  # no duplicate stage names


def test_demo_scanner_produces_deterministic_counts():
    findings = []
    for _, _, _, batch in DemoScanner().scan():
        findings.extend(batch)

    severities = [f.severity for f in findings]
    assert severities.count(Severity.CRITICAL) == 2
    assert severities.count(Severity.WARNING) == 4
    assert severities.count(Severity.OPTIMIZATION) == 3


def test_demo_scanner_findings_are_clearly_marked_as_demo_data():
    for _, _, _, batch in DemoScanner().scan():
        for finding in batch:
            assert "Demo finding" in finding.details
