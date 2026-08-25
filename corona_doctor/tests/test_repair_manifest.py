"""Unit tests for repair/manifest.py persistence — real filesystem, but
isolated to tmp_path (never the real %APPDATA%)."""

from __future__ import annotations

from corona_doctor.repair.manifest import load_last_manifest, load_manifest, save_manifest
from corona_doctor.repair.models import RepairManifest, RepairManifestEntry, RepairState


def _manifest(repair_id: str) -> RepairManifest:
    entry = RepairManifestEntry(
        op_id="op-1",
        map_handle=42,
        map_class="CoronaBitmap",
        source_property="filename",
        old_path=r"C:\proj\wood.jpg",
        new_path=r"D:\Project\Textures\wood.jpg",
        copied_file=r"D:\Project\Textures\wood.jpg",
        timestamp="now",
    )
    return RepairManifest(repair_id=repair_id, plan_id="plan-1", kind="make_project_portable", created_at="now", state=RepairState.VERIFIED, entries=(entry,))


def test_save_then_load_round_trips(tmp_path):
    manifest = _manifest("repair-abc")
    save_manifest(manifest, directory=tmp_path)

    loaded = load_manifest("repair-abc", directory=tmp_path)
    assert loaded == manifest


def test_load_missing_manifest_returns_none(tmp_path):
    assert load_manifest("does-not-exist", directory=tmp_path) is None


def test_load_last_manifest_tracks_the_most_recent_save(tmp_path):
    save_manifest(_manifest("repair-1"), directory=tmp_path)
    save_manifest(_manifest("repair-2"), directory=tmp_path)

    last = load_last_manifest(directory=tmp_path)
    assert last.repair_id == "repair-2"


def test_load_last_manifest_with_no_repairs_yet_returns_none(tmp_path):
    assert load_last_manifest(directory=tmp_path) is None
