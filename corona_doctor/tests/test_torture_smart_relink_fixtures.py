"""Unit tests for devtools/torture_scene.py::create_smart_relink_fixtures
— a fake pymxs runtime (box/material/bitmap construction only), real
tmp_path filesystem for the recovery library files."""

from __future__ import annotations

from corona_doctor.devtools.torture_scene import create_smart_relink_fixtures


class _FakeBitmap:
    def __init__(self) -> None:
        self.filename: str | None = None


class _FakeMaterial:
    def __init__(self) -> None:
        self.name = ""
        self.sub_texmaps: list = [None]  # one slot, matches getNumSubTexmaps==1

    @property
    def material(self):
        return self


class _FakeBox:
    def __init__(self, name: str = "") -> None:
        self.name = name
        self.material = None


class _FakeRuntime:
    def __init__(self) -> None:
        self.CoronaBitmap = _FakeBitmap
        self.CoronaPhysicalMtl = _FakeMaterial
        self.Box = lambda name="": _FakeBox(name)

    def isProperty(self, obj, name):
        return hasattr(obj, name)

    def getNumSubTexmaps(self, mtl):
        return len(mtl.sub_texmaps)

    def setSubTexmap(self, mtl, index, bitmap):
        mtl.sub_texmaps[index - 1] = bitmap


def _fixture_ids(fixtures):
    return {f.fixture_id for f in fixtures}


def test_creates_all_five_smart_relink_fixtures(tmp_path):
    rt = _FakeRuntime()
    fixtures = create_smart_relink_fixtures(rt, tmp_path)

    assert _fixture_ids(fixtures) == {
        "CDT-SMART-001",
        "CDT-SMART-002",
        "CDT-SMART-003",
        "CDT-SMART-004",
        "CDT-SMART-005",
    }
    assert all(not f.skipped for f in fixtures)


def test_cdt_smart_001_writes_exact_file_deep_in_recovery_library(tmp_path):
    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    fixture = next(f for f in fixtures if f.fixture_id == "CDT-SMART-001")

    recovery_path = tmp_path / "recovery_library" / "a" / "b" / "c" / "cdt_smart_001_wood_floor.png"
    assert recovery_path.is_file()
    assert str(recovery_path) in fixture.created_asset_paths
    # The missing (original) path must never actually exist on disk.
    missing_path = tmp_path / "missing_originals" / "cdt_smart_001_wood_floor.png"
    assert not missing_path.exists()


def test_cdt_smart_002_records_known_dimensions_matching_the_renamed_file(tmp_path):
    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    fixture = next(f for f in fixtures if f.fixture_id == "CDT-SMART-002")

    assert fixture.known_width == 512
    assert fixture.known_height == 512
    renamed_path = tmp_path / "recovery_library" / "renamed" / "cdt_smart_002_renamed_asset.png"
    assert renamed_path.is_file()

    from corona_doctor.adapters.image_metadata import read_image_dimensions

    assert read_image_dimensions(str(renamed_path)) == (512, 512)


def test_cdt_smart_003_writes_two_ambiguous_candidates(tmp_path):
    from pathlib import Path

    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    fixture = next(f for f in fixtures if f.fixture_id == "CDT-SMART-003")

    candidate_paths = [p for p in fixture.created_asset_paths if "marble_v" in p]
    assert len(candidate_paths) == 2
    for p in candidate_paths:
        assert Path(p).is_file()


def test_cdt_smart_004_has_no_recovery_candidate_written(tmp_path):
    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    fixture = next(f for f in fixtures if f.fixture_id == "CDT-SMART-004")

    # Only the (never-written) missing path is recorded - no real file.
    assert len(fixture.created_asset_paths) == 1
    for p in fixture.created_asset_paths:
        from pathlib import Path

        assert not Path(p).exists()


def test_cdt_smart_005_unicode_candidate_path_is_written_and_readable(tmp_path):
    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    fixture = next(f for f in fixtures if f.fixture_id == "CDT-SMART-005")

    unicode_path = tmp_path / "recovery_library" / "çalışma" / "İstanbul" / "cdt_smart_005_doku.png"
    assert unicode_path.is_file()
    assert str(unicode_path) in fixture.created_asset_paths


def test_all_smart_relink_fixtures_reference_the_shared_recovery_root(tmp_path):
    fixtures = create_smart_relink_fixtures(_FakeRuntime(), tmp_path)
    expected_root = str(tmp_path / "recovery_library")
    for f in fixtures:
        assert f.recovery_root == expected_root
