"""Regression test for the devtools runtime probe's import chain.

runtime_probe.py imports classify_corona_symbol/classify_chaos_symbol
from corona_adapter.py — this module-level import is the exact chain
that broke once (ImportError: cannot import name 'classify_chaos_symbol').
A plain unit test that only calls run_runtime_probe() would not catch a
broken import by itself, because pytest's collection already performs
the import before any test body runs — so the import statement above is
the actual regression guard; the test body just proves the function is
callable end-to-end outside 3ds Max.
"""

from __future__ import annotations

from corona_doctor.devtools.runtime_probe import run_runtime_probe


def test_run_runtime_probe_importable_and_callable_outside_max():
    report = run_runtime_probe(write_json=False)
    assert report["corona"]["confidence"] == "unknown"
    assert report["corona"]["installed"] is None
