"""The Textures screen: Texture Doctor's scanned texture list + details.

Uses Qt Model/View (QTableView + TextureTableModel + a QSortFilterProxyModel
for search/filter) — never one QWidget per texture, per the UI performance
rules. Operates entirely on cached scan results: search/filter/sort never
re-touch the 3ds Max scene (see docs/TEXTURE_DOCTOR.md).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.ui.components.section_header import SectionHeader
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.models.texture_model import (
    TextureFilter,
    TextureFilterProxyModel,
    TextureRefRole,
    TextureTableModel,
    texture_status,
)
from corona_doctor.ui.responsive.breakpoint_manager import LayoutState

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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Surface")
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

    def show_reference(self, ref: ExternalTextureReference | None) -> None:
        if ref is None:
            self._name_label.setText("Select a texture to see details.")
            for label in self._rows.values():
                label.setText("—")
            return

        self._name_label.setText(ref.filename)
        self._rows["Path"].setText(ref.path_info.normalized_path or ref.path_info.raw_path)
        self._rows["Resolution"].setText(f"{ref.width} x {ref.height}" if ref.width and ref.height else "unknown")
        self._rows["File size"].setText(ref.file_size_human)
        self._rows["Map class"].setText(ref.map_class)
        self._rows["References"].setText(str(ref.reference_count))
        self._rows["Materials"].setText(ref.material_name or "unknown")
        self._rows["Status"].setText(texture_status(ref))


class TexturesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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
        root.addWidget(self._details)

        self._apply_layout_state(LayoutState.STANDARD)

    # -- public API -------------------------------------------------------

    def set_references(self, references: tuple[ExternalTextureReference, ...]) -> None:
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

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)

    def _on_filter_changed(self, _index: int) -> None:
        self._proxy.set_status_filter(self._filter_combo.currentData())

    def _on_selection_changed(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            self._details.show_reference(None)
            return
        ref = indexes[0].data(TextureRefRole)
        self._details.show_reference(ref)
