"""Domain models for diagnostic findings, capabilities and scan results.

These are plain dataclasses with no framework or host dependency so they
can be constructed and tested outside 3ds Max.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """How urgent a finding is."""

    CRITICAL = "critical"
    WARNING = "warning"
    OPTIMIZATION = "optimization"
    HEALTHY = "healthy"
    INFO = "info"


class Repairability(str, Enum):
    """How safe it would be for Corona Doctor to auto-fix a finding.

    No repair actions execute in this bootstrap phase; this classification
    exists so future repair UI can be built against a stable contract.
    """

    SAFE = "safe"
    REVIEW = "review"
    MANUAL = "manual"
    NONE = "none"


class Impact(str, Enum):
    """Coarse magnitude used for performance/memory/render impact fields."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """A single diagnostic result produced by a scanner.

    ``rule_id`` is a stable machine identifier (e.g. ``"env.corona.missing"``)
    used for rule configuration and technical detail panes. It is
    deliberately not meant to be shown prominently in the main UI — see
    ARCHITECTURE.md.
    """

    id: str
    rule_id: str
    category: str
    title: str
    summary: str
    severity: Severity
    confidence: float = 1.0
    performance_impact: Impact = Impact.UNKNOWN
    memory_impact: Impact = Impact.UNKNOWN
    render_impact: Impact = Impact.UNKNOWN
    affected_items: tuple[str, ...] = field(default_factory=tuple)
    details: str = ""
    recommended_action: str = ""
    repairability: Repairability = Repairability.NONE

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0.0, 1.0]")


@dataclass(frozen=True)
class ScanSummary:
    """Aggregate counts derived from a collection of findings."""

    total: int = 0
    critical: int = 0
    warning: int = 0
    optimization: int = 0
    healthy: int = 0
    info: int = 0
    health_score: int = 100

    @staticmethod
    def from_findings(findings: list[Finding]) -> "ScanSummary":
        counts = {severity: 0 for severity in Severity}
        for finding in findings:
            counts[finding.severity] += 1

        score = _compute_health_score(counts)
        return ScanSummary(
            total=len(findings),
            critical=counts[Severity.CRITICAL],
            warning=counts[Severity.WARNING],
            optimization=counts[Severity.OPTIMIZATION],
            healthy=counts[Severity.HEALTHY],
            info=counts[Severity.INFO],
            health_score=score,
        )


def _compute_health_score(counts: dict[Severity, int]) -> int:
    """Deterministic, explainable scoring — not a statistical model.

    Each critical finding costs more than a warning, which costs more than
    an optimization opportunity. The score never goes below zero and is
    capped at 100. This is intentionally simple; a future milestone may
    replace it with weighted rules, but the formula must stay auditable.
    """

    score = 100
    score -= counts[Severity.CRITICAL] * 15
    score -= counts[Severity.WARNING] * 5
    score -= counts[Severity.OPTIMIZATION] * 2
    return max(0, min(100, score))


@dataclass(frozen=True)
class Capability:
    """A single yes/no/unknown capability probe result."""

    key: str
    label: str
    available: bool | None  # True, False, or None for "unknown"

    @property
    def display(self) -> str:
        if self.available is None:
            return "unknown"
        return "yes" if self.available else "no"


@dataclass(frozen=True)
class EnvironmentReport:
    """Structured result of the environment/capability probe.

    Every field defaults to a safe "unknown" value; the environment
    scanner must never raise just because a piece of information could
    not be determined.
    """

    max_version: str = "unknown"
    max_version_raw: str = "unknown"
    max_version_supported: bool | None = None
    python_version: str = "unknown"
    qt_version: str = "unknown"
    pyside_version: str = "unknown"
    corona_detected: bool | None = None
    corona_active: bool | None = None
    corona_renderer_class: str = "unknown"
    corona_renderer_string: str = "unknown"
    corona_version: str = "unknown"
    corona_confidence: str = "unknown"
    current_renderer: str = "unknown"
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def capability(self, key: str) -> Capability | None:
        for cap in self.capabilities:
            if cap.key == key:
                return cap
        return None


@dataclass(frozen=True)
class ScanResult:
    """The complete output of a scanner run: findings plus a summary."""

    scanner_id: str
    findings: tuple[Finding, ...]
    summary: ScanSummary
    metadata: dict[str, Any] = field(default_factory=dict)
