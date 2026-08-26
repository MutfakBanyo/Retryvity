"""Classifying a fresh scan against a stored snapshot.

Identity in V0.1 is the 3ds Max node handle, which is stable for the life
of a node inside one scene. That is exactly the right scope here: this
milestone compares a scene against its own earlier state, not against an
imported revision file. Cross-import identity is explicitly out of scope.
"""

from __future__ import annotations

import time

from revision_guard.core.fingerprint import geometry_changed, transform_changed
from revision_guard.core.models import (
    ChangeEntry,
    ChangeType,
    CompareResult,
    ObjectRecord,
    Snapshot,
)
from revision_guard.log import log


def classify(previous: ObjectRecord, current: ObjectRecord) -> ChangeType:
    """Categorise one node present in both snapshots."""

    geometry = geometry_changed(previous.geometry, current.geometry)
    transform = transform_changed(previous.transform, current.transform)

    if geometry and transform:
        return ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED
    if geometry:
        return ChangeType.GEOMETRY_CHANGED
    if transform:
        return ChangeType.TRANSFORM_CHANGED
    return ChangeType.UNCHANGED


def compare_snapshots(previous: Snapshot, current: Snapshot) -> CompareResult:
    """Compare a stored snapshot against a freshly captured one."""

    started = time.perf_counter()
    entries: list[ChangeEntry] = []

    for handle, before in previous.objects.items():
        after = current.objects.get(handle)
        if after is None:
            entries.append(
                ChangeEntry(
                    handle=handle,
                    name=before.name,
                    object_class=before.object_class,
                    change_type=ChangeType.REMOVED,
                )
            )
            continue
        entries.append(
            ChangeEntry(
                handle=handle,
                # Report the current name: a renamed node is still the same
                # node, and the user needs the name they see in the scene.
                name=after.name,
                object_class=after.object_class,
                change_type=classify(before, after),
            )
        )

    for handle, after in current.objects.items():
        if handle in previous.objects:
            continue
        entries.append(
            ChangeEntry(
                handle=handle,
                name=after.name,
                object_class=after.object_class,
                change_type=ChangeType.ADDED,
            )
        )

    entries.sort(key=_sort_key)

    result = CompareResult(
        entries=entries,
        scanned=current.object_count,
        skipped=current.skipped_count,
        duration_seconds=time.perf_counter() - started,
    )
    log(f"Compare completed in {result.duration_seconds:.2f}s")
    log(result.summary_line())
    return result


def _sort_key(entry: ChangeEntry) -> tuple[int, str]:
    from revision_guard.core.models import CHANGE_TYPE_ORDER

    return (CHANGE_TYPE_ORDER.index(entry.change_type), entry.name.lower())
