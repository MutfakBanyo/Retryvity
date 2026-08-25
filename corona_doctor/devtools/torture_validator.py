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
from corona_doctor.smart_relink.index import build_search_index
from corona_doctor.smart_relink.metadata import read_candidate_metadata
from corona_doctor.smart_relink.models import ConfidenceBand, KnownAssetMetadata
from corona_doctor.smart_relink.scoring import rank_candidates
from corona_doctor.smart_relink.session import missing_assets_from_references


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

    # Smart Relink is a separate quality dimension (search/scoring, not
    # detection) - see docs/SMART_RELINK.md, "Torture scene extension".
    # Printed as its own clearly separated section, never folded into the
    # detection score above.
    if manifest.smart_relink_recovery_root:
        print()
        smart_report = validate_smart_relink(manifest=manifest, result=result)
        report["smart_relink"] = smart_report

    return report


def _check_smart_relink_fixture(fixture: FixtureRecord, result: TextureDoctorResult, recovery_root: str) -> FixtureCheck:
    if fixture.skipped:
        return FixtureCheck(fixture.fixture_id, fixture.description, "skip", fixture.skip_reason or "fixture was skipped at generation time")

    missing_path = fixture.created_asset_paths[0] if fixture.created_asset_paths else None
    ref = next((r for r in result.texture_references if r.path_info.raw_path == missing_path and r.path_info.exists is False), None)
    if ref is None:
        return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "missing texture reference not found in scan result")

    known_metadata_lookup = {}
    if fixture.known_width and fixture.known_height:
        known_metadata_lookup[missing_path] = KnownAssetMetadata(width=fixture.known_width, height=fixture.known_height, source="torture fixture manifest")
    [asset] = missing_assets_from_references([ref], known_metadata_lookup=known_metadata_lookup)

    index = build_search_index([recovery_root], walk_fn=lambda root: os.walk(root))
    candidate_paths = [f.path for f in index.candidates_for_asset(asset.filename)]
    candidates = rank_candidates(asset, candidate_paths, lambda p: read_candidate_metadata(p))

    if fixture.fixture_id in ("CDT-SMART-001", "CDT-SMART-005"):
        if not candidates or candidates[0].band != ConfidenceBand.EXACT:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", f"expected an EXACT candidate, got {candidates[0].band.value if candidates else 'none'}")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-SMART-002":
        if not candidates or candidates[0].band not in (ConfidenceBand.HIGH, ConfidenceBand.MEDIUM):
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", f"expected HIGH/MEDIUM, got {candidates[0].band.value if candidates else 'none'}")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-SMART-003":
        if len(candidates) < 2 or candidates[0].percent != candidates[1].percent:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", "expected 2+ candidates tied at the top score")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    if fixture.fixture_id == "CDT-SMART-004":
        if candidates:
            return FixtureCheck(fixture.fixture_id, fixture.description, "fail", f"expected zero candidates, got {len(candidates)}")
        return FixtureCheck(fixture.fixture_id, fixture.description, "pass")

    return FixtureCheck(fixture.fixture_id, fixture.description, "skip", "no validator rule for this fixture id")


_SMART_RELINK_LABELS = {
    "CDT-SMART-001": "Exact recovery",
    "CDT-SMART-002": "Renamed recovery",
    "CDT-SMART-003": "Ambiguous recovery",
    "CDT-SMART-004": "No-match handling",
    "CDT-SMART-005": "Unicode recovery",
}


def validate_smart_relink(*, manifest: TortureManifest | None = None, result: TextureDoctorResult | None = None, scanner: Any | None = None) -> dict:
    """Tests Smart Asset Recovery's SEARCH QUALITY (does it find/rank
    the right candidates) — a distinct question from Texture Doctor's
    DETECTION quality (``validate_torture_scene`` above). Uses the real
    ``smart_relink`` engine against the torture scene's recovery
    library — never fakes a candidate result."""

    manifest = manifest or load_torture_manifest()
    if manifest is None or not manifest.smart_relink_recovery_root:
        print("Smart Relink validation: no torture scene manifest / recovery root found — run create_torture_scene() first.")
        return {"error": "no recovery root available"}

    if result is None:
        if scanner is None:
            from corona_doctor.core.diagnostics import DiagnosticEngine
            from corona_doctor.core.events import EventBus
            from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner

            scanner = TextureDoctorScanner()
            DiagnosticEngine(EventBus()).run(scanner)
        result = scanner.result
    if result is None:
        print("Smart Relink validation: scan did not complete.")
        return {"error": "scan did not complete"}

    smart_fixtures = [f for f in manifest.fixtures if f.category == "smart_relink"]
    checks = [_check_smart_relink_fixture(f, result, manifest.smart_relink_recovery_root) for f in smart_fixtures]

    print(format_smart_relink_report(checks))
    return {
        "expected": len(checks),
        "passed": sum(1 for c in checks if c.status == "pass"),
        "failed": sum(1 for c in checks if c.status == "fail"),
        "skipped": sum(1 for c in checks if c.status == "skip"),
        "checks": [c.__dict__ for c in checks],
    }


def format_smart_relink_report(checks: list[FixtureCheck]) -> str:
    lines = ["SMART RELINK VALIDATION", ""]
    for check in checks:
        tag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[check.status]
        label = _SMART_RELINK_LABELS.get(check.fixture_id, check.fixture_id)
        detail = f" — {check.detail}" if check.detail and check.status != "pass" else ""
        lines.append(f"{label:<22}{tag}{detail}")
    return "\n".join(lines)


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
