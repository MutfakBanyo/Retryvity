"""A minimal stand-in for pymxs, for testing scene_access without 3ds Max.

It models just enough of the MAXScript value types that scene_access
touches: Matrix3 decomposition, matrix inversion, node transforms and
snapshotAsMesh. The point is to exercise the world-space -> local-space
conversion, which is the piece of RevisionGuard most likely to produce a
false GEOMETRY_CHANGED if it is wrong.

MAXScript's row-vector convention is reproduced faithfully:
``world = local * A + translation``.
"""

from __future__ import annotations

import math
import types


class Point3:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z = float(x), float(y), float(z)


class Quat:
    def __init__(self, x: float, y: float, z: float, w: float) -> None:
        self.x, self.y, self.z, self.w = x, y, z, w


class Matrix3:
    """Built from position + rotation-about-Z + uniform scale.

    The components are stored rather than re-derived, because the fake only
    needs to *answer* decomposition queries the way 3ds Max does.
    """

    def __init__(self, position=(0.0, 0.0, 0.0), angle_z_degrees=0.0, scale=(1.0, 1.0, 1.0)) -> None:
        self.position = tuple(float(v) for v in position)
        self.angle = math.radians(angle_z_degrees)
        self.scale = tuple(float(v) for v in scale)

    # --- decomposition, as MAXScript exposes it ---------------------------
    @property
    def translationPart(self) -> Point3:  # noqa: N802 - MAXScript naming
        return Point3(*self.position)

    @property
    def rotationPart(self) -> Quat:  # noqa: N802
        half = self.angle / 2.0
        return Quat(0.0, 0.0, math.sin(half), math.cos(half))

    @property
    def scalePart(self) -> Point3:  # noqa: N802
        return Point3(*self.scale)

    # --- raw rows ---------------------------------------------------------
    def basis_rows(self) -> tuple[tuple[float, float, float], ...]:
        cos_a, sin_a = math.cos(self.angle), math.sin(self.angle)
        rotation = (
            (cos_a, sin_a, 0.0),
            (-sin_a, cos_a, 0.0),
            (0.0, 0.0, 1.0),
        )
        return tuple(
            tuple(self.scale[i] * component for component in rotation[i]) for i in range(3)
        )

    def transform_point(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        rows = self.basis_rows()
        x, y, z = point
        return (
            x * rows[0][0] + y * rows[1][0] + z * rows[2][0] + self.position[0],
            x * rows[0][1] + y * rows[1][1] + z * rows[2][1] + self.position[1],
            x * rows[0][2] + y * rows[1][2] + z * rows[2][2] + self.position[2],
        )


class InverseMatrix:
    """Result of ``inverse(matrix)``: exposes row1..row4 like Matrix3 does."""

    def __init__(self, rows) -> None:
        self.row1 = Point3(*rows[0])
        self.row2 = Point3(*rows[1])
        self.row3 = Point3(*rows[2])
        self.row4 = Point3(*rows[3])


def _invert_3x3(rows):
    a, b, c = rows[0]
    d, e, f = rows[1]
    g, h, i = rows[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-18:
        raise ZeroDivisionError("singular matrix")
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


class FakeMesh:
    def __init__(self, vertices, face_count: int) -> None:
        self.vertices = list(vertices)
        self.face_count = face_count
        self.freed = False


class FakeNode:
    """A geometry node with a local mesh and a transform."""

    def __init__(
        self,
        name: str,
        handle: int,
        local_vertices,
        face_count: int = 12,
        transform: Matrix3 | None = None,
        class_name: str = "Box",
        superclass: str = "GeometryClass",
        mesh_is_world_space: bool = True,
    ) -> None:
        self.name = name
        self.handle = handle
        self.local_vertices = [tuple(v) for v in local_vertices]
        self.face_count = face_count
        self.transform = transform or Matrix3()
        self.class_name = class_name
        self.superclass = superclass
        # Toggles what snapshotAsMesh hands back, so both interpretations
        # can be tested.
        self.mesh_is_world_space = mesh_is_world_space

    def world_vertices(self):
        return [self.transform.transform_point(v) for v in self.local_vertices]

    def _world_bounds(self):
        verts = self.world_vertices()
        return (
            Point3(*(min(v[axis] for v in verts) for axis in range(3))),
            Point3(*(max(v[axis] for v in verts) for axis in range(3))),
        )

    @property
    def min(self) -> Point3:
        return self._world_bounds()[0]

    @property
    def max(self) -> Point3:
        return self._world_bounds()[1]


class _SuperClass:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other) -> bool:
        return isinstance(other, _SuperClass) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name


class FakeRuntime:
    def __init__(self, nodes=()) -> None:
        self.objects = list(nodes)
        self.selection: list[FakeNode] = []
        self.freed_meshes = 0
        self.GeometryClass = _SuperClass("GeometryClass")

    # --- value constructors ----------------------------------------------
    Point3 = staticmethod(lambda x, y, z: Point3(x, y, z))

    # --- node queries -----------------------------------------------------
    def isValidNode(self, node):  # noqa: N802
        return isinstance(node, FakeNode)

    def superClassOf(self, node):  # noqa: N802
        return _SuperClass(node.superclass)

    def classOf(self, node):  # noqa: N802
        return node.class_name

    def maxOps(self):  # pragma: no cover - replaced by the namespace below
        raise NotImplementedError

    # --- mesh evaluation --------------------------------------------------
    def snapshotAsMesh(self, node):  # noqa: N802
        verts = node.world_vertices() if node.mesh_is_world_space else node.local_vertices
        return FakeMesh(verts, node.face_count)

    def getNumVerts(self, mesh):  # noqa: N802
        return len(mesh.vertices)

    def getNumFaces(self, mesh):  # noqa: N802
        return mesh.face_count

    def getVert(self, mesh, index):  # noqa: N802
        return Point3(*mesh.vertices[index - 1])

    def free(self, mesh):
        mesh.freed = True
        self.freed_meshes += 1

    def inverse(self, matrix: Matrix3) -> InverseMatrix:
        basis = _invert_3x3(matrix.basis_rows())
        tx, ty, tz = matrix.position
        translation = (
            -(tx * basis[0][0] + ty * basis[1][0] + tz * basis[2][0]),
            -(tx * basis[0][1] + ty * basis[1][1] + tz * basis[2][1]),
            -(tx * basis[0][2] + ty * basis[1][2] + tz * basis[2][2]),
        )
        return InverseMatrix((basis[0], basis[1], basis[2], translation))

    # --- selection --------------------------------------------------------
    def clearSelection(self):  # noqa: N802
        self.selection = []

    def select(self, nodes):
        self.selection = list(nodes)


def make_module(runtime: FakeRuntime) -> types.ModuleType:
    """Wrap a FakeRuntime in something importable as ``pymxs``."""

    handles = {node.handle: node for node in runtime.objects}

    class _MaxOps:
        @staticmethod
        def getNodeByHandle(handle):  # noqa: N802
            return handles.get(int(handle))

    runtime.maxOps = _MaxOps()

    module = types.ModuleType("pymxs")
    module.runtime = runtime
    return module
