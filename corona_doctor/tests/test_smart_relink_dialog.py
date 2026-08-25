"""Real-Qt tests for ui/smart_relink_dialog.py (see conftest.py for the
offscreen platform setup). Search itself is exercised via
``_on_search_finished`` directly (what the worker thread's signal would
trigger) rather than starting a real QThread, to keep this
deterministic; test_smart_relink_worker.py covers the worker itself.
QFileDialog/QMessageBox are monkeypatched — same pattern as
test_textures_view_repair_actions.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType  # noqa: E402
from corona_doctor.repair.models import RepairManifest, RepairResult, RepairState  # noqa: E402
from corona_doctor.smart_relink.models import Candidate, CandidateMetadata, ConfidenceBand, KnownAssetMetadata, MissingAsset, ScoreEvidence  # noqa: E402
from corona_doctor.ui.smart_relink_dialog import SmartRelinkDialog  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeRepairController:
    def __init__(self) -> None:
        self.planned_pairs = None
        self.batch_applied_pairs = None

    def plan_batch_relink(self, pairs):
        self.planned_pairs = list(pairs)  # planning always runs - it's the preview step, never gated
        from corona_doctor.repair.models import RepairPlan

        return RepairPlan(plan_id="plan-1", kind="smart_relink_batch", created_at="now")

    def apply_batch_relink(self, plan):
        self.batch_applied_pairs = self.planned_pairs  # only set once Yes was actually clicked
        manifest = RepairManifest(repair_id="repair-1", plan_id=plan.plan_id, kind=plan.kind, created_at="now", state=RepairState.APPLIED)
        return RepairResult(manifest=manifest, summary="ok")

    def verify(self, manifest):
        return RepairState.VERIFIED, ()


def _asset(asset_id: str, filename: str, old_path: str) -> MissingAsset:
    return MissingAsset(asset_id=asset_id, filename=filename, old_path=old_path, known_metadata=KnownAssetMetadata(), map_ref_ids=(f"ref-{asset_id}",))


def _candidate(path: str, band: ConfidenceBand) -> Candidate:
    return Candidate(path=path, score=1, max_possible_score=1, band=band, evidence=(ScoreEvidence("x", True, 1),), metadata=CandidateMetadata())


def _ref(ref_id: str, filename: str, old_path: str) -> ExternalTextureReference:
    info = PathInfo(raw_path=old_path, normalized_path=old_path, comparison_key=old_path.lower(), path_type=PathType.LOCAL, exists=False)
    return ExternalTextureReference(ref_id=ref_id, map_class="CoronaBitmap", map_name=filename, material_name="Mtl", object_names=("Box01",), path_info=info, filename=filename, extension="jpg")


@pytest.fixture
def dialog(qapp):
    assets = [_asset("a1", "wood.jpg", "C:/proj/wood.jpg"), _asset("a2", "metal.jpg", "C:/proj/metal.jpg")]
    refs = {"a1": (_ref("ref-a1", "wood.jpg", "C:/proj/wood.jpg"),), "a2": (_ref("ref-a2", "metal.jpg", "C:/proj/metal.jpg"),)}
    dlg = SmartRelinkDialog(assets, refs, repair_controller=_FakeRepairController())
    yield dlg
    dlg.deleteLater()


def test_table_starts_with_one_row_per_missing_asset(dialog):
    assert dialog._table.rowCount() == 2  # noqa: SLF001


def test_search_finished_populates_table_with_best_candidate(dialog):
    dialog._on_search_finished({"a1": [_candidate("D:/lib/wood.jpg", ConfidenceBand.EXACT)], "a2": []})  # noqa: SLF001

    assert dialog._table.item(0, 1).text() == "D:/lib/wood.jpg"  # noqa: SLF001
    assert dialog._table.item(0, 2).text() == "EXACT"  # noqa: SLF001
    assert dialog._table.item(1, 2).text() == "UNRESOLVED"  # noqa: SLF001


def test_selecting_a_row_populates_candidate_list(dialog):
    dialog._on_search_finished({"a1": [_candidate("D:/lib/wood.jpg", ConfidenceBand.EXACT)], "a2": []})  # noqa: SLF001
    dialog._table.selectRow(0)  # noqa: SLF001

    assert dialog._candidate_list.count() == 1  # noqa: SLF001


def test_accept_all_exact_accepts_only_exact_band(dialog, monkeypatch):
    dialog._on_search_finished(  # noqa: SLF001
        {
            "a1": [_candidate("D:/lib/wood.jpg", ConfidenceBand.EXACT)],
            "a2": [_candidate("D:/lib/metal.jpg", ConfidenceBand.HIGH)],
        }
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dialog._on_accept_all_exact_clicked()  # noqa: SLF001

    assert dialog._session.accepted == {"a1": "D:/lib/wood.jpg"}  # noqa: SLF001


def test_manual_accept_reject_skip_flow(dialog):
    dialog._on_search_finished(  # noqa: SLF001
        {"a1": [_candidate("D:/lib/wood.jpg", ConfidenceBand.HIGH), _candidate("D:/lib/alt.jpg", ConfidenceBand.MEDIUM)], "a2": []}
    )
    dialog._table.selectRow(0)  # noqa: SLF001
    dialog._candidate_list.setCurrentRow(0)  # noqa: SLF001

    dialog._on_accept_clicked()  # noqa: SLF001
    assert dialog._session.accepted["a1"] == "D:/lib/wood.jpg"  # noqa: SLF001

    dialog._on_reject_clicked()  # noqa: SLF001
    assert "a1" not in dialog._session.accepted  # noqa: SLF001
    assert "D:/lib/wood.jpg" in dialog._session.rejected["a1"]  # noqa: SLF001

    dialog._table.selectRow(1)  # noqa: SLF001
    dialog._on_skip_clicked()  # noqa: SLF001
    assert "a2" in dialog._session.skipped  # noqa: SLF001


def test_build_plan_without_acceptances_shows_info_and_does_not_apply(dialog, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: called.append(a)))

    dialog._on_build_plan_clicked()  # noqa: SLF001

    assert called
    assert dialog._repair.batch_applied_pairs is None  # noqa: SLF001


def test_build_plan_cancel_does_not_apply(dialog, monkeypatch):
    dialog._session.accept("a1", "D:/lib/wood.jpg")  # noqa: SLF001
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))

    dialog._on_build_plan_clicked()  # noqa: SLF001

    assert dialog._repair.batch_applied_pairs is None  # noqa: SLF001


def test_build_plan_approved_applies_and_emits_repair_completed(dialog, monkeypatch):
    dialog._session.accept("a1", "D:/lib/wood.jpg")  # noqa: SLF001
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    completed = []
    dialog.repair_completed.connect(lambda: completed.append(True))

    dialog._on_build_plan_clicked()  # noqa: SLF001

    assert dialog._repair.batch_applied_pairs is not None  # noqa: SLF001
    assert completed == [True]


def test_search_online_shows_unavailable_providers(dialog, monkeypatch):
    dialog._table.selectRow(0)  # noqa: SLF001
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda self_, title, text: shown.append(text)))

    dialog._on_search_online_clicked()  # noqa: SLF001

    assert shown
    assert "unavailable" in shown[0]


def test_search_online_never_relinks_anything(dialog, monkeypatch):
    dialog._table.selectRow(0)  # noqa: SLF001
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dialog._on_search_online_clicked()  # noqa: SLF001

    assert dialog._repair.batch_applied_pairs is None  # noqa: SLF001
