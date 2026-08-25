"""Unit tests for ui/repair_controller.py — real filesystem I/O against
tmp_path (never a real user folder), a fake RepairAdapter (no pymxs).
No Qt import in repair_controller.py, so this runs in any Python env.
"""

from __future__ import annotations

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType
from corona_doctor.repair.models import RepairState
from corona_doctor.ui.repair_controller import RepairController


class _FakeAdapter:
    def __init__(self) -> None:
        self.values: dict[int, str] = {}

    def relink_map_property(self, map_handle, source_property, new_path) -> bool:
        if map_handle is None:
            return False
        self.values[map_handle] = new_path
        return True

    def read_map_property(self, map_handle, source_property):
        return self.values.get(map_handle)


def _ref(ref_id: str, filename: str, path, *, exists=True, map_handle=1) -> ExternalTextureReference:
    info = PathInfo(raw_path=str(path), normalized_path=str(path), comparison_key=str(path).lower(), path_type=PathType.LOCAL, exists=exists)
    return ExternalTextureReference(
        ref_id=ref_id,
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mtl",
        object_names=("Box01",),
        path_info=info,
        filename=filename,
        extension="jpg",
        source_property="filename",
        map_handle=map_handle,
    )


def test_make_portable_end_to_end_real_files(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source_file = src_dir / "wood.jpg"
    source_file.write_bytes(b"fake jpeg bytes")

    dest_dir = tmp_path / "project" / "Textures"
    repairs_dir = tmp_path / "repairs"
    monkeypatch.setattr("corona_doctor.repair.manifest.default_repairs_dir", lambda: repairs_dir)

    adapter = _FakeAdapter()
    controller = RepairController(adapter=adapter)
    ref = _ref("ref-1", "wood.jpg", source_file, map_handle=1)

    plan = controller.plan_make_portable([ref], str(dest_dir))
    result = controller.apply_make_portable(plan)

    assert result.manifest.state == RepairState.APPLIED
    copied_file = dest_dir / "wood.jpg"
    assert copied_file.is_file()
    assert copied_file.read_bytes() == b"fake jpeg bytes"
    assert adapter.values[1] == str(copied_file)


def test_verify_after_apply_confirms_real_file_and_scene_state(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source_file = src_dir / "wood.jpg"
    source_file.write_bytes(b"data")
    dest_dir = tmp_path / "project"
    repairs_dir = tmp_path / "repairs"
    monkeypatch.setattr("corona_doctor.repair.manifest.default_repairs_dir", lambda: repairs_dir)

    adapter = _FakeAdapter()
    controller = RepairController(adapter=adapter)
    ref = _ref("ref-1", "wood.jpg", source_file, map_handle=1)

    plan = controller.plan_make_portable([ref], str(dest_dir))
    result = controller.apply_make_portable(plan)

    state, problems = controller.verify(result.manifest)
    assert state == RepairState.VERIFIED
    assert problems == ()


def test_relink_missing_texture_end_to_end(tmp_path, monkeypatch):
    found_dir = tmp_path / "search_root"
    found_dir.mkdir()
    found_file = found_dir / "wood.jpg"
    found_file.write_bytes(b"found it")
    repairs_dir = tmp_path / "repairs"
    monkeypatch.setattr("corona_doctor.repair.manifest.default_repairs_dir", lambda: repairs_dir)

    adapter = _FakeAdapter()
    controller = RepairController(adapter=adapter)

    candidates, classification = controller.find_candidates("wood.jpg", [str(found_dir)])
    assert classification == "single"
    assert candidates[0].path == str(found_file)

    ref = _ref("ref-1", "wood.jpg", tmp_path / "gone.jpg", exists=False, map_handle=1)
    plan = controller.plan_relink(ref, candidates[0].path)
    result = controller.apply_relink(plan)

    assert result.manifest.state == RepairState.APPLIED
    assert adapter.values[1] == str(found_file)


def test_zero_candidates_stay_unresolved(tmp_path):
    controller = RepairController(adapter=_FakeAdapter())
    candidates, classification = controller.find_candidates("wood.jpg", [str(tmp_path)])
    assert candidates == []
    assert classification == "none"


def test_revert_restores_old_path(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source_file = src_dir / "wood.jpg"
    source_file.write_bytes(b"data")
    dest_dir = tmp_path / "project"
    repairs_dir = tmp_path / "repairs"
    monkeypatch.setattr("corona_doctor.repair.manifest.default_repairs_dir", lambda: repairs_dir)

    adapter = _FakeAdapter()
    controller = RepairController(adapter=adapter)
    ref = _ref("ref-1", "wood.jpg", source_file, map_handle=1)

    plan = controller.plan_make_portable([ref], str(dest_dir))
    result = controller.apply_make_portable(plan)
    assert adapter.values[1] != str(source_file)

    revert_plan = controller.plan_revert(result.manifest)
    controller.apply_revert(revert_plan)

    assert adapter.values[1] == str(source_file)


def test_revert_last_manifest_round_trips_through_disk(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source_file = src_dir / "wood.jpg"
    source_file.write_bytes(b"data")
    dest_dir = tmp_path / "project"
    repairs_dir = tmp_path / "repairs"
    monkeypatch.setattr("corona_doctor.repair.manifest.default_repairs_dir", lambda: repairs_dir)

    adapter = _FakeAdapter()
    controller = RepairController(adapter=adapter)
    ref = _ref("ref-1", "wood.jpg", source_file, map_handle=1)
    plan = controller.plan_make_portable([ref], str(dest_dir))
    controller.apply_make_portable(plan)

    last = controller.load_last_manifest()
    assert last is not None
    assert last.state == RepairState.APPLIED


class _FakeMaxAdapter:
    def __init__(self, *, found: int = 0) -> None:
        self.found = found
        self.calls: list[tuple[str, ...]] = []

    def select_nodes_by_name(self, names):
        self.calls.append(tuple(names))
        return self.found


def test_select_objects_delegates_to_max_adapter():
    max_adapter = _FakeMaxAdapter(found=2)
    controller = RepairController(adapter=_FakeAdapter(), max_adapter=max_adapter)

    count = controller.select_objects(["Box01", "Box02"])

    assert count == 2
    assert max_adapter.calls == [("Box01", "Box02")]
