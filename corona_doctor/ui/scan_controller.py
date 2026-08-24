"""Drives DiagnosticEngine.iter_run via QTimer so scans never freeze the UI.

This is the only place in the UI layer that talks to the diagnostic
engine directly; views react to bus events instead of calling scanners.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QTimer

from corona_doctor.core.diagnostics import DiagnosticEngine, Scanner
from corona_doctor.core.models import ScanResult
from corona_doctor.logging.logger import get_logger

_logger = get_logger("scan_controller")


def run_scan_async(
    engine: DiagnosticEngine,
    scanner: Scanner,
    on_finished: Callable[[ScanResult], None] | None = None,
    on_failed: Callable[[Exception], None] | None = None,
) -> None:
    """Step through ``scanner`` one batch per Qt event-loop turn."""

    generator = engine.iter_run(scanner)

    def step() -> None:
        try:
            next(generator)
        except StopIteration as stop:
            if on_finished is not None:
                on_finished(stop.value)
            return
        except Exception as exc:  # noqa: BLE001 - surfaced via on_failed, never raised into Qt
            _logger.exception("Scan '%s' failed", scanner.id)
            if on_failed is not None:
                on_failed(exc)
            return
        QTimer.singleShot(0, step)

    QTimer.singleShot(0, step)
