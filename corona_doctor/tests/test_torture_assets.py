"""Unit tests for devtools/torture_assets.py and torture_manifest.py —
pure stdlib, no pymxs required.
"""

from __future__ import annotations

from corona_doctor.adapters.image_metadata import read_image_dimensions
from corona_doctor.devtools.torture_assets import write_stub_png
from corona_doctor.devtools.torture_manifest import FixtureRecord, TortureManifest, load_torture_manifest, save_torture_manifest


def test_stub_png_reports_correct_dimensions_via_the_real_reader(tmp_path):
    path = tmp_path / "stub_8k.png"
    write_stub_png(path, 8192, 8192)

    dims = read_image_dimensions(str(path))
    assert dims == (8192, 8192)


def test_stub_png_16k_reports_correct_dimensions(tmp_path):
    path = tmp_path / "stub_16k.png"
    write_stub_png(path, 16384, 16384)

    assert read_image_dimensions(str(path)) == (16384, 16384)


def test_stub_png_stays_small_on_disk_even_at_16k(tmp_path):
    path = tmp_path / "stub_16k.png"
    write_stub_png(path, 16384, 16384)

    size = path.stat().st_size
    raw_uncompressed = 16384 * (1 + 16384)
    assert size < raw_uncompressed / 100, f"expected strong compression on uniform data, got {size} bytes"
    assert size < 2 * 1024 * 1024, f"stub PNG should stay well under 2MB, got {size} bytes"


def test_stub_png_is_genuinely_decodable_not_just_a_fake_header(tmp_path):
    import zlib

    path = tmp_path / "stub.png"
    write_stub_png(path, 4, 4, gray_value=200)
    raw = path.read_bytes()

    # Locate and decompress the IDAT chunk to prove it's real pixel data,
    # not a truncated stub - a fake header would fail this decompression.
    idat_start = raw.index(b"IDAT") + 4
    length = int.from_bytes(raw[idat_start - 8 : idat_start - 4], "big")
    idat = raw[idat_start : idat_start + length]
    decompressed = zlib.decompress(idat)
    assert len(decompressed) == 4 * (1 + 4)  # 4 rows of (filter byte + 4 pixels)
    assert decompressed[1] == 200  # first pixel matches gray_value


def test_torture_manifest_round_trips(tmp_path):
    fixture = FixtureRecord(
        fixture_id="CDT-TEX-001",
        category="texture",
        description="Missing texture",
        expected_rule_id="TXT-001",
        expected_detection="1 missing texture reference",
        expected_fixability="manual",
        expected_repair_behavior="Find & Relink",
        created_object_names=("CDT_TEX_001_Box",),
        created_material_names=("CDT_TEX_001_Mtl",),
        created_map_names=("CDT_TEX_001_Map",),
        created_asset_paths=(),
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,))

    path = save_torture_manifest(manifest, path=tmp_path / "manifest.json")
    loaded = load_torture_manifest(path=path)

    assert loaded == manifest


def test_load_torture_manifest_missing_file_returns_none(tmp_path):
    assert load_torture_manifest(path=tmp_path / "does_not_exist.json") is None


def test_skipped_fixture_is_recorded_not_silently_dropped(tmp_path):
    fixture = FixtureRecord(
        fixture_id="CDT-TEX-999",
        category="texture",
        description="Some Corona-specific fixture the runtime could not construct",
        expected_rule_id=None,
        expected_detection="n/a",
        expected_fixability="n/a",
        expected_repair_behavior="n/a",
        skipped=True,
        skip_reason="CoronaTriplanar not constructible on this host",
    )
    manifest = TortureManifest(created_at="now", asset_directory=str(tmp_path), fixtures=(fixture,))
    path = save_torture_manifest(manifest, path=tmp_path / "manifest.json")
    loaded = load_torture_manifest(path=path)

    assert loaded.fixtures[0].skipped is True
    assert "CoronaTriplanar" in loaded.fixtures[0].skip_reason
