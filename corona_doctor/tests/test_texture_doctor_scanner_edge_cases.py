"""Edge-case regression tests for TextureDoctorScanner against a fake pymxs
scene: non-ASCII filenames, spaces in paths, very long paths, inaccessible
filesystem metadata, a map with a filename-like property that isn't
actually file-backed, the production TextureDoctorResult model, and
deterministic result ordering.

Reuses the fake pymxs runtime classes from
test_texture_doctor_scanner_fixtures.py rather than re-defining them.
"""

from __future__ import annotations

import corona_doctor.adapters.max_adapter as max_adapter_module
import corona_doctor.adapters.path_utils as path_utils_module
import corona_doctor.adapters.scene_adapter as scene_adapter_module
from corona_doctor.adapters.scene_adapter import SceneAdapter
from corona_doctor.core.texture_models import TextureDoctorResult
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner
from corona_doctor.tests.test_texture_doctor_scanner_fixtures import (
    _FakeMaterial,
    _FakeNode,
    _FakePymxs,
    _FakeTexmap,
)

_NON_ASCII_PATH = r"C:\proj\tekstür_日本語.jpg"
_SPACES_PATH = r"C:\proj\my textures\wood plank 01.jpg"
_LONG_PATH = "C:\\proj\\" + "\\".join(["deeply_nested_folder"] * 20) + "\\texture.jpg"
_EMPTY_FILENAME_PATH = ""  # a map exposing `.filename` that resolves to an empty string


def _patch(monkeypatch, nodes):
    fake = _FakePymxs(nodes)
    monkeypatch.setattr(scene_adapter_module, "pymxs", fake)
    monkeypatch.setattr(max_adapter_module, "pymxs", fake)
    return fake


def _run(monkeypatch, nodes, isfile=None, getsize=None):
    _patch(monkeypatch, nodes)
    monkeypatch.setattr(path_utils_module.os.path, "isfile", isfile or (lambda p: True))
    monkeypatch.setattr(path_utils_module.os.path, "getsize", getsize or (lambda p: 1024))
    scanner = TextureDoctorScanner(scene_adapter=SceneAdapter())
    list(scanner.scan())
    return scanner


def test_non_ascii_filename_survives_the_full_pipeline(monkeypatch):
    bitmap = _FakeTexmap("NonAsciiMap", 201, "CoronaBitmap", filename=_NON_ASCII_PATH)
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    scanner = _run(monkeypatch, [node])

    assert len(scanner.texture_references) == 1
    ref = scanner.texture_references[0]
    assert "tekstür_日本語" in ref.filename


def test_spaces_in_path_survive_the_full_pipeline(monkeypatch):
    bitmap = _FakeTexmap("SpacesMap", 201, "CoronaBitmap", filename=_SPACES_PATH)
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    scanner = _run(monkeypatch, [node])

    assert len(scanner.texture_references) == 1
    assert scanner.texture_references[0].filename == "wood plank 01.jpg"


def test_very_long_path_does_not_crash_the_scan(monkeypatch):
    bitmap = _FakeTexmap("LongPathMap", 201, "CoronaBitmap", filename=_LONG_PATH)
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    scanner = _run(monkeypatch, [node])

    assert len(scanner.texture_references) == 1
    assert scanner.facts.errors == ()


def test_inaccessible_filesystem_metadata_degrades_to_not_found(monkeypatch):
    """os.path.isfile raising (e.g. PermissionError on a locked network
    share) must degrade to "missing", never crash the scan — see
    adapters/path_utils.py::FilesystemMetadataCache._stat."""

    bitmap = _FakeTexmap("LockedMap", 201, "CoronaBitmap", filename=r"C:\proj\locked.jpg")
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    def raising_isfile(_path):
        raise PermissionError("access denied")

    scanner = _run(monkeypatch, [node], isfile=raising_isfile)

    assert len(scanner.texture_references) == 1
    ref = scanner.texture_references[0]
    assert ref.path_info.exists is False
    assert ref.file_size_bytes is None
    assert scanner.facts.errors == ()


def test_map_with_empty_filename_property_is_not_treated_as_file_backed(monkeypatch):
    """A map class that exposes `.filename` but resolves to an empty
    string must be recorded as unsupported/unknown, not as a bogus
    zero-length texture reference — see
    adapters/scene_adapter.py::_probe_filename."""

    weird_map = _FakeTexmap("EmptyFilenameMap", 201, "CoronaColor", filename=_EMPTY_FILENAME_PATH)
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[weird_map])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    scanner = _run(monkeypatch, [node])

    assert scanner.texture_references == ()
    assert "CoronaColor" in scanner.facts.unknown_map_classes


def test_texture_doctor_result_model_is_populated_after_scan(monkeypatch):
    bitmap = _FakeTexmap("Map", 201, "CoronaBitmap", filename=r"C:\proj\wood.jpg")
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)

    scanner = _run(monkeypatch, [node])

    assert isinstance(scanner.result, TextureDoctorResult)
    assert scanner.result.inventory == scanner.inventory
    assert scanner.result.texture_references == scanner.texture_references
    assert scanner.result.timings.total_ms > 0
    # Formatting/filtering must never trigger a new scene traversal - the
    # result is a plain frozen dataclass snapshot, not a live query.
    assert scanner.result.errors == scanner.facts.errors


def test_result_ordering_is_deterministic_across_repeated_scans(monkeypatch):
    bitmap_a = _FakeTexmap("AMap", 201, "CoronaBitmap", filename=r"C:\proj\a.jpg")
    bitmap_b = _FakeTexmap("BMap", 202, "CoronaBitmap", filename=r"C:\proj\b.jpg")
    mat = _FakeMaterial("Mat", 100, sub_texmaps=[bitmap_a, bitmap_b])
    node = _FakeNode("Box01", 1, "GeometryClass", "Box", material=mat)
    nodes = [node]

    first = _run(monkeypatch, nodes)
    second = _run(monkeypatch, nodes)

    first_names = [r.filename for r in first.result.texture_references]
    second_names = [r.filename for r in second.result.texture_references]
    assert first_names == second_names == ["a.jpg", "b.jpg"]
