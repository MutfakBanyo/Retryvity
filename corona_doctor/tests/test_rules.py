"""Unit tests for the rule engine. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.core.models import Severity
from corona_doctor.core.rules import CallableRule, RuleDefinition, RuleEngine


def _make_rule(rule_id: str, fn, enabled: bool = True) -> CallableRule:
    return CallableRule(
        definition=RuleDefinition(id=rule_id, category="Test", title=rule_id, description="", enabled=enabled),
        fn=fn,
    )


def test_rule_engine_runs_matching_rule():
    from corona_doctor.core.models import Finding

    def fn(ctx):
        if ctx.get("trigger"):
            return Finding(id="f1", rule_id="r1", category="Test", title="t", summary="s", severity=Severity.WARNING)
        return None

    engine = RuleEngine([_make_rule("r1", fn)])
    findings = engine.run({"trigger": True})
    assert len(findings) == 1
    assert findings[0].rule_id == "r1"


def test_rule_engine_skips_non_matching_rule():
    engine = RuleEngine([_make_rule("r1", lambda ctx: None)])
    assert engine.run({}) == []


def test_disabled_rule_never_evaluates():
    calls = []

    def fn(ctx):
        calls.append(1)
        return None

    engine = RuleEngine([_make_rule("r1", fn, enabled=False)])
    engine.run({})
    assert calls == []


def test_rule_exception_becomes_info_finding_not_a_crash():
    def broken(ctx):
        raise RuntimeError("boom")

    engine = RuleEngine([_make_rule("r1", broken)])
    findings = engine.run({})
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert "boom" in findings[0].details
