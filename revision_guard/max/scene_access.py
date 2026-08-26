"""The only module allowed to import pymxs.

Everything here degrades to a safe default instead of raising when 3ds Max
is absent, so importing RevisionGuard outside the host never explodes.

Threading: every function here touches the scene and must be called from
the main thread only.
"""

from __future__ import annotations

from typing import Any, Iterable

from revision_guard.core.fingerprint import (
    build_geometry_signature,
    build_transform_signature,
    vertex_indices_to_hash,
)
from revision_guard.core.models import GeometrySignature, TransformSignature
from revision_guard.log import debug, warn

try:  # pragma: no cover - the import only succeeds inside 3ds Max
    import pymxs  # type: ignore
except ImportError:
    pymxs = None


# Classes that are GeometryClass in 3ds Max but are not model geometry a
# revision would ever concern itself with. Everything that is not
# GeometryClass at all (cameras, lights, helpers, shapes, space warps) is
# already excluded by the superclass check and needs no entry here.
EXCLUDED_CLASS_NAMES = frozenset(
    {
        "Targetobject",  # the target node of a target camera/light
        "BoneGeometry",
        "Bone",
        # Legacy particle systems: geometry superclass, but their mesh is
        # regenerated every evaluation, so they would always look changed.
        "Spray",
        "Snow",
        "Blizzard",
        "PArray",
        "PCloud",
        "SuperSpray",
        "PF_Source",
    }
)


class SceneUnavailableError(RuntimeError):
    """Raised when a scene operation is attempted outside 3ds Max."""


def is_available() -> bool:
    """True when running inside a 3ds Max process with pymxs importable."""

    return pymxs is not None


def _runtime():
    if pymxs is None:
        raise SceneUnavailableError(
            "3ds Max (pymxs) is not available. RevisionGuard scene operations "
            "must run inside 3ds Max."
        )
    return pymxs.runtime


# --------------------------------------------------------------------------
# Node discovery
# --------------------------------------------------------------------------


def class_name_of(node: Any) -> str:
    rt = _runtime()
    try:
        return str(rt.classOf(node))
    except Exception:  # noqa: BLE001 - a broken node must not stop the scan
        return "<unknown>"


def name_of(node: Any) -> str:
    try:
        return str(node.name)
    except Exception:  # noqa: BLE001
        return "<unnamed>"


def handle_of(node: Any) -> int:
    """The node's persistent INode handle.

    Must be ``node.handle``, not ``getHandleByAnim``: those are two
    different handle spaces, and only ``node.handle`` round-trips through
    ``maxOps.getNodeByHandle`` - which is how Select Changed resolves a
    result row back to a scene object.
    """

    return int(node.handle)


def is_eligible(node: Any) -> tuple[bool, str]:
    """Decide whether ``node`` participates in a revision comparison.

    Returns ``(eligible, reason)``; ``reason`` is only meaningful when the
    node is rejected and exists so the panel can report *why* something was
    skipped rather than silently dropping it.
    """

    rt = _runtime()
    try:
        if not rt.isValidNode(node):
            return False, "invalid node"
        if rt.superClassOf(node) != rt.GeometryClass:
            return False, "not geometry"
        class_name = class_name_of(node)
        if class_name in EXCLUDED_CLASS_NAMES:
            return False, f"excluded class ({class_name})"
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"eligibility check failed ({exc})"


def all_scene_nodes() -> list[Any]:
    """Every node in the scene, as a plain Python list."""

    rt = _runtime()
    return list(rt.objects)


def node_from_handle(handle: int) -> Any | None:
    """Resolve a node handle, or None when the node no longer exists."""

    rt = _runtime()
    try:
        node = rt.maxOps.getNodeByHandle(handle)
    except Exception:  # noqa: BLE001
        return None
    if node is None:
        return None
    try:
        return node if rt.isValidNode(node) else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Transform fingerprinting
# --------------------------------------------------------------------------


def transform_signature_of(node: Any) -> TransformSignature:
    """Decompose the node's world transform into a fingerprint."""

    matrix = node.transform
    position = matrix.translationPart
    rotation = matrix.rotationPart
    scale = matrix.scalePart
    return build_transform_signature(
        (position.x, position.y, position.z),
        (rotation.x, rotation.y, rotation.z, rotation.w),
        (scale.x, scale.y, scale.z),
    )


# --------------------------------------------------------------------------
# Geometry fingerprinting
# --------------------------------------------------------------------------


def _inverse_matrix_rows(node: Any) -> tuple[tuple[float, ...], ...]:
    """Rows of inverse(node.transform) as plain floats.

    Pulled out of pymxs once so the per-vertex world->local multiply can
    run in pure Python instead of crossing the pymxs boundary per vertex.
    """

    rt = _runtime()
    inverse = rt.inverse(node.transform)
    return tuple(
        (row.x, row.y, row.z)
        for row in (inverse.row1, inverse.row2, inverse.row3, inverse.row4)
    )


def _looks_world_space(
    mesh_bounds: tuple[float, float, float, float, float, float],
    node: Any,
    sampled: bool,
) -> bool:
    """Whether the evaluated mesh's vertices are already in world space.

    ``snapshotAsMesh`` returns world-space geometry in current 3ds Max, but
    rather than trust that across versions we check empirically: compare
    the mesh's own AABB against the node's world AABB (``node.min`` /
    ``node.max``). They coincide only when the mesh is in world space -
    except at an identity transform, where both readings agree anyway and
    the subsequent (identity) conversion is a no-op.

    A sampled mesh has no usable AABB (a vertex subset only ever gives an
    inner approximation, which would fail the comparison and wrongly leave
    world-space coordinates unconverted - turning every move of a dense
    object into a false GEOMETRY_CHANGED). For those we take the
    documented snapshotAsMesh behaviour instead. A node cannot cross the
    sampling threshold without its vertex count changing, which is already
    a geometry change, so the two paths never disagree about one object.
    """

    if sampled:
        return True

    try:
        world_min = node.min
        world_max = node.max
        world = (
            world_min.x,
            world_min.y,
            world_min.z,
            world_max.x,
            world_max.y,
            world_max.z,
        )
    except Exception:  # noqa: BLE001
        # No world AABB available: assume world space, matching the
        # documented snapshotAsMesh behaviour.
        return True

    extent = max(
        abs(world[3] - world[0]),
        abs(world[4] - world[1]),
        abs(world[5] - world[2]),
        1.0,
    )
    tolerance = max(1.0e-3, extent * 1.0e-3)
    return all(abs(a - b) <= tolerance for a, b in zip(mesh_bounds, world))


def geometry_signature_of(node: Any) -> GeometrySignature:
    """Evaluate ``node`` to a mesh and fingerprint it in local space.

    The evaluated mesh is a temporary copy: the user's object is never
    collapsed or otherwise modified, and the temporary is freed before
    returning even if fingerprinting fails.
    """

    rt = _runtime()
    mesh = rt.snapshotAsMesh(node)
    if mesh is None:
        raise RuntimeError("snapshotAsMesh returned undefined")

    try:
        vertex_count = int(rt.getNumVerts(mesh))
        face_count = int(rt.getNumFaces(mesh))
        indices, sampled = vertex_indices_to_hash(vertex_count)

        raw: list[tuple[int, float, float, float]] = []
        min_x = min_y = min_z = float("inf")
        max_x = max_y = max_z = float("-inf")
        for index in indices:
            vertex = rt.getVert(mesh, index)
            x, y, z = float(vertex.x), float(vertex.y), float(vertex.z)
            raw.append((index, x, y, z))
            min_x, min_y, min_z = min(min_x, x), min(min_y, y), min(min_z, z)
            max_x, max_y, max_z = max(max_x, x), max(max_y, y), max(max_z, z)
    finally:
        try:
            rt.free(mesh)
        except Exception:  # noqa: BLE001 - freeing is best effort
            pass

    if not raw:
        return build_geometry_signature(vertex_count, face_count, [], sampled=False)

    if _looks_world_space((min_x, min_y, min_z, max_x, max_y, max_z), node, sampled):
        r1, r2, r3, r4 = _inverse_matrix_rows(node)
        vertices = [
            (
                index,
                x * r1[0] + y * r2[0] + z * r3[0] + r4[0],
                x * r1[1] + y * r2[1] + z * r3[1] + r4[1],
                x * r1[2] + y * r2[2] + z * r3[2] + r4[2],
            )
            for index, x, y, z in raw
        ]
    else:
        vertices = raw

    return build_geometry_signature(vertex_count, face_count, vertices, sampled=sampled)


# --------------------------------------------------------------------------
# Result interaction
# --------------------------------------------------------------------------


def select_handles(handles: Iterable[int]) -> int:
    """Select the still-existing nodes for ``handles``. Returns the count."""

    rt = _runtime()
    nodes = [node for node in (node_from_handle(handle) for handle in handles) if node is not None]
    rt.clearSelection()
    if not nodes:
        return 0
    try:
        rt.select(nodes)
    except Exception:  # noqa: BLE001 - some builds want an explicit array
        rt.select(rt.Array(*nodes))
    return len(nodes)


def isolate_selection() -> bool:
    """Enter 3ds Max's Isolate Selection mode for the current selection.

    Returns False when neither entry point is available on this build; the
    caller reports that as a limitation rather than inventing a workaround
    that would leave the scene in a modified state.
    """

    rt = _runtime()
    isolate = getattr(rt, "IsolateSelection", None)
    if isolate is not None:
        try:
            isolate.EnterIsolateSelectionMode()
            return True
        except Exception:  # noqa: BLE001
            debug("IsolateSelection.EnterIsolateSelectionMode() unavailable; trying macro.")
    try:
        rt.macros.run("Tools", "Isolate_Selection")
        return True
    except Exception as exc:  # noqa: BLE001
        warn(f"Isolate Selection is not available on this build: {exc}")
        return False


def exit_isolation() -> bool:
    """Leave Isolate Selection mode if it is active."""

    rt = _runtime()
    isolate = getattr(rt, "IsolateSelection", None)
    if isolate is not None:
        try:
            isolate.ExitIsolateSelectionMode()
            return True
        except Exception:  # noqa: BLE001
            pass
    try:
        rt.macros.run("Tools", "Isolate_Selection")
        return True
    except Exception:  # noqa: BLE001
        return False


def clear_selection() -> None:
    _runtime().clearSelection()


def scene_unit_scale() -> float:
    """System unit scale, logged once per scan to aid tolerance debugging."""

    rt = _runtime()
    try:
        return float(rt.units.SystemScale)
    except Exception:  # noqa: BLE001
        return 1.0
