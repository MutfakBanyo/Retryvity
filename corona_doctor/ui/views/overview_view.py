"""The Overview screen: Scene Health + scan trigger.

Owns no scanning logic itself — it emits ``scan_requested`` and displays
whatever ``ScanSummary`` it is given by the panel that owns the
DiagnosticEngine.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from corona_doctor.core.models import ScanSummary
from corona_doctor.core.texture_models import SceneInventory
from corona_doctor.ui.components.health_score import HealthScoreWidget
from corona_doctor.ui.components.section_header import SectionHeader
from corona_doctor.ui.design.metrics import Spacing


class _StatTile(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Surface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(2)

        self._value_label = QLabel("0", self)
        self._value_label.setObjectName("Title")
        layout.addWidget(self._value_label)

        caption = QLabel(label, self)
        caption.setObjectName("Caption")
        layout.addWidget(caption)

    def set_value(self, value: int) -> None:
        self._value_label.setText(str(value))


class OverviewView(QWidget):
    scan_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        self._scan_button = QPushButton("Scan Scene", self)
        self._scan_button.setObjectName("Primary")
        self._scan_button.clicked.connect(self.scan_requested.emit)

        header = SectionHeader("Scene Health", trailing=self._scan_button, parent=self)
        root.addWidget(header)

        health_row = QWidget(self)
        health_row.setObjectName("Surface")
        health_layout = QVBoxLayout(health_row)
        health_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        health_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._health_widget = HealthScoreWidget(health_row)
        health_layout.addWidget(self._health_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._status_label = QLabel("No scan has been performed yet.", health_row)
        self._status_label.setObjectName("Caption")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        health_layout.addWidget(self._status_label)

        root.addWidget(health_row)

        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(Spacing.SM)
        self._critical_tile = _StatTile("Critical", self)
        self._warning_tile = _StatTile("Warnings", self)
        self._optimization_tile = _StatTile("Optimization", self)
        self._stats_grid.addWidget(self._critical_tile, 0, 0)
        self._stats_grid.addWidget(self._warning_tile, 0, 1)
        self._stats_grid.addWidget(self._optimization_tile, 0, 2)
        root.addLayout(self._stats_grid)

        root.addWidget(SectionHeader("Scene", parent=self))
        self._scene_grid = QGridLayout()
        self._scene_grid.setSpacing(Spacing.SM)
        self._objects_tile = _StatTile("Objects", self)
        self._materials_tile = _StatTile("Materials", self)
        self._textures_tile = _StatTile("Textures", self)
        self._missing_tile = _StatTile("Missing", self)
        self._oversized_tile = _StatTile("8K+", self)
        self._scene_tiles = (
            self._objects_tile,
            self._materials_tile,
            self._textures_tile,
            self._missing_tile,
            self._oversized_tile,
        )
        root.addLayout(self._scene_grid)

        root.addStretch(1)

        self.set_stacked_layout(False)

    def set_stacked_layout(self, stacked: bool) -> None:
        """Switch stat tiles between a multi-column row and a single column.

        Called by the panel when the breakpoint manager reports COMPACT.
        """

        _restack(self._stats_grid, [self._critical_tile, self._warning_tile, self._optimization_tile], stacked)
        _restack(self._scene_grid, list(self._scene_tiles), stacked)

    def set_scanning(self, in_progress: bool) -> None:
        self._scan_button.setEnabled(not in_progress)
        if in_progress:
            self._status_label.setText("Scanning scene…")

    def show_summary(self, summary: ScanSummary) -> None:
        self._health_widget.set_score(summary.health_score)
        self._critical_tile.set_value(summary.critical)
        self._warning_tile.set_value(summary.warning)
        self._optimization_tile.set_value(summary.optimization)
        self._status_label.setText(f"{summary.total} finding(s) from the last scan.")
        self._scan_button.setEnabled(True)

    def show_inventory(self, inventory: SceneInventory) -> None:
        self._objects_tile.set_value(inventory.total_nodes)
        self._materials_tile.set_value(inventory.unique_material_count)
        self._textures_tile.set_value(inventory.unique_external_texture_count)
        self._missing_tile.set_value(inventory.missing_texture_count)
        self._oversized_tile.set_value(inventory.oversized_8k_count)

    def show_no_scan(self) -> None:
        self._health_widget.set_score(None)
        for tile in (self._critical_tile, self._warning_tile, self._optimization_tile, *self._scene_tiles):
            tile.set_value(0)
        self._status_label.setText("No scan has been performed yet.")
        self._scan_button.setEnabled(True)

    def show_error(self, message: str) -> None:
        self._status_label.setText(message)
        self._scan_button.setEnabled(True)


def _restack(grid: QGridLayout, widgets: list[QWidget], stacked: bool) -> None:
    for i in reversed(range(grid.count())):
        item = grid.itemAt(i)
        if item and item.widget():
            grid.removeWidget(item.widget())

    if stacked:
        for row, widget in enumerate(widgets):
            grid.addWidget(widget, row, 0)
    else:
        for col, widget in enumerate(widgets):
            grid.addWidget(widget, 0, col)
