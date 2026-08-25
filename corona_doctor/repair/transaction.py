"""Applies a :class:`RepairPlan` — the only place in ``repair/`` allowed
to actually mutate anything, and even here only via callables the caller
injects. This module has no filesystem or pymxs import of its own: real
callers pass real ``shutil.copy2``/``os.makedirs``/a
``adapters/repair_adapter.py`` method; tests pass fakes. That is what
keeps every failure-handling path (partial copy failure, partial relink
failure, read-only destination, ...) unit-testable without a real
filesystem or 3ds Max — see docs/REPAIR_ENGINE.md, "Why the transaction
executor takes callables".

Failure policy: a failed ``COPY_FILE`` blocks every ``RELINK_TEXTURE`` that
depends on it (relinking to a file that was never actually copied would
silently point the scene at nothing) — those relinks are marked failed
without being attempted, not silently skipped. Other, independent unique
sources in the same plan continue normally. See
docs/REPAIR_ENGINE.md, "Partial failure semantics".
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from corona_doctor.repair.models import (
    OperationKind,
    RepairManifest,
    RepairManifestEntry,
    RepairPlan,
    RepairResult,
    RepairState,
    ValidationState,
)

CopyFileFn = Callable[[str, str], None]  # (source, destination) -> raises on failure
CreateDirectoryFn = Callable[[str], None]  # (path) -> raises on failure
RelinkFn = Callable[[int | None, str | None, str, str], bool]  # (map_handle, source_property, ref_id, new_path) -> success


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def apply_plan(
    plan: RepairPlan,
    *,
    copy_file: CopyFileFn,
    create_directory: CreateDirectoryFn,
    relink: RelinkFn,
) -> RepairResult:
    """Apply every ``READY`` operation in ``plan``. Never called during
    preview — only after explicit user approval (see
    docs/REPAIR_ENGINE.md, "No mutation during proposal/preview")."""

    repair_id = f"repair-{uuid.uuid4().hex[:12]}"
    entries: list[RepairManifestEntry] = []
    failed_op_ids: list[str] = []
    errors: list[str] = []
    failed_sources: set[str] = set()

    for op in plan.operations:
        if op.validation_state == ValidationState.BLOCKED:
            failed_op_ids.append(op.op_id)
            continue

        if op.kind == OperationKind.CREATE_DIRECTORY:
            try:
                create_directory(op.destination or "")
            except Exception as exc:  # noqa: BLE001 - must never crash the whole apply
                failed_op_ids.append(op.op_id)
                errors.append(f"could not create destination directory: {exc}")
                # A directory failure blocks every copy that would write into it.
                failed_sources.add("__directory__")
            continue

        if op.kind == OperationKind.COPY_FILE:
            if "__directory__" in failed_sources:
                failed_op_ids.append(op.op_id)
                failed_sources.add(op.source or "")
                continue
            try:
                copy_file(op.source or "", op.destination or "")
            except Exception as exc:  # noqa: BLE001
                failed_op_ids.append(op.op_id)
                errors.append(f"copy failed for {op.source}: {exc}")
                failed_sources.add(op.source or "")
            continue

        if op.kind == OperationKind.RELINK_TEXTURE:
            if op.source in failed_sources:
                failed_op_ids.append(op.op_id)
                continue
            try:
                ok = relink(op.map_handle, op.source_property, op.map_ref_id or "", op.new_value or "")
            except Exception as exc:  # noqa: BLE001
                ok = False
                errors.append(f"relink failed for {op.map_ref_id}: {exc}")
            if not ok:
                failed_op_ids.append(op.op_id)
                continue
            entries.append(
                RepairManifestEntry(
                    op_id=op.op_id,
                    map_handle=op.map_handle,
                    map_class=op.map_class,
                    source_property=op.source_property,
                    old_path=op.old_value or "",
                    new_path=op.new_value or "",
                    copied_file=_matching_copy_destination(plan, op),
                    timestamp=_now_iso(),
                )
            )
            continue

        # UPDATE_PATH (used by revert.py) is handled the same as RELINK_TEXTURE.
        if op.kind == OperationKind.UPDATE_PATH:
            try:
                ok = relink(op.map_handle, op.source_property, op.map_ref_id or "", op.new_value or "")
            except Exception as exc:  # noqa: BLE001
                ok = False
                errors.append(f"path update failed for {op.map_ref_id}: {exc}")
            if not ok:
                failed_op_ids.append(op.op_id)
                continue
            entries.append(
                RepairManifestEntry(
                    op_id=op.op_id,
                    map_handle=op.map_handle,
                    map_class=op.map_class,
                    source_property=op.source_property,
                    old_path=op.old_value or "",
                    new_path=op.new_value or "",
                    copied_file=None,
                    timestamp=_now_iso(),
                )
            )

    ready_count = len(plan.ready_operations)
    if ready_count == 0:
        state = RepairState.FAILED if plan.operations else RepairState.APPLIED
    elif not failed_op_ids and not errors:
        state = RepairState.APPLIED
    elif len(entries) == 0:
        state = RepairState.FAILED
    else:
        state = RepairState.PARTIAL

    manifest = RepairManifest(
        repair_id=repair_id,
        plan_id=plan.plan_id,
        kind=plan.kind,
        created_at=_now_iso(),
        state=state,
        entries=tuple(entries),
        failed_op_ids=tuple(failed_op_ids),
    )
    summary = (
        f"{len(entries)} operation(s) applied, {len(failed_op_ids)} failed/blocked."
        if failed_op_ids
        else f"{len(entries)} operation(s) applied."
    )
    return RepairResult(manifest=manifest, summary=summary, errors=tuple(errors))


def _matching_copy_destination(plan: RepairPlan, relink_op) -> str | None:
    for op in plan.operations:
        if op.kind == OperationKind.COPY_FILE and op.source == relink_op.source:
            return op.destination
    return None
