"""Qt-signal-arity-safe callback helpers.

A real 3ds Max 2026.2 host (PySide6 6.5.3, embedded in 3ds Max's own Qt
event-loop bridge rather than a standalone ``QApplication.exec()``) threw::

    TypeError: MainPanel._build_nav.<locals>.<lambda>() missing 1
    required positional argument: '_checked'

from a nav button's ``clicked.connect(lambda _checked, sid=section_id:
...)``. PySide6 documents ``QAbstractButton.clicked`` as
``clicked(bool checked=False)``, so a lambda requiring exactly one
positional argument is normally safe — but this host evidently invoked it
with zero. That divergence is not reproducible in this sandboxed dev
environment (no PySide6 install here to inspect further), so rather than
guess at a different fixed arity, every Qt connection in this codebase
that needs to capture extra context uses :func:`ignore_signal_args`
instead of a bare lambda with a required leading parameter — tolerant of
however many positional/keyword arguments the connected signal actually
sends, in this host or any other, present or future Qt/PySide version.
"""

from __future__ import annotations

from typing import Callable


def ignore_signal_args(fn: Callable[[], None]) -> Callable[..., None]:
    """Wrap a zero-argument callable so it is safe as a Qt slot regardless
    of how many positional/keyword arguments the connected signal sends.

    Use this instead of writing ``lambda checked: fn()`` (or worse,
    ``lambda checked, x=captured: fn(x)``) for any signal argument the
    handler doesn't actually need — see the module docstring for why a
    fixed-arity lambda broke on a real host. Loop-variable capture still
    works the normal way (default-argument trick) since ``fn`` itself can
    be a closure/lambda; only the *signal-supplied* arguments are
    discarded here.
    """

    def handler(*_args, **_kwargs) -> None:
        fn()

    return handler
