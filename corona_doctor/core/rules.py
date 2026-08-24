"""Rule engine primitives.

A "rule" is a declarative unit of diagnostic logic: given some input data
(gathered by a scanner/adapter) it decides whether a Finding should be
produced. The rule engine here is intentionally minimal — no DSL, no
dynamic code loading — because production rules are a future milestone
(see rules/loader.py). This module only defines the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from corona_doctor.core.models import Finding


@dataclass(frozen=True)
class RuleDefinition:
    """Static metadata describing a rule, independent of its evaluation."""

    id: str
    category: str
    title: str
    description: str
    enabled: bool = True


class Rule(Protocol):
    """A rule evaluates a context and optionally returns a Finding.

    ``context`` is a plain dict assembled by the scanner from adapter
    output. Rules must never reach into pymxs/qtmax themselves — that
    keeps rules unit-testable without 3ds Max.
    """

    definition: RuleDefinition

    def evaluate(self, context: dict[str, Any]) -> Finding | None:
        ...


@dataclass
class CallableRule:
    """Adapts a plain function into the Rule protocol."""

    definition: RuleDefinition
    fn: Callable[[dict[str, Any]], Finding | None]

    def evaluate(self, context: dict[str, Any]) -> Finding | None:
        if not self.definition.enabled:
            return None
        return self.fn(context)


class RuleEngine:
    """Holds a collection of rules and evaluates them against a context.

    The engine never accesses the 3ds Max scene directly; it only consumes
    the context dict handed to it by a scanner.
    """

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = list(rules or [])

    def register(self, rule: Rule) -> None:
        self._rules.append(rule)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(self._rules)

    def run(self, context: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self._rules:
            try:
                finding = rule.evaluate(context)
            except Exception as exc:  # noqa: BLE001 - rules must never crash a scan
                findings.append(_rule_failure_finding(rule, exc))
                continue
            if finding is not None:
                findings.append(finding)
        return findings


def _rule_failure_finding(rule: Rule, exc: Exception) -> Finding:
    from corona_doctor.core.models import Impact, Repairability, Severity

    return Finding(
        id=f"{rule.definition.id}.error",
        rule_id=rule.definition.id,
        category=rule.definition.category,
        title=f"Rule failed: {rule.definition.title}",
        summary="This diagnostic rule could not complete safely and was skipped.",
        severity=Severity.INFO,
        confidence=1.0,
        performance_impact=Impact.NONE,
        memory_impact=Impact.NONE,
        render_impact=Impact.NONE,
        details=str(exc),
        recommended_action="",
        repairability=Repairability.NONE,
    )
