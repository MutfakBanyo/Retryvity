"""Revert Last Repair — builds and previews a plan that undoes a
manifest's path mutations. Never deletes a copied file (see
``repair/models.py::RepairManifestEntry`` docstring): reverting "Make
Project Portable" restores the old scene paths but leaves the copies in
the project asset directory in place, since Corona Doctor cannot prove
deleting them wouldn't destroy something else that now depends on them.

If the scene no longer matches the manifest (a property was changed by
something else since the repair), that entry is marked BLOCKED for
review rather than force-reverted — see docs/REPAIR_ENGINE.md, "Revert
conflict handling".
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from corona_doctor.repair.models import OperationKind, RepairManifest, RepairOperation, RepairPlan, ValidationState

ReadCurrentValueFn = Callable[[int | None, str | None, str], str | None]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_revert_plan(manifest: RepairManifest, *, read_current_value: ReadCurrentValueFn) -> RepairPlan:
    """Side-effect-free — only reads current scene values to detect
    conflicts, never writes. See ``repair/transaction.py::apply_plan``
    for the step that actually applies this plan."""

    operations: list[RepairOperation] = []
    unresolved: list[str] = []

    for entry in manifest.entries:
        current = read_current_value(entry.map_handle, entry.source_property, entry.op_id)
        if current != entry.new_path:
            unresolved.append(
                f"{entry.op_id}: scene now reads {current!r}, not the repair's {entry.new_path!r} - skipped, needs manual review"
            )
            operations.append(
                RepairOperation(
                    op_id=f"revert-{entry.op_id}",
                    kind=OperationKind.UPDATE_PATH,
                    reason="Revert to pre-repair path.",
                    map_handle=entry.map_handle,
                    map_class=entry.map_class,
                    source_property=entry.source_property,
                    old_value=entry.new_path,
                    new_value=entry.old_path,
                    map_ref_id=entry.op_id,
                    validation_state=ValidationState.BLOCKED,
                    blocked_reason="scene state no longer matches the repair manifest",
                )
            )
            continue

        operations.append(
            RepairOperation(
                op_id=f"revert-{entry.op_id}",
                kind=OperationKind.UPDATE_PATH,
                reason="Revert to pre-repair path.",
                map_handle=entry.map_handle,
                map_class=entry.map_class,
                source_property=entry.source_property,
                old_value=entry.new_path,
                new_value=entry.old_path,
                map_ref_id=entry.op_id,
            )
        )

    return RepairPlan(
        plan_id=f"plan-{uuid.uuid4().hex[:12]}",
        kind="revert_repair",
        created_at=_now_iso(),
        operations=tuple(operations),
        unresolved=tuple(unresolved),
    )
