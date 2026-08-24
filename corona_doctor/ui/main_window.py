"""The Corona Doctor panel content widget.

Wires navigation, the three active views (Overview/Diagnostics/
Environment) and the scan controller together. Contains no scene-analysis
logic itself — it only reacts to core events and drives the scan
controller.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from corona_doctor.app.services import AppServices
from corona_doctor.core.constants import APP_NAME
from corona_doctor.core.events import EnvironmentUpdated, ScanFailed, ScanStarted
from corona_doctor.logging.logger import get_logger
from corona_doctor.scanners.demo_scanner import DemoScanner
from corona_doctor.scanners.environment_scanner import EnvironmentScanner
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.ui.icons.icon_registry import get_icon_registry
from corona_doctor.ui.responsive.breakpoint_manager import BreakpointManager, LayoutState
from corona_doctor.ui.scan_controller import run_scan_async
from corona_doctor.ui.themes import load_dark_theme
from corona_doctor.ui.views.diagnostics_view import DiagnosticsView
from corona_doctor.ui.views.environment_view import EnvironmentView
from corona_doctor.ui.views.overview_view import OverviewView

_logger = get_logger("ui")

_NAV_ITEMS = (
    ("overview", "Overview", "overview"),
    ("diagnostics", "Diagnostics", "diagnostics"),
    ("environment", "Environment", "environment"),
)


class MainPanel(QWidget):
    def __init__(self, services: AppServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self.setStyleSheet(load_dark_theme())

        self._breakpoints = BreakpointManager(self)
        self._breakpoints.state_changed.connect(self._on_layout_state_changed)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nav = self._build_nav()
        root.addWidget(self._nav)

        divider = QFrame(self)
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.VLine)
        root.addWidget(divider)

        self._stack = QStackedWidget(self)
        self._overview = OverviewView(self._stack)
        self._diagnostics = DiagnosticsView(self._stack)
        self._environment = EnvironmentView(self._stack)
        for view in (self._overview, self._diagnostics, self._environment):
            self._stack.addWidget(view)
        root.addWidget(self._stack, stretch=1)

        self._overview.scan_requested.connect(self._start_demo_scan)

        self._unsubscribe = services.bus.subscribe(self._on_event)

        self._show_section("overview")
        self._start_environment_probe()

    # -- navigation -----------------------------------------------------

    def _build_nav(self) -> QWidget:
        nav = QWidget(self)
        nav.setFixedWidth(160)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(Spacing.XS)

        title = QLabel(APP_NAME.upper(), nav)
        title.setObjectName("Caption")
        title.setContentsMargins(Spacing.SM, 0, 0, Spacing.SM)
        layout.addWidget(title)

        icons = get_icon_registry()
        self._nav_group = QButtonGroup(nav)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}

        from corona_doctor.ui.design.colors import Color

        for section_id, label, icon_name in _NAV_ITEMS:
            button = QPushButton(icons.icon(icon_name, Color.TEXT_SECONDARY), f"  {label}", nav)
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked, sid=section_id: self._show_section(sid))
            self._nav_group.addButton(button)
            self._nav_buttons[section_id] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return nav

    def _show_section(self, section_id: str) -> None:
        index = {"overview": 0, "diagnostics": 1, "environment": 2}.get(section_id, 0)
        self._stack.setCurrentIndex(index)
        button = self._nav_buttons.get(section_id)
        if button is not None:
            button.setChecked(True)
        self._services.settings.set("last_nav_section", section_id)

    # -- scanning ---------------------------------------------------------

    def _start_environment_probe(self) -> None:
        self._environment.show_probing()
        scanner = EnvironmentScanner()

        def on_finished(_result) -> None:
            if scanner.last_report is not None:
                self._services.bus.publish(EnvironmentUpdated(report=scanner.last_report))
                self._environment.show_report(scanner.last_report)

        run_scan_async(
            self._services.engine,
            scanner,
            on_finished=on_finished,
            on_failed=lambda exc: _logger.warning("Environment probe failed: %s", exc),
        )

    def _start_demo_scan(self) -> None:
        self._overview.set_scanning(True)

        def on_finished(result) -> None:
            self._overview.show_summary(result.summary)
            self._diagnostics.set_findings(list(result.findings))

        run_scan_async(
            self._services.engine,
            DemoScanner(),
            on_finished=on_finished,
            on_failed=lambda exc: self._overview.show_error("Scan failed. See log for details."),
        )

    # -- events -----------------------------------------------------------

    def _on_event(self, event) -> None:
        if isinstance(event, ScanStarted) and event.scanner_id == "demo":
            self._diagnostics.clear()
        elif isinstance(event, ScanFailed):
            _logger.warning("Scan '%s' failed: %s", event.scanner_id, event.message)

    def _on_layout_state_changed(self, state_value: str) -> None:
        self._overview.set_stacked_layout(state_value == LayoutState.COMPACT.value)
        self._nav.setVisible(state_value != LayoutState.COMPACT.value)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        super().resizeEvent(event)
        self._breakpoints.update_width(self.width())
