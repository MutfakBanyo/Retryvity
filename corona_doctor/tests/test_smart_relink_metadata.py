"""Unit tests for smart_relink/metadata.py — real tiny files under
tmp_path (reuses devtools/torture_assets.py's stub PNG writer)."""

from __future__ import annotations

from corona_doctor.devtools.torture_assets import write_stub_png
from corona_doctor.smart_relink.metadata import read_candidate_metadata


def test_reads_real_dimensions_and_size(tmp_path):
    path = tmp_path / "candidate.png"
    write_stub_png(path, 512, 256)

    meta = read_candidate_metadata(str(path))

    assert meta.width == 512
    assert meta.height == 256
    assert meta.file_size_bytes == path.stat().st_size
    assert meta.modified_at is not None


def test_missing_file_returns_all_none_never_raises(tmp_path):
    meta = read_candidate_metadata(str(tmp_path / "does_not_exist.png"))

    assert meta.width is None
    assert meta.height is None
    assert meta.file_size_bytes is None
    assert meta.modified_at is None


def test_unsupported_format_still_returns_size_and_mtime_but_no_dimensions(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not an image")

    meta = read_candidate_metadata(str(path))

    assert meta.width is None
    assert meta.height is None
    assert meta.file_size_bytes == path.stat().st_size
