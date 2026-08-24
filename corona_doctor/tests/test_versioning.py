"""Unit tests for compatibility/versioning.py. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.compatibility.versioning import ParsedVersion, is_at_least, parse_version


def test_parse_version_basic():
    assert parse_version("2026.3.1") == ParsedVersion(2026, 3, 1)


def test_parse_version_partial():
    assert parse_version("15") == ParsedVersion(15, 0, 0)
    assert parse_version("6.5") == ParsedVersion(6, 5, 0)


def test_parse_version_with_extra_text():
    assert parse_version("3ds Max 2026.3 Update 1") == ParsedVersion(2026, 3)


def test_parse_version_none_or_malformed():
    assert parse_version(None) is None
    assert parse_version("") is None
    assert parse_version("unknown") is None


def test_is_at_least_true():
    assert is_at_least("2026.3.1", (2026, 3)) is True


def test_is_at_least_false():
    assert is_at_least("2025.0.0", (2026, 3)) is False


def test_is_at_least_unknown_returns_none():
    assert is_at_least("unknown", (2026, 3)) is None
    assert is_at_least(None, (2026, 3)) is None
