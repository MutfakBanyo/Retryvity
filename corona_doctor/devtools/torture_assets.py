"""Generates small, real, decodable test image files for the Torture
Scene — pure stdlib (``struct``/``zlib``), no pymxs, no new dependency,
no PIL. Kept separate from ``torture_scene.py`` so the byte-level image
generation is unit-testable without 3ds Max.

``write_stub_png`` writes a genuinely valid PNG at whatever declared
width/height is asked for (so ``adapters/image_metadata.py`` reads back
correct dimensions, and 3ds Max/Corona's own bitmap loader can actually
open it — never a truncated/fake header) while staying tiny on disk: a
single solid color compresses to a few KB even at 16384x16384, because
DEFLATE crushes uniform data. This is what lets Texture Doctor's
oversized-texture fixtures (CDT-TEX-004/005) exist without shipping (or
generating) hundreds of MB of real pixel data — see docs/REPAIR_ENGINE.md,
"Torture scene assets".
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from corona_doctor.core.constants import ORG_NAME


def default_torture_asset_dir() -> Path:
    """A dedicated, clearly-labeled temp directory — never an arbitrary
    user folder. Safe to delete entirely between runs."""

    import tempfile

    return Path(tempfile.gettempdir()) / ORG_NAME / "torture_assets"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_stub_png(path: Path, width: int, height: int, gray_value: int = 128) -> None:
    """Write a minimal, valid, single-color 8-bit grayscale PNG at
    ``width``x``height``. Streams row-by-row through the compressor so
    peak memory stays at one row (``width`` bytes), not the full
    (potentially huge) uncompressed image."""

    path.parent.mkdir(parents=True, exist_ok=True)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit grayscale, no interlace

    compressor = zlib.compressobj(zlib.Z_BEST_COMPRESSION)
    row = bytes([0]) + bytes([gray_value]) * width  # filter-type-0 byte + pixel data
    compressed = bytearray()
    for _ in range(height):
        compressed += compressor.compress(row)
    compressed += compressor.flush()

    png = signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", bytes(compressed)) + _png_chunk(b"IEND", b"")
    path.write_bytes(png)
