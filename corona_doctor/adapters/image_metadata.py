"""Lightweight, header-only image dimension readers.

Deliberately does NOT decode pixel data — every reader here seeks/reads
only the small header region needed to find width/height, using nothing
but the Python standard library (``struct`` + file I/O). This is what
lets Texture Doctor report resolution for thousands of production
textures (including 8K/16K files) without ever loading a full image.

Every function returns ``None`` (unknown) rather than raising on a
malformed, truncated, or unrecognized file — see docs/TEXTURE_DOCTOR.md,
"Image format support" for the exact guarantee.
"""

from __future__ import annotations

import struct

_HEADER_READ_CAP = 65536  # generous cap so a malformed file can't force a huge read


def read_image_dimensions(path: str) -> tuple[int, int] | None:
    """Dispatch to the right header parser by (lowercased) extension."""

    lowered = path.lower()
    for suffix, reader in _READERS_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            try:
                with open(path, "rb") as handle:
                    return reader(handle)
            except (OSError, ValueError, struct.error):
                return None
    return None


def _read_png(handle) -> tuple[int, int] | None:
    header = handle.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _read_bmp(handle) -> tuple[int, int] | None:
    header = handle.read(26)
    if len(header) < 26 or header[:2] != b"BM":
        return None
    width, height = struct.unpack("<ii", header[18:26])
    return width, abs(height)


def _read_tga(handle) -> tuple[int, int] | None:
    header = handle.read(18)
    if len(header) < 18:
        return None
    width, height = struct.unpack("<HH", header[12:16])
    if width == 0 or height == 0:
        return None
    return width, height


def _read_jpeg(handle) -> tuple[int, int] | None:
    data = handle.read(2)
    if data != b"\xff\xd8":
        return None
    while True:
        marker = handle.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        marker_id = marker[1]
        if marker_id in (0xD8, 0x01) or 0xD0 <= marker_id <= 0xD7:
            continue  # markers with no payload
        length_bytes = handle.read(2)
        if len(length_bytes) < 2:
            return None
        (segment_length,) = struct.unpack(">H", length_bytes)
        is_sof = marker_id in range(0xC0, 0xD0) and marker_id not in (0xC4, 0xC8, 0xCC)
        if is_sof:
            payload = handle.read(5)
            if len(payload) < 5:
                return None
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height
        if marker_id == 0xD9:  # EOI reached without a SOF — malformed/truncated
            return None
        handle.seek(segment_length - 2, 1)


def _read_tiff_impl(handle) -> tuple[int, int] | None:
    header = handle.read(8)
    if len(header) < 8:
        return None
    if header[:2] == b"II":
        endian = "<"
    elif header[:2] == b"MM":
        endian = ">"
    else:
        return None

    (ifd_offset,) = struct.unpack(endian + "I", header[4:8])
    handle.seek(ifd_offset)
    count_bytes = handle.read(2)
    if len(count_bytes) < 2:
        return None
    (entry_count,) = struct.unpack(endian + "H", count_bytes)

    width: int | None = None
    height: int | None = None
    entries = handle.read(12 * entry_count)
    if len(entries) < 12 * entry_count:
        return None

    for i in range(entry_count):
        entry = entries[i * 12 : i * 12 + 12]
        tag, field_type = struct.unpack(endian + "HH", entry[0:4])
        value_field = entry[8:12]
        if field_type == 3:  # SHORT
            value = struct.unpack(endian + "H", value_field[:2])[0]
        elif field_type == 4:  # LONG
            value = struct.unpack(endian + "I", value_field)[0]
        else:
            continue
        if tag == 256:
            width = value
        elif tag == 257:
            height = value
        if width is not None and height is not None:
            return width, height

    return None


def _read_hdr(handle) -> tuple[int, int] | None:
    data = handle.read(_HEADER_READ_CAP)
    try:
        text = data.decode("latin-1")
    except UnicodeDecodeError:
        return None
    for line in text.splitlines():
        parts = line.split()
        # Radiance resolution line, e.g. "-Y 2048 +X 4096".
        if len(parts) == 4 and parts[0] in ("-Y", "+Y") and parts[2] in ("-X", "+X"):
            try:
                height = int(parts[1])
                width = int(parts[3])
            except ValueError:
                return None
            return width, height
    return None


def _read_exr(handle) -> tuple[int, int] | None:
    magic = handle.read(4)
    if magic != b"\x76\x2f\x31\x01":
        return None
    handle.read(4)  # version + flags, unused

    data = handle.read(_HEADER_READ_CAP)
    cursor = 0
    while cursor < len(data):
        name_end = data.find(b"\x00", cursor)
        if name_end == -1 or name_end == cursor:
            return None  # empty name terminates the attribute list
        name = data[cursor:name_end]
        cursor = name_end + 1

        type_end = data.find(b"\x00", cursor)
        if type_end == -1:
            return None
        attr_type = data[cursor:type_end]
        cursor = type_end + 1

        if cursor + 4 > len(data):
            return None
        (size,) = struct.unpack("<i", data[cursor : cursor + 4])
        cursor += 4

        if cursor + size > len(data):
            return None
        value = data[cursor : cursor + size]
        cursor += size

        if name == b"dataWindow" and attr_type == b"box2i" and size == 16:
            x_min, y_min, x_max, y_max = struct.unpack("<iiii", value)
            return (x_max - x_min + 1), (y_max - y_min + 1)

    return None


_READERS_BY_SUFFIX = {
    ".png": _read_png,
    ".bmp": _read_bmp,
    ".tga": _read_tga,
    ".jpg": _read_jpeg,
    ".jpeg": _read_jpeg,
    ".tif": _read_tiff_impl,
    ".tiff": _read_tiff_impl,
    ".hdr": _read_hdr,
    ".exr": _read_exr,
}
