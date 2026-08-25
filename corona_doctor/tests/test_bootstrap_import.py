"""Regression test for Corona Doctor's public entry points.

install_corona_doctor.ms / helpers.ms's macroScripts import exactly these
two names via ``python.Execute`` string literals (not a normal Python
import pytest can already catch at collection time) — this is the
regression guard for that path specifically. See item 8/11 of the
real-host UI/integration repair milestone.
"""

from __future__ import annotations


def test_show_corona_doctor_importable():
    from corona_doctor.bootstrap import show_corona_doctor

    assert callable(show_corona_doctor)


def test_show_corona_doctor_about_importable():
    from corona_doctor.bootstrap import show_corona_doctor_about

    assert callable(show_corona_doctor_about)


def test_bootstrap_module_import_string_matches_maxscript_python_execute_calls():
    """The exact strings baked into helpers.ms's `python.Execute "..."`
    calls must match real importable names — a typo here would only ever
    surface as a real-host MAXScript error, never a Python import error."""

    from pathlib import Path

    helpers = (Path(__file__).resolve().parents[2] / "corona_doctor" / "maxscript" / "helpers.ms").read_text(encoding="utf-8")
    assert "from corona_doctor.bootstrap import show_corona_doctor; show_corona_doctor()" in helpers
    assert "from corona_doctor.bootstrap import show_corona_doctor_about; show_corona_doctor_about()" in helpers
