"""Corona Doctor application entry point.

``launch()`` is what a 3ds Max macroscript/menu command should call. It
must stay lightweight: no full scene scan, no splash screen, just the
shell appearing as fast as possible (see docs/ARCHITECTURE.md, "Startup
performance").
"""

from __future__ import annotations

from corona_doctor.app.lifecycle import set_instance, show_or_focus_existing
from corona_doctor.app.services import AppServices
from corona_doctor.logging.logger import configure_logging, get_logger
from corona_doctor.performance.profiler import Profiler
from corona_doctor.version import __version__

_logger = get_logger("application")


def launch() -> None:
    """Show the Corona Doctor dock panel, reusing an existing instance."""

    configure_logging()
    _logger.info("Corona Doctor %s launching", __version__)

    if show_or_focus_existing():
        return

    profiler = Profiler()
    with profiler.measure("bootstrap.total"):
        services = AppServices.create()

        with profiler.measure("bootstrap.ui_shell"):
            dock_widget = _create_dock_widget(services)

        set_instance(dock_widget)
        dock_widget.show()

    _logger.info("Corona Doctor shell ready in %.1f ms", profiler.report().get("bootstrap.total", -1.0))


def _create_dock_widget(services: AppServices):
    # Local imports: Qt/qtmax must never be imported at module scope so
    # corona_doctor.app stays importable for host-independent tooling.
    from corona_doctor.ui.dock_manager import create_docked_panel
    from corona_doctor.ui.main_window import MainPanel

    panel = MainPanel(services)
    return create_docked_panel(panel)
