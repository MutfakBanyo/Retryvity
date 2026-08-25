"""Repair engine domain models — pure dataclasses, no pymxs, no Qt, no
filesystem access. See docs/REPAIR_ENGINE.md for the full DETECT ->
EXPLAIN -> LOCATE -> PREVIEW -> FIX -> VERIFY pipeline this supports.

A :class:`RepairPlan` describes *what would happen* and is always
side-effect free to build — see ``repair/planner.py``. Nothing in this
module ever touches a file or the scene; ``repair/transaction.py`` is
where a plan's operations actually run, against callables the caller
injects (so the transaction executor stays testable without a real
filesystem or 3ds Max — see that module's docstring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OperationKind(str, Enum):
    COPY_FILE = "copy_file"
    RELINK_TEXTURE = "relink_texture"
    CREATE_DIRECTORY = "create_directory"
    UPDATE_PATH = "update_path"  # generic path-only bookkeeping (e.g. revert of a relink)


class ValidationState(str, Enum):
    """Per-operation readiness, decided at plan time by the planner."""

    READY = "ready"
    BLOCKED = "blocked"  # e.g. missing source, inaccessible file, unresolved conflict


class RepairState(str, Enum):
    """Whole-plan lifecycle state — see docs/REPAIR_ENGINE.md, "States"."""

    PLANNED = "planned"
    APPLIED = "applied"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    REVERTED = "reverted"


@dataclass(frozen=True)
class RepairOperation:
    """One atomic step in a :class:`RepairPlan`.

    Not every field applies to every ``kind`` — e.g. ``COPY_FILE`` has no
    ``map_handle``/``source_property`` (it never touches the scene) and
    ``RELINK_TEXTURE`` has no ``destination`` (it has ``new_value``
    instead). Kept as one shape rather than a kind-specific subclass per
    op so :class:`RepairPlan` stays trivially serializable as one flat
    list.
    """

    op_id: str
    kind: OperationKind
    reason: str
    source: str | None = None
    destination: str | None = None
    map_ref_id: str | None = None  # ExternalTextureReference.ref_id, if this op targets one
    map_handle: int | None = None  # scene identity for RELINK_TEXTURE — see adapters/scene_adapter.py
    map_class: str | None = None
    source_property: str | None = None  # e.g. "filename" — see adapters/scene_adapter.py's candidate list
    old_value: str | None = None
    new_value: str | None = None
    validation_state: ValidationState = ValidationState.READY
    blocked_reason: str | None = None

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["kind"] = self.kind.value
        d["validation_state"] = self.validation_state.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "RepairOperation":
        d = dict(d)
        d["kind"] = OperationKind(d["kind"])
        d["validation_state"] = ValidationState(d.get("validation_state", ValidationState.READY.value))
        return RepairOperation(**d)


@dataclass(frozen=True)
class RepairPlan:
    """A fully-computed, side-effect-free description of a repair.

    Building one (see ``repair/planner.py``) never touches a file or the
    scene — only ``repair/transaction.py::apply_plan`` does, and only
    after explicit user approval (see docs/REPAIR_ENGINE.md, "No
    mutation during proposal/preview").
    """

    plan_id: str
    kind: str  # "make_project_portable" | "relink_missing_texture"
    created_at: str  # ISO 8601 timestamp
    operations: tuple[RepairOperation, ...] = ()
    conflicts: tuple[str, ...] = ()
    missing_sources: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    already_portable_ref_ids: tuple[str, ...] = ()

    @property
    def ready_operations(self) -> tuple[RepairOperation, ...]:
        return tuple(op for op in self.operations if op.validation_state == ValidationState.READY)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "operations": [op.to_dict() for op in self.operations],
            "conflicts": list(self.conflicts),
            "missing_sources": list(self.missing_sources),
            "unresolved": list(self.unresolved),
            "already_portable_ref_ids": list(self.already_portable_ref_ids),
        }

    @staticmethod
    def from_dict(d: dict) -> "RepairPlan":
        return RepairPlan(
            plan_id=d["plan_id"],
            kind=d["kind"],
            created_at=d["created_at"],
            operations=tuple(RepairOperation.from_dict(op) for op in d.get("operations", [])),
            conflicts=tuple(d.get("conflicts", ())),
            missing_sources=tuple(d.get("missing_sources", ())),
            unresolved=tuple(d.get("unresolved", ())),
            already_portable_ref_ids=tuple(d.get("already_portable_ref_ids", ())),
        )


@dataclass(frozen=True)
class RepairManifestEntry:
    """One successfully-applied ``RELINK_TEXTURE`` operation's record —
    the ground truth ``repair/revert.py`` reverts against and
    ``repair/verification.py`` re-checks. Only relink operations are
    revertible; ``COPY_FILE`` successes are recorded (``copied_file``)
    for verification but a copied file is never deleted on revert — see
    docs/REPAIR_ENGINE.md, "Revert never deletes copied files"."""

    op_id: str
    map_handle: int | None
    map_class: str | None
    source_property: str | None
    old_path: str
    new_path: str
    copied_file: str | None
    timestamp: str


@dataclass(frozen=True)
class RepairManifest:
    """The persisted record of one applied repair — see
    ``repair/manifest.py`` for load/save and ``repair/revert.py`` for how
    this drives "Revert Last Repair"."""

    repair_id: str
    plan_id: str
    kind: str
    created_at: str
    state: RepairState
    entries: tuple[RepairManifestEntry, ...] = ()
    failed_op_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "repair_id": self.repair_id,
            "plan_id": self.plan_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "state": self.state.value,
            "entries": [e.__dict__ for e in self.entries],
            "failed_op_ids": list(self.failed_op_ids),
        }

    @staticmethod
    def from_dict(d: dict) -> "RepairManifest":
        return RepairManifest(
            repair_id=d["repair_id"],
            plan_id=d["plan_id"],
            kind=d["kind"],
            created_at=d["created_at"],
            state=RepairState(d["state"]),
            entries=tuple(RepairManifestEntry(**e) for e in d.get("entries", [])),
            failed_op_ids=tuple(d.get("failed_op_ids", ())),
        )


@dataclass(frozen=True)
class RepairResult:
    """What ``repair/transaction.py::apply_plan`` returns — the manifest
    plus a short, user-safe summary line (no raw exceptions/tracebacks;
    see ``reports/`` for the same "production-safe text" discipline)."""

    manifest: RepairManifest
    summary: str
    errors: tuple[str, ...] = field(default_factory=tuple)
