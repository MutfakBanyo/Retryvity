"""Unit tests for persistence/settings.py. No 3ds Max, no Qt required."""

from __future__ import annotations

from pathlib import Path

from corona_doctor.persistence.settings import DEFAULT_SETTINGS, SettingsStore


def test_defaults_when_no_file_exists(tmp_path: Path):
    store = SettingsStore(path=tmp_path / "settings.json")
    assert store.get("theme") == DEFAULT_SETTINGS["theme"]
    assert store.get("developer_mode") is False


def test_set_and_save_round_trip(tmp_path: Path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path=path)
    store.set("developer_mode", True)
    store.set("last_nav_section", "environment")
    store.save()

    reloaded = SettingsStore(path=path)
    assert reloaded.get("developer_mode") is True
    assert reloaded.get("last_nav_section") == "environment"


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = SettingsStore(path=path)
    assert store.get("theme") == DEFAULT_SETTINGS["theme"]


def test_get_unknown_key_returns_default():
    store = SettingsStore(path=Path("/nonexistent/path/settings.json"))
    assert store.get("does_not_exist", "fallback") == "fallback"
