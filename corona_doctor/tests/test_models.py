"""Unit tests for core diagnostic domain models. No 3ds Max required."""

from __future__ import annotations

import pytest

from corona_doctor.core.models import Finding, Impact, Repairability, ScanSummary, Severity


def _finding(severity: Severity, **overrides) -> Finding:
    defaults = dict(
        id="f1",
        rule_id="r1",
        category="Test",
        title="Title",
        summary="Summary",
        severity=severity,
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_finding_confidence_validation():
    with pytest.raises(ValueError):
        _finding(Severity.INFO, confidence=1.5)
    with pytest.raises(ValueError):
        _finding(Severity.INFO, confidence=-0.1)


def test_finding_defaults():
    finding = _finding(Severity.WARNING)
    assert finding.repairability == Repairability.NONE
    assert finding.performance_impact == Impact.UNKNOWN
    assert finding.affected_items == ()


def test_scan_summary_from_empty_findings():
    summary = ScanSummary.from_findings([])
    assert summary.total == 0
    assert summary.health_score == 100


def test_scan_summary_counts_by_severity():
    findings = [
        _finding(Severity.CRITICAL, id="c1"),
        _finding(Severity.CRITICAL, id="c2"),
        _finding(Severity.WARNING, id="w1"),
        _finding(Severity.OPTIMIZATION, id="o1"),
    ]
    summary = ScanSummary.from_findings(findings)
    assert summary.total == 4
    assert summary.critical == 2
    assert summary.warning == 1
    assert summary.optimization == 1


def test_scan_summary_health_score_never_negative():
    findings = [_finding(Severity.CRITICAL, id=f"c{i}") for i in range(20)]
    summary = ScanSummary.from_findings(findings)
    assert summary.health_score == 0


def test_scan_summary_health_score_capped_at_100():
    findings = [_finding(Severity.HEALTHY, id="h1")]
    summary = ScanSummary.from_findings(findings)
    assert summary.health_score == 100
