"""Capability registry: the single place future code asks "can I do X?".

Instead of scattering ``hasattr`` checks or hardcoded Corona property
assumptions across scanners and rules, everything queries this registry.
It is built once from an :class:`EnvironmentReport` and handed down.
"""

from __future__ import annotations

from dataclasses import dataclass

from corona_doctor.core.models import Capability, EnvironmentReport


@dataclass(frozen=True)
class CapabilityRegistry:
    """Read-only view over the capability probe results.

    ``supports(key)`` returns ``True``/``False`` when known, or ``None``
    when the capability could not be determined — callers must treat
    ``None`` as "do not assume this exists" rather than as "yes" or "no".
    """

    _capabilities: dict[str, Capability]

    @staticmethod
    def from_report(report: EnvironmentReport) -> "CapabilityRegistry":
        return CapabilityRegistry({cap.key: cap for cap in report.capabilities})

    def supports(self, key: str) -> bool | None:
        cap = self._capabilities.get(key)
        if cap is None:
            return None
        return cap.available

    def require(self, key: str) -> bool:
        """Strict variant: unknown is treated as unsupported.

        Use this only where a rule truly cannot proceed under uncertainty;
        prefer ``supports`` plus an explicit "skipped: unknown" outcome
        wherever a graceful degradation is possible.
        """

        return self.supports(key) is True

    def all(self) -> tuple[Capability, ...]:
        return tuple(self._capabilities.values())
