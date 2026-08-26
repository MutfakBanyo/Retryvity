"""Scanning the live scene into a Snapshot.

The scan is intentionally straightforward: walk the eligible nodes, build
two signatures each, and record failures instead of aborting. pymxs is
main-thread-only, so this runs on the UI thread and offers a progress
callback the panel uses to yield to Qt between objects.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from revision_guard.core.constants import UI_YIELD_INTERVAL
from revision_guard.core.models import ObjectRecord, SkippedObject, Snapshot
from revision_guard.log import debug, log, warn

ProgressCallback = Callable[[int, int, str], None]
NodeFilter = Callable[[Any], bool]


def capture_snapshot(
    nodes: Iterable[Any] | None = None,
    node_filter: NodeFilter | None = None,
    progress: ProgressCallback | None = None,
) -> Snapshot:
    """Fingerprint every eligible geometry node in the scene.

    ``nodes`` defaults to the whole scene. ``node_filter`` narrows it
    further - the smoke test uses it to touch only its own temporary
    objects and leave the user's scene alone.
    """

    from revision_guard.max import scene_access

    started = time.perf_counter()
    candidates = list(nodes) if nodes is not None else scene_access.all_scene_nodes()
    total = len(candidates)

    objects: dict[int, ObjectRecord] = {}
    skipped: list[SkippedObject] = []

    for index, node in enumerate(candidates, start=1):
        if progress is not None and (index == 1 or index % UI_YIELD_INTERVAL == 0 or index == total):
            progress(index, total, scene_access.name_of(node))

        if node_filter is not None:
            try:
                if not node_filter(node):
                    continue
            except Exception:  # noqa: BLE001 - a filter must never abort a scan
                continue

        eligible, reason = scene_access.is_eligible(node)
        if not eligible:
            if reason and reason != "not geometry":
                skipped.append(
                    SkippedObject(handle=_safe_handle(node), name=scene_access.name_of(node), reason=reason)
                )
            continue

        record = _record_for(node)
        if record is None:
            skipped.append(
                SkippedObject(
                    handle=_safe_handle(node),
                    name=scene_access.name_of(node),
                    reason="evaluation failed",
                )
            )
            continue
        objects[record.handle] = record

    snapshot = Snapshot(
        objects=objects,
        skipped=skipped,
        created_at=time.time(),
        duration_seconds=time.perf_counter() - started,
    )
    log(
        f"Snapshot created: {snapshot.object_count} objects "
        f"({snapshot.skipped_count} skipped) in {snapshot.duration_seconds:.2f}s"
    )
    return snapshot


def _record_for(node: Any) -> ObjectRecord | None:
    """Fingerprint one node, or None when it cannot be evaluated."""

    from revision_guard.max import scene_access

    name = scene_access.name_of(node)
    try:
        handle = scene_access.handle_of(node)
        transform = scene_access.transform_signature_of(node)
        geometry = scene_access.geometry_signature_of(node)
    except Exception as exc:  # noqa: BLE001 - one bad object must not end the scan
        warn(f"Skipped '{name}': {type(exc).__name__}: {exc}")
        return None

    debug(f"'{name}' v={geometry.vertex_count} f={geometry.face_count}")
    return ObjectRecord(
        handle=handle,
        name=name,
        object_class=scene_access.class_name_of(node),
        transform=transform,
        geometry=geometry,
    )


def _safe_handle(node: Any) -> int:
    from revision_guard.max import scene_access

    try:
        return scene_access.handle_of(node)
    except Exception:  # noqa: BLE001
        return -1
