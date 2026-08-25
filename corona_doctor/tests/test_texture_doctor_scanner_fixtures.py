"""End-to-end TextureDoctorScanner test against a fake pymxs scene.

Exercises the full pipeline (scene_adapter -> scanner -> rules ->
Findings) the way it will run inside 3ds Max, without needing a real
host. The fixture scene is deliberately built to cover:

  - a Multi/Sub material instanced twice under one node (dedup by handle,
    not by Python id() — see adapters/max_adapter.py's
    get_animatable_handle docstring)
  - a self-referential ("cyclic") map graph, proving traversal doesn't
    infinite-loop
  - an unsupported/custom map class with no resolvable file property
  - a missing texture file
  - two distinct map nodes pointing at the same underlying file (the
    TXT-002 duplicate-reference scenario)
"""

from __future__ import annotations

import corona_doctor.adapters.max_adapter as max_adapter_module
import corona_doctor.adapters.path_utils as path_utils_module
import corona_doctor.adapters.scene_adapter as scene_adapter_module
from corona_doctor.adapters.scene_adapter import SceneAdapter
from corona_doctor.core.models import Severity
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner

_WOOD_PATH = r"C:\proj\wood.jpg"
_MISSING_PATH = r"C:\proj\missing_texture_xyz.png"


class _FakeNode:
    def __init__(self, name, handle, superclass, class_name, material=None, hidden=False, frozen=False, group_head=False):
        self.name = name
        self.material = material
        self.isHidden = hidden
        self.isFrozen = frozen
        self.isGroupHead = group_head
        self._handle = handle
        self._superclass = superclass
        self._class_name = class_name


class _FakeMaterial:
    def __init__(self, name, handle, class_name="Multi/Sub Object", sub_mtls=None, sub_texmaps=None):
        self.name = name
        self._handle = handle
        self._superclass = "Material"
        self._class_name = class_name
        self.sub_mtls = sub_mtls or []
        self.sub_texmaps = sub_texmaps or []


class _FakeTexmap:
    def __init__(self, name, handle, class_name, filename=None, sub_texmaps=None):
        self.name = name
        self._handle = handle
        self._superclass = "TextureMap"
        self._class_name = class_name
        self.filename = filename
        self.sub_texmaps = sub_texmaps or []


class _FakeObjects(list):
    @property
    def count(self):
        return len(self)


class _FakeRuntime:
    def __init__(self, objects):
        self.objects = _FakeObjects(objects)

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

    def maxversion(self):
        return [28000, 68, 0, 28, 2, 0, 20659, 2026, ".2"]


class _FakePymxs:
    def __init__(self, objects):
        self.runtime = _FakeRuntime(objects)


def _build_scene():
    bitmap_wood = _FakeTexmap("WoodMap", 201, "CoronaBitmap", filename=_WOOD_PATH)
    bitmap_missing = _FakeTexmap("MissingMap", 202, "Bitmaptexture", filename=_MISSING_PATH)
    bitmap_dup = _FakeTexmap("DupMap1", 203, "CoronaBitmap", filename=_WOOD_PATH)
    unsupported_map = _FakeTexmap("WeirdMap", 204, "SomeThirdPartyProceduralMap", filename=None)

    cyclic_map = _FakeTexmap("CyclicMap", 205, "CoronaMix", filename=None)
    cyclic_map.sub_texmaps = [cyclic_map]  # self-reference

    shared_sub_mtl = _FakeMaterial("SharedSub", 110, "CoronaPhysicalMtl", sub_texmaps=[bitmap_wood, unsupported_map])
    multi_sub = _FakeMaterial("MultiMat", 100, "Multi/Sub Object", sub_mtls=[shared_sub_mtl, shared_sub_mtl])
    mtl_with_cycle = _FakeMaterial("CyclicOwner", 120, "CoronaLayeredMtl", sub_texmaps=[cyclic_map])
    mtl_missing = _FakeMaterial("MissingOwner", 130, "CoronaPhysicalMtl", sub_texmaps=[bitmap_missing])
    mtl_dup = _FakeMaterial("DupOwner", 140, "CoronaPhysicalMtl", sub_texmaps=[bitmap_dup])

    nodes = [
        _FakeNode("Box01", 1, "GeometryClass", "Box", material=multi_sub),
        _FakeNode("Box02", 2, "GeometryClass", "Box", material=mtl_with_cycle),
        _FakeNode("Box03", 3, "GeometryClass", "Box", material=mtl_missing),
        _FakeNode("Box04", 4, "GeometryClass", "Box", material=mtl_dup),
        _FakeNode("Light01", 5, "Light", "CoronaLight"),
        _FakeNode("Cam01", 6, "Camera", "CoronaCam"),
        _FakeNode("Helper01", 7, "Helper", "Point"),
        _FakeNode("HiddenBox", 8, "GeometryClass", "Box", hidden=True),
        _FakeNode("FrozenBox", 9, "GeometryClass", "Box", frozen=True),
        _FakeNode("GroupHead01", 10, "GeometryClass", "Dummy", group_head=True),
    ]
    return nodes


def _patch_pymxs(monkeypatch):
    fake = _FakePymxs(_build_scene())
    monkeypatch.setattr(scene_adapter_module, "pymxs", fake)
    monkeypatch.setattr(max_adapter_module, "pymxs", fake)
    return fake


def _patch_filesystem(monkeypatch):
    exists_map = {_WOOD_PATH.lower(): (True, 2048), _MISSING_PATH.lower(): (False, None)}

    def fake_isfile(path):
        return exists_map.get(str(path).lower(), (False, None))[0]

    def fake_getsize(path):
        return exists_map.get(str(path).lower(), (False, None))[1] or 0

    monkeypatch.setattr(path_utils_module.os.path, "isfile", fake_isfile)
    monkeypatch.setattr(path_utils_module.os.path, "getsize", fake_getsize)


def _run_scan(monkeypatch):
    _patch_pymxs(monkeypatch)
    _patch_filesystem(monkeypatch)
    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    assert scanner.is_available()
    batches = list(scanner.scan())
    return scanner, batches


def test_scan_never_raises_on_cyclic_and_shared_graph(monkeypatch):
    scanner, batches = _run_scan(monkeypatch)
    assert batches  # at least one batch per stage was yielded
    assert scanner.inventory is not None


def test_inventory_node_classification(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    inv = scanner.inventory
    assert inv.total_nodes == 10
    assert inv.geometry_count == 7
    assert inv.light_count == 1
    assert inv.camera_count == 1
    assert inv.helper_count == 1
    assert inv.hidden_count == 1
    assert inv.frozen_count == 1
    assert inv.group_count == 1
    assert inv.corona_light_count == 1
    assert inv.corona_camera_count == 1


def test_shared_submaterial_deduplicated_by_handle_not_by_id(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    inv = scanner.inventory
    # 5 unique materials: MultiMat, SharedSub (visited once despite being
    # referenced twice), CyclicOwner, MissingOwner, DupOwner.
    assert inv.unique_material_count == 5
    # 4 nodes actually have a material assigned (Box01..Box04).
    assert inv.material_count == 4


def test_map_graph_traversal_finds_expected_maps_without_infinite_loop(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    inv = scanner.inventory
    # WoodMap, MissingMap, DupMap1, WeirdMap, CyclicMap = 5 unique Texmap
    # nodes, despite SharedSub being reachable via two sub_mtls slots and
    # CyclicMap referencing itself.
    assert inv.map_reference_count == 5


def test_unsupported_map_class_recorded_not_dropped(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    assert "SomeThirdPartyProceduralMap" in scanner.facts.unknown_map_classes


def test_missing_texture_detected(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    assert scanner.inventory.missing_texture_count == 1
    missing_refs = [r for r in scanner.texture_references if r.path_info.exists is False]
    assert len(missing_refs) == 1
    assert missing_refs[0].filename == "missing_texture_xyz.png"


def test_duplicate_reference_group_detected(monkeypatch):
    scanner, _ = _run_scan(monkeypatch)
    assert scanner.inventory.duplicate_group_count == 1
    wood_refs = [r for r in scanner.texture_references if r.filename == "wood.jpg"]
    assert len(wood_refs) == 2
    assert all(r.reference_count == 2 for r in wood_refs)


def test_findings_include_missing_and_duplicate_rules(monkeypatch):
    scanner, batches = _run_scan(monkeypatch)
    findings_by_rule = {f.rule_id: f for _stage, _c, _t, batch in batches for f in batch}
    assert "TXT-001" in findings_by_rule
    assert findings_by_rule["TXT-001"].severity == Severity.CRITICAL
    assert "TXT-002" in findings_by_rule


def test_cancel_stops_scan_early(monkeypatch):
    _patch_pymxs(monkeypatch)
    _patch_filesystem(monkeypatch)
    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    generator = scanner.scan()
    next(generator)  # first ("nodes", ...) batch
    scanner.cancel()
    remaining = list(generator)
    assert remaining == []
    assert scanner.inventory is None  # scan never reached the final stage
