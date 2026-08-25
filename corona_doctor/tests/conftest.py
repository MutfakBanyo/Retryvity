"""Shared pytest fixtures for the whole suite.

Sets ``QT_QPA_PLATFORM=offscreen`` before any test module can import
PySide6/Qt, so real Qt widget tests (see test_main_window_navigation.py)
run headless in CI/dev environments with no display, exactly like the
existing pure-Python tests. Must happen at conftest import time, before
pytest imports any test module.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
