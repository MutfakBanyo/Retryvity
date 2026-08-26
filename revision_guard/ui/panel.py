"""The RevisionGuard panel.

State lives here: V0.1 keeps exactly one snapshot and one comparison
result in memory, both owned by the panel. Closing the panel drops them,
which is the documented V0.1 behaviour.

Threading note: pymxs is main-thread-only, so the scan runs on the UI
thread and yields to Qt between objects (see _on_progress) instead of
moving to a worker. That keeps the panel repainting during a scan of a few
thousand objects without ever touching the scene off-thread.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from revision_guard.core.compare import compare_snapshots
from revision_guard.core.models import CHANGE_TYPE_ORDER, ChangeType, CompareResult, Snapshot
from revision_guard.core.snapshot import capture_snapshot
from revision_guard.log import log, warn
from revision_guard.ui.style import CHANGE_COLORS, MUTED, STYLESHEET
from revision_guard.version import __version__

NO_SNAPSHOT_MESSAGE = "No snapshot exists.\nCreate a snapshot first."
EMPTY_SCENE_MESSAGE = "No eligible geometry objects found."
MAX_RESULT_ROWS = 500

CHANGED_TYPES = (
    ChangeType.ADDED,
    ChangeType.GEOMETRY_CHANGED,
    ChangeType.TRANSFORM_CHANGED,
    ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED,
)


class RevisionGuardPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RevisionGuardPanel")
        self.setStyleSheet(STYLESHEET)
        self.setMinimumWidth(260)

        self._snapshot: Snapshot | None = None
        self._result: CompareResult | None = None
        self._busy = False
        self._count_labels: dict[ChangeType, QLabel] = {}

        self._build_ui()
        self._refresh_enabled_state()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("REVISIONGUARD")
        title.setObjectName("Title")
        layout.addWidget(title)

        self._snapshot_button = QPushButton("Create Snapshot")
        self._snapshot_button.setObjectName("Primary")
        self._snapshot_button.clicked.connect(self._on_create_snapshot)
        layout.addWidget(self._snapshot_button)

        self._snapshot_label = QLabel("Snapshot: none")
        self._snapshot_label.setObjectName("Muted")
        self._snapshot_label.setWordWrap(True)
        layout.addWidget(self._snapshot_label)

        self._compare_button = QPushButton("Compare Scene")
        self._compare_button.clicked.connect(self._on_compare)
        layout.addWidget(self._compare_button)

        layout.addWidget(_separator())

        result_header = QLabel("RESULT")
        result_header.setObjectName("SectionHeader")
        layout.addWidget(result_header)

        layout.addLayout(self._build_counts_grid())
        layout.addWidget(_separator())

        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, stretch=1)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self._select_button = QPushButton("Select Changed")
        self._select_button.clicked.connect(self._on_select_changed)
        self._isolate_button = QPushButton("Isolate Changed")
        self._isolate_button.clicked.connect(self._on_isolate_changed)
        buttons.addWidget(self._select_button)
        buttons.addWidget(self._isolate_button)
        layout.addLayout(buttons)

        self._clear_button = QPushButton("Clear Result")
        self._clear_button.clicked.connect(self._on_clear_result)
        layout.addWidget(self._clear_button)

        self._status = QLabel(f"RevisionGuard {__version__} - ready.")
        self._status.setObjectName("Status")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _build_counts_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)

        for row, change_type in enumerate(CHANGE_TYPE_ORDER):
            name = QLabel(change_type.label)
            name.setStyleSheet(f"color: {CHANGE_COLORS[change_type.value]};")

            value = QLabel("-")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            font = QFont(value.font())
            font.setBold(True)
            value.setFont(font)

            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self._count_labels[change_type] = value

        self._scanned_label = QLabel("Objects scanned: -")
        self._scanned_label.setObjectName("Muted")
        grid.addWidget(self._scanned_label, len(CHANGE_TYPE_ORDER), 0, 1, 2)
        return grid

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _on_create_snapshot(self) -> None:
        if self._busy:
            return
        with self._working("Scanning scene..."):
            snapshot = self._scan("Snapshot")
        if snapshot is None:
            return

        if snapshot.object_count == 0:
            # Keep any snapshot already taken - the user scanned an empty
            # scene, which is no reason to throw away earlier work.
            self._set_status(EMPTY_SCENE_MESSAGE)
            self._refresh_enabled_state()
            return

        self._snapshot = snapshot
        self._clear_result_view()
        self._snapshot_label.setText(
            f"Snapshot:\n{snapshot.object_count} geometry objects\n"
            f"Created: {time.strftime('%H:%M:%S', time.localtime(snapshot.created_at))}"
        )
        self._set_status(
            f"Snapshot created in {snapshot.duration_seconds:.2f}s"
            + (f" ({snapshot.skipped_count} skipped)" if snapshot.skipped_count else "")
        )
        self._refresh_enabled_state()

    def _on_compare(self) -> None:
        if self._busy:
            return
        if self._snapshot is None:
            self._set_status(NO_SNAPSHOT_MESSAGE)
            return

        with self._working("Comparing scene..."):
            current = self._scan("Compare")
        if current is None:
            return

        # An empty current scene is a legitimate result, not an error: every
        # snapshotted object is simply REMOVED.
        result = compare_snapshots(self._snapshot, current)
        self._result = result
        self._populate_result(result)
        self._set_status(
            f"Compared {result.scanned} objects in {current.duration_seconds:.2f}s - "
            f"{result.changed_count} changed"
            + (f", {result.skipped} skipped" if result.skipped else "")
        )
        self._refresh_enabled_state()

    def _on_select_changed(self) -> int:
        from revision_guard.max import scene_access

        if self._result is None:
            self._set_status("Nothing to select. Run Compare Scene first.")
            return 0

        handles = self._result.selectable_handles()
        if not handles:
            self._set_status("No selectable changes. (Removed objects no longer exist.)")
            return 0

        try:
            selected = scene_access.select_handles(handles)
        except Exception as exc:  # noqa: BLE001 - never crash the host
            warn(f"Select Changed failed: {exc}")
            self._set_status(f"Select failed: {exc}")
            return 0

        missing = len(handles) - selected
        message = f"Selected {selected} changed object(s)."
        if missing:
            message += f" {missing} no longer exist."
        self._set_status(message)
        log(message)
        return selected

    def _on_isolate_changed(self) -> None:
        from revision_guard.max import scene_access

        if self._on_select_changed() == 0:
            return
        try:
            isolated = scene_access.isolate_selection()
        except Exception as exc:  # noqa: BLE001
            warn(f"Isolate Changed failed: {exc}")
            isolated = False

        if isolated:
            self._set_status("Isolated the changed objects. Use Max's Isolate toggle to exit.")
        else:
            self._set_status(
                "Objects are selected, but Isolate Selection is unavailable on this "
                "3ds Max build. Use Alt+Q manually."
            )

    def _on_clear_result(self) -> None:
        self._clear_result_view()
        self._set_status("Result cleared. The snapshot is kept.")
        self._refresh_enabled_state()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        from revision_guard.max import scene_access

        handle = item.data(Qt.ItemDataRole.UserRole)
        if handle is None:
            self._set_status("This object was removed and cannot be selected.")
            return
        try:
            if scene_access.select_handles([handle]):
                self._set_status(f"Selected '{item.text().split('] ', 1)[-1]}'.")
            else:
                self._set_status("That object no longer exists in the scene.")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Select failed: {exc}")

    # ------------------------------------------------------------------
    # scanning
    # ------------------------------------------------------------------
    def _scan(self, label: str) -> Snapshot | None:
        from revision_guard.max import scene_access

        if not scene_access.is_available():
            self._set_status("3ds Max (pymxs) unavailable - RevisionGuard must run inside 3ds Max.")
            return None
        try:
            return capture_snapshot(progress=self._on_progress)
        except Exception as exc:  # noqa: BLE001 - a failed scan must not kill the panel
            warn(f"{label} scan failed: {type(exc).__name__}: {exc}")
            self._set_status(f"{label} failed: {exc}")
            return None

    def _on_progress(self, index: int, total: int, name: str) -> None:
        """Report progress and let Qt repaint. Called on the main thread."""

        self._status.setText(f"Scanning {index}/{total}: {name}")
        QApplication.processEvents()

    # ------------------------------------------------------------------
    # result view
    # ------------------------------------------------------------------
    def _populate_result(self, result: CompareResult) -> None:
        counts = result.counts()
        for change_type, label in self._count_labels.items():
            label.setText(str(counts[change_type]))
        self._scanned_label.setText(f"Objects scanned: {result.scanned}")

        self._list.clear()
        shown = [entry for entry in result.entries if entry.change_type.is_change]
        for entry in shown[:MAX_RESULT_ROWS]:
            item = QListWidgetItem(f"[{entry.change_type.value}] {entry.name}")
            item.setForeground(QColor(CHANGE_COLORS[entry.change_type.value]))
            item.setToolTip(f"{entry.object_class} - handle {entry.handle}")
            if entry.change_type.is_selectable:
                item.setData(Qt.ItemDataRole.UserRole, entry.handle)
            else:
                item.setToolTip(f"{entry.object_class} - removed from the scene")
            self._list.addItem(item)

        if len(shown) > MAX_RESULT_ROWS:
            overflow = QListWidgetItem(f"... and {len(shown) - MAX_RESULT_ROWS} more")
            overflow.setForeground(QColor(MUTED))
            self._list.addItem(overflow)
        elif not shown:
            item = QListWidgetItem("No changes detected.")
            item.setForeground(QColor(MUTED))
            self._list.addItem(item)

    def _clear_result_view(self) -> None:
        self._result = None
        self._list.clear()
        for label in self._count_labels.values():
            label.setText("-")
        self._scanned_label.setText("Objects scanned: -")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set_status(self, message: str) -> None:
        self._status.setText(message)

    def _refresh_enabled_state(self) -> None:
        has_snapshot = self._snapshot is not None
        has_result = self._result is not None
        self._compare_button.setEnabled(has_snapshot and not self._busy)
        self._snapshot_button.setEnabled(not self._busy)
        self._select_button.setEnabled(has_result and not self._busy)
        self._isolate_button.setEnabled(has_result and not self._busy)
        self._clear_button.setEnabled(has_result and not self._busy)

    def _working(self, message: str):
        return _BusyScope(self, message)


class _BusyScope:
    """Disables the panel's buttons for the duration of a scan."""

    def __init__(self, panel: RevisionGuardPanel, message: str) -> None:
        self._panel = panel
        self._message = message

    def __enter__(self) -> None:
        self._panel._busy = True
        self._panel._refresh_enabled_state()
        self._panel._set_status(self._message)
        QApplication.processEvents()

    def __exit__(self, *exc_info) -> bool:
        self._panel._busy = False
        self._panel._refresh_enabled_state()
        return False


def _separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line
