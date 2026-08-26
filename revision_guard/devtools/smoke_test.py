"""One-command validation of the comparison engine inside real 3ds Max.

Run it from the 3ds Max Python listener:

    from revision_guard.devtools.smoke_test import run_smoke_test
    run_smoke_test()

It builds its own throwaway objects (all named ``RG_Smoke_*``), scans only
those, mutates them, re-scans, and checks each object landed in the
expected category. The user's own scene objects are never scanned, never
modified, and never selected. Every created object is deleted again in a
finally block, including when a case fails.
"""

from __future__ import annotations

from typing import Any

from revision_guard.core.compare import compare_snapshots
from revision_guard.core.models import ChangeType
from revision_guard.core.snapshot import capture_snapshot
from revision_guard.log import log

PREFIX = "RG_Smoke_"

# case label -> (object name, expected category)
_CASES = (
    ("UNCHANGED", f"{PREFIX}Unchanged", ChangeType.UNCHANGED),
    ("TRANSFORM_MOVED", f"{PREFIX}Moved", ChangeType.TRANSFORM_CHANGED),
    ("TRANSFORM_ROTATED", f"{PREFIX}Rotated", ChangeType.TRANSFORM_CHANGED),
    ("TRANSFORM_SCALED", f"{PREFIX}Scaled", ChangeType.TRANSFORM_CHANGED),
    ("GEOMETRY_CHANGED", f"{PREFIX}Geometry", ChangeType.GEOMETRY_CHANGED),
    ("ADDED", f"{PREFIX}Added", ChangeType.ADDED),
    ("REMOVED", f"{PREFIX}Removed", ChangeType.REMOVED),
    ("GEOMETRY_AND_TRANSFORM", f"{PREFIX}Both", ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED),
)


def _is_smoke_node(node: Any) -> bool:
    try:
        return str(node.name).startswith(PREFIX)
    except Exception:  # noqa: BLE001
        return False


def run_smoke_test(verbose: bool = False) -> bool:
    """Run all six cases. Returns True when every case passes."""

    from revision_guard.max import scene_access, scene_edit

    if not scene_access.is_available():
        print("REVISIONGUARD V0.1 SMOKE TEST")
        print("SKIPPED - pymxs is unavailable. Run this inside 3ds Max.")
        return False

    if verbose:
        from revision_guard.log import set_verbose

        set_verbose(True)

    # Refuse to run if the scene already holds objects with our prefix; we
    # would otherwise delete something the user made.
    existing = scene_edit.nodes_with_prefix(PREFIX)
    if existing:
        print("REVISIONGUARD V0.1 SMOKE TEST")
        print(f"ABORTED - {len(existing)} existing '{PREFIX}*' object(s) in the scene.")
        print("Rename or delete them and run again.")
        return False

    results: dict[str, ChangeType | None] = {}
    error: Exception | None = None

    try:
        with scene_edit.undo_disabled():
            results = _run_cases(scene_edit)
    except Exception as exc:  # noqa: BLE001 - report, don't traceback at the user
        error = exc
    finally:
        try:
            with scene_edit.undo_disabled():
                removed = scene_edit.delete_nodes_with_prefix(PREFIX)
            if removed:
                log(f"Smoke test cleanup: removed {removed} temporary object(s).")
        except Exception as cleanup_exc:  # noqa: BLE001
            print(f"[RevisionGuard] Smoke test cleanup failed: {cleanup_exc}")

    return _report(results, error)


def _run_cases(scene_edit) -> dict[str, ChangeType | None]:
    """Build, snapshot, mutate, re-scan. Returns case label -> actual category."""

    unchanged = scene_edit.create_box(f"{PREFIX}Unchanged", (0.0, 0.0, 0.0))
    moved = scene_edit.create_box(f"{PREFIX}Moved", (50.0, 0.0, 0.0))
    rotated = scene_edit.create_box(f"{PREFIX}Rotated", (100.0, 0.0, 0.0))
    scaled = scene_edit.create_box(f"{PREFIX}Scaled", (150.0, 0.0, 0.0))
    geometry = scene_edit.create_box(f"{PREFIX}Geometry", (200.0, 0.0, 0.0))
    removed = scene_edit.create_box(f"{PREFIX}Removed", (250.0, 0.0, 0.0))
    both = scene_edit.create_box(f"{PREFIX}Both", (300.0, 0.0, 0.0))

    # Collapse the two meshes we are going to edit *before* snapshotting, so
    # the only geometry difference the compare sees is the vertex move.
    scene_edit.convert_to_editable_poly(geometry)
    scene_edit.convert_to_editable_poly(both)

    before = capture_snapshot(node_filter=_is_smoke_node)
    log(f"Smoke test snapshot: {before.object_count} temporary objects.")

    # --- mutations ---------------------------------------------------------
    # Move, rotate and scale must all land in TRANSFORM_CHANGED, not
    # GEOMETRY_CHANGED: the local-space mesh is identical in each case and
    # only the node's transform moved. That is exactly what a naive
    # world-space fingerprint gets wrong.
    scene_edit.move_node(moved, (0.0, 75.0, 0.0))
    scene_edit.rotate_node(rotated, 35.0)
    scene_edit.scale_node(scaled, 1.5)
    scene_edit.offset_poly_vertex(geometry, 1, (0.0, 0.0, 25.0))
    scene_edit.delete_node(removed)
    scene_edit.offset_poly_vertex(both, 1, (0.0, 0.0, 25.0))
    scene_edit.move_node(both, (0.0, 75.0, 0.0))
    scene_edit.create_box(f"{PREFIX}Added", (350.0, 0.0, 0.0))
    del unchanged  # deliberately untouched

    after = capture_snapshot(node_filter=_is_smoke_node)
    result = compare_snapshots(before, after)

    by_name = {entry.name: entry.change_type for entry in result.entries}
    return {label: by_name.get(name) for label, name, _ in _CASES}


def _report(results: dict[str, ChangeType | None], error: Exception | None) -> bool:
    print("REVISIONGUARD V0.1 SMOKE TEST")

    passed = 0
    for label, _name, expected in _CASES:
        actual = results.get(label)
        ok = actual is expected
        passed += int(ok)
        detail = "" if ok else f"  (got {actual.value if actual else 'MISSING'})"
        print(f"{label:<26} {'PASS' if ok else 'FAIL'}{detail}")

    print(f"RESULT: {passed}/{len(_CASES)} PASS")
    if error is not None:
        print(f"ERROR: {type(error).__name__}: {error}")
    return passed == len(_CASES) and error is None


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    run_smoke_test()
