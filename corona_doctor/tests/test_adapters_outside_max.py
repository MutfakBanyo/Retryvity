"""Verifies host adapters degrade safely when 3ds Max is not present.

This IS testable without 3ds Max — it is exactly the "pymxs missing"
path every adapter method must handle. Real 3ds Max integration behavior
requires host validation (see docs/HOST_VALIDATION.md).
"""

from __future__ import annotations

from corona_doctor.adapters.corona_adapter import CoronaAdapter
from corona_doctor.adapters.environment_adapter import EnvironmentAdapter
from corona_doctor.adapters.max_adapter import MaxAdapter


def test_max_adapter_reports_unavailable_outside_max():
    adapter = MaxAdapter()
    assert adapter.is_available() is False
    assert adapter.get_max_version_string() is None
    assert adapter.get_max_main_window() is None
    assert adapter.get_current_renderer_class_name() is None
    assert adapter.get_scene_object_count() is None


def test_corona_adapter_reports_unknown_outside_max():
    adapter = CoronaAdapter()
    assert adapter.is_installed() is None
    assert adapter.is_active_renderer() is None
    assert adapter.get_renderer_class() is None
    assert adapter.get_available_properties() == ()


def test_environment_adapter_never_raises_outside_max():
    report = EnvironmentAdapter().probe()
    assert report.max_version == "unknown"
    assert report.corona_detected is None
    assert report.python_version  # e.g. "3.11.x"
    assert len(report.capabilities) > 0
