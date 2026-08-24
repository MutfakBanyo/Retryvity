"""A minimal, host-independent event bus.

The UI must never call into the scanner layer synchronously and the
scanner layer must never touch a widget. Events are the only channel
between them. This module intentionally avoids Qt so it stays importable
and testable outside 3ds Max; the UI layer subscribes to these events and
re-emits them as Qt signals where convenient (see ui/main_window.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from corona_doctor.core.models import EnvironmentReport, Finding, ScanResult


@dataclass(frozen=True)
class ScanStarted:
    scanner_id: str


@dataclass(frozen=True)
class ScanProgress:
    scanner_id: str
    stage: str
    completed: int
    total: int


@dataclass(frozen=True)
class FindingAdded:
    scanner_id: str
    finding: Finding


@dataclass(frozen=True)
class ScanFinished:
    scanner_id: str
    result: ScanResult


@dataclass(frozen=True)
class ScanFailed:
    scanner_id: str
    message: str


@dataclass(frozen=True)
class EnvironmentUpdated:
    report: EnvironmentReport


Event = ScanStarted | ScanProgress | FindingAdded | ScanFinished | ScanFailed | EnvironmentUpdated
Listener = Callable[[Event], None]


@dataclass
class EventBus:
    """Synchronous, in-process publish/subscribe bus.

    Kept deliberately tiny: no threads, no queueing, no priorities. Handlers
    run on the caller's thread in subscription order. Because scanners are
    driven from the main/Qt-event-loop thread (see docs/ARCHITECTURE.md),
    this is sufficient for the bootstrap phase.
    """

    _listeners: list[Listener] = field(default_factory=list)

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: Event) -> None:
        for listener in tuple(self._listeners):
            listener(event)
