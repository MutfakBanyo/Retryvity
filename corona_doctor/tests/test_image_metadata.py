"""Unit tests for adapters/image_metadata.py using small synthetic files.

Every fixture here is hand-built to the minimum bytes each format's
header parser needs — never a real decoded image — which is exactly what
the header-only reader is meant to handle. No 3ds Max required.
"""

from __future__ import annotations

import struct

from corona_doctor.adapters.image_metadata import read_image_dimensions

_WIDTH, _HEIGHT = 800, 600


def _write(tmp_path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_png_dimensions(tmp_path):
    data = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", _WIDTH, _HEIGHT)
        + bytes(5)
        + bytes(4)
    )
    path = _write(tmp_path, "a.png", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_bmp_dimensions(tmp_path):
    data = b"BM" + bytes(4) + bytes(4) + bytes(4) + bytes(4) + struct.pack("<ii", _WIDTH, _HEIGHT)
    path = _write(tmp_path, "a.bmp", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_tga_dimensions(tmp_path):
    data = bytes(12) + struct.pack("<HH", _WIDTH, _HEIGHT) + bytes(2)
    path = _write(tmp_path, "a.tga", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_jpeg_dimensions(tmp_path):
    data = b"\xff\xd8" + b"\xff\xc0" + b"\x00\x11" + struct.pack(">BHH", 8, _HEIGHT, _WIDTH)
    path = _write(tmp_path, "a.jpg", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_tiff_dimensions_little_endian(tmp_path):
    entry1 = struct.pack("<HHI", 256, 3, 1) + struct.pack("<H", _WIDTH) + b"\x00\x00"
    entry2 = struct.pack("<HHI", 257, 3, 1) + struct.pack("<H", _HEIGHT) + b"\x00\x00"
    ifd = struct.pack("<H", 2) + entry1 + entry2
    header = b"II" + struct.pack("<H", 42) + struct.pack("<I", 8)
    data = header + ifd
    path = _write(tmp_path, "a.tif", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_hdr_dimensions(tmp_path):
    text = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {_HEIGHT} +X {_WIDTH}\n"
    path = _write(tmp_path, "a.hdr", text.encode("ascii"))
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_exr_dimensions(tmp_path):
    attr = (
        b"dataWindow\x00"
        + b"box2i\x00"
        + struct.pack("<i", 16)
        + struct.pack("<iiii", 0, 0, _WIDTH - 1, _HEIGHT - 1)
    )
    data = b"\x76\x2f\x31\x01" + bytes(4) + attr + b"\x00"
    path = _write(tmp_path, "a.exr", data)
    assert read_image_dimensions(path) == (_WIDTH, _HEIGHT)


def test_unsupported_extension_returns_none(tmp_path):
    path = _write(tmp_path, "a.xyz", b"whatever")
    assert read_image_dimensions(path) is None


def test_missing_file_returns_none(tmp_path):
    assert read_image_dimensions(str(tmp_path / "missing.png")) is None


def test_truncated_png_returns_none(tmp_path):
    path = _write(tmp_path, "a.png", b"\x89PNG\r\n\x1a\n")
    assert read_image_dimensions(path) is None


def test_truncated_jpeg_returns_none(tmp_path):
    path = _write(tmp_path, "a.jpg", b"\xff\xd8\xff\xc0")
    assert read_image_dimensions(path) is None
