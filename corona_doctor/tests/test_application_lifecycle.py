"""Real-Qt end-to-end tests for app/application.py's launch()/show_about():
singleton behavior, and that a menu-registration failure never prevents
launch. Offscreen Qt (see conftest.py) — no 3ds Max/qtmax required, since
outside 3ds Max ``MaxAdapter.get_max_main_window()`` returns ``None`` and
``dock_manager.create_docked_panel`` falls back to a standalone
``QDockWidget`` rather than docking into a (nonexistent) Max main window.

Isolates the real user's settings file: ``AppServices.create()`` ->
``SettingsStore()`` would otherwise read/write the actual
``%APPDATA%\\CoronaDoctor\\corona_doctor.json`` on the machine running
this test — redirected to a temp path for every test here.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import corona_doctor.persistence.settings as settings_module  # noqa: E402
from corona_doctor.app import lifecycle  # noqa: E402
from corona_doctor.ui.main_window import _SECTION_INDEX  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "corona_doctor.json"
    monkeypatch.setattr(settings_module, "default_settings_path", lambda: settings_path)
    lifecycle.clear_instance()
    yield
    lifecycle.clear_instance()


def test_launch_creates_exactly_one_instance():
    from corona_doctor.app.application import launch

    launch()
    first = lifecycle.get_instance()
    assert first is not None
    assert first.widget() is not None


def test_repeated_launch_reuses_the_same_instance_no_duplicate():
    """Calling launch() again (mirrors show_corona_doctor() being called
    a second time — e.g. re-running the install script, or the menu
    command firing while the panel is already open) must focus the
    existing dock/panel, never construct a second MainPanel."""

    from corona_doctor.app.application import launch

    launch()
    first_dock = lifecycle.get_instance()
    first_panel = first_dock.widget()

    launch()
    second_dock = lifecycle.get_instance()

    assert second_dock is first_dock
    assert second_dock.widget() is first_panel


def test_launch_after_stale_instance_creates_a_fresh_one():
    """Simulates 3ds Max closing the dock without our close handler
    firing (see app/lifecycle.py::show_or_focus_existing's stale-instance
    handling): the next launch() must build a genuinely new panel."""

    from corona_doctor.app.application import launch

    launch()
    first_panel = lifecycle.get_instance().widget()

    lifecycle.clear_instance()  # what a real closeEvent would have done
    launch()
    second_panel = lifecycle.get_instance().widget()

    assert second_panel is not first_panel


def test_show_about_launches_and_switches_to_about_section():
    from corona_doctor.app.application import show_about

    show_about()
    panel = lifecycle.get_instance().widget()
    assert panel._stack.currentIndex() == _SECTION_INDEX["about"]  # noqa: SLF001


def test_show_about_reuses_existing_instance_instead_of_relaunching():
    from corona_doctor.app.application import launch, show_about

    launch()
    first_panel = lifecycle.get_instance().widget()

    show_about()

    assert lifecycle.get_instance().widget() is first_panel
    assert first_panel._stack.currentIndex() == _SECTION_INDEX["about"]  # noqa: SLF001


def test_menu_registration_failure_does_not_prevent_launch():
    """Bug 2's requirement: menu creation must never block Corona Doctor
    from launching. Menu registration is pure MAXScript (see
    maxscript/helpers.ms) with zero Python-side dependency — proven here
    by confirming app/application.py's launch path has no menu-related
    code at all, then confirming launch() succeeds regardless."""

    import corona_doctor.app.application as application_module

    source = inspect.getsource(application_module)
    for forbidden in ("menuman", "cuiregistermenus", "cuimenumanager", "getmainmenubar"):
        assert forbidden not in source.lower()

    from corona_doctor.app.application import launch

    launch()  # must not raise regardless of any real-host menu API state
    assert lifecycle.get_instance() is not None
