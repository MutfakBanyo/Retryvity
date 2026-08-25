"""Pure-Python filtering/sorting over already-scanned texture data.

No Qt, no pymxs, no filesystem access — operates only on
:class:`~corona_doctor.core.texture_models.ExternalTextureReference` and
:class:`~corona_doctor.core.models.Finding` collections a scan already
produced. A future UI table can delegate here instead of re-implementing
filter/sort logic inside a ``QSortFilterProxyModel`` — see
docs/ARCHITECTURE.md, "UI boundary": scanners/rules stay UI-free, and this
module keeps filtering/sorting UI-free too, so it is usable from a report,
a test, or a future UI alike.

Every function returns a new list — never mutates its input — and sorting
always uses a stable secondary tie-break (filename) so result order is
deterministic across repeated calls with equal primary keys.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from corona_doctor.core.models import Finding, Severity
from corona_doctor.core.texture_models import ExternalTextureReference, PathType, TextureThresholds


class TextureFilter(str, Enum):
    ALL = "all"
    MISSING = "missing"
    OVERSIZED = "oversized"
    LOCAL = "local"
    DUPLICATE = "duplicate"


class TextureSortKey(str, Enum):
    FILENAME = "filename"
    RESOLUTION = "resolution"
    FILE_SIZE = "file_size"
    REFERENCE_COUNT = "reference_count"
    PATH = "path"


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.OPTIMIZATION: 2,
    Severity.INFO: 3,
    Severity.HEALTHY: 4,
}


def apply_filter(
    refs: Iterable[ExternalTextureReference],
    filter_: TextureFilter,
    *,
    thresholds: TextureThresholds | None = None,
) -> list[ExternalTextureReference]:
    """One of the fixed :class:`TextureFilter` buckets. See
    ``filter_by_extension``/``filter_by_map_class``/``filter_by_material``/
    ``filter_by_object`` for the open-ended (value-parameterized) filters."""

    thresholds = thresholds or TextureThresholds()
    refs = list(refs)

    if filter_ == TextureFilter.ALL:
        return refs
    if filter_ == TextureFilter.MISSING:
        return [r for r in refs if r.path_info.exists is False]
    if filter_ == TextureFilter.OVERSIZED:
        return [
            r
            for r in refs
            if r.width and r.height and max(r.width, r.height) >= thresholds.oversized_warning_px
        ]
    if filter_ == TextureFilter.LOCAL:
        return [r for r in refs if r.path_info.path_type == PathType.LOCAL]
    if filter_ == TextureFilter.DUPLICATE:
        return [r for r in refs if r.reference_count > 1]
    raise ValueError(f"unknown filter: {filter_}")  # pragma: no cover - exhaustive enum above


def filter_by_extension(refs: Iterable[ExternalTextureReference], extension: str) -> list[ExternalTextureReference]:
    target = extension.lower().lstrip(".")
    return [r for r in refs if r.extension.lower() == target]


def filter_by_map_class(refs: Iterable[ExternalTextureReference], map_class: str) -> list[ExternalTextureReference]:
    return [r for r in refs if r.map_class == map_class]


def filter_by_material(refs: Iterable[ExternalTextureReference], material_name: str) -> list[ExternalTextureReference]:
    return [r for r in refs if r.material_name == material_name]


def filter_by_object(refs: Iterable[ExternalTextureReference], object_name: str) -> list[ExternalTextureReference]:
    return [r for r in refs if object_name in r.object_names]


def filter_local_workstation_paths(
    refs: Iterable[ExternalTextureReference], thresholds: TextureThresholds | None = None
) -> list[ExternalTextureReference]:
    """References under a workstation-specific local path (user profile,
    Desktop, Downloads, Temp, AppData — see
    ``TextureThresholds.local_path_markers``).

    The single source of truth for this: TXT-006 (see
    ``rules/definitions/texture_rules.py``) and the production report
    formatter (``reports/texture_report.py``) both call this rather than
    each re-implementing the marker match, so the two can never disagree
    on what counts as a "local path" reference.
    """

    thresholds = thresholds or TextureThresholds()
    return [
        r
        for r in refs
        if r.path_info.path_type == PathType.LOCAL
        and any(marker in r.path_info.normalized_path.lower() for marker in thresholds.local_path_markers)
    ]


def local_workstation_path_count(refs: Iterable[ExternalTextureReference], thresholds: TextureThresholds | None = None) -> int:
    return len(filter_local_workstation_paths(refs, thresholds))


_SORT_KEY_FUNCS = {
    TextureSortKey.FILENAME: lambda r: (r.filename.lower(),),
    TextureSortKey.RESOLUTION: lambda r: ((r.width or 0) * (r.height or 0), r.filename.lower()),
    TextureSortKey.FILE_SIZE: lambda r: (r.file_size_bytes or 0, r.filename.lower()),
    TextureSortKey.REFERENCE_COUNT: lambda r: (r.reference_count, r.filename.lower()),
    TextureSortKey.PATH: lambda r: (r.path_info.normalized_path.lower(),),
}


def sort_references(
    refs: Iterable[ExternalTextureReference],
    key: TextureSortKey,
    *,
    reverse: bool = False,
) -> list[ExternalTextureReference]:
    """Sort by one :class:`TextureSortKey`. Deterministic: every key
    tie-breaks on lowercased filename, so equal-value rows keep a stable,
    repeatable order instead of falling back to insertion order."""

    key_fn = _SORT_KEY_FUNCS[key]
    return sorted(refs, key=key_fn, reverse=reverse)


def sort_findings_by_severity(findings: Iterable[Finding], *, reverse: bool = False) -> list[Finding]:
    """Most severe first (critical > warning > optimization > info > healthy),
    tie-broken by ``rule_id`` for determinism."""

    return sorted(findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.rule_id), reverse=reverse)
