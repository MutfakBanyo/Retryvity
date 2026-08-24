"""Repair engine boundary.

No repair action modifies the scene in this bootstrap phase — only the
interfaces exist. This is a deliberate design invariant: a scanner must
never be able to reach a repair action directly, and a repair action must
never run without an explicit, user-approved trigger going through this
boundary. Future repair actions must also support undo before they can
run against real scene data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from corona_doctor.core.models import Finding, Repairability


@dataclass(frozen=True)
class RepairOutcome:
    success: bool
    message: str


class RepairAction(Protocol):
    """A repair action targets exactly one Finding's ``rule_id``.

    ``tier`` mirrors :class:`~corona_doctor.core.models.Repairability` and
    must match the Finding's own ``repairability`` before ``apply`` may be
    invoked — callers are responsible for enforcing this; the interface
    intentionally does not auto-apply anything.
    """

    rule_id: str
    tier: Repairability

    def can_apply(self, finding: Finding) -> bool:
        ...

    def apply(self, finding: Finding) -> RepairOutcome:
        ...

    def undo(self, finding: Finding) -> RepairOutcome:
        ...
