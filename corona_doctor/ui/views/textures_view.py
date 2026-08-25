"""The Textures screen: Texture Doctor's scanned texture list + details.

Uses Qt Model/View (QTableView + TextureTableModel + a QSortFilterProxyModel
for search/filter) — never one QWidget per texture, per the UI performance
rules. Operates entirely on cached scan results: search/filter/sort never
re-touch the 3ds Max scene (see docs/TEXTURE_DOCTOR.md).

Repair actions (Make Project Portable / Find & Relink / Show Objects) go
through ``ui/repair_controller.py`` — this view builds dialogs/previews
only; it never touches ``repair/`` or an adapter directly. Every mutating
action requires an explicit confirm click (QMessageBox) after a preview
that states "No changes have been made yet." — see
docs/REPAIR_ENGINE.md, "No mutation during proposal/preview".
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.repair.models import OperationKind, RepairResult, RepairState, ValidationState
from corona_doctor.ui.components.section_header import SectionHeader
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.models.texture_model import (
    TextureFilter,
    TextureFilterProxyModel,
    TextureRefRole,
    TextureTableModel,
    texture_status,
)
from corona_doctor.smart_relink.session import missing_assets_from_references
from corona_doctor.ui.qt_safe import ignore_signal_args
from corona_doctor.ui.repair_controller import RepairController
from corona_doctor.ui.responsive.breakpoint_manager import LayoutState
from corona_doctor.ui.smart_relink_dialog import SmartRelinkDialog

_FILTER_LABELS = {
    TextureFilter.ALL: "All",
    TextureFilter.MISSING: "Missing",
    TextureFilter.OVERSIZED: "Oversized",
    TextureFilter.DUPLICATE: "Duplicate",
    TextureFilter.LOCAL: "Local",
    TextureFilter.NETWORK: "Network",
}

# Column indices hidden per layout state — see TextureTableModel's _COLUMNS.
_HIDDEN_COLUMNS_BY_STATE = {
    LayoutState.COMPACT: (2, 3, 5),  # hide Size, Path Type, References
    LayoutState.STANDARD: (3,),  # hide Path Type
    LayoutState.EXPANDED: (),
}


class _TextureDetailsPanel(QWidget):
    relink_requested = Signal()
    show_objects_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Surface")
        self._current_ref: ExternalTextureReference | None = None
        self._form = QFormLayout(self)
        self._form.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        self._form.setSpacing(Spacing.XS)

        self._name_label = QLabel("Select a texture to see details.", self)
        self._name_label.setObjectName("SectionTitle")
        self._name_label.setWordWrap(True)
        self._form.addRow(self._name_label)

        self._rows: dict[str, QLabel] = {}
        for field in ("Path", "Resolution", "File size", "Map class", "References", "Materials", "Status"):
            value = QLabel("—", self)
            value.setWordWrap(True)
            self._form.addRow(field, value)
            self._rows[field] = value

        self._relink_button = QPushButton("Find & Relink", self)
        self._relink_button.setObjectName("Secondary")
        self._relink_button.clicked.connect(ignore_signal_args(self.relink_requested.emit))
        self._relink_button.hide()
        self._form.addRow(self._relink_button)

        self._show_objects_button = QPushButton("Show Objects", self)
        self._show_objects_button.setObjectName("Secondary")
        self._show_objects_button.clicked.connect(ignore_signal_args(self.show_objects_requested.emit))
        self._show_objects_button.hide()
        self._form.addRow(self._show_objects_button)

    @property
    def current_reference(self) -> ExternalTextureReference | None:
        return self._current_ref

    def show_reference(self, ref: ExternalTextureReference | None) -> None:
        self._current_ref = ref
        if ref is None:
            self._name_label.setText("Select a texture to see details.")
            for label in self._rows.values():
                label.setText("—")
            self._relink_button.hide()
            self._show_objects_button.hide()
            return

        self._name_label.setText(ref.filename)
        self._rows["Path"].setText(ref.path_info.normalized_path or ref.path_info.raw_path)
        self._rows["Resolution"].setText(f"{ref.width} x {ref.height}" if ref.width and ref.height else "unknown")
        self._rows["File size"].setText(ref.file_size_human)
        self._rows["Map class"].setText(ref.map_class)
        self._rows["References"].setText(str(ref.reference_count))
        self._rows["Materials"].setText(ref.material_name or "unknown")
        self._rows["Status"].setText(texture_status(ref))

        self._relink_button.setVisible(ref.path_info.exists is False)
        self._show_objects_button.setVisible(bool(ref.object_names))


class TexturesView(QWidget):
    # Emitted after a repair actually applied something, so the panel
    # owner can rescan (see docs/REPAIR_ENGINE.md, "Verify after fix" —
    # a repair result is reported, then the caller is expected to rerun
    # Texture Doctor to confirm the relevant findings actually cleared).
    repair_completed = Signal()

    def __init__(self, parent: QWidget | None = None, repair_controller: RepairController | None = None) -> None:
        super().__init__(parent)
        self._repair = repair_controller or RepairController()
        self._references: tuple[ExternalTextureReference, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(SectionHeader("Textures", parent=self))

        self._summary_label = QLabel("No scan has been performed yet.", self)
        self._summary_label.setObjectName("Caption")
        root.addWidget(self._summary_label)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Search textures…")
        self._search_edit.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search_edit)

        self._filter_combo = QComboBox(self)
        for filter_value in TextureFilter:
            self._filter_combo.addItem(_FILTER_LABELS[filter_value], filter_value)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        root.addWidget(self._filter_combo)

        self._portable_button = QPushButton("Make Project Portable…", self)
        self._portable_button.setObjectName("Secondary")
        self._portable_button.clicked.connect(ignore_signal_args(self._on_make_portable_clicked))
        root.addWidget(self._portable_button)

        self._recover_button = QPushButton("Find All Missing Assets…", self)
        self._recover_button.setObjectName("Secondary")
        self._recover_button.clicked.connect(ignore_signal_args(self._on_find_all_missing_clicked))
        root.addWidget(self._recover_button)

        self._model = TextureTableModel(parent=self)
        self._proxy = TextureFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)

        self._table = QTableView(self)
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.hide()
        root.addWidget(self._table, stretch=1)

        self._empty_label = QLabel("No external textures found.", self)
        self._empty_label.setObjectName("Caption")
        self._empty_label.hide()
        root.addWidget(self._empty_label)

        self._details = _TextureDetailsPanel(self)
        self._details.relink_requested.connect(self._on_relink_requested)
        self._details.show_objects_requested.connect(self._on_show_objects_requested)
        root.addWidget(self._details)

        self._apply_layout_state(LayoutState.STANDARD)

    # -- public API -------------------------------------------------------

    def set_references(self, references: tuple[ExternalTextureReference, ...]) -> None:
        self._references = tuple(references)
        self._model.set_references(references)
        self._details.show_reference(None)

        has_refs = bool(references)
        self._table.setVisible(has_refs)
        self._empty_label.setVisible(not has_refs)

        unique_paths = len({r.path_info.comparison_key for r in references if r.path_info.comparison_key})
        self._summary_label.setText(f"{len(references)} reference(s), {unique_paths} unique file(s)")

    def clear(self) -> None:
        self.set_references(())
        self._summary_label.setText("No scan has been performed yet.")

    def set_layout_state(self, state: LayoutState) -> None:
        self._apply_layout_state(state)

    # -- internals ----------------------------------------------------------

    def _apply_layout_state(self, state: LayoutState) -> None:
        hidden = _HIDDEN_COLUMNS_BY_STATE.get(state, ())
        for column in range(self._model.columnCount()):
            self._table.setColumnHidden(column, column in hidden)

    def _on_search_changed(self, text: str = "") -> None:
        self._proxy.set_search_text(text)

    def _on_filter_changed(self, _index: int = -1) -> None:
        self._proxy.set_status_filter(self._filter_combo.currentData())

    def _on_selection_changed(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            self._details.show_reference(None)
            return
        ref = indexes[0].data(TextureRefRole)
        self._details.show_reference(ref)

    # -- repair actions -------------------------------------------------------

    def _on_show_objects_requested(self) -> None:
        ref = self._details.current_reference
        if ref is None or not ref.object_names:
            return
        count = self._repair.select_objects(ref.object_names)
        if count == 0:
            QMessageBox.information(
                self,
                "Show Objects",
                "No matching objects could be found/selected in the current scene.",
            )

    def _on_relink_requested(self) -> None:
        ref = self._details.current_reference
        if ref is None:
            return

        search_root = QFileDialog.getExistingDirectory(self, "Select a folder to search for a replacement texture")
        if not search_root:
            return

        candidates, classification = self._repair.find_candidates(ref.filename, [search_root])
        if classification == "none":
            QMessageBox.information(
                self,
                "Find & Relink",
                f"No candidate files named {ref.filename!r} were found under that folder. Still unresolved.",
            )
            return

        if classification == "single":
            chosen_path = candidates[0].path
        else:
            paths = [c.path for c in candidates]
            chosen_path, accepted = QInputDialog.getItem(
                self,
                "Find & Relink",
                f"Multiple candidates found for {ref.filename!r} — choose one:",
                paths,
                editable=False,
            )
            if not accepted:
                return

        confirmed = QMessageBox.question(
            self,
            "Relink Texture",
            f"Relink {ref.filename!r} to:\n\n{chosen_path}\n\nNo changes have been made yet.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        plan = self._repair.plan_relink(ref, chosen_path)
        result = self._repair.apply_relink(plan)
        state, problems = self._repair.verify(result.manifest)
        self._report_repair_result(result, state, problems)

    def _on_make_portable_clicked(self) -> None:
        if not self._references:
            QMessageBox.information(self, "Make Project Portable", "No scanned textures to work with — run a scan first.")
            return

        destination = QFileDialog.getExistingDirectory(self, "Select the project asset directory")
        if not destination:
            return

        plan = self._repair.plan_make_portable(self._references, destination)
        copy_count = sum(1 for op in plan.operations if op.kind == OperationKind.COPY_FILE)
        relink_count = sum(
            1 for op in plan.operations if op.kind == OperationKind.RELINK_TEXTURE and op.validation_state == ValidationState.READY
        )
        preview = (
            "MAKE PROJECT PORTABLE\n\n"
            f"{len(self._references)} texture reference(s) inspected\n"
            f"{copy_count} unique source file(s)\n\n"
            f"{copy_count} file(s) will be copied\n"
            f"{relink_count} map path(s) will be updated\n\n"
            f"Destination:\n{destination}\n\n"
            f"Conflicts:\n{len(plan.conflicts)}\n\n"
            f"Missing source files:\n{len(plan.missing_sources)}\n\n"
            f"Already portable (skipped):\n{len(plan.already_portable_ref_ids)}\n\n"
            "No changes have been made yet."
        )
        confirmed = QMessageBox.question(
            self,
            "Make Project Portable",
            preview,
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        result = self._repair.apply_make_portable(plan)
        state, problems = self._repair.verify(result.manifest)
        self._report_repair_result(result, state, problems)

    def _on_find_all_missing_clicked(self) -> None:
        """"Find All Missing Assets" — Smart Asset Recovery (see
        docs/SMART_RELINK.md). One folder-selection session covers every
        missing texture at once, unlike per-row Find & Relink."""

        missing_refs = [r for r in self._references if r.path_info.exists is False]
        if not missing_refs:
            QMessageBox.information(self, "Find All Missing Assets", "No missing textures in the current scan.")
            return

        missing_assets = missing_assets_from_references(missing_refs)
        refs_by_ref_id = {r.ref_id: r for r in missing_refs}
        refs_by_asset_id = {asset.asset_id: tuple(refs_by_ref_id[rid] for rid in asset.map_ref_ids) for asset in missing_assets}

        dialog = SmartRelinkDialog(missing_assets, refs_by_asset_id, repair_controller=self._repair, parent=self)
        dialog.repair_completed.connect(ignore_signal_args(self.repair_completed.emit))
        dialog.exec()

    def _report_repair_result(self, result: RepairResult, state: RepairState, problems: tuple[str, ...]) -> None:
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
