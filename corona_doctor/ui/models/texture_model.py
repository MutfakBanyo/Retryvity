"""Qt Model/View over ExternalTextureReference — never one QWidget per row.

A ``QAbstractTableModel`` backs a ``QTableView``; search/filter is done by
a ``QSortFilterProxyModel`` subclass on top of it, so filtering/sorting
never re-scans the scene — it only operates on the already-scanned,
cached model data (see docs/TEXTURE_DOCTOR.md, "Search and filters").
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from corona_doctor.core.texture_models import ExternalTextureReference, PathType, TextureThresholds

TextureRefRole = Qt.ItemDataRole.UserRole + 1

_COLUMNS = ("Texture", "Resolution", "Size", "Path Type", "Status", "References")
_DEFAULT_THRESHOLDS = TextureThresholds()

_PATH_TYPE_LABELS = {
    PathType.LOCAL: "Local",
    PathType.NETWORK_UNC: "Network",
    PathType.RELATIVE: "Relative",
    PathType.MISSING: "Missing",
    PathType.UNKNOWN: "Unknown",
}


class TextureFilter(str, Enum):
    ALL = "all"
    MISSING = "missing"
    OVERSIZED = "oversized"
    DUPLICATE = "duplicate"
    LOCAL = "local"
    NETWORK = "network"


def texture_status(ref: ExternalTextureReference, thresholds: TextureThresholds = _DEFAULT_THRESHOLDS) -> str:
    """Single-word status label used for both display and filtering."""

    if ref.path_info.exists is False:
        return "Missing"
    if ref.width and ref.height and max(ref.width, ref.height) >= thresholds.oversized_warning_px:
        return "Oversized"
    if ref.reference_count > 1:
        return "Duplicate"
    return "OK"


class TextureTableModel(QAbstractTableModel):
    def __init__(self, references: tuple[ExternalTextureReference, ...] = (), parent=None) -> None:
        super().__init__(parent)
        self._refs: tuple[ExternalTextureReference, ...] = references

    def set_references(self, references: tuple[ExternalTextureReference, ...]) -> None:
        self.beginResetModel()
        self._refs = tuple(references)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._refs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or not (0 <= index.row() < len(self._refs)):
            return None
        ref = self._refs[index.row()]

        if role == TextureRefRole:
            return ref
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        column = index.column()
        if column == 0:
            return ref.filename
        if column == 1:
            return f"{ref.width}x{ref.height}" if ref.width and ref.height else "unknown"
        if column == 2:
            return ref.file_size_human
        if column == 3:
            return _PATH_TYPE_LABELS.get(ref.path_info.path_type, "Unknown")
        if column == 4:
            return texture_status(ref)
        if column == 5:
            return str(ref.reference_count)
        return None

    def ref_at(self, row: int) -> ExternalTextureReference | None:
        if 0 <= row < len(self._refs):
            return self._refs[row]
        return None


class TextureFilterProxyModel(QSortFilterProxyModel):
    """Client-side search + status filter over an already-scanned TextureTableModel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search_text = ""
        self._status_filter = TextureFilter.ALL
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_text(self, text: str) -> None:
        self._search_text = text.strip().lower()
        self.invalidateFilter()

    def set_status_filter(self, status_filter: TextureFilter) -> None:
        self._status_filter = status_filter
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True
        ref = model.ref_at(source_row)
        if ref is None:
            return False

        if self._search_text:
            haystack = " ".join(
                filter(
                    None,
                    (
                        ref.filename,
                        ref.path_info.normalized_path,
                        ref.material_name,
                        ref.map_class,
                    ),
                )
            ).lower()
            if self._search_text not in haystack:
                return False

        if self._status_filter == TextureFilter.ALL:
            return True
        if self._status_filter == TextureFilter.MISSING:
            return ref.path_info.exists is False
        if self._status_filter == TextureFilter.OVERSIZED:
            return bool(ref.width and ref.height and max(ref.width, ref.height) >= _DEFAULT_THRESHOLDS.oversized_warning_px)
        if self._status_filter == TextureFilter.DUPLICATE:
            return ref.reference_count > 1
        if self._status_filter == TextureFilter.LOCAL:
            return ref.path_info.path_type == PathType.LOCAL
        if self._status_filter == TextureFilter.NETWORK:
            return ref.path_info.path_type == PathType.NETWORK_UNC
        return True
