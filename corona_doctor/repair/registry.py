"""Registry mapping rule_id -> RepairAction.

Empty in the bootstrap phase. Kept as a real module (rather than deferred
entirely) so future milestones register actions in one place instead of
scattering lookups through the UI or scanners.
"""

from __future__ import annotations

from corona_doctor.repair.base import RepairAction


class RepairRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, RepairAction] = {}

    def register(self, action: RepairAction) -> None:
        self._actions[action.rule_id] = action

    def for_rule(self, rule_id: str) -> RepairAction | None:
        return self._actions.get(rule_id)

    def __len__(self) -> int:
        return len(self._actions)
