"""Regression tests using fixtures that mirror REAL observed 3ds Max host values.

3ds Max 2026.2 / Corona, probed 2026-08-25:
    rt.maxversion()                        -> #(28000, 68, 0, 28, 2, 0, 20659, 2026, ".2")
    rt.renderers.current                   -> Corona:Corona
    classOf(rt.renderers.current)          -> Corona
    "CoronaRenderer" in rt.renderers.classes (str form)

pymxs is not installed outside 3ds Max, so these tests monkeypatch the
module-level ``pymxs`` reference each adapter module holds with a small
fake object built from the values above. This must never regress back to
the "Corona: unknown" bug the fixtures are named after.
"""

from __future__ import annotations

import corona_doctor.adapters.corona_adapter as corona_adapter_module
import corona_doctor.adapters.max_adapter as max_adapter_module
from corona_doctor.adapters.corona_adapter import CoronaAdapter
from corona_doctor.adapters.environment_adapter import EnvironmentAdapter
from corona_doctor.adapters.max_adapter import MaxAdapter


class _FakeRendererInstance:
    def __str__(self) -> str:
        return "Corona:Corona"


class _FakeRenderers:
    def __init__(self) -> None:
        self.classes = ["CoronaRenderer", "Default_Scanline_Renderer", "ART_Renderer"]
        self.current = _FakeRendererInstance()


class _FakeRuntime:
    """Mimics the subset of pymxs.runtime this codebase touches."""

    def __init__(self) -> None:
        self.renderers = _FakeRenderers()
        # Installation-signal globals (existence only matters).
        self.CoronaRenderer = "class:CoronaRenderer"
        self.CoronaPhysicalMtl = "class:CoronaPhysicalMtl"
        self.CoronaLight = "class:CoronaLight"
        self.CoronaBitmap = "class:CoronaBitmap"
        self.CoronaMtl = "class:CoronaMtl"
        # A representative slice of the real discovered symbol list.
        self.CoronaAO = "class:CoronaAO"
        self.CoronaSun = "class:CoronaSun"
        self.ChaosScatter = "class:ChaosScatter"
        self.ChaosScatterEdgeTrimming = "class:ChaosScatterEdgeTrimming"
        self.launchCoronaDoctor = "fn:launchCoronaDoctor"
        self.show_corona_doctor = "fn:show_corona_doctor"

    def classOf(self, obj):
        return "Corona"

    def getPropNames(self, obj):
        return ["diffuseLevel", "causticsEnabled", "primarySolver"]

    def maxversion(self):
        return [28000, 68, 0, 28, 2, 0, 20659, 2026, ".2"]


class _FakePymxs:
    def __init__(self) -> None:
        self.runtime = _FakeRuntime()


def _patch_pymxs(monkeypatch) -> None:
    fake = _FakePymxs()
    monkeypatch.setattr(corona_adapter_module, "pymxs", fake)
    monkeypatch.setattr(max_adapter_module, "pymxs", fake)


def test_corona_detect_matches_real_host_values(monkeypatch):
    _patch_pymxs(monkeypatch)

    detection = CoronaAdapter().detect()

    assert detection.installed is True
    assert detection.active is True
    assert detection.renderer_class == "Corona"
    assert detection.renderer_string == "Corona:Corona"
    assert detection.confidence == "confirmed"
    # No documented safe version source exists yet — must not be guessed.
    assert detection.version is None


def test_corona_detect_never_regresses_to_unknown(monkeypatch):
    _patch_pymxs(monkeypatch)

    detection = CoronaAdapter().detect()

    assert detection.installed is not None
    assert detection.confidence != "unknown"


def test_max_version_normalizes_to_display_string(monkeypatch):
    _patch_pymxs(monkeypatch)

    adapter = MaxAdapter()
    assert adapter.get_max_version_string() == "2026.2"
    assert adapter.get_max_version_raw() == "[28000, 68, 0, 28, 2, 0, 20659, 2026, '.2']"


def test_environment_report_reflects_confirmed_corona(monkeypatch):
    _patch_pymxs(monkeypatch)

    report = EnvironmentAdapter().probe()

    assert report.max_version == "2026.2"
    assert report.corona_detected is True
    assert report.corona_active is True
    assert report.corona_renderer_class == "Corona"
    assert report.corona_confidence == "confirmed"


def test_discover_symbols_finds_corona_and_chaos_names(monkeypatch):
    _patch_pymxs(monkeypatch)

    adapter = CoronaAdapter()
    corona_symbols = adapter.discover_symbols("corona")
    chaos_symbols = adapter.discover_symbols("chaos")

    assert "CoronaRenderer" in corona_symbols
    assert "CoronaPhysicalMtl" in corona_symbols
    assert "launchCoronaDoctor" in corona_symbols
    assert "ChaosScatter" in chaos_symbols
    assert "ChaosScatterEdgeTrimming" in chaos_symbols
