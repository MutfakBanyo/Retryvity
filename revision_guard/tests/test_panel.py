"""Panel behaviour, driven headlessly with a fake scene.

These run offscreen without 3ds Max: a fake pymxs supplies the scene, so
the panel's real button handlers, error paths and result rendering are
exercised end to end.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from revision_guard.core.models import ChangeType  # noqa: E402
from revision_guard.tests.fake_pymxs import FakeNode, FakeRuntime, Matrix3, make_module  # noqa: E402
from revision_guard.tests.test_scene_access import CUBE  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def panel(qt_app, monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setitem(sys.modules, "pymxs", make_module(runtime))

    import revision_guard.max.scene_access as scene_access

    importlib.reload(scene_access)

    from revision_guard.ui import panel as panel_module

    widget = panel_module.RevisionGuardPanel()
    yield runtime, widget, panel_module

    widget.deleteLater()
    monkeypatch.undo()
    importlib.reload(scene_access)


def _install(runtime, nodes):
    runtime.objects = list(nodes)
    make_module(runtime)


def test_compare_without_snapshot_reports_the_error(panel):
    runtime, widget, module = panel
    _install(runtime, [FakeNode("Box", 1, CUBE)])

    widget._on_compare()

    assert widget._status.text() == module.NO_SNAPSHOT_MESSAGE


def test_empty_scene_reports_no_eligible_objects(panel):
    runtime, widget, module = panel
    _install(runtime, [])

    widget._on_create_snapshot()

    assert widget._status.text() == module.EMPTY_SCENE_MESSAGE
    assert not widget._compare_button.isEnabled()


def test_snapshot_then_compare_populates_the_summary(panel):
    runtime, widget, _ = panel
    kept = FakeNode("Wall_001", 1, CUBE)
    moved = FakeNode("Chair_008", 2, CUBE, transform=Matrix3(position=(50.0, 0.0, 0.0)))
    doomed = FakeNode("Column_003", 3, CUBE, transform=Matrix3(position=(100.0, 0.0, 0.0)))
    _install(runtime, [kept, moved, doomed])

    widget._on_create_snapshot()
    assert widget._snapshot is not None
    assert "3 geometry objects" in widget._snapshot_label.text()
    assert widget._compare_button.isEnabled()

    moved.transform = Matrix3(position=(50.0, 240.0, 0.0))
    fresh = FakeNode("Table_New", 4, CUBE, transform=Matrix3(position=(150.0, 0.0, 0.0)))
    _install(runtime, [kept, moved, fresh])

    widget._on_compare()

    counts = {change: widget._count_labels[change].text() for change in widget._count_labels}
    assert counts[ChangeType.ADDED] == "1"
    assert counts[ChangeType.REMOVED] == "1"
    assert counts[ChangeType.TRANSFORM_CHANGED] == "1"
    assert counts[ChangeType.UNCHANGED] == "1"
    assert widget._scanned_label.text() == "Objects scanned: 3"


def test_result_list_lists_changes_and_omits_unchanged(panel):
    runtime, widget, _ = panel
    kept = FakeNode("Wall_001", 1, CUBE)
    moved = FakeNode("Chair_008", 2, CUBE, transform=Matrix3(position=(50.0, 0.0, 0.0)))
    _install(runtime, [kept, moved])
    widget._on_create_snapshot()

    moved.transform = Matrix3(position=(50.0, 240.0, 0.0))
    _install(runtime, [kept, moved])
    widget._on_compare()

    rows = [widget._list.item(i).text() for i in range(widget._list.count())]
    assert rows == ["[TRANSFORM_CHANGED] Chair_008"]


def test_select_changed_selects_only_existing_nodes(panel):
    runtime, widget, _ = panel
    moved = FakeNode("Chair_008", 1, CUBE)
    doomed = FakeNode("Column_003", 2, CUBE, transform=Matrix3(position=(90.0, 0.0, 0.0)))
    _install(runtime, [moved, doomed])
    widget._on_create_snapshot()

    moved.transform = Matrix3(position=(0.0, 200.0, 0.0))
    _install(runtime, [moved])
    widget._on_compare()

    selected = widget._on_select_changed()
    assert selected == 1
    assert [node.name for node in runtime.selection] == ["Chair_008"]


def test_select_changed_without_a_result_is_a_no_op(panel):
    runtime, widget, _ = panel
    _install(runtime, [FakeNode("Box", 1, CUBE)])
    assert widget._on_select_changed() == 0


def test_clear_result_keeps_the_snapshot(panel):
    runtime, widget, _ = panel
    node = FakeNode("Box", 1, CUBE)
    _install(runtime, [node])
    widget._on_create_snapshot()
    widget._on_compare()

    widget._on_clear_result()

    assert widget._result is None
    assert widget._list.count() == 0
    assert widget._snapshot is not None
    assert widget._compare_button.isEnabled()
    assert not widget._select_button.isEnabled()


def test_no_changes_renders_a_placeholder_row(panel):
    runtime, widget, _ = panel
    node = FakeNode("Box", 1, CUBE)
    _install(runtime, [node])
    widget._on_create_snapshot()
    widget._on_compare()

    assert widget._list.item(0).text() == "No changes detected."


def test_a_broken_object_does_not_break_the_panel(panel):
    runtime, widget, _ = panel
    good = FakeNode("Good", 1, CUBE)
    broken = FakeNode("Broken", 2, CUBE)
    _install(runtime, [good, broken])

    original = runtime.snapshotAsMesh
    runtime.snapshotAsMesh = lambda node: (_ for _ in ()).throw(RuntimeError("boom")) if node.name == "Broken" else original(node)

    widget._on_create_snapshot()

    assert widget._snapshot is not None
    assert widget._snapshot.object_count == 1
    assert "1 skipped" in widget._status.text()


def test_double_click_selects_the_node(panel):
    runtime, widget, _ = panel
    moved = FakeNode("Chair_008", 1, CUBE)
    _install(runtime, [moved])
    widget._on_create_snapshot()

    moved.transform = Matrix3(position=(0.0, 200.0, 0.0))
    _install(runtime, [moved])
    widget._on_compare()

    widget._on_item_double_clicked(widget._list.item(0))
    assert [node.name for node in runtime.selection] == ["Chair_008"]


def test_opening_the_panel_twice_reuses_one_dock(qt_app):
    from revision_guard.ui import dock

    dock.clear_instance()
    try:
        first = dock.show_panel()
        second = dock.show_panel()
        assert first is second
    finally:
        dock.clear_instance()
        first.deleteLater()


def test_scanning_an_empty_scene_keeps_an_earlier_snapshot(panel):
    runtime, widget, module = panel
    _install(runtime, [FakeNode("Box", 1, CUBE)])
    widget._on_create_snapshot()
    original = widget._snapshot

    _install(runtime, [])
    widget._on_create_snapshot()

    assert widget._status.text() == module.EMPTY_SCENE_MESSAGE
    assert widget._snapshot is original
    assert widget._compare_button.isEnabled()


def test_deleting_everything_reports_every_object_as_removed(panel):
    runtime, widget, _ = panel
    _install(runtime, [FakeNode("Wall_001", 1, CUBE), FakeNode("Wall_002", 2, CUBE)])
    widget._on_create_snapshot()

    _install(runtime, [])
    widget._on_compare()

    assert widget._count_labels[ChangeType.REMOVED].text() == "2"
    assert widget._on_select_changed() == 0
