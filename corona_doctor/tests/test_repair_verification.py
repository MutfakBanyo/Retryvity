"""Unit tests for repair/verification.py — pure, fake scene/filesystem
readers, no real I/O or 3ds Max.
"""

from __future__ import annotations

from corona_doctor.repair.models import RepairManifest, RepairManifestEntry, RepairState
from corona_doctor.repair.verification import verify_repair


def _manifest(state: RepairState, entries: tuple[RepairManifestEntry, ...]) -> RepairManifest:
    return RepairManifest(repair_id="repair-1", plan_id="plan-1", kind="make_project_portable", created_at="now", state=state, entries=entries)


def _entry(op_id="op-1", new_path=r"D:\Project\Textures\wood.jpg", copied_file=r"D:\Project\Textures\wood.jpg") -> RepairManifestEntry:
    return RepairManifestEntry(
        op_id=op_id,
        map_handle=42,
        map_class="CoronaBitmap",
        source_property="filename",
        old_path=r"C:\proj\wood.jpg",
        new_path=new_path,
        copied_file=copied_file,
        timestamp="now",
    )


def test_verified_when_scene_and_file_both_match():
    manifest = _manifest(RepairState.APPLIED, (_entry(),))
    state, problems = verify_repair(
        manifest,
        read_current_value=lambda *_: r"D:\Project\Textures\wood.jpg",
        exists_checker=lambda _p: True,
    )
    assert state == RepairState.VERIFIED
    assert problems == ()


def test_scene_property_mismatch_fails_verification():
    manifest = _manifest(RepairState.APPLIED, (_entry(),))
    state, problems = verify_repair(
        manifest,
        read_current_value=lambda *_: r"C:\proj\wood.jpg",  # still the OLD path - relink didn't stick
        exists_checker=lambda _p: True,
    )
    assert state == RepairState.FAILED
    assert problems


def test_copied_file_missing_fails_verification():
    manifest = _manifest(RepairState.APPLIED, (_entry(),))
    state, problems = verify_repair(
        manifest,
        read_current_value=lambda *_: r"D:\Project\Textures\wood.jpg",
        exists_checker=lambda _p: False,
    )
    assert state == RepairState.FAILED
    assert problems


def test_partial_verification_when_some_entries_check_out_and_others_dont():
    good = _entry(op_id="op-good", new_path=r"D:\Project\Textures\a.jpg", copied_file=r"D:\Project\Textures\a.jpg")
    bad = _entry(op_id="op-bad", new_path=r"D:\Project\Textures\b.jpg", copied_file=r"D:\Project\Textures\b.jpg")
    manifest = _manifest(RepairState.APPLIED, (good, bad))

    def read_current(_handle, _prop, op_id):
        return r"D:\Project\Textures\a.jpg" if op_id == "op-good" else r"C:\proj\b.jpg"

    state, problems = verify_repair(manifest, read_current_value=read_current, exists_checker=lambda _p: True)
    assert state == RepairState.PARTIAL
    assert len(problems) == 1


def test_verification_never_upgrades_an_already_failed_manifest():
    manifest = _manifest(RepairState.FAILED, ())
    state, problems = verify_repair(manifest, read_current_value=lambda *_: None, exists_checker=lambda _p: True)
    assert state == RepairState.FAILED
    assert problems == ()


def test_verification_is_read_only():
    """The injected callables must only ever be READ operations from the
    caller's side too - this test just documents/locks that contract by
    using read-only lambdas with no mutation capability."""

    calls = []

    def read_current(handle, prop, op_id):
        calls.append((handle, prop, op_id))
        return r"D:\Project\Textures\wood.jpg"

    manifest = _manifest(RepairState.APPLIED, (_entry(),))
    verify_repair(manifest, read_current_value=read_current, exists_checker=lambda _p: True)
    assert calls == [(42, "filename", "op-1")]
