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
            dock_widget = _create_dock_widget(services, profiler)

        set_instance(dock_widget)
        dock_widget.show()

    total_ms = profiler.report().get("bootstrap.total", -1.0)
    _logger.info("Corona Doctor shell ready in %.1f ms", total_ms)
    # Per-stage breakdown at DEBUG (not INFO) so a normal launch log stays
    # one line; see docs/ARCHITECTURE.md, "Startup performance" for what
    # each stage covers and why ~190ms was added over the pre-UI ~24ms
    # bootstrap-only figure.
    _logger.debug("Corona Doctor bootstrap stage timings (ms): %s", profiler.report())


def show_about() -> None:
    """Show/focus the panel and switch it to the About section.

    The "About Corona Doctor" menu command's target — see
    ``maxscript/helpers.ms``'s ``CoronaDoctor_About`` macroScript and
    ``bootstrap.py::show_corona_doctor_about``. Launches the panel first
    if it isn't already open, exactly like ``launch()``.
    """

    from corona_doctor.app.lifecycle import get_instance

    launch()
    dock_widget = get_instance()
    if dock_widget is None:
        return
    panel = dock_widget.widget()
    show_about_section = getattr(panel, "show_about_section", None)
    if callable(show_about_section):
        show_about_section()


def _create_dock_widget(services: AppServices, profiler: Profiler):
    # Local imports: Qt/qtmax must never be imported at module scope so
    # corona_doctor.app stays importable for host-independent tooling.
    from corona_doctor.ui.dock_manager import create_docked_panel
    from corona_doctor.ui.main_window import MainPanel

    panel = MainPanel(services, profiler=profiler)
    with profiler.measure("bootstrap.dock_registration"):
        return create_docked_panel(panel)
