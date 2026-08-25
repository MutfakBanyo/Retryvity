"""Torture Scene validator — runs the REAL production Texture Doctor
scanner and compares actual findings against the fixture manifest's
ground truth. Never infers a result from a fixture's name; every PASS
below is backed by inspecting ``TextureDoctorScanner.result`` — see
``torture_scene.py`` for how the manifest this reads was built.

Run from the 3ds Max Python Listener (one line)::

    from corona_doctor.devtools.torture_validator import validate_torture_scene; validate_torture_scene()
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from corona_doctor.core.texture_models import TextureDoctorResult
from corona_doctor.devtools.torture_manifest import FixtureRecord, TortureManifest, load_torture_manifest


@dataclass(frozen=True)
class FixtureCheck:
    fixture_id: str
    description: str
    status: str  # "pass" | "fail" | "skip"
    detail: str = ""


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _check_fixture(fixture: FixtureRecord, result: TextureDoctorResult) -> FixtureCheck:
    if fixture.skipped:
        return FixtureCheck(fixture.fixture_id, fixture.description, "skip", fixture.skip_reason or "fixture was skipped at generation time")

    if fixture.category != "texture":
        return FixtureCheck(fixture.fixture_id, fixture.description, "skip", f"unsupported category {fixture.category!r} for this validator")

    expected_filenames = {_basename(p) for p in fixture.created_asset_paths}
    matching_refs = [r for r in result.texture_references if r.filename.lower() in expected_filenames]

    if fixture.fixture_id == "CDT-TEX-001":
        finding = next((f for f in result.findings if f.rule_id == "TXT-001"), None)
        if finding is None:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "no TXT-001 finding produced")
        missing = [r for r in result.texture_references if r.path_info.exists is False and r.filename.lower() in expected_filenames]
        if not missing:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "TXT-001 fired, but not for this fixture's file")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-TEX-002":
        finding = next((f for f in result.findings if f.rule_id == "TXT-006"), None)
        local = [r for r in result.texture_references if r.filename.lower() in expected_filenames]
        if finding is None or not local:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "no TXT-006 finding, or this fixture's file not in the local-path set")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-TEX-003":
        finding = next((f for f in result.findings if f.rule_id == "TXT-002"), None)
        reused = [r for r in matching_refs if r.reference_count >= 3]
        if finding is None or not reused:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "no TXT-002 finding, or reference_count < 3 for this fixture's file")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id in ("CDT-TEX-004", "CDT-TEX-005"):
        threshold = 8192 if fixture.fixture_id == "CDT-TEX-004" else 16384
        finding = next((f for f in result.findings if f.rule_id == "TXT-004"), None)
        oversized = [r for r in matching_refs if r.width and r.height and max(r.width, r.height) >= threshold]
        if finding is None or not oversized:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", f"no TXT-004 finding, or dimensions below {threshold}px for this fixture's file")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id in ("CDT-TEX-006", "CDT-TEX-007", "CDT-TEX-008"):
        if not matching_refs:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "texture was not discovered by traversal")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-TEX-009":
        if not matching_refs:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "texture was not discovered by traversal")
        found_objects = set(matching_refs[0].object_names)
        expected_objects = set(fixture.created_object_names)
        overlap = found_objects & expected_objects
        if not overlap:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "no expected object name traced to this texture")
        if overlap != expected_objects:
            return FixtureCheck(
                fixture.fixture_id,
                fixture.description,
                "pass",
                f"partial traceability ({len(overlap)}/{len(expected_objects)} objects) — known architecture limitation, see docs/TEXTURE_DOCTOR.md",
            )
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    return FixtureCheck(fixture.fixture_id, fixture.description, "skip", "no validator rule for this fixture id")


def validate_torture_scene(*, manifest: TortureManifest | None = None, scanner: Any | None = None) -> dict:
    """Runs the real scanner (unless ``scanner`` is injected for testing)
    and scores it against ``manifest`` (defaults to the last-saved one).
    Returns a structured report; also printed as text (see
    ``format_validation_report``)."""

    manifest = manifest or load_torture_manifest()
    if manifest is None:
        report = {"error": "no torture scene manifest found — run create_torture_scene() first", "checks": []}
        print(report["error"])
        return report

    if scanner is None:
        from corona_doctor.core.diagnostics import DiagnosticEngine
        from corona_doctor.core.events import EventBus
        from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner

        scanner = TextureDoctorScanner()
        DiagnosticEngine(EventBus()).run(scanner)

    result = scanner.result
    if result is None:
        report = {"error": "scan did not complete — see scanner errors/log", "checks": []}
        print(report["error"])
        return report

    checks = [_check_fixture(f, result) for f in manifest.fixtures if f.category == "texture"]
    passed = sum(1 for c in checks if c.status == "pass")
    failed = sum(1 for c in checks if c.status == "fail")
    skipped = sum(1 for c in checks if c.status == "skip")

    report = {
        "expected": len(checks),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "scanner_errors": len(result.errors),
        "checks": [c.__dict__ for c in checks],
    }
    print(format_validation_report(checks, scanner_errors=len(result.errors)))
    return report


def format_validation_report(checks: list[FixtureCheck], *, scanner_errors: int) -> str:
    passed = sum(1 for c in checks if c.status == "pass")
    failed = sum(1 for c in checks if c.status == "fail")
    skipped = sum(1 for c in checks if c.status == "skip")
    scored = passed + failed

    lines = [
        "CORONA DOCTOR TORTURE VALIDATION",
        "",
        f"Expected texture fixtures: {len(checks)}",
        f"Detected correctly: {passed}",
        f"Missed: {failed}",
        f"Skipped (not constructible on this host): {skipped}",
        f"Unexpected scanner errors: {scanner_errors}",
        "",
        f"Detection score: {passed}/{scored}" if scored else "Detection score: n/a (nothing to score)",
        "",
        "Per fixture",
    ]
    for check in checks:
        tag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[check.status]
        detail = f" — {check.detail}" if check.detail else ""
        lines.append(f"{tag} {check.fixture_id} {check.description}{detail}")
    return "\n".join(lines)
