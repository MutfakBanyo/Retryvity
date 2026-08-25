"""Unit tests for reports/texture_report.py — pure formatting, no Qt/3ds Max.

Guards the "production report must not include internal debug details"
requirement from docs/TEXTURE_DOCTOR.md: no raw repr, no AnimHandle text,
no rejected-map property dumps — those stay in devtools/texture_probe.py.
"""

from __future__ import annotations

from corona_doctor.core.models import Finding, Repairability, Severity
from corona_doctor.core.texture_models import ScanTimings, SceneInventory, TextureDoctorResult
from corona_doctor.reports.texture_report import format_host_validation_block, format_texture_doctor_report


def _finding(rule_id: str, severity: Severity, title: str = "Some finding", summary: str = "summary text") -> Finding:
    return Finding(
        id=rule_id,
        rule_id=rule_id,
        category="Textures",
        title=title,
        summary=summary,
        severity=severity,
        repairability=Repairability.NONE,
    )


def _result(**overrides) -> TextureDoctorResult:
    defaults = dict(
        inventory=SceneInventory(
            unique_external_texture_count=5,
            missing_texture_count=0,
            oversized_8k_count=0,
            duplicate_group_count=0,
        ),
        texture_references=(),
        findings=(),
        compatibility_warnings=(),
        unknown_map_classes=(),
        errors=(),
        timings=ScanTimings(total_ms=42.0),
    )
    defaults.update(overrides)
    return TextureDoctorResult(**defaults)


def test_report_includes_headline_counts():
    result = _result(inventory=SceneInventory(unique_external_texture_count=138, missing_texture_count=0, oversized_8k_count=3, duplicate_group_count=46))
    report = format_texture_doctor_report(result)
    assert "138 unique files" in report
    assert "0 missing" in report
    assert "3 oversized" in report
    assert "46 reuse/duplicate groups" in report


def test_report_lists_findings_with_severity_and_summary():
    findings = (_finding("TXT-001", Severity.CRITICAL, title="Missing texture", summary="1 texture missing"),)
    report = format_texture_doctor_report(_result(findings=findings))
    assert "[CRITICAL] TXT-001  Missing texture — 1 texture missing" in report


def test_report_says_none_when_no_findings():
    report = format_texture_doctor_report(_result(findings=()))
    assert "(none)" in report


def test_report_includes_compatibility_warnings_when_present():
    report = format_texture_doctor_report(_result(compatibility_warnings=("something looks inconsistent",)))
    assert "Compatibility warnings" in report
    assert "something looks inconsistent" in report


def test_report_omits_compatibility_warnings_section_when_empty():
    report = format_texture_doctor_report(_result(compatibility_warnings=()))
    assert "Compatibility warnings" not in report


def test_report_never_includes_internal_debug_markers():
    """No raw repr, no AnimHandle diagnostics, no rejected-map dumps -
    that content only ever appears in devtools/texture_probe.py's dev
    diagnostics section, never in the production report."""

    report = format_texture_doctor_report(_result())
    for forbidden in ("AnimHandle", "getHandleByAnim", "repr(", "property_names", "0x0000"):
        assert forbidden not in report


def test_host_validation_block_reports_fallback_identities_and_duration():
    result = _result(timings=ScanTimings(total_ms=211.3))
    block = format_host_validation_block(result, fallback_identities=7)
    assert "HOST VALIDATION" in block
    assert "fallback identities used:  7" in block
    assert "211.3 ms" in block


def test_host_validation_block_defaults_fallback_identities_to_zero():
    block = format_host_validation_block(_result())
    assert "fallback identities used:  0" in block
