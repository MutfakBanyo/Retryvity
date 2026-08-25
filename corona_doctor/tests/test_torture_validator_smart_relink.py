"""Unit tests for devtools/torture_validator.py's Smart Relink section —
real recovery-library files under tmp_path, a fake scanner result (no
pymxs). Proves the validator inspects the REAL smart_relink engine's
output, never fakes a PASS from a fixture id."""

from __future__ import annotations

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType, SceneInventory, TextureDoctorResult
from corona_doctor.devtools.torture_assets import write_stub_png
from corona_doctor.devtools.torture_manifest import FixtureRecord, TortureManifest
from corona_doctor.devtools.torture_validator import validate_smart_relink


def _path_info(raw: str, exists: bool | None = False) -> PathInfo:
    return PathInfo(raw_path=raw, normalized_path=raw, comparison_key=raw.lower(), path_type=PathType.LOCAL, exists=exists)


def _missing_ref(filename: str, old_path: str) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id=f"ref-{filename}",
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mtl",
        object_names=("Box01",),
        path_info=_path_info(old_path, exists=False),
        filename=filename,
        extension="png",
    )


def _result(refs) -> TextureDoctorResult:
    return TextureDoctorResult(inventory=SceneInventory(), texture_references=tuple(refs), findings=(), compatibility_warnings=(), unknown_map_classes=(), errors=())


def test_exact_recovery_fixture_passes_when_engine_finds_exact_candidate(tmp_path):
    recovery_root = tmp_path / "recovery_library"
    write_stub_png(recovery_root / "a" / "b" / "cdt_smart_001_wood_floor.png", 64, 64)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_001_wood_floor.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-001",
        category="smart_relink",
        description="exact",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_001_wood_floor.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["passed"] == 1
    assert report["failed"] == 0


def test_exact_recovery_fixture_fails_when_engine_finds_nothing(tmp_path):
    """No recovery file written - the validator must not fake a PASS."""

    recovery_root = tmp_path / "recovery_library"
    recovery_root.mkdir(parents=True)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_001_wood_floor.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-001",
        category="smart_relink",
        description="exact",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_001_wood_floor.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["failed"] == 1
    assert report["passed"] == 0


def test_renamed_recovery_fixture_passes_with_known_metadata(tmp_path):
    recovery_root = tmp_path / "recovery_library"
    write_stub_png(recovery_root / "renamed" / "cdt_smart_002_renamed_asset.png", 512, 512)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_002_original_name.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-002",
        category="smart_relink",
        description="renamed",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        known_width=512,
        known_height=512,
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_002_original_name.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["passed"] == 1


def test_ambiguous_recovery_fixture_passes_when_two_candidates_tie(tmp_path):
    recovery_root = tmp_path / "recovery_library"
    write_stub_png(recovery_root / "v1" / "cdt_smart_003_marble.png", 64, 64)
    write_stub_png(recovery_root / "v2" / "cdt_smart_003_marble.png", 64, 64)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_003_marble.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-003",
        category="smart_relink",
        description="ambiguous",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_003_marble.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["passed"] == 1


def test_no_match_fixture_passes_when_zero_candidates_found(tmp_path):
    recovery_root = tmp_path / "recovery_library"
    recovery_root.mkdir(parents=True)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_004_totally_unique_zzz.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-004",
        category="smart_relink",
        description="no match",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_004_totally_unique_zzz.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["passed"] == 1


def test_unicode_recovery_fixture_passes(tmp_path):
    recovery_root = tmp_path / "recovery_library"
    write_stub_png(recovery_root / "çalışma" / "İstanbul" / "cdt_smart_005_doku.png", 32, 32)
    old_path = str(tmp_path / "missing_originals" / "cdt_smart_005_doku.png")

    fixture = FixtureRecord(
        fixture_id="CDT-SMART-005",
        category="smart_relink",
        description="unicode",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        created_asset_paths=(old_path,),
        recovery_root=str(recovery_root),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,), smart_relink_recovery_root=str(recovery_root))
    result = _result([_missing_ref("cdt_smart_005_doku.png", old_path)])

    report = validate_smart_relink(manifest=manifest, result=result)
    assert report["passed"] == 1


def test_skipped_fixture_reported_as_skip():
    fixture = FixtureRecord(
        fixture_id="CDT-SMART-001",
        category="smart_relink",
        description="exact",
        expected_rule_id="TXT-001",
        expected_detection="",
        expected_fixability="manual",
        expected_repair_behavior="",
        skipped=True,
        skip_reason="not constructible",
        recovery_root="C:/does_not_matter",
    )
    manifest = TortureManifest(created_at="now", asset_directory="C:/tmp", fixtures=(fixture,), smart_relink_recovery_root="C:/does_not_matter")
    report = validate_smart_relink(manifest=manifest, result=_result([]))

    assert report["skipped"] == 1
    assert report["failed"] == 0


def test_no_manifest_returns_error_not_crash(monkeypatch):
    import corona_doctor.devtools.torture_validator as validator_module

    monkeypatch.setattr(validator_module, "load_torture_manifest", lambda: None)
    report = validate_smart_relink()
    assert "error" in report
