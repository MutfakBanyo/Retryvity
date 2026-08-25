"""Background search worker for Smart Asset Recovery — runs the
recursive filesystem search, candidate pre-filtering, and lazy metadata/
scoring OFF the Qt/3ds Max main thread, per docs/SMART_RELINK.md,
"Search performance".

Everything this thread touches (``smart_relink/index.py``,
``smart_relink/metadata.py``, ``smart_relink/scoring.py``) is pure
Python with no pymxs/Qt-widget access — "background workers may perform
filesystem discovery and metadata analysis only" (never scene access,
never widget mutation) is enforced by construction here, not just by
convention: this module imports nothing from ``adapters/`` or
``ui/views/``.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from corona_doctor.smart_relink.index import build_search_index
from corona_doctor.smart_relink.metadata import read_candidate_metadata
from corona_doctor.smart_relink.models import Candidate, MissingAsset
from corona_doctor.smart_relink.scoring import rank_candidates


class SmartRelinkSearchWorker(QThread):
    """One search pass over ``roots`` for every asset in
    ``missing_assets``. Emits ``progress(done, total)`` as each asset
    finishes scoring, and ``finished_search(results)`` with
    ``{asset_id: [Candidate, ...]}`` when done (or when cancelled — a
    cancelled run still emits whatever it completed, never silently
    drops it). Call :meth:`cancel` from the main thread to stop early;
    checked between assets, not mid-index-build, so cancellation can lag
    by up to one very large root's walk — acceptable since the walk
    itself is the only unbounded step and ``build_search_index`` already
    checks its own ``cancel_check`` between directories.
    """

    progress = Signal(int, int)
    finished_search = Signal(dict)

    def __init__(self, roots: list[str], missing_assets: list[MissingAsset], parent=None) -> None:
        super().__init__(parent)
        self._roots = roots
        self._missing_assets = missing_assets
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D102 - QThread override
        index = build_search_index(self._roots, walk_fn=self._walk, cancel_check=lambda: self._cancelled)

        results: dict[str, list[Candidate]] = {}
        total = len(self._missing_assets)
        for i, asset in enumerate(self._missing_assets, start=1):
            if self._cancelled:
                break
            candidate_files = index.candidates_for_asset(asset.filename)
            candidates = rank_candidates(asset, [f.path for f in candidate_files], read_candidate_metadata)
            results[asset.asset_id] = candidates
            self.progress.emit(i, total)

        self.finished_search.emit(results)

    @staticmethod
    def _walk(root: str):
        import os

        yield from os.walk(root)
