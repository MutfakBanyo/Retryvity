"""Domain models for Scene Inventory + Texture Doctor.

Plain, framework-free dataclasses — no pymxs, no Qt — so scanners can
build them from real scene data while rules and UI models stay fully
unit-testable outside 3ds Max. See docs/TEXTURE_DOCTOR.md for what each
field means and its known limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from corona_doctor.core.models import Finding


class PathType(str, Enum):
    """Structural classification of a raw path string.

    This describes the *shape* of the path, not whether the file exists —
    see ``PathInfo.exists`` for that. ``MISSING`` here means "no path
    string was present at all", not "file not found on disk".
    """

    LOCAL = "local"
    NETWORK_UNC = "network_unc"
    RELATIVE = "relative"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PathInfo:
    """Result of classifying/normalizing one raw texture path string.

    ``raw_path`` is preserved verbatim — never rewritten. ``normalized_path``
    is a display-friendly ``os.path.normpath`` form. ``comparison_key`` is a
    case-folded form used *only* for grouping/dedup and must never be shown
    to the user (it may mangle case-sensitive-looking paths).
    """

    raw_path: str
    normalized_path: str
    comparison_key: str
    path_type: PathType
    exists: bool | None  # None = existence could not be reliably determined


@dataclass(frozen=True)
class TextureThresholds:
    """Centralized, configurable thresholds for texture diagnostic rules.

    Every rule that needs a size/dimension cutoff reads from here instead
    of hardcoding a number inline — see docs/TEXTURE_DOCTOR.md, "Threshold
    logic".
    """

    oversized_warning_px: int = 8192
    oversized_strong_warning_px: int = 16384
    large_file_warning_bytes: int = 100 * 1024 * 1024
    large_file_strong_bytes: int = 250 * 1024 * 1024
    large_file_extreme_bytes: int = 500 * 1024 * 1024
    local_path_markers: tuple[str, ...] = (
        "\\users\\",
        "\\desktop\\",
        "\\downloads\\",
        "\\temp\\",
        "\\appdata\\",
    )


@dataclass(frozen=True)
class ExternalTextureReference:
    """One discovered file-backed texture map node, detached from pymxs.

    Represents exactly one unique Texmap object encountered during
    traversal (deduplicated by Animatable handle — see
    adapters/scene_adapter.py's module docstring for why). ``reference_count``
    is filled in by the scanner *after* traversal: it counts how many other
    ``ExternalTextureReference`` entries share the same ``comparison_key``
    (i.e. how many distinct map nodes point at the same underlying file).
    """

    ref_id: str
    map_class: str
    map_name: str | None
    material_name: str | None
    object_names: tuple[str, ...]
    path_info: PathInfo
    filename: str
    extension: str
    file_size_bytes: int | None = None
    file_size_human: str = "unknown"
    width: int | None = None
    height: int | None = None
    reference_count: int = 1
    unsupported: bool = False
    source_property: str | None = None
    # The map object's Animatable handle (see adapters/scene_adapter.py's
    # module docstring) — the stable identity a repair action needs to
    # find this exact live scene object again to relink it. None if the
    # scan fell back to a per-scan identity (see
    # SceneAdapter._identity) — a repair targeting such a map cannot
    # reliably re-locate it and must be treated as unsupported/blocked
    # (see repair/planner.py).
    map_handle: int | None = None


@dataclass(frozen=True)
class SceneInventory:
    """Aggregate scene counts produced by the Scene Inventory scanner.

    Every count defaults to 0 / empty rather than being omitted, so UI code
    never has to special-case "no scan yet" vs "scanned, found nothing".
    """

    total_nodes: int = 0
    geometry_count: int = 0
    light_count: int = 0
    camera_count: int = 0
    helper_count: int = 0
    shape_count: int = 0
    group_count: int = 0
    hidden_count: int = 0
    frozen_count: int = 0

    # Nodes with a material assigned — NOT a count of materials. Renamed
    # from the misleading "material_count" after a real-host scan showed
    # 363 here alongside 0 unique_material_count and no obvious way to
    # tell, from the field name alone, that this was assignment count, not
    # material count. See docs/TEXTURE_DOCTOR.md, "Material count semantics".
    nodes_with_material_count: int = 0
    unique_material_count: int = 0

    map_reference_count: int = 0
    unique_external_texture_count: int = 0

    corona_light_count: int = 0
    corona_camera_count: int = 0

    missing_texture_count: int = 0
    oversized_8k_count: int = 0
    oversized_16k_count: int = 0
    duplicate_group_count: int = 0

    extension_counts: dict[str, int] = field(default_factory=dict)

    scan_duration_ms: float = 0.0


@dataclass(frozen=True)
class TextureDoctorDiagnostics:
    """Development-only counters/samples for real-host compatibility debugging.

    Populated by ``SceneAdapter`` during traversal, surfaced by
    ``devtools/texture_probe.py`` — not shown in production UI. Exists so a
    real-host run can explain *why* a count looks wrong (e.g. 0 unique
    materials with 363 material assignments) instead of silently reporting
    a plausible-looking but incorrect result. See docs/TEXTURE_DOCTOR.md,
    "No silent zeroes".
    """

    root_materials_encountered: int = 0
    materials_with_valid_handle: int = 0
    materials_using_fallback_identity: int = 0
    sub_material_edges_traversed: int = 0
    map_nodes_encountered: int = 0
    maps_with_valid_handle: int = 0
    maps_using_fallback_identity: int = 0
    external_file_backed_maps_recognized: int = 0
    maps_with_candidate_filename_properties: int = 0
    maps_rejected_as_non_file_backed: int = 0
    identity_samples: tuple[dict, ...] = ()
    rejected_map_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class TextureScanFacts:
    """Everything Texture Doctor's rules evaluate — facts only, no verdicts.

    Scanners build this; rules read it; the boundary between "collecting
    facts" and "interpreting facts" (see docs/ARCHITECTURE.md) runs right
    through this class.
    """

    inventory: SceneInventory
    texture_references: tuple[ExternalTextureReference, ...] = ()
    unknown_map_classes: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    diagnostics: TextureDoctorDiagnostics = field(default_factory=TextureDoctorDiagnostics)
    compatibility_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanTimings:
    """Per-stage scan timing, in milliseconds — see performance/profiler.py.

    Mirrors ``Profiler.report()``'s ``texture_doctor.*`` keys as named
    fields so consumers don't need to know the profiler's label strings.
    ``report_format_ms`` is filled in only by callers that time their own
    call to ``reports/texture_report.py::format_texture_doctor_report`` —
    formatting a result never re-runs the scan, so it has no bearing on
    the other fields.
    """

    nodes_ms: float = 0.0
    materials_maps_ms: float = 0.0
    filesystem_ms: float = 0.0
    rules_ms: float = 0.0
    total_ms: float = 0.0
    report_format_ms: float = 0.0


@dataclass(frozen=True)
class TextureDoctorResult:
    """The stable, production-facing Texture Doctor result.

    This is what a caller outside the scanner (a future UI table, an
    export, ``reports/texture_report.py``) should hold onto — never the
    dev-only ``TextureScanFacts.diagnostics`` (AnimHandle samples,
    rejected-map property dumps, etc.), which stays a development-only
    concern surfaced only by ``devtools/texture_probe.py``. See
    docs/TEXTURE_DOCTOR.md, "Production result model".
    """

    inventory: SceneInventory
    texture_references: tuple[ExternalTextureReference, ...]
    findings: tuple[Finding, ...]
    compatibility_warnings: tuple[str, ...]
    unknown_map_classes: tuple[str, ...]
    errors: tuple[str, ...]
    timings: ScanTimings = field(default_factory=ScanTimings)

    @staticmethod
    def from_facts(facts: TextureScanFacts, findings: tuple[Finding, ...], timings: ScanTimings) -> "TextureDoctorResult":
        return TextureDoctorResult(
            inventory=facts.inventory,
            texture_references=facts.texture_references,
            findings=findings,
            compatibility_warnings=facts.compatibility_warnings,
            unknown_map_classes=facts.unknown_map_classes,
            errors=facts.errors,
            timings=timings,
        )
