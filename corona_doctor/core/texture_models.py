"""Domain models for Scene Inventory + Texture Doctor.

Plain, framework-free dataclasses — no pymxs, no Qt — so scanners can
build them from real scene data while rules and UI models stay fully
unit-testable outside 3ds Max. See docs/TEXTURE_DOCTOR.md for what each
field means and its known limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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

    material_count: int = 0
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
