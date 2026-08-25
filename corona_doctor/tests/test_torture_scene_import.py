"""Regression test for devtools/torture_scene.py's import chain and its
safety guard outside 3ds Max (pymxs unavailable). Real fixture
construction cannot run here — see the milestone report's "REAL-HOST
VALIDATION REQUIRED" section.
"""

from __future__ import annotations

import pytest

from corona_doctor.devtools.torture_scene import TortureSceneAbortedError, create_torture_scene, scene_appears_empty


def test_scene_appears_empty_is_false_without_pymxs():
    assert scene_appears_empty() is False


def test_create_torture_scene_aborts_without_pymxs_not_crashes():
    with pytest.raises(TortureSceneAbortedError):
        create_torture_scene()


def test_create_torture_scene_never_silently_no_ops():
    """The abort must be a raised exception a caller can see, never a
    silent no-op that looks like success."""

    with pytest.raises(TortureSceneAbortedError) as excinfo:
        create_torture_scene()
    assert "pymxs" in str(excinfo.value).lower()
