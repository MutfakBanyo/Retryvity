"""Interface-contract regression tests between adapter layers.

This exists because of a real host failure: SceneAdapter called
``self._max.get_animatable_handle(...)`` while the *deployed* copy of
MaxAdapter didn't have that method yet (the commit adding it had been
made locally but never pushed — see git history around
"fix: repair unpushed Texture Doctor adapter contract"). No unit test
caught this because every existing test either mocked pymxs (so
``self._max`` was always the real, up-to-date MaxAdapter class in the
same working tree) or never exercised the actual attribute lookup.

These tests statically scan the caller source for every
``self._max.<name>`` / ``self._corona.<name>`` attribute access and
assert the target class actually defines a callable public method with
that name — so a future rename/drift fails CI immediately instead of
only inside a real 3ds Max session.
"""

from __future__ import annotations

import ast
from pathlib import Path

from corona_doctor.adapters.corona_adapter import CoronaAdapter
from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.adapters.scene_adapter import SceneAdapter
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner

_ADAPTERS_DIR = Path(__file__).resolve().parent.parent / "adapters"
_SCANNERS_DIR = Path(__file__).resolve().parent.parent / "scanners"


def _find_receiver_attr_calls(source_path: Path, receiver_attr: str) -> set[str]:
    """Every ``self.<receiver_attr>.<name>`` access in ``source_path``."""

    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        inner = node.value
        if (
            isinstance(inner, ast.Attribute)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "self"
            and inner.attr == receiver_attr
        ):
            names.add(node.attr)
    return names


def _assert_all_present(target_cls: type, names: set[str], context: str) -> None:
    """Verify every name resolves on a real instance.

    Checks an *instance*, not the bare class: some referenced names (e.g.
    SceneAdapter.errors/unknown_map_classes) are plain instance attributes
    set in ``__init__``, not methods, so a class-level ``getattr`` would
    report a false positive missing-attribute failure for those.
    """

    instance = target_cls()
    missing = [name for name in sorted(names) if not hasattr(instance, name)]
    assert not missing, f"{context}: {target_cls.__name__} is missing attribute(s) {missing} referenced via attribute access"


def test_scene_adapter_max_adapter_contract():
    names = _find_receiver_attr_calls(_ADAPTERS_DIR / "scene_adapter.py", "_max")
    assert "get_animatable_handle" in names  # sanity: the test actually found calls
    _assert_all_present(MaxAdapter, names, "scene_adapter.py -> self._max")


def test_environment_adapter_max_adapter_contract():
    names = _find_receiver_attr_calls(_ADAPTERS_DIR / "environment_adapter.py", "_max")
    assert names  # sanity
    _assert_all_present(MaxAdapter, names, "environment_adapter.py -> self._max")


def test_environment_adapter_corona_adapter_contract():
    names = _find_receiver_attr_calls(_ADAPTERS_DIR / "environment_adapter.py", "_corona")
    assert names  # sanity
    _assert_all_present(CoronaAdapter, names, "environment_adapter.py -> self._corona")


def test_texture_doctor_scanner_scene_adapter_contract():
    names = _find_receiver_attr_calls(_SCANNERS_DIR / "texture_doctor_scanner.py", "_scene")
    assert names  # sanity
    _assert_all_present(SceneAdapter, names, "texture_doctor_scanner.py -> self._scene")


def test_scanner_object_graph_constructs_without_attribute_error_outside_max():
    """Structural smoke test: build the real (non-mocked) adapter chain.

    Outside 3ds Max, pymxs is None everywhere, so this can't run a real
    scan — but constructing TextureDoctorScanner -> SceneAdapter ->
    MaxAdapter and confirming every method SceneAdapter will call on
    MaxAdapter actually resolves (without calling it, since that needs
    pymxs) is exactly the class of bug this milestone hit: an
    AttributeError from a missing method, not from missing pymxs.
    """

    scanner = TextureDoctorScanner()
    assert scanner.is_available() is False  # pymxs unavailable outside Max

    scene = scanner._scene  # noqa: SLF001 - intentional white-box structural check
    max_adapter = scene._max  # noqa: SLF001
    assert isinstance(max_adapter, MaxAdapter)

    for method_name in ("get_scene_object_count", "get_animatable_handle"):
        assert callable(getattr(max_adapter, method_name, None)), f"MaxAdapter.{method_name} missing"

    # Every attribute SceneAdapter exposes for the scanner must resolve too.
    for method_name in ("is_available", "get_node_count", "iter_node_facts", "traverse_materials_and_maps"):
        assert callable(getattr(scene, method_name, None)), f"SceneAdapter.{method_name} missing"
