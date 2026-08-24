"""The diagnostic engine: orchestrates scanners and publishes events.

This is the seam between the UI and the scanner layer. The UI only ever
talks to a DiagnosticEngine; it never imports a scanner directly, and a
scanner never imports a widget.
"""

from __future__ import annotations

from typing import Protocol

from corona_doctor.core.events import (
    EventBus,
    FindingAdded,
    ScanFailed,
    ScanFinished,
    ScanProgress,
    ScanStarted,
)
from corona_doctor.core.models import Finding, ScanResult, ScanSummary


class Scanner(Protocol):
    """Contract every scanner (demo or production) must satisfy.

    ``scan`` is a generator so long scans can yield control back to the
    caller between batches instead of freezing the host UI. Each ``yield``
    is a natural checkpoint for the diagnostic engine to publish progress
    and, in the real integration, hand control back to Qt's event loop
    (e.g. via QTimer.singleShot chaining) before resuming.
    """

    id: str
    name: str

    def is_available(self) -> bool:
        ...

    def scan(self) -> "ScannerRun":
        ...


class ScannerRun(Protocol):
    """An iterator of (stage, completed, total, findings_batch) tuples."""

    def __iter__(self):
        ...


class DiagnosticEngine:
    """Runs a scanner step by step, publishing events as it goes.

    In this bootstrap phase, callers drive ``run`` to completion directly.
    A future milestone can wrap ``run`` in a QTimer-chunked driver without
    changing this class's public contract.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def run(self, scanner: Scanner) -> ScanResult:
        """Run a scanner to completion synchronously.

        Prefer :meth:`iter_run` when driving from a Qt event loop so
        long-running scans do not freeze the host UI (see docs/
        ARCHITECTURE.md, "Chunked / incremental scanning").
        """

        generator = self.iter_run(scanner)
        try:
            while True:
                next(generator)
        except StopIteration as stop:
            return stop.value

    def iter_run(self, scanner: Scanner):
        """Generator variant of ``run``: yields once per scan batch.

        Each ``yield`` happens only after that batch's events have been
        published, so a caller driving this with e.g.
        ``QTimer.singleShot(0, step)`` hands control back to the Qt event
        loop between stages instead of blocking it for the whole scan.
        The final :class:`ScanResult` is available as the generator's
        ``StopIteration.value`` once exhausted.
        """

        self._bus.publish(ScanStarted(scanner_id=scanner.id))

        if not scanner.is_available():
            message = f"Scanner '{scanner.name}' is not available in this environment."
            self._bus.publish(ScanFailed(scanner_id=scanner.id, message=message))
            raise ScannerUnavailableError(message)

        findings: list[Finding] = []
        try:
            for stage, completed, total, batch in scanner.scan():
                findings.extend(batch)
                for finding in batch:
                    self._bus.publish(FindingAdded(scanner_id=scanner.id, finding=finding))
                self._bus.publish(
                    ScanProgress(
                        scanner_id=scanner.id,
                        stage=stage,
                        completed=completed,
                        total=total,
                    )
                )
                yield
        except Exception as exc:  # noqa: BLE001 - scans must degrade, never crash the host
            message = f"Scan failed: {exc}"
            self._bus.publish(ScanFailed(scanner_id=scanner.id, message=message))
            raise

        result = ScanResult(
            scanner_id=scanner.id,
            findings=tuple(findings),
            summary=ScanSummary.from_findings(findings),
        )
        self._bus.publish(ScanFinished(scanner_id=scanner.id, result=result))
        return result


class ScannerUnavailableError(RuntimeError):
    """Raised when a scanner's prerequisites are not met."""
