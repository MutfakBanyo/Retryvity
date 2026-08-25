"""Regression test for the devtools Texture Doctor probe's import chain.

Mirrors test_devtools_import.py's rationale for runtime_probe.py: the
import statements at module load time are the actual regression guard
(pytest's collection performs them before any test body runs) — this
also proves run_texture_probe() is callable end-to-end outside 3ds Max,
where it is expected to raise ScannerUnavailableError (pymxs is
unavailable, so TextureDoctorScanner.is_available() is False) rather
than any other exception (e.g. an ImportError from a broken
reports/texture_report.py wiring).
"""

from __future__ import annotations

import pytest

from corona_doctor.core.diagnostics import ScannerUnavailableError
from corona_doctor.devtools.texture_probe import run_texture_probe


def test_run_texture_probe_importable_and_fails_gracefully_outside_max():
    with pytest.raises(ScannerUnavailableError):
        run_texture_probe(write_json=False)
