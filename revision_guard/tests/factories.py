"""Snapshot builders for host-independent tests.

These construct ObjectRecords straight from numbers, bypassing pymxs, so
the classification logic can be exercised without 3ds Max.
"""

from __future__ import annotations

from revision_guard.core.fingerprint import build_geometry_signature, build_transform_signature
from revision_guard.core.models import ObjectRecord, Snapshot

# A unit cube's 8 corners, in local space.
CUBE_VERTICES = [
    (1, -1.0, -1.0, -1.0),
    (2, 1.0, -1.0, -1.0),
    (3, 1.0, 1.0, -1.0),
    (4, -1.0, 1.0, -1.0),
    (5, -1.0, -1.0, 1.0),
    (6, 1.0, -1.0, 1.0),
    (7, 1.0, 1.0, 1.0),
    (8, -1.0, 1.0, 1.0),
]


def make_record(
    handle: int,
    name: str = "Box001",
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    vertices=None,
    face_count: int = 12,
) -> ObjectRecord:
    verts = CUBE_VERTICES if vertices is None else vertices
    return ObjectRecord(
        handle=handle,
        name=name,
        object_class="Box",
        transform=build_transform_signature(position, rotation, scale),
        geometry=build_geometry_signature(len(verts), face_count, verts),
    )


def make_snapshot(*records: ObjectRecord) -> Snapshot:
    return Snapshot(objects={record.handle: record for record in records})


def move_vertex(vertices, index: int, delta: tuple[float, float, float]):
    """Return a copy of ``vertices`` with one corner nudged."""

    out = []
    for vertex in vertices:
        if vertex[0] == index:
            out.append((vertex[0], vertex[1] + delta[0], vertex[2] + delta[1], vertex[3] + delta[2]))
        else:
            out.append(vertex)
    return out
