"""scene_access against a fake pymxs.

The property under test is the one that decides whether RevisionGuard is
trustworthy at all: moving, rotating or scaling an object must change its
transform signature and leave its geometry signature untouched.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from revision_guard.core.compare import compare_snapshots
from revision_guard.core.models import ChangeType
from revision_guard.core.fingerprint import vertex_indices_to_hash
from revision_guard.core.snapshot import capture_snapshot
from revision_guard.tests.fake_pymxs import FakeNode, FakeRuntime, Matrix3, make_module

CUBE = [
    (-10.0, -10.0, 0.0),
    (10.0, -10.0, 0.0),
    (10.0, 10.0, 0.0),
    (-10.0, 10.0, 0.0),
    (-10.0, -10.0, 20.0),
    (10.0, -10.0, 20.0),
    (10.0, 10.0, 20.0),
    (-10.0, 10.0, 20.0),
]


@pytest.fixture
def scene(monkeypatch):
    """Install a fake pymxs and hand back a (runtime, scene_access) pair."""

    runtime = FakeRuntime()
    monkeypatch.setitem(sys.modules, "pymxs", make_module(runtime))

    import revision_guard.max.scene_access as module

    importlib.reload(module)
    yield runtime, module

    # Put the real (absent) pymxs back so later tests see an honest module.
    monkeypatch.undo()
    importlib.reload(module)


def _install(runtime, module, nodes):
    runtime.objects = list(nodes)
    make_module(runtime)  # refresh the handle lookup table
    return module


def test_geometry_signature_is_transform_invariant(scene):
    runtime, module = scene
    at_origin = FakeNode("Wall", 1, CUBE, transform=Matrix3())
    moved = FakeNode("Wall", 1, CUBE, transform=Matrix3(position=(1234.0, -56.0, 78.0)))

    _install(runtime, module, [at_origin])
    before = module.geometry_signature_of(at_origin)
    after = module.geometry_signature_of(moved)

    assert before.digest == after.digest, "a pure move must not alter the geometry digest"


def test_geometry_signature_is_rotation_and_scale_invariant(scene):
    runtime, module = scene
    plain = FakeNode("Wall", 1, CUBE, transform=Matrix3())
    spun = FakeNode(
        "Wall",
        1,
        CUBE,
        transform=Matrix3(position=(400.0, 0.0, 0.0), angle_z_degrees=37.0, scale=(2.5, 2.5, 2.5)),
    )
    _install(runtime, module, [plain])

    assert module.geometry_signature_of(plain).digest == module.geometry_signature_of(spun).digest


def test_local_space_meshes_are_passed_through_unchanged(scene):
    """A host that hands back local-space geometry must not be re-transformed."""

    runtime, module = scene
    world_space = FakeNode("Wall", 1, CUBE, transform=Matrix3(position=(300.0, 0.0, 0.0)))
    local_space = FakeNode(
        "Wall", 2, CUBE, transform=Matrix3(position=(300.0, 0.0, 0.0)), mesh_is_world_space=False
    )
    _install(runtime, module, [world_space, local_space])

    assert module.geometry_signature_of(world_space).digest == module.geometry_signature_of(local_space).digest


def test_temporary_mesh_is_always_freed(scene):
    runtime, module = scene
    node = FakeNode("Wall", 1, CUBE)
    _install(runtime, module, [node])

    module.geometry_signature_of(node)
    assert runtime.freed_meshes == 1


def test_non_geometry_nodes_are_not_eligible(scene):
    runtime, module = scene
    camera = FakeNode("Camera001", 1, CUBE, class_name="Freecamera", superclass="camera")
    _install(runtime, module, [camera])

    eligible, reason = module.is_eligible(camera)
    assert not eligible
    assert reason == "not geometry"


def test_excluded_geometry_classes_are_skipped(scene):
    runtime, module = scene
    target = FakeNode("Camera001.Target", 1, CUBE, class_name="Targetobject")
    _install(runtime, module, [target])

    eligible, reason = module.is_eligible(target)
    assert not eligible
    assert "excluded class" in reason


def test_scan_survives_an_object_that_fails_to_evaluate(scene):
    """One broken object must not abort the scan."""

    runtime, module = scene
    good = FakeNode("Good", 1, CUBE)
    broken = FakeNode("Broken", 2, CUBE)
    _install(runtime, module, [good, broken])

    original = runtime.snapshotAsMesh

    def explode(node):
        if node.name == "Broken":
            raise RuntimeError("mesh evaluation blew up")
        return original(node)

    runtime.snapshotAsMesh = explode

    snapshot = capture_snapshot()
    assert snapshot.object_count == 1
    assert snapshot.skipped_count == 1
    assert snapshot.skipped[0].name == "Broken"


def test_empty_scene_produces_an_empty_snapshot(scene):
    runtime, module = scene
    _install(runtime, module, [])
    assert capture_snapshot().object_count == 0


def test_end_to_end_move_is_transform_changed_not_geometry(scene):
    """The full snapshot -> mutate -> compare loop, through scene_access."""

    runtime, module = scene
    node = FakeNode("Chair_008", 1, CUBE, transform=Matrix3())
    _install(runtime, module, [node])
    before = capture_snapshot()

    node.transform = Matrix3(position=(500.0, 25.0, 0.0), angle_z_degrees=90.0)
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    assert result.entries[0].change_type is ChangeType.TRANSFORM_CHANGED


def test_end_to_end_vertex_edit_is_geometry_changed(scene):
    runtime, module = scene
    node = FakeNode("Wall_014", 1, CUBE, transform=Matrix3(position=(90.0, 0.0, 0.0)))
    _install(runtime, module, [node])
    before = capture_snapshot()

    edited = list(CUBE)
    edited[6] = (10.0, 10.0, 33.0)  # one corner pulled up; counts unchanged
    node.local_vertices = edited
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    assert result.entries[0].change_type is ChangeType.GEOMETRY_CHANGED


def test_end_to_end_geometry_and_transform(scene):
    runtime, module = scene
    node = FakeNode("Slab_002", 1, CUBE, transform=Matrix3())
    _install(runtime, module, [node])
    before = capture_snapshot()

    edited = list(CUBE)
    edited[6] = (10.0, 10.0, 33.0)
    node.local_vertices = edited
    node.transform = Matrix3(position=(0.0, 0.0, 120.0))
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    assert result.entries[0].change_type is ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED


def test_end_to_end_added_and_removed(scene):
    runtime, module = scene
    kept = FakeNode("Kept", 1, CUBE)
    doomed = FakeNode("Column_003", 2, CUBE, transform=Matrix3(position=(60.0, 0.0, 0.0)))
    _install(runtime, module, [kept, doomed])
    before = capture_snapshot()

    fresh = FakeNode("Table_New", 3, CUBE, transform=Matrix3(position=(120.0, 0.0, 0.0)))
    _install(runtime, module, [kept, fresh])
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    by_name = {entry.name: entry.change_type for entry in result.entries}
    assert by_name["Column_003"] is ChangeType.REMOVED
    assert by_name["Table_New"] is ChangeType.ADDED
    assert by_name["Kept"] is ChangeType.UNCHANGED


def test_select_changed_skips_removed_nodes(scene):
    runtime, module = scene
    kept = FakeNode("Kept", 1, CUBE)
    doomed = FakeNode("Doomed", 2, CUBE, transform=Matrix3(position=(60.0, 0.0, 0.0)))
    _install(runtime, module, [kept, doomed])
    before = capture_snapshot()

    kept.transform = Matrix3(position=(0.0, 0.0, 40.0))
    _install(runtime, module, [kept])
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    selected = module.select_handles(result.selectable_handles())

    assert selected == 1
    assert [node.name for node in runtime.selection] == ["Kept"]


def test_node_from_handle_returns_none_for_a_deleted_node(scene):
    runtime, module = scene
    node = FakeNode("Gone", 7, CUBE)
    _install(runtime, module, [node])
    assert module.node_from_handle(7) is not None

    _install(runtime, module, [])
    assert module.node_from_handle(7) is None


def _dense_cube(vertex_count: int):
    """A mesh above the sampling threshold, laid out deterministically.

    One vertex deliberately sits far outside the rest *and* outside the
    strided sample, so the sampled AABB genuinely differs from the node's
    true world AABB. Without that the sampled bounds would coincide with
    the real ones by accident and the regression below would not bite.
    """

    vertices = [(float(i % 97), float((i * 7) % 53), float((i * 13) % 31)) for i in range(vertex_count)]
    sampled_indices = set(vertex_indices_to_hash(vertex_count)[0])
    outlier = next(i for i in range(1, vertex_count + 1) if i not in sampled_indices)
    vertices[outlier - 1] = (-900.0, -900.0, -900.0)
    return vertices


def test_dense_mesh_move_is_not_reported_as_a_geometry_change(scene):
    """Regression: sampled meshes must still be compared in local space.

    A vertex subset only gives an inner-approximation AABB, so the
    empirical world-space probe cannot be used for them. Getting this
    wrong turns every move of a dense object into a false
    GEOMETRY_CHANGED.
    """

    from revision_guard.core.constants import MAX_HASHED_VERTICES

    runtime, module = scene
    dense = _dense_cube(MAX_HASHED_VERTICES + 500)
    node = FakeNode("Terrain", 1, dense, face_count=40000, transform=Matrix3())
    _install(runtime, module, [node])
    before = capture_snapshot()

    assert before.objects[1].geometry.sampled, "test needs a mesh above the sampling threshold"

    node.transform = Matrix3(position=(2500.0, -800.0, 60.0), angle_z_degrees=45.0)
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    assert result.entries[0].change_type is ChangeType.TRANSFORM_CHANGED


def test_dense_mesh_vertex_edit_is_still_detected(scene):
    from revision_guard.core.constants import MAX_HASHED_VERTICES

    runtime, module = scene
    dense = _dense_cube(MAX_HASHED_VERTICES + 500)
    node = FakeNode("Terrain", 1, dense, face_count=40000, transform=Matrix3())
    _install(runtime, module, [node])
    before = capture_snapshot()

    edited = list(dense)
    edited[0] = (500.0, 500.0, 500.0)  # index 1 is always in the sample
    node.local_vertices = edited
    after = capture_snapshot()

    result = compare_snapshots(before, after)
    assert result.entries[0].change_type is ChangeType.GEOMETRY_CHANGED


def test_handle_round_trips_through_get_node_by_handle(scene):
    """Regression: node.handle and getHandleByAnim are different handle spaces.

    Select Changed resolves result rows via maxOps.getNodeByHandle, so the
    handle recorded in a snapshot must be the INode handle.
    """

    runtime, module = scene
    node = FakeNode("Wall_001", 4242, CUBE)
    _install(runtime, module, [node])

    snapshot = capture_snapshot()
    (handle,) = snapshot.objects.keys()

    assert handle == 4242
    assert module.node_from_handle(handle) is node
