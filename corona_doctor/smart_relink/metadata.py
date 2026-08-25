"""Lazy candidate metadata extraction — width/height/size/mtime are only
read for candidates that already passed the cheap filename-based filter
(see docs/SMART_RELINK.md, "Search index" — "read expensive image
metadata lazily"). Reuses ``adapters/image_metadata.py``'s existing
header-only readers (never decodes full pixel data) — no new dependency.
"""

from __future__ import annotations

import os

from corona_doctor.adapters.image_metadata import read_image_dimensions
from corona_doctor.smart_relink.models import CandidateMetadata


def read_candidate_metadata(path: str) -> CandidateMetadata:
    """Never raises — a candidate whose metadata can't be read still
    gets scored (on filename/folder evidence alone), just with fewer
    applicable criteria (see scoring.py)."""

    width: int | None = None
    height: int | None = None
    try:
        dims = read_image_dimensions(path)
        if dims is not None:
            width, height = dims
    except Exception:  # noqa: BLE001
        pass

    size_bytes: int | None = None
    modified_at: float | None = None
    try:
        size_bytes = os.path.getsize(path)
    except OSError:
        pass
    try:
        modified_at = os.path.getmtime(path)
    except OSError:
        pass

    return CandidateMetadata(width=width, height=height, file_size_bytes=size_bytes, modified_at=modified_at)
