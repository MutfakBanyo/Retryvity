"""Regression tests for the real-host (3ds Max 2026.2) compatibility repair.

A real scan against a production scene returned:

    Nodes 462, Materials 363, Unique materials 0, Texture refs 0,
    Lights 0, Cameras 0, Corona lights 14, Corona cameras 3

i.e. material identity/traversal silently dropped every material (despite
363 node->material assignments existing), and generic node classification
missed every light/camera even though the Corona-specific classifier found
them fine. These tests build a fake pymxs runtime that reproduces the two
underlying real-host quirks in isolation:

  1. ``rt.getHandleByAnim`` returning ``None`` for some material objects
     (adapters/scene_adapter.py's ``_identity`` fallback must not drop
     them).
  2. ``str(rt.superClassOf(node))`` not matching the plain class-name
     strings the scanner used to compare against, for light/camera nodes
     specifically, while a live Class-object comparison and the host
     ``rt.lights``/``rt.cameras`` collections are still reliable.

See docs/TEXTURE_DOCTOR.md, "Node/material classification" and "Identity".
"""

from __future__ import annotations

import corona_doctor.adapters.max_adapter as max_adapter_module
import corona_doctor.adapters.scene_adapter as scene_adapter_module
from corona_doctor.adapters.scene_adapter import SceneAdapter
from corona_doctor.core.texture_models import SceneInventory
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner, _check_invariants


class _Opaque:
    """Stand-in for a live pymxs Class object whose str() doesn't match
    the plain name the scanner used to guess (e.g. "Light"/"Camera")."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __str__(self) -> str:  # deliberately NOT "Light"/"Camera"
        return f"<Superclass:{self.label}>"

    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)


class _FakeNode:
    def __init__(self, name, handle, superclass, class_name, material=None):
        self.name = name
        self.material = material
        self.isHidden = False
        self.isFrozen = False
        self.isGroupHead = False
        self._handle = handle
        self._superclass = superclass
        self._class_name = class_name


class _FakeMaterial:
    """A material whose AnimHandle is unavailable (``handle=None``)."""

    def __init__(self, name, handle=None, class_name="CoronaPhysicalMtl", sub_texmaps=None):
        self.name = name
        self._handle = handle
        self._superclass = "Material"
        self._class_name = class_name
        self.sub_mtls: list = []
        self.sub_texmaps = sub_texmaps or []


class _FakeTexmap:
    def __init__(self, name, handle, class_name="CoronaBitmap", filename=None):
        self.name = name
        self._handle = handle
        self._superclass = "TextureMap"
        self._class_name = class_name
        self.filename = filename
        self.sub_texmaps: list = []


class _FakeObjects(list):
    @property
    def count(self):
        return len(self)


class _FakeRuntime:
    """No ``Light``/``Camera``/``GeometryClass``/... attributes exist on
    this runtime — simulates a host where Class-object equality is
    unavailable, forcing the classifier down to host-collection
    membership (the most reliable signal on the real host, per
    docs/TEXTURE_DOCTOR.md)."""

    def __init__(self, objects, lights=(), cameras=(), geometry=(), helpers=(), shapes=()):
        self.objects = _FakeObjects(objects)
        self.lights = list(lights)
        self.cameras = list(cameras)
        self.geometry = list(geometry)
        self.helpers = list(helpers)
        self.shapes = list(shapes)

    def superClassOf(self, obj):
        return obj._superclass

    def classOf(self, obj):
        return obj._class_name

    def getHandleByAnim(self, obj):
        return obj._handle

    def getNumSubMtls(self, obj):
        return len(getattr(obj, "sub_mtls", []))

    def getSubMtl(self, obj, index):
        return obj.sub_mtls[index - 1]

    def getNumSubTexmaps(self, obj):
        return len(getattr(obj, "sub_texmaps", []))

    def getSubTexmap(self, obj, index):
        return obj.sub_texmaps[index - 1]

    def isProperty(self, obj, name):
        return getattr(obj, name, None) is not None

    def getPropNames(self, obj):
        return ["name"]

    def maxversion(self):
        return [28000, 68, 0, 28, 2, 0, 20659, 2026, ".2"]


class _FakePymxs:
    def __init__(self, rt):
        self.runtime = rt


def _patch(monkeypatch, rt):
    fake = _FakePymxs(rt)
    monkeypatch.setattr(scene_adapter_module, "pymxs", fake)
    monkeypatch.setattr(max_adapter_module, "pymxs", fake)
    return fake


# -- Material identity fallback -------------------------------------------


def test_animhandle_unavailable_material_still_traversed(monkeypatch):
    """A material with no AnimHandle must not disappear from the scan."""

    mat = _FakeMaterial("HandlelessMat", handle=None)
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)
    rt = _FakeRuntime([node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.unique_material_count == 1
    assert scanner.inventory.nodes_with_material_count == 1
    assert scanner.facts.diagnostics.materials_using_fallback_identity == 1
    assert scanner.facts.compatibility_warnings == ()


def test_multiple_references_to_same_handleless_wrapper_deduplicated(monkeypatch):
    """Two nodes sharing the *same* Python material object dedup to one."""

    mat = _FakeMaterial("SharedHandlelessMat", handle=None)
    node1 = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)
    node2 = _FakeNode("Box02", 2, "GeometryClass", "Box", material=mat)
    rt = _FakeRuntime([node1, node2])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.unique_material_count == 1
    assert scanner.inventory.nodes_with_material_count == 2


def test_distinct_handleless_materials_remain_distinct(monkeypatch):
    """Two different handleless material objects must not collapse into one."""

    mat_a = _FakeMaterial("MatA", handle=None)
    mat_b = _FakeMaterial("MatB", handle=None)
    node1 = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat_a)
    node2 = _FakeNode("Box02", 2, "GeometryClass", "Box", material=mat_b)
    rt = _FakeRuntime([node1, node2])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.unique_material_count == 2


def test_material_with_nested_texmap_survives_handleless_material(monkeypatch):
    bitmap = _FakeTexmap("WoodMap", handle=10, filename=r"C:\proj\wood.jpg")
    mat = _FakeMaterial("MatWithMap", handle=None, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)
    rt = _FakeRuntime([node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.unique_material_count == 1
    assert scanner.inventory.map_reference_count == 1
    assert scanner.facts.diagnostics.external_file_backed_maps_recognized == 1


# -- Node classification: host collections over guessed strings -----------


def test_corona_light_classified_via_host_collection(monkeypatch):
    light_node = _FakeNode("Sun01", 50, _Opaque("Light"), "CoronaLight")
    rt = _FakeRuntime([light_node], lights=[light_node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.light_count == 1
    assert scanner.inventory.corona_light_count == 1
    assert scanner.facts.compatibility_warnings == ()


def test_corona_camera_classified_via_host_collection(monkeypatch):
    cam_node = _FakeNode("Cam01", 51, _Opaque("Camera"), "CoronaCam")
    rt = _FakeRuntime([cam_node], cameras=[cam_node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.camera_count == 1
    assert scanner.inventory.corona_camera_count == 1
    assert scanner.facts.compatibility_warnings == ()


def test_target_object_not_counted_as_geometry(monkeypatch):
    """A Target node sitting in rt.geometry must not inflate geometry_count."""

    target_node = _FakeNode("Sun01.Target", 52, "GeometryClass", "Target")
    box_node = _FakeNode("Box01", 53, "GeometryClass", "Box")
    rt = _FakeRuntime([target_node, box_node], geometry=[target_node, box_node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.inventory.geometry_count == 1
    assert scanner.inventory.helper_count == 1


def test_generic_classification_missing_produces_no_false_warning_when_correct(monkeypatch):
    """A fully-correct scan (host collections match Corona counts) reports no warnings."""

    light_node = _FakeNode("Sun01", 50, _Opaque("Light"), "CoronaLight")
    cam_node = _FakeNode("Cam01", 51, _Opaque("Camera"), "CoronaCam")
    rt = _FakeRuntime([light_node, cam_node], lights=[light_node], cameras=[cam_node])
    _patch(monkeypatch, rt)

    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())

    assert scanner.facts.compatibility_warnings == ()


# -- Invariant checks (pure function, no pymxs needed) ---------------------


def test_invariant_warns_on_materials_assigned_but_zero_unique():
    inv = SceneInventory(nodes_with_material_count=363, unique_material_count=0)
    warnings = _check_invariants(inv)
    assert any("363" in w and "0 unique materials" in w for w in warnings)


def test_invariant_warns_on_corona_light_exceeding_generic_light():
    inv = SceneInventory(corona_light_count=14, light_count=0)
    warnings = _check_invariants(inv)
    assert any("corona_light_count" in w for w in warnings)


def test_invariant_warns_on_corona_camera_exceeding_generic_camera():
    inv = SceneInventory(corona_camera_count=3, camera_count=0)
    warnings = _check_invariants(inv)
    assert any("corona_camera_count" in w for w in warnings)


def test_invariant_silent_when_consistent():
    inv = SceneInventory(
        nodes_with_material_count=3,
        unique_material_count=2,
        corona_light_count=1,
        light_count=1,
        corona_camera_count=1,
        camera_count=1,
    )
    assert _check_invariants(inv) == []
