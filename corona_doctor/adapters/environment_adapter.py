"""Builds the structured environment/capability probe.

This is the single entry point the diagnostic engine and UI use to learn
what host functionality is actually available. It never raises — every
failure is captured as a string in ``EnvironmentReport.errors`` and the
corresponding field falls back to "unknown".
"""

from __future__ import annotations

import platform
import sys

from corona_doctor.adapters.corona_adapter import CoronaAdapter
from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.compatibility.versioning import is_at_least
from corona_doctor.core.models import Capability, EnvironmentReport
from corona_doctor.version import MIN_3DS_MAX_VERSION


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - probes must never crash
        return default


class EnvironmentAdapter:
    """Aggregates MaxAdapter/CoronaAdapter output into an EnvironmentReport."""

    def __init__(self, max_adapter: MaxAdapter | None = None, corona_adapter: CoronaAdapter | None = None) -> None:
        self._max = max_adapter or MaxAdapter()
        self._corona = corona_adapter or CoronaAdapter()

    def probe(self) -> EnvironmentReport:
        errors: list[str] = []

        python_version = platform.python_version()

        qt_version = _safe(_detect_qt_version) or "unknown"
        pyside_version = _safe(_detect_pyside_version) or "unknown"

        max_version = "unknown"
        if self._max.is_available():
            detected = _safe(self._max.get_max_version_string)
            max_version = detected or "unknown"
            if detected is None:
                errors.append("Could not read 3ds Max version string.")
        max_supported = is_at_least(max_version, MIN_3DS_MAX_VERSION) if max_version != "unknown" else None

        corona_detected = _safe(self._corona.is_installed)
        corona_renderer_class = _safe(self._corona.get_renderer_class) or "unknown"
        current_renderer = _safe(self._max.get_current_renderer_class_name) or "unknown"

        capabilities = _build_capabilities(self._max, self._corona, corona_detected)

        return EnvironmentReport(
            max_version=max_version,
            max_version_supported=max_supported,
            python_version=python_version,
            qt_version=qt_version,
            pyside_version=pyside_version,
            corona_detected=corona_detected,
            corona_renderer_class=corona_renderer_class,
            corona_version="unknown",
            current_renderer=current_renderer,
            capabilities=capabilities,
            errors=tuple(errors),
        )


def _detect_qt_version() -> str | None:
    from PySide6.QtCore import qVersion  # noqa: PLC0415 - optional dependency

    return qVersion()


def _detect_pyside_version() -> str | None:
    import PySide6  # noqa: PLC0415 - optional dependency

    return PySide6.__version__


def _build_capabilities(max_adapter: MaxAdapter, corona_adapter: CoronaAdapter, corona_detected: bool | None) -> tuple[Capability, ...]:
    renderer_access = max_adapter.is_available()

    properties: tuple[str, ...] = ()
    if corona_detected:
        properties = _safe(corona_adapter.get_available_properties, ()) or ()

    def has_property_hint(*names: str) -> bool | None:
        if not corona_detected:
            return False if corona_detected is False else None
        if not properties:
            return None
        lowered = {p.lower() for p in properties}
        return any(name.lower() in lowered for name in names)

    return (
        Capability(key="renderer_access", label="Renderer access", available=renderer_access),
        Capability(key="corona_materials", label="Corona materials", available=corona_detected),
        Capability(key="corona_lights", label="Corona lights", available=corona_detected),
        Capability(key="scatter_api", label="Chaos Scatter API", available=has_property_hint("scatter")),
        Capability(key="proxy_api", label="Corona Proxy API", available=has_property_hint("proxy")),
    )
