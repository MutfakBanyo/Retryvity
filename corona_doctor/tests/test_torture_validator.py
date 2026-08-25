"""Unit tests for devtools/torture_validator.py — a fake scanner (real
TextureDoctorResult data, no pymxs) proves the validator actually
inspects scan results rather than trusting fixture names/status."""

from __future__ import annotations

from corona_doctor.core.models import Finding, Repairability, Severity
from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType, SceneInventory, TextureDoctorResult
from corona_doctor.devtools.torture_manifest import FixtureRecord, TortureManifest
from corona_doctor.devtools.torture_validator import validate_torture_scene


class _FakeScanner:
    def __init__(self, result: TextureDoctorResult) -> None:
        self.result = result


def _path_info(raw: str, exists: bool | None = True) -> PathInfo:
    return PathInfo(raw_path=raw, normalized_path=raw, comparison_key=raw.lower(), path_type=PathType.LOCAL, exists=exists)


def _ref(filename: str, *, exists=True, width=None, height=None, reference_count=1, object_names=("Box01",)) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id=f"ref-{filename}",
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mtl",
        object_names=object_names,
        path_info=_path_info(f"C:/proj/{filename}", exists=exists),
        filename=filename,
        extension=filename.rsplit(".", 1)[-1],
        width=width,
        height=height,
        reference_count=reference_count,
    )


def _finding(rule_id: str) -> Finding:
    return Finding(id=rule_id, rule_id=rule_id, category="Textures", title=rule_id, summary="", severity=Severity.INFO, repairability=Repairability.NONE)


def _result(refs, findings) -> TextureDoctorResult:
    return TextureDoctorResult(
        inventory=SceneInventory(),
        texture_references=tuple(refs),
        findings=tuple(findings),
        compatibility_warnings=(),
        unknown_map_classes=(),
        errors=(),
    )


def _fixture(fixture_id: str, asset_path: str, **kwargs) -> FixtureRecord:
    defaults = dict(
        category="texture",
        description=fixture_id,
        expected_rule_id=None,
        expected_detection="",
        expected_fixability="n/a",
        expected_repair_behavior="",
        created_asset_paths=(asset_path,),
    )
    defaults.update(kwargs)
    return FixtureRecord(fixture_id=fixture_id, **defaults)


def test_missing_texture_fixture_passes_when_actually_reported_missing():
    fixture = _fixture("CDT-TEX-001", "gone.png")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))
    scanner = _FakeScanner(_result([_ref("gone.png", exists=False)], [_finding("TXT-001")]))

    report = validate_torture_scene(manifest=manifest, scanner=scanner)
    assert report["passed"] == 1
    assert report["failed"] == 0


def test_missing_texture_fixture_fails_when_scanner_does_not_actually_report_it():
    """The validator must not pass a fixture just because it EXISTS in
    the manifest - it must inspect the real scan result."""

    fixture = _fixture("CDT-TEX-001", "gone.png")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))
    scanner = _FakeScanner(_result([_ref("gone.png", exists=True)], []))  # scanner disagrees: file "exists"

    report = validate_torture_scene(manifest=manifest, scanner=scanner)
    assert report["failed"] == 1
    assert report["passed"] == 0


def test_reused_texture_fixture_requires_actual_reference_count():
    fixture = _fixture("CDT-TEX-003", "shared.png")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))

    scanner_ok = _FakeScanner(_result([_ref("shared.png", reference_count=3)], [_finding("TXT-002")]))
    assert validate_torture_scene(manifest=manifest, scanner=scanner_ok)["passed"] == 1

    scanner_bad = _FakeScanner(_result([_ref("shared.png", reference_count=1)], [_finding("TXT-002")]))
    assert validate_torture_scene(manifest=manifest, scanner=scanner_bad)["failed"] == 1


def test_oversized_texture_fixture_checks_actual_dimensions():
    fixture = _fixture("CDT-TEX-004", "big.png")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))

    scanner_ok = _FakeScanner(_result([_ref("big.png", width=8192, height=8192)], [_finding("TXT-004")]))
    assert validate_torture_scene(manifest=manifest, scanner=scanner_ok)["passed"] == 1

    scanner_small = _FakeScanner(_result([_ref("big.png", width=1024, height=1024)], [_finding("TXT-004")]))
    assert validate_torture_scene(manifest=manifest, scanner=scanner_small)["failed"] == 1


def test_discovery_only_fixture_passes_when_texture_is_found():
    fixture = _fixture("CDT-TEX-006", "çalışma.png")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))
    scanner = _FakeScanner(_result([_ref("çalışma.png")], []))

    report = validate_torture_scene(manifest=manifest, scanner=scanner)
    assert report["passed"] == 1


def test_multi_object_fixture_reports_partial_traceability_without_failing():
    fixture = _fixture("CDT-TEX-009", "multi.png", created_object_names=("Box1", "Box2", "Box3"))
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))
    scanner = _FakeScanner(_result([_ref("multi.png", object_names=("Box1",))], []))

    report = validate_torture_scene(manifest=manifest, scanner=scanner)
    assert report["passed"] == 1
    assert "partial" in report["checks"][0]["detail"]


def test_skipped_fixture_is_reported_as_skip_not_fail():
    fixture = _fixture("CDT-TEX-004", "big.png", skipped=True, skip_reason="not constructible")
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,))
    scanner = _FakeScanner(_result([], []))

    report = validate_torture_scene(manifest=manifest, scanner=scanner)
    assert report["skipped"] == 1
    assert report["failed"] == 0


def test_no_manifest_returns_an_error_not_a_crash(tmp_path, monkeypatch):
    import corona_doctor.devtools.torture_validator as validator_module

    monkeypatch.setattr(validator_module, "load_torture_manifest", lambda: None)
    report = validate_torture_scene()
    assert "error" in report
