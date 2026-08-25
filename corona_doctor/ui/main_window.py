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
from corona_doctor.scanners.environment_scanner import EnvironmentScanner
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner
from corona_doctor.ui.design.metrics import Spacing
from corona_doctor.performance.profiler import Profiler
from corona_doctor.ui.icons.icon_registry import get_icon_registry
from corona_doctor.ui.qt_safe import ignore_signal_args
from corona_doctor.ui.responsive.breakpoint_manager import BreakpointManager, LayoutState
from corona_doctor.ui.scan_controller import run_scan_async
from corona_doctor.ui.themes import load_dark_theme
from corona_doctor.ui.views.about_view import AboutView
from corona_doctor.ui.views.diagnostics_view import DiagnosticsView
from corona_doctor.ui.views.environment_view import EnvironmentView
from corona_doctor.ui.views.overview_view import OverviewView
from corona_doctor.ui.views.textures_view import TexturesView

_logger = get_logger("ui")

_NAV_ITEMS = (
    ("overview", "Overview", "overview"),
    ("diagnostics", "Diagnostics", "diagnostics"),
    ("textures", "Textures", "diagnostics"),
    ("environment", "Environment", "environment"),
    ("about", "About", "about"),
)
_SECTION_INDEX = {"overview": 0, "diagnostics": 1, "textures": 2, "environment": 3, "about": 4}


class MainPanel(QWidget):
    def __init__(self, services: AppServices, parent: QWidget | None = None, profiler: Profiler | None = None) -> None:
        super().__init__(parent)
        self._services = services
        # Optional: app/application.py::launch() passes its own profiler so
        # these stages show up in one bootstrap timing report; construction
        # outside launch() (tests, host-independent tooling) still works
        # with a throwaway Profiler(). See docs/ARCHITECTURE.md, "Startup
        # performance".
        profiler = profiler or Profiler()

        with profiler.measure("bootstrap.theme"):
            self.setStyleSheet(load_dark_theme())

        self._breakpoints = BreakpointManager(self)
        self._breakpoints.state_changed.connect(self._on_layout_state_changed)
        self._active_scanner: TextureDoctorScanner | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        with profiler.measure("bootstrap.nav_icons"):
            self._nav = self._build_nav()
        root.addWidget(self._nav)

        divider = QFrame(self)
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.VLine)
        root.addWidget(divider)

        with profiler.measure("bootstrap.views"):
            self._stack = QStackedWidget(self)
            self._overview = OverviewView(self._stack)
            self._diagnostics = DiagnosticsView(self._stack)
            self._textures = TexturesView(self._stack)
            self._environment = EnvironmentView(self._stack)
            self._about = AboutView(self._stack)
            for view in (self._overview, self._diagnostics, self._textures, self._environment, self._about):
                self._stack.addWidget(view)
        root.addWidget(self._stack, stretch=1)

        self._overview.scan_requested.connect(self._start_scene_scan)
        # Part I, "Verify after fix": a repair reports its own outcome
        # immediately, but the Texture Doctor state it affected (e.g.
        # TXT-006's local-path count) is only trustworthy after an
        # actual rescan — see docs/REPAIR_ENGINE.md.
        self._textures.repair_completed.connect(ignore_signal_args(self._start_scene_scan))

        self._unsubscribe = services.bus.subscribe(self._on_event)

        self._show_section("overview")
        with profiler.measure("bootstrap.scan_scheduling"):
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
            button.clicked.connect(ignore_signal_args(lambda sid=section_id: self._show_section(sid)))
            self._nav_group.addButton(button)
            self._nav_buttons[section_id] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return nav

    def show_about_section(self) -> None:
        """Switch to the About section — the "About Corona Doctor" menu
        command's target (see app/application.py::show_about)."""

        self._show_section("about")

    def _show_section(self, section_id: str) -> None:
        index = _SECTION_INDEX.get(section_id, 0)
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
                self._about.show_environment(scanner.last_report)

        run_scan_async(
            self._services.engine,
            scanner,
            on_finished=on_finished,
            on_failed=lambda exc: _logger.warning("Environment probe failed: %s", exc),
        )

    def _start_scene_scan(self) -> None:
        self._overview.set_scanning(True)
        scanner = TextureDoctorScanner()
        self._active_scanner = scanner

        def on_finished(result) -> None:
            self._overview.show_summary(result.summary)
            if scanner.inventory is not None:
                self._overview.show_inventory(scanner.inventory)
            self._diagnostics.set_findings(list(result.findings))
            self._textures.set_references(scanner.texture_references)
            self._active_scanner = None

        def on_failed(exc: Exception) -> None:
            self._overview.show_error(
                "Scan requires a running 3ds Max session." if not scanner.is_available() else "Scan failed. See log for details."
            )
            self._active_scanner = None

        run_scan_async(
            self._services.engine,
            scanner,
            on_finished=on_finished,
            on_failed=on_failed,
        )

    # -- events -----------------------------------------------------------

    def _on_event(self, event) -> None:
        if isinstance(event, ScanStarted) and event.scanner_id == TextureDoctorScanner.id:
            self._diagnostics.clear()
            self._textures.clear()
        elif isinstance(event, ScanFailed):
            _logger.warning("Scan '%s' failed: %s", event.scanner_id, event.message)

    def _on_layout_state_changed(self, state_value: str) -> None:
        self._overview.set_stacked_layout(state_value == LayoutState.COMPACT.value)
        self._textures.set_layout_state(LayoutState(state_value))
        self._nav.setVisible(state_value != LayoutState.COMPACT.value)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        super().resizeEvent(event)
        self._breakpoints.update_width(self.width())
