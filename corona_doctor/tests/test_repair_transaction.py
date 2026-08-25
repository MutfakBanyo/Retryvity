"""Unit tests for repair/transaction.py::apply_plan — pure, fake
filesystem/scene callables, no real I/O or 3ds Max.
"""

from __future__ import annotations

from corona_doctor.repair.models import OperationKind, RepairState
from corona_doctor.repair.planner import build_make_portable_plan
from corona_doctor.repair.transaction import apply_plan
from corona_doctor.tests.test_repair_planner import _always_exists, _ref


class _FakeFilesystem:
    def __init__(self, *, copy_should_fail_for: set[str] | None = None, directory_should_fail: bool = False) -> None:
        self.copied: list[tuple[str, str]] = []
        self.created_dirs: list[str] = []
        self._copy_should_fail_for = copy_should_fail_for or set()
        self._directory_should_fail = directory_should_fail

    def copy_file(self, source: str, destination: str) -> None:
        if source in self._copy_should_fail_for:
            raise OSError(f"simulated copy failure for {source}")
        self.copied.append((source, destination))

    def create_directory(self, path: str) -> None:
        if self._directory_should_fail:
            raise OSError("simulated permission error")
        self.created_dirs.append(path)


class _FakeSceneAdapter:
    def __init__(self, *, relink_should_fail_for: set[str] | None = None) -> None:
        self.relinked: dict[str, str] = {}
        self._relink_should_fail_for = relink_should_fail_for or set()

    def relink(self, map_handle, source_property, ref_id: str, new_path: str) -> bool:
        if ref_id in self._relink_should_fail_for:
            return False
        self.relinked[ref_id] = new_path
        return True


def _apply(plan, fs: _FakeFilesystem, scene: _FakeSceneAdapter):
    return apply_plan(plan, copy_file=fs.copy_file, create_directory=fs.create_directory, relink=scene.relink)


def test_successful_apply_copies_once_and_relinks_all():
    same_path = r"C:\proj\shared.jpg"
    refs = [_ref(f"ref-{i}", "shared.jpg", same_path) for i in range(3)]
    plan = build_make_portable_plan(refs, r"D:\Project\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    assert result.manifest.state == RepairState.APPLIED
    assert len(fs.copied) == 1
    assert len(scene.relinked) == 3
    assert len(result.manifest.entries) == 3
    assert result.manifest.failed_op_ids == ()


def test_partial_copy_failure_blocks_its_own_relinks_but_not_others():
    ok_ref = _ref("ref-ok", "wood.jpg", r"C:\proj\wood.jpg")
    fail_ref = _ref("ref-fail", "metal.jpg", r"C:\proj\metal.jpg")
    plan = build_make_portable_plan([ok_ref, fail_ref], r"D:\Project\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem(copy_should_fail_for={r"C:\proj\metal.jpg"})
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    assert result.manifest.state == RepairState.PARTIAL
    assert "ref-ok" in scene.relinked
    assert "ref-fail" not in scene.relinked
    assert result.errors  # copy failure recorded, not swallowed


def test_partial_relink_failure_does_not_undo_the_successful_copy():
    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], r"D:\Project\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter(relink_should_fail_for={"ref-1"})
    result = _apply(plan, fs, scene)

    assert len(fs.copied) == 1  # the file really did get copied
    assert result.manifest.state == RepairState.FAILED  # but nothing was successfully relinked
    assert len(result.manifest.failed_op_ids) == 1


def test_read_only_destination_directory_fails_the_whole_group_safely():
    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], r"D:\Readonly\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem(directory_should_fail=True)
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    assert fs.copied == []
    assert scene.relinked == {}
    assert result.manifest.state == RepairState.FAILED


def test_blocked_operations_from_the_plan_are_never_attempted():
    def unknown_exists(_path: str):
        return None

    ref = _ref("ref-1", "locked.jpg", r"C:\proj\locked.jpg")
    plan = build_make_portable_plan([ref], r"D:\Project\Textures", exists_checker=unknown_exists)

    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    assert scene.relinked == {}
    assert result.manifest.entries == ()


def test_missing_source_never_produces_a_manifest_entry():
    ref = _ref("ref-1", "gone.jpg", r"C:\proj\gone.jpg", exists=False)
    plan = build_make_portable_plan([ref], r"D:\Project\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    assert result.manifest.entries == ()
    assert scene.relinked == {}


def test_manifest_records_copied_file_for_each_relink_entry():
    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], r"D:\Project\Textures", exists_checker=_always_exists)

    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    entry = result.manifest.entries[0]
    assert entry.copied_file == fs.copied[0][1]
    assert entry.old_path == r"C:\proj\wood.jpg"


def test_manifest_serialization_round_trip():
    from corona_doctor.repair.models import RepairManifest

    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], r"D:\Project\Textures", exists_checker=_always_exists)
    fs = _FakeFilesystem()
    scene = _FakeSceneAdapter()
    result = _apply(plan, fs, scene)

    round_tripped = RepairManifest.from_dict(result.manifest.to_dict())
    assert round_tripped == result.manifest
