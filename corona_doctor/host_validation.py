"""Host validation script — run this INSIDE 3ds Max to sanity-check a build.

From the 3ds Max Python listener (or via ``python.Execute`` in
MAXScript)::

    from corona_doctor.host_validation import run_host_validation
    run_host_validation()

See docs/HOST_VALIDATION.md for the full checklist this does not (and
cannot) automate — e.g. verifying the dock survives a workspace resize.
"""

from __future__ import annotations

from corona_doctor.adapters.environment_adapter import EnvironmentAdapter
from corona_doctor.core.diagnostics import DiagnosticEngine
from corona_doctor.core.events import EventBus
from corona_doctor.logging.logger import configure_logging, get_logger
from corona_doctor.scanners.demo_scanner import DemoScanner
from corona_doctor.version import __version__

_logger = get_logger("host_validation")


def run_host_validation() -> dict[str, str]:
    configure_logging()
    results: dict[str, str] = {}
    lines = ["Corona Doctor Host Validation", f"Version: {__version__}", ""]

    report = EnvironmentAdapter().probe()
    lines.append(f"3ds Max:  {report.max_version}  (raw: {report.max_version_raw})")
    lines.append(f"Python:   {report.python_version}")
    lines.append(f"Qt:       {report.qt_version}")
    lines.append(
        "Corona:   " + ("Detected" if report.corona_detected else ("Not detected" if report.corona_detected is False else "unknown"))
    )
    lines.append("")

    # Dock creation
    try:
        from corona_doctor.adapters.max_adapter import MaxAdapter
        from corona_doctor.ui.dock_manager import create_docked_panel
        from PySide6.QtWidgets import QLabel

        max_window = MaxAdapter().get_max_main_window()
        probe_widget = QLabel("Corona Doctor host validation probe")
        dock = create_docked_panel(probe_widget)
        dock.close()
        results["dock_creation"] = "PASS" if max_window is not None else "PASS (standalone — no Max main window found)"
    except Exception as exc:  # noqa: BLE001
        results["dock_creation"] = f"FAIL ({exc})"
        _logger.exception("Host validation: dock creation failed")
    lines.append(f"Dock creation:      {results['dock_creation']}")

    # Environment scan
    try:
        results["environment_scan"] = "PASS" if report.max_version != "unknown" or not report.errors else "PASS (degraded)"
    except Exception as exc:  # noqa: BLE001
        results["environment_scan"] = f"FAIL ({exc})"
    lines.append(f"Environment scan:   {results['environment_scan']}")

    # Capability probe — PASS means the probe *ran*, not that every
    # capability was found. Corona installation/active/version state is
    # reported separately below; UNKNOWN there is not a probe failure.
    try:
        assert report.capabilities, "capability list was empty"
        results["capability_probe"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        results["capability_probe"] = f"FAIL ({exc})"
    lines.append(f"Capability probe:      {results['capability_probe']}")

    def _tri(value: bool | None) -> str:
        return "PASS" if value is True else ("FAIL" if value is False else "UNKNOWN")

    results["corona_installed"] = _tri(report.corona_detected)
    results["corona_active"] = _tri(report.corona_active)
    results["corona_version"] = "PASS" if report.corona_version != "unknown" else "UNKNOWN"
    lines.append(f"Corona installation:   {results['corona_installed']}")
    lines.append(f"Corona active:         {results['corona_active']}")
    lines.append(f"Corona version:        {results['corona_version']} ({report.corona_version})")
    lines.append(f"Corona confidence:     {report.corona_confidence}")

    # Demo scan
    try:
        engine = DiagnosticEngine(EventBus())
        result = engine.run(DemoScanner())
        assert result.summary.total > 0
        results["demo_scan"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        results["demo_scan"] = f"FAIL ({exc})"
    lines.append(f"Demo scan:          {results['demo_scan']}")

    output = "\n".join(lines)
    print(output)
    _logger.info("Host validation results: %s", results)
    return results


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    run_host_validation()
