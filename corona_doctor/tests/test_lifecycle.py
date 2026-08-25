"""Unit tests for app/lifecycle.py's singleton contract. Pure Python, no
Qt/3ds Max required — ``lifecycle.py`` only type-checks against
``QDockWidget`` (``TYPE_CHECKING`` only), so a lightweight fake stands in
for the real dock widget here.
"""

from __future__ import annotations

from corona_doctor.app import lifecycle


class _FakeWidget:
    def __init__(self) -> None:
        self.focus_calls = 0

    def setFocus(self) -> None:  # noqa: N802 - Qt naming
        self.focus_calls += 1


class _FakeDock:
    def __init__(self, *, raise_on_show: bool = False) -> None:
        self.show_calls = 0
        self.raise_calls = 0
        self.activate_calls = 0
        self._raise_on_show = raise_on_show
        self._widget = _FakeWidget()

    def show(self) -> None:
        if self._raise_on_show:
            raise RuntimeError("Internal C++ object already deleted.")
        self.show_calls += 1

    def raise_(self) -> None:  # noqa: N802 - mirrors QWidget.raise_
        self.raise_calls += 1

    def activateWindow(self) -> None:  # noqa: N802 - Qt naming
        self.activate_calls += 1

    def widget(self):
        return self._widget


def setup_function(_fn) -> None:
    lifecycle.clear_instance()


def teardown_function(_fn) -> None:
    lifecycle.clear_instance()


def test_no_instance_initially():
    assert lifecycle.get_instance() is None
    assert lifecycle.show_or_focus_existing() is False


def test_set_instance_then_get_instance_returns_it():
    dock = _FakeDock()
    lifecycle.set_instance(dock)
    assert lifecycle.get_instance() is dock


def test_show_or_focus_existing_reuses_the_single_instance():
    dock = _FakeDock()
    lifecycle.set_instance(dock)

    reused = lifecycle.show_or_focus_existing()

    assert reused is True
    assert dock.show_calls == 1
    assert dock.raise_calls == 1
    assert dock.activate_calls == 1
    assert dock.widget().focus_calls == 1


def test_repeated_show_or_focus_never_creates_a_second_instance():
    """Simulates calling show_corona_doctor()/launch() multiple times in
    one session: the same dock/panel instance must be reused every time,
    never replaced or duplicated."""

    dock = _FakeDock()
    lifecycle.set_instance(dock)

    for _ in range(5):
        assert lifecycle.show_or_focus_existing() is True

    assert lifecycle.get_instance() is dock
    assert dock.show_calls == 5


def test_clear_instance_resets_singleton():
    lifecycle.set_instance(_FakeDock())
    lifecycle.clear_instance()
    assert lifecycle.get_instance() is None
    assert lifecycle.show_or_focus_existing() is False


def test_stale_instance_is_cleared_and_reported_as_not_reused():
    """If the underlying C++ object was already destroyed (Max closed the
    dock without going through our close handler), show_or_focus_existing
    must clear the stale reference and report False so the caller creates
    a fresh instance instead of repeatedly failing."""

    dock = _FakeDock(raise_on_show=True)
    lifecycle.set_instance(dock)

    reused = lifecycle.show_or_focus_existing()

    assert reused is False
    assert lifecycle.get_instance() is None


def test_set_instance_replaces_the_tracked_reference():
    """Replacing the tracked instance (e.g. after a stale one was
    cleared and a new panel was built) must not leave the old one
    reachable through get_instance()."""

    first = _FakeDock()
    second = _FakeDock()
    lifecycle.set_instance(first)
    lifecycle.set_instance(second)
    assert lifecycle.get_instance() is second
