"""Unit tests for the capability model and registry. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.compatibility.capabilities import CapabilityRegistry
from corona_doctor.core.models import Capability, EnvironmentReport


def _report(*capabilities: Capability) -> EnvironmentReport:
    return EnvironmentReport(capabilities=tuple(capabilities))


def test_supports_known_true():
    registry = CapabilityRegistry.from_report(_report(Capability("scatter_api", "Scatter", True)))
    assert registry.supports("scatter_api") is True


def test_supports_known_false():
    registry = CapabilityRegistry.from_report(_report(Capability("scatter_api", "Scatter", False)))
    assert registry.supports("scatter_api") is False


def test_supports_unknown_key_returns_none():
    registry = CapabilityRegistry.from_report(_report())
    assert registry.supports("nonexistent") is None


def test_supports_uncertain_capability_returns_none():
    registry = CapabilityRegistry.from_report(_report(Capability("scatter_api", "Scatter", None)))
    assert registry.supports("scatter_api") is None


def test_require_treats_unknown_as_false():
    registry = CapabilityRegistry.from_report(_report(Capability("scatter_api", "Scatter", None)))
    assert registry.require("scatter_api") is False


def test_capability_display_strings():
    assert Capability("k", "K", True).display == "yes"
    assert Capability("k", "K", False).display == "no"
    assert Capability("k", "K", None).display == "unknown"
