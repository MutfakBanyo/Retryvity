"""Real-Qt tests for ui/smart_relink_worker.py (see conftest.py for the
offscreen platform setup). Calls ``run()`` directly (not ``start()``) so
the search executes synchronously on the test thread — exercises the
exact same code path a real background thread runs, without needing
real OS-thread synchronization in the test itself."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from corona_doctor.devtools.torture_assets import write_stub_png  # noqa: E402
from corona_doctor.smart_relink.models import KnownAssetMetadata, MissingAsset  # noqa: E402
from corona_doctor.ui.smart_relink_worker import SmartRelinkSearchWorker  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _asset(asset_id: str, filename: str) -> MissingAsset:
    return MissingAsset(asset_id=asset_id, filename=filename, old_path=f"C:/proj/{filename}", known_metadata=KnownAssetMetadata(), map_ref_ids=("ref-1",))


def test_worker_finds_candidates_for_every_missing_asset(qapp, tmp_path):
    write_stub_png(tmp_path / "lib" / "wood.jpg", 32, 32)
    write_stub_png(tmp_path / "lib" / "metal.jpg", 32, 32)

    worker = SmartRelinkSearchWorker([str(tmp_path / "lib")], [_asset("a1", "wood.jpg"), _asset("a2", "metal.jpg")])

    progress_calls = []
    results_holder = {}
    worker.progress.connect(lambda done, total: progress_calls.append((done, total)))
    worker.finished_search.connect(lambda results: results_holder.update(results))

    worker.run()

    assert progress_calls == [(1, 2), (2, 2)]
    assert results_holder["a1"][0].path.endswith("wood.jpg")
    assert results_holder["a2"][0].path.endswith("metal.jpg")


def test_worker_reports_empty_candidates_for_unmatched_asset(qapp, tmp_path):
    (tmp_path / "lib").mkdir()
    worker = SmartRelinkSearchWorker([str(tmp_path / "lib")], [_asset("a1", "nothing_here.jpg")])

    results_holder = {}
    worker.finished_search.connect(lambda results: results_holder.update(results))
    worker.run()

    assert results_holder["a1"] == []


def test_worker_cancellation_stops_before_scoring_remaining_assets(qapp, tmp_path):
    write_stub_png(tmp_path / "lib" / "a.jpg", 16, 16)
    worker = SmartRelinkSearchWorker([str(tmp_path / "lib")], [_asset("a1", "a.jpg"), _asset("a2", "b.jpg"), _asset("a3", "c.jpg")])
    worker.cancel()  # cancel before run() - proves the loop's cancel_check is honored immediately

    results_holder = {}
    worker.finished_search.connect(lambda results: results_holder.update(results))
    worker.run()

    assert results_holder == {}


def test_worker_emits_finished_search_exactly_once(qapp, tmp_path):
    (tmp_path / "lib").mkdir()
    worker = SmartRelinkSearchWorker([str(tmp_path / "lib")], [_asset("a1", "x.jpg")])

    calls = []
    worker.finished_search.connect(lambda results: calls.append(results))
    worker.run()

    assert len(calls) == 1
