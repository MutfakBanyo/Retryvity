"""Unit tests for repair/revert.py — pure, no real filesystem/3ds Max."""

from __future__ import annotations

from corona_doctor.repair.models import OperationKind, RepairManifest, RepairManifestEntry, RepairState, ValidationState
from corona_doctor.repair.revert import build_revert_plan


def _manifest(entries) -> RepairManifest:
    return RepairManifest(repair_id="repair-1", plan_id="plan-1", kind="make_project_portable", created_at="now", state=RepairState.APPLIED, entries=tuple(entries))


def _entry(op_id="op-1", old="C:\\proj\\wood.jpg", new="D:\\Project\\Textures\\wood.jpg") -> RepairManifestEntry:
    return RepairManifestEntry(op_id=op_id, map_handle=42, map_class="CoronaBitmap", source_property="filename", old_path=old, new_path=new, copied_file=new, timestamp="now")


def test_revert_plan_swaps_new_and_old_paths():
    manifest = _manifest([_entry()])
    plan = build_revert_plan(manifest, read_current_value=lambda *_: "D:\\Project\\Textures\\wood.jpg")

    op = plan.operations[0]
    assert op.kind == OperationKind.UPDATE_PATH
    assert op.old_value == "D:\\Project\\Textures\\wood.jpg"
    assert op.new_value == "C:\\proj\\wood.jpg"
    assert op.validation_state == ValidationState.READY


def test_revert_plan_never_mutates_scene_while_building():
    calls = []

    def tracking_read(handle, prop, op_id):
        calls.append((handle, prop, op_id))
        return "D:\\Project\\Textures\\wood.jpg"

    manifest = _manifest([_entry()])
    build_revert_plan(manifest, read_current_value=tracking_read)
    assert calls  # only reads happened
    assert len(calls) == 1


def test_revert_marks_conflict_when_scene_no_longer_matches_manifest():
    manifest = _manifest([_entry()])
    plan = build_revert_plan(manifest, read_current_value=lambda *_: "C:\\someone_else_changed_it.jpg")

    op = plan.operations[0]
    assert op.validation_state == ValidationState.BLOCKED
    assert plan.unresolved


def test_revert_never_touches_copied_files():
    """revert.py must never emit a delete/COPY_FILE operation - only
    UPDATE_PATH. Copied files are never removed on revert (see
    repair/models.py::RepairManifestEntry docstring)."""

    manifest = _manifest([_entry()])
    plan = build_revert_plan(manifest, read_current_value=lambda *_: "D:\\Project\\Textures\\wood.jpg")
    assert all(op.kind == OperationKind.UPDATE_PATH for op in plan.operations)


def test_revert_handles_multiple_entries_independently():
    good = _entry(op_id="op-good", old="C:\\a.jpg", new="D:\\Project\\a.jpg")
    conflicted = _entry(op_id="op-conflict", old="C:\\b.jpg", new="D:\\Project\\b.jpg")
    manifest = _manifest([good, conflicted])

    def read_current(handle, prop, op_id):
        return "D:\\Project\\a.jpg" if op_id == "op-good" else "C:\\changed_elsewhere.jpg"

    plan = build_revert_plan(manifest, read_current_value=read_current)
    ready = [op for op in plan.operations if op.validation_state == ValidationState.READY]
    blocked = [op for op in plan.operations if op.validation_state == ValidationState.BLOCKED]
    assert len(ready) == 1
    assert len(blocked) == 1
