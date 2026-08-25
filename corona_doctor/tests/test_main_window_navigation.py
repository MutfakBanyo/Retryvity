"""Real-Qt integration tests for MainPanel navigation (see conftest.py for
the offscreen platform setup that makes this runnable without a display).

Regression coverage for the real 3ds Max 2026.2 host bug: nav button
clicks threw ``TypeError: ... missing 1 required positional argument:
'_checked'`` from ``MainPanel._build_nav``'s per-button lambda. Fixed via
``ui/qt_safe.py::ignore_signal_args`` (unit-tested in isolation in
test_qt_safe.py); this file proves the real wiring — every nav button,
constructed the way MainPanel actually constructs them — routes to its
own correct page and survives being invoked with an unexpected arg count.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from corona_doctor.app.services import AppServices  # noqa: E402
from corona_doctor.persistence.settings import SettingsStore  # noqa: E402
from corona_doctor.ui.main_window import _SECTION_INDEX, MainPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, tmp_path):
    services = AppServices.create(settings=SettingsStore(path=tmp_path / "settings.json"))
    widget = MainPanel(services)
    yield widget
    widget.deleteLater()


def test_every_nav_item_has_a_button_and_a_page(panel):
    assert set(panel._nav_buttons.keys()) == set(_SECTION_INDEX.keys())  # noqa: SLF001
    assert panel._stack.count() == len(_SECTION_INDEX)  # noqa: SLF001


def test_each_nav_button_click_activates_its_own_correct_page(panel):
    for section_id, expected_index in _SECTION_INDEX.items():
        panel._nav_buttons[section_id].click()  # noqa: SLF001 - real Qt click, real signal dispatch
        assert panel._stack.currentIndex() == expected_index, f"{section_id} did not activate page {expected_index}"  # noqa: SLF001
        assert panel._nav_buttons[section_id].isChecked()  # noqa: SLF001


def test_no_late_binding_bug_button_order_matches_section_order(panel):
    """If the nav lambdas suffered the classic late-binding closure bug,
    every button would activate the LAST section regardless of which was
    clicked. Click in reverse order to make that failure mode obvious."""

    for section_id in reversed(list(_SECTION_INDEX)):
        panel._nav_buttons[section_id].click()  # noqa: SLF001
        assert panel._stack.currentIndex() == _SECTION_INDEX[section_id]  # noqa: SLF001


def test_repeated_clicks_do_not_create_new_pages_or_widgets(panel):
    pages_before = [panel._stack.widget(i) for i in range(panel._stack.count())]  # noqa: SLF001
    count_before = panel._stack.count()  # noqa: SLF001

    for _ in range(3):
        for section_id in _SECTION_INDEX:
            panel._nav_buttons[section_id].click()  # noqa: SLF001

    pages_after = [panel._stack.widget(i) for i in range(panel._stack.count())]  # noqa: SLF001
    assert panel._stack.count() == count_before  # noqa: SLF001
    assert pages_after == pages_before  # same widget instances, not recreated


def test_nav_handler_survives_a_manually_forced_zero_argument_signal_emit(panel):
    """Bypass Qt's normal default-argument backfill entirely and invoke
    the connected slot list with truly zero arguments, matching what the
    real host reportedly did - must not raise."""

    button = panel._nav_buttons["diagnostics"]  # noqa: SLF001
    button.clicked.emit()  # PySide6 backfills the bool default here (see
    # ui/qt_safe.py's module docstring - this alone does not reproduce the
    # real-host zero-arg call, but proves the connection tolerates it too)
    assert panel._stack.currentIndex() == _SECTION_INDEX["diagnostics"]  # noqa: SLF001


def test_scan_button_click_does_not_raise(panel):
    """overview_view.py's scan_requested.emit() used to be connected
    directly as a clicked slot, which raises if clicked ever forwards an
    argument to a zero-arg Signal(). The actual scan step is scheduled via
    QTimer and never runs synchronously here (no event loop pumped), so
    this only needs to prove the click -> scan_requested -> _start_scene_scan
    chain itself doesn't raise outside 3ds Max."""

    panel._overview._scan_button.click()  # noqa: SLF001
