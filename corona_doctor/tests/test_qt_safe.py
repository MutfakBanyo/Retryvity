"""Unit tests for ui/qt_safe.py::ignore_signal_args. Pure Python, no Qt.

Regression coverage for the real-host bug: MainPanel._build_nav's nav
button lambda required exactly one positional argument
(`lambda _checked, sid=section_id: ...`) and broke with
`TypeError: missing 1 required positional argument: '_checked'` when the
connected Qt signal was invoked with zero arguments on a real 3ds Max
2026.2 host. ignore_signal_args must tolerate any call arity a Qt signal
might actually use.
"""

from __future__ import annotations

from corona_doctor.ui.qt_safe import ignore_signal_args


def test_wrapped_handler_accepts_zero_arguments():
    calls = []
    handler = ignore_signal_args(lambda: calls.append("called"))
    handler()
    assert calls == ["called"]


def test_wrapped_handler_accepts_a_checked_bool_argument():
    """Simulates PySide6's documented `clicked(bool checked=False)`."""

    calls = []
    handler = ignore_signal_args(lambda: calls.append("called"))
    handler(True)
    handler(False)
    assert calls == ["called", "called"]


def test_wrapped_handler_accepts_arbitrary_extra_positional_and_keyword_args():
    calls = []
    handler = ignore_signal_args(lambda: calls.append("called"))
    handler(1, 2, 3, keyword="value")
    assert calls == ["called"]


def test_wrapped_handler_never_forwards_signal_args_to_the_wrapped_callable():
    """The wrapped callable must always be invoked with zero arguments -
    if it required an argument, calling it bare would raise, proving
    ignore_signal_args truly discards whatever the signal sent."""

    def zero_arg_only():
        return "ok"

    handler = ignore_signal_args(zero_arg_only)
    handler("unexpected", "signal", "args")  # must not raise


def test_no_late_binding_bug_across_multiple_wrapped_handlers():
    """Each handler must close over its OWN loop-variable value - the
    classic Python late-binding closure bug (all lambdas in a loop
    capturing the same final loop-variable value) would make every
    handler report the same, wrong section id."""

    section_ids = ["overview", "diagnostics", "textures", "environment", "about"]
    invoked_with: list[str] = []

    handlers = [ignore_signal_args(lambda sid=section_id: invoked_with.append(sid)) for section_id in section_ids]

    for handler in handlers:
        handler(True)  # simulate a clicked(bool) call

    assert invoked_with == section_ids


def test_repeated_invocation_is_idempotent_per_call():
    """Clicking the same handler twice must just invoke the wrapped
    callable twice - no hidden state, no widget/page recreation here
    (that's MainPanel._show_section's job, which reuses the existing
    QStackedWidget page - see main_window.py)."""

    calls = []
    handler = ignore_signal_args(lambda: calls.append(1))
    handler()
    handler()
    handler(False)
    assert calls == [1, 1, 1]
