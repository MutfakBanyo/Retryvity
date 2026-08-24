"""Unit tests for Corona/Chaos runtime symbol classification. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.adapters.corona_adapter import classify_chaos_symbol, classify_corona_symbol


def test_classify_known_renderer_symbol():
    assert classify_corona_symbol("Corona") == "renderer"
    assert classify_corona_symbol("CoronaRenderer") == "renderer"


def test_classify_known_material_symbols():
    assert classify_corona_symbol("CoronaPhysicalMtl") == "materials"
    assert classify_corona_symbol("CoronaLegacyMtl") == "materials"


def test_classify_known_light_symbols():
    assert classify_corona_symbol("CoronaLight") == "lights"
    assert classify_corona_symbol("CoronaSun") == "lights"


def test_classify_known_scatter_symbols():
    assert classify_corona_symbol("VRayCoronaScatterMod") == "scatter"
    assert classify_chaos_symbol("ChaosScatter") == "scatter"
    assert classify_chaos_symbol("ChaosScatterEdgeTrimming") == "scatter"
    assert classify_chaos_symbol("ChaosScatterSurfaceColor") == "scatter"


def test_classify_own_tooling_symbols_not_mistaken_for_chaos_api():
    assert classify_corona_symbol("launchCoronaDoctor") == "internal_tooling"
    assert classify_corona_symbol("show_corona_doctor") == "internal_tooling"


def test_classify_unknown_future_symbol_falls_back_to_keyword_heuristic():
    assert classify_corona_symbol("CoronaSuperNewMtl2027") == "materials"
    assert classify_corona_symbol("CoronaTotallyNovelThing") == "unknown"


def test_classify_is_case_insensitive():
    assert classify_corona_symbol("coronaphysicalmtl") == "materials"
    assert classify_corona_symbol("CORONALIGHT") == "lights"
