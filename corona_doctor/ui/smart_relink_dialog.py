"""Smart Asset Recovery review dialog — the batch review screen for
"Find All Missing Assets" (see docs/SMART_RELINK.md, "Batch review UI").

Search runs on a background ``SmartRelinkSearchWorker`` (QThread) so a
large asset library never freezes the panel; relinking always goes
through ``ui/repair_controller.py`` -> the Repair Engine, never a direct
scene mutation from here (see docs/SMART_RELINK.md, "Relink must use the
Repair Engine"). Uses only native Qt widgets and the existing design
tokens — no new visual language.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.repair.models import OperationKind, ValidationState
from corona_doctor.smart_relink.models import Candidate, ConfidenceBand, MissingAsset
from corona_doctor.smart_relink.providers import build_privacy_safe_query, list_providers
from corona_doctor.smart_relink.session import SearchSession
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.qt_safe import ignore_signal_args
from corona_doctor.ui.repair_controller import RepairController
from corona_doctor.ui.smart_relink_worker import SmartRelinkSearchWorker

_BAND_LABELS = {
    ConfidenceBand.EXACT: "EXACT",
    ConfidenceBand.HIGH: "HIGH",
    ConfidenceBand.MEDIUM: "MEDIUM",
    ConfidenceBand.LOW: "LOW",
    ConfidenceBand.NONE: "UNRESOLVED",
}

_THUMBNAIL_SIZE = 96


class SmartRelinkDialog(QDialog):
    repair_completed = Signal()

    def __init__(
        self,
        missing_assets: list[MissingAsset],
        refs_by_asset_id: dict[str, tuple[ExternalTextureReference, ...]],
        repair_controller: RepairController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Smart Asset Recovery")
        self.resize(760, 560)

        self._refs_by_asset_id = refs_by_asset_id
        self._repair = repair_controller or RepairController()
        self._session = SearchSession(missing_assets=tuple(missing_assets))
        self._worker: SmartRelinkSearchWorker | None = None
        self._thumbnail_cache: dict[str, QPixmap] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(self._build_roots_row())
        root.addWidget(self._build_search_row())
        root.addWidget(self._build_table(), stretch=1)
        root.addWidget(self._build_detail_panel())
        root.addWidget(self._build_bottom_row())

        self._refresh_table()

    # -- layout builders -----------------------------------------------------

    def _build_roots_row(self) -> QWidget:
        box = QWidget(self)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self._roots_list = QListWidget(box)
        self._roots_list.setMaximumHeight(70)
        layout.addWidget(self._roots_list, stretch=1)

        buttons = QVBoxLayout()
        add_button = QPushButton("Add Root…", box)
        add_button.setObjectName("Secondary")
        add_button.clicked.connect(ignore_signal_args(self._on_add_root))
        buttons.addWidget(add_button)

        remove_button = QPushButton("Remove Root", box)
        remove_button.setObjectName("Secondary")
        remove_button.clicked.connect(ignore_signal_args(self._on_remove_root))
        buttons.addWidget(remove_button)
        layout.addLayout(buttons)
        return box

    def _build_search_row(self) -> QWidget:
        box = QWidget(self)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search_button = QPushButton("Search Library", box)
        self._search_button.setObjectName("Primary")
        self._search_button.clicked.connect(ignore_signal_args(self._on_search_clicked))
        layout.addWidget(self._search_button)

        self._cancel_button = QPushButton("Cancel Search", box)
        self._cancel_button.setObjectName("Secondary")
        self._cancel_button.clicked.connect(ignore_signal_args(self._on_cancel_clicked))
        self._cancel_button.hide()
        layout.addWidget(self._cancel_button)

        self._progress_bar = QProgressBar(box)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar, stretch=1)

        self._search_online_button = QPushButton("Search Online", box)
        self._search_online_button.setObjectName("Secondary")
        self._search_online_button.clicked.connect(ignore_signal_args(self._on_search_online_clicked))
        layout.addWidget(self._search_online_button)
        return box

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Missing Asset", "Best Candidate", "Confidence"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        return self._table

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("Surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        top = QHBoxLayout()
        self._thumbnail_label = QLabel(panel)
        self._thumbnail_label.setFixedSize(_THUMBNAIL_SIZE, _THUMBNAIL_SIZE)
        self._thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail_label.setObjectName("Caption")
        self._thumbnail_label.setText("no preview")
        top.addWidget(self._thumbnail_label)

        self._evidence_text = QTextEdit(panel)
        self._evidence_text.setReadOnly(True)
        self._evidence_text.setMaximumHeight(_THUMBNAIL_SIZE)
        top.addWidget(self._evidence_text, stretch=1)
        layout.addLayout(top)

        self._candidate_list = QListWidget(panel)
        self._candidate_list.setMaximumHeight(70)
        self._candidate_list.currentRowChanged.connect(self._on_candidate_row_changed)
        layout.addWidget(self._candidate_list)

        actions = QHBoxLayout()
        self._accept_button = QPushButton("Accept", panel)
        self._accept_button.clicked.connect(ignore_signal_args(self._on_accept_clicked))
        actions.addWidget(self._accept_button)

        self._reject_button = QPushButton("Reject", panel)
        self._reject_button.setObjectName("Secondary")
        self._reject_button.clicked.connect(ignore_signal_args(self._on_reject_clicked))
        actions.addWidget(self._reject_button)

        self._skip_button = QPushButton("Skip", panel)
        self._skip_button.setObjectName("Secondary")
        self._skip_button.clicked.connect(ignore_signal_args(self._on_skip_clicked))
        actions.addWidget(self._skip_button)
        layout.addLayout(actions)
        return panel

    def _build_bottom_row(self) -> QWidget:
        box = QWidget(self)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self._accept_all_exact_button = QPushButton("Accept All Exact Matches", box)
        self._accept_all_exact_button.clicked.connect(ignore_signal_args(self._on_accept_all_exact_clicked))
        layout.addWidget(self._accept_all_exact_button)

        layout.addStretch(1)

        self._build_plan_button = QPushButton("Build Repair Plan…", box)
        self._build_plan_button.setObjectName("Primary")
        self._build_plan_button.clicked.connect(ignore_signal_args(self._on_build_plan_clicked))
        layout.addWidget(self._build_plan_button)

        close_button = QPushButton("Close", box)
        close_button.setObjectName("Secondary")
        close_button.clicked.connect(ignore_signal_args(self.close))
        layout.addWidget(close_button)
        return box

    # -- roots ----------------------------------------------------------

    def _on_add_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Add a folder to search")
        if not directory:
            return
        if directory not in [self._roots_list.item(i).text() for i in range(self._roots_list.count())]:
            self._roots_list.addItem(QListWidgetItem(directory))

    def _on_remove_root(self) -> None:
        for item in self._roots_list.selectedItems():
            self._roots_list.takeItem(self._roots_list.row(item))

    def _roots(self) -> list[str]:
        return [self._roots_list.item(i).text() for i in range(self._roots_list.count())]

    # -- search -----------------------------------------------------------

    def _on_search_clicked(self) -> None:
        roots = self._roots()
        if not roots:
            QMessageBox.information(self, "Search Library", "Add at least one folder to search first.")
            return
        if not self._session.missing_assets:
            QMessageBox.information(self, "Search Library", "No missing textures to search for.")
            return

        self._search_button.setEnabled(False)
        self._cancel_button.show()
        self._progress_bar.setRange(0, len(self._session.missing_assets))
        self._progress_bar.setValue(0)
        self._progress_bar.show()

        self._worker = SmartRelinkSearchWorker(roots, list(self._session.missing_assets), self)
        self._worker.progress.connect(self._on_search_progress)
        self._worker.finished_search.connect(self._on_search_finished)
        self._worker.start()

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_search_progress(self, done: int, total: int) -> None:
        self._progress_bar.setValue(done)

    def _on_search_finished(self, results: dict) -> None:
        for asset_id, candidates in results.items():
            self._session.set_candidates(asset_id, candidates)
        self._search_button.setEnabled(True)
        self._cancel_button.hide()
        self._progress_bar.hide()
        self._refresh_table()

    # -- table / detail -----------------------------------------------------

    def _refresh_table(self) -> None:
        self._table.setRowCount(len(self._session.missing_assets))
        for row, asset in enumerate(self._session.missing_assets):
            self._table.setItem(row, 0, QTableWidgetItem(asset.filename))
            best = self._session.best_candidate(asset.asset_id)
            self._table.setItem(row, 1, QTableWidgetItem(best.path if best else "—"))
            confidence = f"{best.percent}%" if best and best.band != ConfidenceBand.EXACT else _BAND_LABELS[best.band if best else ConfidenceBand.NONE]
            self._table.setItem(row, 2, QTableWidgetItem(confidence))

    def _selected_asset(self) -> MissingAsset | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        return self._session.missing_assets[rows[0].row()]

    def _on_table_selection_changed(self) -> None:
        asset = self._selected_asset()
        self._candidate_list.clear()
        self._evidence_text.clear()
        self._thumbnail_label.setText("no preview")
        self._thumbnail_label.setPixmap(QPixmap())
        if asset is None:
            return
        for candidate in self._session.candidates_by_asset.get(asset.asset_id, []):
            item = QListWidgetItem(f"[{_BAND_LABELS[candidate.band]} · {candidate.percent}%] {candidate.path}")
            self._candidate_list.addItem(item)
        if self._candidate_list.count() > 0:
            self._candidate_list.setCurrentRow(0)

    def _selected_candidate(self) -> Candidate | None:
        asset = self._selected_asset()
        if asset is None:
            return None
        candidates = self._session.candidates_by_asset.get(asset.asset_id, [])
        row = self._candidate_list.currentRow()
        if row < 0 or row >= len(candidates):
            return None
        return candidates[row]

    def _on_candidate_row_changed(self, _row: int) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            self._evidence_text.clear()
            self._thumbnail_label.setText("no preview")
            self._thumbnail_label.setPixmap(QPixmap())
            return

        lines = []
        for line in candidate.evidence:
            mark = "?" if line.matched is None else ("✓" if line.matched else "✗")
            lines.append(f"{mark} {line.label}")
        self._evidence_text.setPlainText("\n".join(lines))
        self._set_thumbnail(candidate.path)

    def _set_thumbnail(self, path: str) -> None:
        pixmap = self._thumbnail_cache.get(path)
        if pixmap is None:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    _THUMBNAIL_SIZE,
                    _THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            self._thumbnail_cache[path] = pixmap
        if pixmap.isNull():
            self._thumbnail_label.setText("no preview\n(metadata only)")
            self._thumbnail_label.setPixmap(QPixmap())
        else:
            self._thumbnail_label.setText("")
            self._thumbnail_label.setPixmap(pixmap)

    # -- accept/reject/skip -------------------------------------------------

    def _on_accept_clicked(self) -> None:
        asset = self._selected_asset()
        candidate = self._selected_candidate()
        if asset is None or candidate is None:
            return
        self._session.accept(asset.asset_id, candidate.path)
        self._refresh_table()

    def _on_reject_clicked(self) -> None:
        asset = self._selected_asset()
        candidate = self._selected_candidate()
        if asset is None or candidate is None:
            return
        self._session.reject(asset.asset_id, candidate.path)
        self._refresh_table()

    def _on_skip_clicked(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            return
        self._session.skip(asset.asset_id)
        self._refresh_table()

    def _on_accept_all_exact_clicked(self) -> None:
        count = self._session.accept_all_exact()
        self._refresh_table()
        QMessageBox.information(self, "Accept All Exact Matches", f"{count} exact match(es) accepted.")

    # -- online search (architecture only this milestone) ---------------

    def _on_search_online_clicked(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            QMessageBox.information(self, "Search Online", "Select a missing asset first.")
            return

        providers = list_providers()
        available = [p for p in providers if p.is_available()]
        query = build_privacy_safe_query(asset)
        lines = [f"Query (privacy-safe): {query}", ""]
        for provider in providers:
            status = "available" if provider.is_available() else "unavailable — not configured"
            lines.append(f"{provider.name}: {status}")
        if not available:
            lines.append("")
            lines.append(
                "No online provider is configured. Online replacements are never automatic — "
                "this is a REPLACEMENT search, not local recovery of the original asset. "
                "Configure a provider's API key to enable it."
            )
        QMessageBox.information(self, "Search Online", "\n".join(lines))

    # -- build & apply the repair plan --------------------------------------

    def _on_build_plan_clicked(self) -> None:
        accepted = self._session.accepted_pairs()
        if not accepted:
            QMessageBox.information(self, "Build Repair Plan", "No candidates have been accepted yet.")
            return

        pairs = [(self._refs_by_asset_id.get(asset_id, ()), path) for asset_id, path in accepted]
        plan = self._repair.plan_batch_relink(pairs)
        ready = [op for op in plan.operations if op.kind == OperationKind.RELINK_TEXTURE and op.validation_state == ValidationState.READY]

        preview = (
            "SMART ASSET RECOVERY\n\n"
            f"{len(accepted)} missing asset(s) approved for relink\n"
            f"{len(ready)} map path(s) will be updated\n\n"
            "No changes have been made yet."
        )
        confirmed = QMessageBox.question(
            self,
            "Build Repair Plan",
            preview,
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        result = self._repair.apply_batch_relink(plan)
        state, problems = self._repair.verify(result.manifest)

        lines = [result.summary, f"State: {state.value.upper()}"]
        if result.errors:
            lines.append("")
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in result.errors)
        if problems:
            lines.append("")
            lines.append("Verification issues:")
            lines.extend(f"  - {p}" for p in problems)
        QMessageBox.information(self, "Repair Result", "\n".join(lines))
        self.repair_completed.emit()
