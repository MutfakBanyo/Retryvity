"""Post-repair verification — "a repair is not successful just because no
exception was thrown" (docs/REPAIR_ENGINE.md, "Verify after fix").

Two checks, both required for :data:`~corona_doctor.repair.models.RepairState.VERIFIED`:

1. Every manifest entry's scene property still reads back the new value
   (proves the relink actually stuck, not just that the call returned
   True).
2. Every copied file genuinely exists at its destination.

Pure — every filesystem/scene read is injected, same discipline as
``repair/transaction.py``.
"""

from __future__ import annotations

from typing import Callable

from corona_doctor.repair.models import RepairManifest, RepairState

ReadCurrentValueFn = Callable[[int | None, str | None, str], str | None]  # (map_handle, source_property, ref_id) -> current value
ExistsFn = Callable[[str], bool | None]


def verify_repair(
    manifest: RepairManifest,
    *,
    read_current_value: ReadCurrentValueFn,
    exists_checker: ExistsFn,
) -> tuple[RepairState, tuple[str, ...]]:
    """Returns ``(new_state, problems)``. ``new_state`` is only ever
    :data:`RepairState.VERIFIED` (everything checked out) or
    :data:`RepairState.PARTIAL`/:data:`RepairState.FAILED` (carried over
    from the manifest's own state if verification finds a problem) —
    never silently upgrades a manifest that was already ``FAILED``."""

    if manifest.state not in (RepairState.APPLIED, RepairState.PARTIAL):
        return manifest.state, ()

    problems: list[str] = []
    for entry in manifest.entries:
        current = read_current_value(entry.map_handle, entry.source_property, entry.op_id)
        if current != entry.new_path:
            problems.append(f"{entry.op_id}: scene property reads {current!r}, expected {entry.new_path!r}")
            continue
        if entry.copied_file is not None:
            exists = exists_checker(entry.copied_file)
            if exists is not True:
                problems.append(f"{entry.op_id}: copied file not found at {entry.copied_file!r}")

    if not problems:
        return RepairState.VERIFIED, ()

    new_state = RepairState.PARTIAL if len(problems) < len(manifest.entries) else RepairState.FAILED
    return new_state, tuple(problems)
