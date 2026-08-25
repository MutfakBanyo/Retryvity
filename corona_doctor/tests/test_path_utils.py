"""Unit tests for adapters/path_utils.py. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.adapters.path_utils import (
    FilesystemMetadataCache,
    build_path_info,
    classify_path,
    human_readable_size,
)
from corona_doctor.core.texture_models import PathType


def test_classify_unc_path():
    assert classify_path(r"\\server\assets\wood.jpg") == PathType.NETWORK_UNC
    assert classify_path("//server/assets/wood.jpg") == PathType.NETWORK_UNC


def test_classify_relative_path():
    assert classify_path("textures/wood.jpg") == PathType.RELATIVE
    assert classify_path("..\\textures\\wood.jpg") == PathType.RELATIVE


def test_classify_missing_path():
    assert classify_path("") == PathType.MISSING
    assert classify_path(None) == PathType.MISSING
    assert classify_path("   ") == PathType.MISSING


def test_classify_drive_letter_local_via_probe():
    assert classify_path(r"C:\project\textures\wood.jpg", drive_type_probe=lambda d: 3) == PathType.LOCAL


def test_classify_drive_letter_network_via_probe():
    # A mapped drive letter can still be a network path — must not be
    # blindly labeled "local" just because it has a drive letter.
    assert classify_path(r"Z:\textures\wood.jpg", drive_type_probe=lambda d: 4) == PathType.NETWORK_UNC


def test_classify_drive_letter_unknown_when_probe_unavailable():
    assert classify_path(r"C:\project\textures\wood.jpg", drive_type_probe=lambda d: None) == PathType.UNKNOWN


def test_build_path_info_preserves_raw_path():
    info = build_path_info(r"C:\Project\Textures\Wood.jpg", exists_checker=lambda p: True, drive_type_probe=lambda d: 3)
    assert info.raw_path == r"C:\Project\Textures\Wood.jpg"
    assert info.exists is True
    assert info.path_type == PathType.LOCAL


def test_build_path_info_relative_never_checks_existence():
    calls = []

    def exists_checker(path):
        calls.append(path)
        return True

    info = build_path_info("textures/wood.jpg", exists_checker=exists_checker)
    assert info.exists is None
    assert calls == []


def test_build_path_info_comparison_key_is_case_insensitive():
    a = build_path_info(r"C:\Project\Wood.jpg", exists_checker=lambda p: True, drive_type_probe=lambda d: 3)
    b = build_path_info(r"C:\PROJECT\WOOD.JPG", exists_checker=lambda p: True, drive_type_probe=lambda d: 3)
    assert a.comparison_key == b.comparison_key


def test_human_readable_size():
    assert human_readable_size(None) == "unknown"
    assert human_readable_size(500) == "500 B"
    assert human_readable_size(1536) == "1.5 KB"
    assert human_readable_size(5 * 1024 * 1024) == "5.0 MB"


def test_filesystem_metadata_cache_stats_each_path_once(tmp_path):
    calls = []
    target = tmp_path / "wood.jpg"
    target.write_bytes(b"x" * 42)

    cache = FilesystemMetadataCache()
    import os

    original_isfile = os.path.isfile

    def counting_isfile(path):
        calls.append(path)
        return original_isfile(path)

    os.path.isfile = counting_isfile
    try:
        assert cache.exists(str(target)) is True
        assert cache.exists(str(target)) is True
        assert cache.size_bytes(str(target)) == 42
    finally:
        os.path.isfile = original_isfile

    assert calls.count(str(target)) == 1


def test_filesystem_metadata_cache_missing_file():
    cache = FilesystemMetadataCache()
    assert cache.exists(r"C:\definitely\not\a\real\path\wood.jpg") is False
    assert cache.size_bytes(r"C:\definitely\not\a\real\path\wood.jpg") is None
