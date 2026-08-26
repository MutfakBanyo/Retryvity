"""Data model for snapshots and comparison results.

Everything here is a plain dataclass with a ``to_dict`` method. V0.1 keeps
snapshots in memory only, but shaping them as JSON-friendly primitives now
means persisting them later is a serialisation call, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator


class ChangeType(str, Enum):
    """The six V0.1 comparison outcomes."""

    ADDED = "ADDED"
    REMOVED = "REMOVED"
    GEOMETRY_CHANGED = "GEOMETRY_CHANGED"
    TRANSFORM_CHANGED = "TRANSFORM_CHANGED"
    GEOMETRY_AND_TRANSFORM_CHANGED = "GEOMETRY_AND_TRANSFORM_CHANGED"
    UNCHANGED = "UNCHANGED"

    @property
    def label(self) -> str:
        """Human-facing label used in the panel summary."""

        return _LABELS[self]

    @property
    def is_change(self) -> bool:
        return self is not ChangeType.UNCHANGED

    @property
    def is_selectable(self) -> bool:
        """True when nodes of this category still exist in the scene."""

        return self.is_change and self is not ChangeType.REMOVED


_LABELS = {
    ChangeType.ADDED: "Added",
    ChangeType.REMOVED: "Removed",
    ChangeType.GEOMETRY_CHANGED: "Geometry Changed",
    ChangeType.TRANSFORM_CHANGED: "Transform Changed",
    ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED: "Geometry + Transform",
    ChangeType.UNCHANGED: "Unchanged",
}

# Display / reporting order. Deliberately not the enum declaration order:
# the panel lists the categories a user acts on before the inert ones.
CHANGE_TYPE_ORDER = (
    ChangeType.ADDED,
    ChangeType.REMOVED,
    ChangeType.GEOMETRY_CHANGED,
    ChangeType.TRANSFORM_CHANGED,
    ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED,
    ChangeType.UNCHANGED,
)

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


@dataclass(frozen=True)
class TransformSignature:
    """World-space transform of a node, decomposed and digested.

    The components are kept alongside the digest on purpose: the digest is
    only a fast-path equality check, and the actual decision is made by a
    tolerant component comparison (see fingerprint.transform_changed).
    """

    position: Vector3
    rotation: Quaternion
    scale: Vector3
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class GeometrySignature:
    """Local-space mesh fingerprint of a node."""

    vertex_count: int
    face_count: int
    bbox_min: Vector3
    bbox_max: Vector3
    digest: str
    hashed_vertices: int = 0
    sampled: bool = False

    @property
    def bbox_size(self) -> Vector3:
        return (
            self.bbox_max[0] - self.bbox_min[0],
            self.bbox_max[1] - self.bbox_min[1],
            self.bbox_max[2] - self.bbox_min[2],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "bbox_min": list(self.bbox_min),
            "bbox_max": list(self.bbox_max),
            "digest": self.digest,
            "hashed_vertices": self.hashed_vertices,
            "sampled": self.sampled,
        }


@dataclass(frozen=True)
class ObjectRecord:
    """One eligible geometry node as captured at snapshot time."""

    handle: int
    name: str
    object_class: str
    transform: TransformSignature
    geometry: GeometrySignature

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "class": self.object_class,
            "transform": self.transform.to_dict(),
            "geometry": self.geometry.to_dict(),
        }


@dataclass(frozen=True)
class SkippedObject:
    """A node the scan could not or would not fingerprint."""

    handle: int
    name: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"handle": self.handle, "name": self.name, "reason": self.reason}


@dataclass
class Snapshot:
    """Immutable-by-convention record of the scene at one point in time."""

    objects: dict[int, ObjectRecord] = field(default_factory=dict)
    skipped: list[SkippedObject] = field(default_factory=list)
    created_at: float = 0.0
    duration_seconds: float = 0.0

    def __len__(self) -> int:
        return len(self.objects)

    def __iter__(self) -> Iterator[ObjectRecord]:
        return iter(self.objects.values())

    @property
    def object_count(self) -> int:
        return len(self.objects)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
            "objects": {str(handle): record.to_dict() for handle, record in self.objects.items()},
            "skipped": [item.to_dict() for item in self.skipped],
        }


@dataclass(frozen=True)
class ChangeEntry:
    """One line of the comparison result."""

    handle: int
    name: str
    object_class: str
    change_type: ChangeType

    @property
    def exists_in_scene(self) -> bool:
        return self.change_type.is_selectable or self.change_type is ChangeType.UNCHANGED

    def __str__(self) -> str:
        return f"[{self.change_type.value}] {self.name}"


@dataclass
class CompareResult:
    """Outcome of comparing a stored snapshot against the current scene."""

    entries: list[ChangeEntry] = field(default_factory=list)
    scanned: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0

    def counts(self) -> dict[ChangeType, int]:
        result = {change_type: 0 for change_type in CHANGE_TYPE_ORDER}
        for entry in self.entries:
            result[entry.change_type] += 1
        return result

    def count_of(self, change_type: ChangeType) -> int:
        return sum(1 for entry in self.entries if entry.change_type is change_type)

    @property
    def changed_count(self) -> int:
        return sum(1 for entry in self.entries if entry.change_type.is_change)

    def entries_of(self, change_types: Iterable[ChangeType]) -> list[ChangeEntry]:
        wanted = set(change_types)
        return [entry for entry in self.entries if entry.change_type in wanted]

    def selectable_handles(self) -> list[int]:
        """Handles of changed nodes that still exist and can be selected."""

        return [entry.handle for entry in self.entries if entry.change_type.is_selectable]

    def summary_line(self) -> str:
        """Compact one-line summary for the 3ds Max listener."""

        counts = self.counts()
        return (
            f"Added={counts[ChangeType.ADDED]} "
            f"Removed={counts[ChangeType.REMOVED]} "
            f"Geometry={counts[ChangeType.GEOMETRY_CHANGED]} "
            f"Transform={counts[ChangeType.TRANSFORM_CHANGED]} "
            f"Both={counts[ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED]} "
            f"Unchanged={counts[ChangeType.UNCHANGED]}"
        )
