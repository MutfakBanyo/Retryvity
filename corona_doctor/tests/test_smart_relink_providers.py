"""Unit tests for smart_relink/providers.py — pure, no network."""

from __future__ import annotations

import pytest

from corona_doctor.smart_relink.models import KnownAssetMetadata, MissingAsset
from corona_doctor.smart_relink.providers import (
    PexelsProvider,
    UnsplashProvider,
    build_privacy_safe_query,
    list_providers,
)


def _missing(filename="floor_dark_07.jpg", old_path=r"C:\Users\alice\Desktop\OldProject\wood\oak\floor_dark_07.jpg") -> MissingAsset:
    return MissingAsset(
        asset_id="a1",
        filename=filename,
        old_path=old_path,
        known_metadata=KnownAssetMetadata(),
        map_ref_ids=("ref-1",),
    )


# -- provider availability / credential gating -------------------------------


def test_provider_unavailable_without_api_key():
    provider = UnsplashProvider(api_key=None)
    assert provider.is_available() is False


def test_provider_available_with_explicit_api_key():
    provider = UnsplashProvider(api_key="test-key-123")
    assert provider.is_available() is True


def test_provider_reads_api_key_from_env_var(monkeypatch):
    monkeypatch.setenv("CORONA_DOCTOR_UNSPLASH_API_KEY", "from-env")
    provider = UnsplashProvider()
    assert provider.is_available() is True


def test_unavailable_provider_search_raises_not_silently_empty():
    """An unconfigured provider must not be mistaken for "found zero
    results" - it raises, so the UI can show "not configured" instead
    of a misleading empty result list."""

    provider = UnsplashProvider(api_key=None)
    with pytest.raises(RuntimeError, match="not configured"):
        provider.search("oak floor texture")


def test_available_but_unimplemented_provider_raises_not_implemented():
    """No real HTTP call is implemented this milestone (no credentials
    to develop/test against) - a configured provider must fail loudly,
    never silently pretend to search."""

    provider = UnsplashProvider(api_key="test-key")
    with pytest.raises(NotImplementedError):
        provider.search("oak floor texture")


def test_list_providers_returns_every_known_provider():
    providers = list_providers()
    names = {p.name for p in providers}
    assert names == {"Unsplash", "Pexels"}


def test_each_provider_reports_its_own_availability_independently(monkeypatch):
    monkeypatch.delenv("CORONA_DOCTOR_UNSPLASH_API_KEY", raising=False)
    monkeypatch.setenv("CORONA_DOCTOR_PEXELS_API_KEY", "configured")

    unsplash = UnsplashProvider()
    pexels = PexelsProvider()
    assert unsplash.is_available() is False
    assert pexels.is_available() is True


# -- privacy-safe query generation -------------------------------------------


def test_query_never_contains_the_drive_letter_or_full_path():
    missing = _missing()
    query = build_privacy_safe_query(missing)
    assert "c:" not in query.lower()
    assert "\\" not in query


def test_query_never_contains_username_or_project_folder_names():
    missing = _missing(old_path=r"C:\Users\alice\Desktop\SecretClientProject\wood\oak\floor_dark_07.jpg")
    query = build_privacy_safe_query(missing)
    assert "alice" not in query.lower()
    assert "secretclientproject" not in query.lower()
    assert "users" not in query.lower()
    assert "desktop" not in query.lower()


def test_query_includes_filename_stem_words():
    missing = _missing(filename="floor_dark_07.jpg")
    query = build_privacy_safe_query(missing)
    assert "floor" in query
    assert "dark" in query


def test_query_includes_immediate_parent_folder_words():
    missing = _missing(old_path=r"C:\Users\alice\Desktop\Project\wood\oak\floor_dark_07.jpg")
    query = build_privacy_safe_query(missing)
    assert "oak" in query


def test_query_excludes_purely_numeric_and_short_tokens():
    missing = _missing(filename="img_07.jpg")
    query = build_privacy_safe_query(missing)
    assert "07" not in query.split()


def test_query_can_include_material_and_map_name():
    missing = _missing(filename="tex01.jpg", old_path=r"C:\proj\tex01.jpg")
    query = build_privacy_safe_query(missing, material_name="OakFloorMaterial", map_name="DiffuseMap")
    assert "oak" in query
    assert "floor" in query


def test_query_deduplicates_repeated_words():
    missing = _missing(filename="wood_wood.jpg", old_path=r"C:\proj\wood\wood_wood.jpg")
    query = build_privacy_safe_query(missing)
    words = query.split()
    assert words.count("wood") == 1
