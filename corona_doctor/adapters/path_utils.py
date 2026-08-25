"""Conservative texture-path classification, normalization and filesystem caching.

Pure Python — no pymxs, no Qt — so it is fully unit-testable outside 3ds
Max. Never rewrites or "fixes" a path; ``PathInfo.raw_path`` is always the
verbatim string a texmap reported.
"""

from __future__ import annotations

import ntpath
import os
from dataclasses import dataclass
from typing import Callable

from corona_doctor.core.texture_models import PathInfo, PathType

# Windows drive-type codes from GetDriveTypeW (kernel32). DRIVE_REMOTE is
# the only one that means "this drive letter is actually a network share".
_DRIVE_REMOTE = 4


def _real_drive_type_probe(drive: str) -> int | None:
    """Best-effort ``GetDriveTypeW`` lookup for a drive letter like "Z:".

    Windows-only, stdlib-only (``ctypes``). Returns ``None`` (unknown)
    rather than guessing when the platform API is unavailable — e.g. in a
    non-Windows test environment, or if the call itself fails for any
    reason.
    """

    if os.name != "nt":
        return None
    try:
        import ctypes  # noqa: PLC0415 - Windows-only, kept local

        result = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive + "\\"))
        return int(result)
    except Exception:  # noqa: BLE001 - never let a path probe crash a scan
        return None


def classify_path(
    raw_path: str | None,
    drive_type_probe: Callable[[str], int | None] = _real_drive_type_probe,
) -> PathType:
    """Classify a raw path string's *shape* — never checks existence.

    A drive-letter path (``Z:\\...``) is conservatively reported as
    ``UNKNOWN`` unless ``drive_type_probe`` can confirm it is a fixed/local
    drive (-> ``LOCAL``) or a mapped network share (-> ``NETWORK_UNC``);
    per docs/TEXTURE_DOCTOR.md this deliberately avoids assuming every
    drive letter is safe/local, since mapped drives are a common studio
    pattern.
    """

    if not raw_path or not raw_path.strip():
        return PathType.MISSING

    stripped = raw_path.strip()

    if stripped.startswith("\\\\") or stripped.startswith("//"):
        return PathType.NETWORK_UNC

    drive, _tail = ntpath.splitdrive(stripped)
    if drive and len(drive) == 2 and drive[1] == ":":
        drive_type = drive_type_probe(drive)
        if drive_type == _DRIVE_REMOTE:
            return PathType.NETWORK_UNC
        if drive_type in (2, 3):  # DRIVE_REMOVABLE, DRIVE_FIXED
            return PathType.LOCAL
        return PathType.UNKNOWN

    if ntpath.isabs(stripped):
        return PathType.UNKNOWN

    return PathType.RELATIVE


def build_path_info(
    raw_path: str | None,
    exists_checker: Callable[[str], bool | None],
    drive_type_probe: Callable[[str], int | None] = _real_drive_type_probe,
) -> PathInfo:
    """Build a :class:`PathInfo` for one raw texture path.

    ``exists_checker`` is injected so callers can share a single cached
    filesystem lookup (see :class:`FilesystemMetadataCache`) across many
    references to the same path, and so tests never touch the real
    filesystem.
    """

    raw = raw_path or ""
    path_type = classify_path(raw, drive_type_probe)

    if path_type == PathType.MISSING:
        return PathInfo(raw_path=raw, normalized_path="", comparison_key="", path_type=path_type, exists=None)

    normalized = ntpath.normpath(raw)
    comparison_key = ntpath.normcase(normalized)

    exists: bool | None
    if path_type == PathType.RELATIVE:
        # Resolving a relative path against the wrong base directory would
        # silently produce a wrong answer, which is worse than "unknown" —
        # see docs/TEXTURE_DOCTOR.md, "Relative paths".
        exists = None
    else:
        exists = exists_checker(normalized)

    return PathInfo(
        raw_path=raw,
        normalized_path=normalized,
        comparison_key=comparison_key,
        path_type=path_type,
        exists=exists,
    )


def human_readable_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"  # pragma: no cover - unreachable in practice


@dataclass
class _FileStat:
    exists: bool
    size_bytes: int | None


class FilesystemMetadataCache:
    """Per-scan cache so the same normalized path is stat'd only once.

    See docs/TEXTURE_DOCTOR.md, "Filesystem check optimization" — without
    this, a scene with many maps sharing one texture would repeat the same
    ``os.path.exists``/``os.path.getsize`` calls once per reference.
    """

    def __init__(self) -> None:
        self._cache: dict[str, _FileStat] = {}

    def _stat(self, normalized_path: str) -> _FileStat:
        cached = self._cache.get(normalized_path)
        if cached is not None:
            return cached
        try:
            exists = os.path.isfile(normalized_path)
            size = os.path.getsize(normalized_path) if exists else None
        except OSError:
            exists, size = False, None
        stat = _FileStat(exists=exists, size_bytes=size)
        self._cache[normalized_path] = stat
        return stat

    def exists(self, normalized_path: str) -> bool:
        return self._stat(normalized_path).exists

    def size_bytes(self, normalized_path: str) -> int | None:
        return self._stat(normalized_path).size_bytes
