"""The smoke test's own orchestration, driven without 3ds Max.

Running run_smoke_test() for real needs the host, so here the scene-edit
helpers are swapped for fakes backed by the same FakeRuntime the rest of
the suite uses. That checks the wiring - object names, mutation order,
expected categories, the report - so the in-Max run only has to prove the
pymxs calls themselves work.
"""

from __future__ import annotations

import contextlib
import importlib
import sys

import pytest

from revision_guard.core.models import ChangeType
from revision_guard.tests.fake_pymxs import FakeNode, FakeRuntime, Matrix3, make_module
from revision_guard.tests.test_scene_access import CUBE


class FakeSceneEdit:
    """Stand-in for revision_guard.max.scene_edit, backed by FakeRuntime."""

    def __init__(self, runtime: FakeRuntime) -> None:
        self._runtime = runtime
        self._next_handle = 1

    def _refresh(self) -> None:
        make_module(self._runtime)

    @staticmethod
    def undo_disabled():
        return contextlib.nullcontext()

    def create_box(self, name, position, size=20.0):
        node = FakeNode(name, self._next_handle, CUBE, transform=Matrix3(position=position))
        self._next_handle += 1
        self._runtime.objects.append(node)
        self._refresh()
        return node

    def convert_to_editable_poly(self, node):
        node.class_name = "Editable_Poly"
        return node

    def offset_poly_vertex(self, node, index, delta):
        vertices = list(node.local_vertices)
        x, y, z = vertices[index - 1]
        vertices[index - 1] = (x + delta[0], y + delta[1], z + delta[2])
        node.local_vertices = vertices

    def move_node(self, node, delta):
        old = node.transform
        node.transform = Matrix3(
            position=tuple(old.position[i] + delta[i] for i in range(3)),
            angle_z_degrees=old.angle * 180.0 / 3.141592653589793,
            scale=old.scale,
        )

    def rotate_node(self, node, degrees_z):
        old = node.transform
        node.transform = Matrix3(
            position=old.position,
            angle_z_degrees=(old.angle * 180.0 / 3.141592653589793) + degrees_z,
            scale=old.scale,
        )

    def scale_node(self, node, factor):
        old = node.transform
        node.transform = Matrix3(
            position=old.position,
            angle_z_degrees=old.angle * 180.0 / 3.141592653589793,
            scale=tuple(component * factor for component in old.scale),
        )

    def delete_node(self, node):
        self._runtime.objects.remove(node)
        self._refresh()

    def nodes_with_prefix(self, prefix):
        return [node for node in self._runtime.objects if node.name.startswith(prefix)]

    def delete_nodes_with_prefix(self, prefix):
        doomed = self.nodes_with_prefix(prefix)
        for node in doomed:
            self._runtime.objects.remove(node)
        self._refresh()
        return len(doomed)


@pytest.fixture
def smoke(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setitem(sys.modules, "pymxs", make_module(runtime))

    import revision_guard.max.scene_access as scene_access

    importlib.reload(scene_access)

    from revision_guard.devtools import smoke_test

    yield runtime, smoke_test

    monkeypatch.undo()
    importlib.reload(scene_access)


def test_all_cases_pass_against_a_fake_scene(smoke):
    runtime, smoke_test = smoke
    results = smoke_test._run_cases(FakeSceneEdit(runtime))

    expected = {label: change_type for label, _name, change_type in smoke_test._CASES}
    assert results == expected


def test_the_report_is_a_pass_when_every_case_matches(smoke, capsys):
    runtime, smoke_test = smoke
    results = smoke_test._run_cases(FakeSceneEdit(runtime))

    assert smoke_test._report(results, None) is True

    output = capsys.readouterr().out
    assert f"RESULT: {len(smoke_test._CASES)}/{len(smoke_test._CASES)} PASS" in output


def test_the_report_shows_what_a_failing_case_actually_produced(smoke, capsys):
    _runtime, smoke_test = smoke
    results = {label: ChangeType.UNCHANGED for label, _name, _expected in smoke_test._CASES}

    assert smoke_test._report(results, None) is False

    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "(got UNCHANGED)" in output


def test_run_smoke_test_skips_cleanly_without_3ds_max(capsys):
    from revision_guard.devtools.smoke_test import run_smoke_test

    assert run_smoke_test() is False
    assert "pymxs is unavailable" in capsys.readouterr().out
