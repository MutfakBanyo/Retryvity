"""Development-only, READ-ONLY 3ds Max / Corona / Chaos runtime probe.

This is not part of the production diagnostic engine and is never
imported by it. It exists so a developer working against a real host can
dump everything Corona Doctor can safely observe about the running
process: normalized + raw 3ds Max version, active-renderer identity,
every discoverable "*corona*"/"*chaos*" runtime symbol (classified
best-effort), and the active renderer's property names.

Safety guarantees:
  - Never creates, deletes, or modifies a scene object, material,
    renderer setting, or selection.
  - Never instantiates a Corona/Chaos class merely because its name was
    discovered — this only uses ``dir()``, ``getPropNames()``, ``str()``
    and ``classOf()``, none of which have scene side effects.
  - Never raises — every failure is captured in the report's "errors"
    list instead of propagating.

Run from the 3ds Max Python listener::

    from corona_doctor.devtools.runtime_probe import run_runtime_probe
    run_runtime_probe()
"""

from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from corona_doctor.adapters.corona_adapter import CoronaAdapter, classify_chaos_symbol, classify_corona_symbol
from corona_doctor.adapters.environment_adapter import _detect_pyside_version, _detect_qt_version
from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.logging.logger import default_log_path

T = TypeVar("T")


def _write_json_report(report: dict[str, Any]) -> Path:
    path = default_log_path().parent / "runtime_probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def run_runtime_probe(write_json: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    timings_ms: dict[str, float] = {}

    def _measured(label: str, fn: Callable[[], T], default: T) -> T:
        start = time.perf_counter()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - probe must never crash
            errors.append(f"{label}: {exc}")
            return default
        finally:
            timings_ms[label] = round((time.perf_counter() - start) * 1000, 2)

    max_adapter = MaxAdapter()
    corona_adapter = CoronaAdapter()

    environment = {
        "max_version_display": _measured("max_version_display", max_adapter.get_max_version_string, None),
        "max_version_raw": _measured("max_version_raw", max_adapter.get_max_version_raw, None),
        "python_version": platform.python_version(),
        "qt_version": _measured("qt_version", _detect_qt_version, None),
        "pyside_version": _measured("pyside_version", _detect_pyside_version, None),
    }

    detection = _measured("corona_detect", corona_adapter.detect, None)
    corona_symbols = _measured("corona_symbols", lambda: corona_adapter.discover_symbols("corona"), ())
    chaos_symbols = _measured("chaos_symbols", lambda: corona_adapter.discover_symbols("chaos"), ())
    renderer_properties = _measured("renderer_properties", corona_adapter.get_available_properties, ())

    corona_categories: dict[str, list[str]] = {}
    for name in corona_symbols:
        corona_categories.setdefault(classify_corona_symbol(name), []).append(name)

    chaos_categories: dict[str, list[str]] = {}
    for name in chaos_symbols:
        chaos_categories.setdefault(classify_chaos_symbol(name), []).append(name)

    report: dict[str, Any] = {
        "environment": environment,
        "renderer": {
            "current_string": detection.renderer_string if detection else None,
            "current_class": detection.renderer_class if detection else None,
            "properties": list(renderer_properties),
        },
        "corona": {
            "installed": detection.installed if detection else None,
            "active": detection.active if detection else None,
            "version": detection.version if detection else None,
            "confidence": detection.confidence if detection else "unknown",
            "runtime_symbols": list(corona_symbols),
            "categories": corona_categories,
            "renderer_properties": list(renderer_properties),
        },
        "chaos": {
            "runtime_symbols": list(chaos_symbols),
            "categories": chaos_categories,
        },
        "capabilities": {
            "pymxs_available": max_adapter.is_available(),
        },
        "unknowns": [name for name, cat in [(n, classify_corona_symbol(n)) for n in corona_symbols] if cat == "unknown"],
        "errors": errors,
        "timings_ms": timings_ms,
    }

    _print_summary(report)

    if write_json:
        path = _write_json_report(report)
        print(f"\nJSON report written to: {path}")

    return report


def _print_summary(report: dict[str, Any]) -> None:
    env = report["environment"]
    corona = report["corona"]

    lines = [
        "Corona Doctor Runtime Probe",
        "",
        "3ds Max",
        f"{env['max_version_display']}  (raw: {env['max_version_raw']})",
        "",
        "Python",
        str(env["python_version"]),
        "",
        "Qt",
        str(env["qt_version"]),
        "",
        "Corona",
        f"Installed: {_yesno(corona['installed'])}",
        f"Active: {_yesno(corona['active'])}",
        f"Renderer class: {report['renderer']['current_class']}",
        f"Renderer string: {report['renderer']['current_string']}",
        f"Version: {corona['version'] or 'unknown'}",
        f"Confidence: {corona['confidence']}",
        "",
        "Corona runtime symbols",
        f"{len(corona['runtime_symbols'])} discovered",
        "",
        "Chaos runtime symbols",
        f"{len(report['chaos']['runtime_symbols'])} discovered",
        "",
        "Renderer properties",
        f"{len(report['renderer']['properties'])} discovered",
    ]
    if report["errors"]:
        lines += ["", f"Errors: {len(report['errors'])} (see JSON report)"]

    print("\n".join(lines))


def _yesno(value: bool | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "YES" if value else "NO"


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    run_runtime_probe()
