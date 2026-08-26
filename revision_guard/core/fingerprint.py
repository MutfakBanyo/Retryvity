"""Deterministic fingerprints for transforms and meshes.

Two rules drive this module:

1. Digests must be *stable* across evaluations of the same unchanged
   object, so coordinates are snapped to a quantisation grid before they
   reach the hash. Python's built-in ``hash()`` is never used - it is
   salted per process and is not a fingerprint.
2. Change *decisions* are never made by comparing raw floats with ``==``.
   The digest is only a fast path; when digests differ, a tolerant
   component-wise comparison has the final say.

The module takes plain numbers, not scene nodes, which is what lets the
whole comparison engine be tested without 3ds Max.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable, Sequence

from revision_guard.core.constants import (
    BBOX_TOLERANCE,
    MAX_HASHED_VERTICES,
    POSITION_TOLERANCE,
    ROTATION_TOLERANCE,
    SCALE_TOLERANCE,
    VERTEX_QUANTIZATION,
)
from revision_guard.core.models import (
    GeometrySignature,
    Quaternion,
    TransformSignature,
    Vector3,
)

_EMPTY_DIGEST = hashlib.sha256(b"revisionguard:empty").hexdigest()


def quantize(value: float, step: float) -> int:
    """Snap ``value`` onto a grid of ``step``, as an integer bucket.

    Uses floor(x + 0.5) rather than round() so the tie-breaking direction
    is fixed and obvious instead of banker's rounding.
    """

    if not math.isfinite(value):
        # A NaN/inf coordinate is a broken object, not a change signal;
        # collapse it to a single reserved bucket so it hashes stably.
        return -(2**31)
    return int(math.floor(value / step + 0.5))


def canonical_quaternion(quat: Sequence[float]) -> Quaternion:
    """Return ``quat`` in the hemisphere where w >= 0.

    q and -q describe the same rotation, and 3ds Max may hand back either
    for an object that never moved. Without this, a pure re-evaluation
    could look like a rotation change.
    """

    x, y, z, w = (float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))
    if w < 0.0:
        return (-x, -y, -z, -w)
    if w == 0.0:
        # w == 0 is the hemisphere boundary; break the tie on the first
        # non-zero component so the sign stays deterministic.
        for component in (x, y, z):
            if component < 0.0:
                return (-x, -y, -z, w)
            if component > 0.0:
                break
    return (x, y, z, w)


def build_transform_signature(
    position: Sequence[float],
    rotation: Sequence[float],
    scale: Sequence[float],
) -> TransformSignature:
    """Build a transform fingerprint from decomposed matrix components."""

    pos: Vector3 = (float(position[0]), float(position[1]), float(position[2]))
    rot = canonical_quaternion(rotation)
    scl: Vector3 = (float(scale[0]), float(scale[1]), float(scale[2]))

    hasher = hashlib.sha256()
    hasher.update(b"revisionguard:transform:1")
    for value, tolerance in (
        (pos[0], POSITION_TOLERANCE),
        (pos[1], POSITION_TOLERANCE),
        (pos[2], POSITION_TOLERANCE),
        (rot[0], ROTATION_TOLERANCE),
        (rot[1], ROTATION_TOLERANCE),
        (rot[2], ROTATION_TOLERANCE),
        (rot[3], ROTATION_TOLERANCE),
        (scl[0], SCALE_TOLERANCE),
        (scl[1], SCALE_TOLERANCE),
        (scl[2], SCALE_TOLERANCE),
    ):
        hasher.update(str(quantize(value, tolerance)).encode("ascii"))
        hasher.update(b";")

    return TransformSignature(position=pos, rotation=rot, scale=scl, digest=hasher.hexdigest())


def vertex_indices_to_hash(vertex_count: int) -> tuple[list[int], bool]:
    """Pick which vertex indices contribute to the geometry digest.

    Returns ``(indices, sampled)``. Below MAX_HASHED_VERTICES every vertex
    is hashed, so moving a single vertex of a cube is always detected. Very
    dense meshes fall back to a fixed stride - deterministic for a given
    vertex count, so the same indices are compared on both sides.
    """

    if vertex_count <= 0:
        return [], False
    if vertex_count <= MAX_HASHED_VERTICES:
        return list(range(1, vertex_count + 1)), False

    stride = vertex_count / float(MAX_HASHED_VERTICES)
    indices = []
    previous = 0
    for step in range(MAX_HASHED_VERTICES):
        index = int(step * stride) + 1
        if index != previous:
            indices.append(index)
            previous = index
    return indices, True


def build_geometry_signature(
    vertex_count: int,
    face_count: int,
    vertices: Iterable[tuple[int, float, float, float]],
    sampled: bool = False,
) -> GeometrySignature:
    """Build a mesh fingerprint from local-space vertices.

    ``vertices`` yields ``(index, x, y, z)``. The index is folded into the
    digest so a sampled digest cannot collide with a differently-strided
    one, and so reordered vertices register as a change.

    The bounding box is derived from the vertices supplied; for a sampled
    mesh that makes it an inner approximation, which is fine because it is
    computed the same way on both sides of a comparison.
    """

    hasher = hashlib.sha256()
    hasher.update(b"revisionguard:geometry:1")
    hasher.update(f"v={vertex_count};f={face_count};".encode("ascii"))

    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    hashed = 0

    for index, x, y, z in vertices:
        qx = quantize(x, VERTEX_QUANTIZATION)
        qy = quantize(y, VERTEX_QUANTIZATION)
        qz = quantize(z, VERTEX_QUANTIZATION)
        hasher.update(f"{index}:{qx},{qy},{qz};".encode("ascii"))
        hashed += 1

        if x < min_x:
            min_x = x
        if y < min_y:
            min_y = y
        if z < min_z:
            min_z = z
        if x > max_x:
            max_x = x
        if y > max_y:
            max_y = y
        if z > max_z:
            max_z = z

    if hashed == 0:
        bbox_min: Vector3 = (0.0, 0.0, 0.0)
        bbox_max: Vector3 = (0.0, 0.0, 0.0)
    else:
        bbox_min = (min_x, min_y, min_z)
        bbox_max = (max_x, max_y, max_z)

    return GeometrySignature(
        vertex_count=vertex_count,
        face_count=face_count,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        digest=hasher.hexdigest() if hashed else _EMPTY_DIGEST,
        hashed_vertices=hashed,
        sampled=sampled,
    )


def _components_differ(left: Sequence[float], right: Sequence[float], tolerance: float) -> bool:
    return any(abs(a - b) > tolerance for a, b in zip(left, right))


def transform_changed(before: TransformSignature, after: TransformSignature) -> bool:
    """True when the node's world transform moved beyond tolerance."""

    if before.digest == after.digest:
        return False
    if _components_differ(before.position, after.position, POSITION_TOLERANCE):
        return True
    if _components_differ(before.rotation, after.rotation, ROTATION_TOLERANCE):
        return True
    if _components_differ(before.scale, after.scale, SCALE_TOLERANCE):
        return True
    # Digests disagreed only because a component sat on a quantisation
    # boundary - not a real move.
    return False


def geometry_changed(before: GeometrySignature, after: GeometrySignature) -> bool:
    """True when the node's local-space mesh changed.

    Counts and bounding box are checked first because they are the cheap,
    tolerant signals; the vertex digest is what catches an edit that keeps
    both counts identical (the moved-vertex-on-a-cube case).
    """

    if before.vertex_count != after.vertex_count:
        return True
    if before.face_count != after.face_count:
        return True
    if _components_differ(before.bbox_min, after.bbox_min, BBOX_TOLERANCE):
        return True
    if _components_differ(before.bbox_max, after.bbox_max, BBOX_TOLERANCE):
        return True
    return before.digest != after.digest
