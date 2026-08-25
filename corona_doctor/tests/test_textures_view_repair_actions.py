"""Real-Qt tests for ui/views/textures_view.py's repair action wiring
(see conftest.py for the offscreen platform setup). A fake
RepairController isolates this to "does the view call the right thing
with the right arguments and never mutate anything without an explicit
Yes" — real planning/apply/verify logic is covered end-to-end in
test_repair_controller.py.

QFileDialog/QMessageBox/QInputDialog are monkeypatched at their static
methods — headless offscreen Qt cannot click a real modal dialog, so
this is the standard, safe way to exercise the flow without hanging.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType  # noqa: E402
from corona_doctor.repair.models import RepairManifest, RepairResult, RepairState  # noqa: E402
from corona_doctor.repair.planner import RelinkCandidate  # noqa: E402
from corona_doctor.ui.views.textures_view import TexturesView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeRepairController:
    def __init__(self) -> None:
        self.select_objects_calls: list[tuple[str, ...]] = []
        self.make_portable_applied = False
        self.relink_applied = False
        self.candidates: list[RelinkCandidate] = []
        self.classification = "none"
        self.plan_destination: str | None = None

    def select_objects(self, names) -> int:
        self.select_objects_calls.append(tuple(names))
        return 2

    def plan_make_portable(self, references, destination_dir):
        self.plan_destination = destination_dir
        return _fake_plan()

    def apply_make_portable(self, plan):
        self.make_portable_applied = True
        return _fake_result()

    def find_candidates(self, missing_filename, search_roots):
        return self.candidates, self.classification

    def plan_relink(self, ref, chosen_path):
        return _fake_plan()

    def apply_relink(self, plan):
        self.relink_applied = True
        return _fake_result()

    def verify(self, manifest):
        return RepairState.VERIFIED, ()


def _fake_plan():
    from corona_doctor.repair.models import RepairPlan

    return RepairPlan(plan_id="plan-1", kind="make_project_portable", created_at="now")


def _fake_result() -> RepairResult:
    manifest = RepairManifest(repair_id="repair-1", plan_id="plan-1", kind="make_project_portable", created_at="now", state=RepairState.APPLIED)
    return RepairResult(manifest=manifest, summary="1 operation(s) applied.")


def _path_info(exists: bool | None) -> PathInfo:
    return PathInfo(raw_path="C:/proj/wood.jpg", normalized_path="C:/proj/wood.jpg", comparison_key="c:/proj/wood.jpg", path_type=PathType.LOCAL, exists=exists)


def _ref(*, exists=True, object_names=("Box01",)) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id="ref-1",
        map_class="CoronaBitmap",
        map_name="wood.jpg",
        material_name="Mtl",
        object_names=object_names,
        path_info=_path_info(exists),
        filename="wood.jpg",
        extension="jpg",
    )


@pytest.fixture
def view(qapp):
    return TexturesView(repair_controller=_FakeRepairController())


def test_relink_button_visible_only_for_missing_texture(view):
    # isHidden() (not isVisible()) - these widgets are never .show()n
    # (no real window in offscreen tests), so isVisible() would always
    # report False regardless of the explicit setVisible() calls below.
    view._details.show_reference(_ref(exists=False))  # noqa: SLF001
    assert not view._details._relink_button.isHidden()  # noqa: SLF001

    view._details.show_reference(_ref(exists=True))  # noqa: SLF001
    assert view._details._relink_button.isHidden()  # noqa: SLF001


def test_show_objects_button_visible_only_when_objects_known(view):
    view._details.show_reference(_ref(object_names=("Box01",)))  # noqa: SLF001
    assert not view._details._show_objects_button.isHidden()  # noqa: SLF001

    view._details.show_reference(_ref(object_names=()))  # noqa: SLF001
    assert view._details._show_objects_button.isHidden()  # noqa: SLF001


def test_show_objects_action_delegates_to_controller(view):
    view._details.show_reference(_ref(object_names=("Box01", "Box02")))  # noqa: SLF001
    view._on_show_objects_requested()  # noqa: SLF001

    assert view._repair.select_objects_calls == [("Box01", "Box02")]  # noqa: SLF001


def test_make_portable_without_references_shows_info_and_does_not_plan(view, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: called.append(a)))

    view._on_make_portable_clicked()  # noqa: SLF001

    assert called
    assert not view._repair.make_portable_applied  # noqa: SLF001


def test_make_portable_cancel_never_applies(view, monkeypatch):
    view.set_references((_ref(),))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "D:/Project/Textures"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))

    view._on_make_portable_clicked()  # noqa: SLF001

    assert not view._repair.make_portable_applied  # noqa: SLF001


def test_make_portable_approved_applies_and_emits_repair_completed(view, monkeypatch):
    view.set_references((_ref(),))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "D:/Project/Textures"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    completed = []
    view.repair_completed.connect(lambda: completed.append(True))

    view._on_make_portable_clicked()  # noqa: SLF001

    assert view._repair.make_portable_applied  # noqa: SLF001
    assert view._repair.plan_destination == "D:/Project/Textures"  # noqa: SLF001
    assert completed == [True]


def test_make_portable_empty_destination_cancels_silently(view, monkeypatch):
    view.set_references((_ref(),))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))

    view._on_make_portable_clicked()  # noqa: SLF001

    assert not view._repair.make_portable_applied  # noqa: SLF001


def test_relink_zero_candidates_shows_info_and_stays_unresolved(view, monkeypatch):
    view._details.show_reference(_ref(exists=False))  # noqa: SLF001
    view._repair.classification = "none"  # noqa: SLF001
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "C:/search"))
    called = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: called.append(a)))

    view._on_relink_requested()  # noqa: SLF001

    assert called
    assert not view._repair.relink_applied  # noqa: SLF001


def test_relink_single_candidate_approved_applies(view, monkeypatch):
    view._details.show_reference(_ref(exists=False))  # noqa: SLF001
    view._repair.candidates = [RelinkCandidate(path="C:/found/wood.jpg", score=100, reasons=("exact filename match",))]  # noqa: SLF001
    view._repair.classification = "single"  # noqa: SLF001
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "C:/search"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    view._on_relink_requested()  # noqa: SLF001

    assert view._repair.relink_applied  # noqa: SLF001


def test_relink_multiple_candidates_uses_input_dialog(view, monkeypatch):
    view._details.show_reference(_ref(exists=False))  # noqa: SLF001
    view._repair.candidates = [  # noqa: SLF001
        RelinkCandidate(path="C:/a/wood.jpg", score=100, reasons=()),
        RelinkCandidate(path="C:/b/wood.jpg", score=100, reasons=()),
    ]
    view._repair.classification = "multiple"  # noqa: SLF001
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "C:/search"))
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("C:/b/wood.jpg", True)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    view._on_relink_requested()  # noqa: SLF001

    assert view._repair.relink_applied  # noqa: SLF001


def test_relink_multiple_candidates_dialog_cancelled_does_not_apply(view, monkeypatch):
    view._details.show_reference(_ref(exists=False))  # noqa: SLF001
    view._repair.candidates = [  # noqa: SLF001
        RelinkCandidate(path="C:/a/wood.jpg", score=100, reasons=()),
        RelinkCandidate(path="C:/b/wood.jpg", score=100, reasons=()),
    ]
    view._repair.classification = "multiple"  # noqa: SLF001
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "C:/search"))
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False)))

    view._on_relink_requested()  # noqa: SLF001

    assert not view._repair.relink_applied  # noqa: SLF001
