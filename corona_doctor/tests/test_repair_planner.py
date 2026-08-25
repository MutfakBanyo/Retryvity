"""Unit tests for repair/planner.py — pure, no filesystem/3ds Max/Qt.

Covers PART M's planner-facing requirements: RepairPlan is side-effect
free, copy-once/relink-many, missing source handling, destination
collision, same filename/different source, Unicode paths, spaces in
paths, long paths, inaccessible source, relink candidate ranking
(deterministic, exact/multiple/zero), unsupported map property is simply
carried through (planner never inspects/validates map class support —
that is the adapter's job at apply time).
"""

from __future__ import annotations

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType
from corona_doctor.repair.models import OperationKind, ValidationState
from corona_doctor.repair.planner import (
    build_make_portable_plan,
    build_relink_plan,
    classify_candidates,
    find_relink_candidates,
)

_DEST = r"D:\Project\Textures"


def _path_info(raw: str, path_type: PathType = PathType.LOCAL, exists: bool | None = True) -> PathInfo:
    return PathInfo(raw_path=raw, normalized_path=raw, comparison_key=raw.lower(), path_type=path_type, exists=exists)


def _ref(ref_id: str, filename: str, path: str, *, exists: bool | None = True, path_type: PathType = PathType.LOCAL) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id=ref_id,
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mat_A",
        object_names=("Box01",),
        path_info=_path_info(path, path_type=path_type, exists=exists),
        filename=filename,
        extension=filename.rsplit(".", 1)[-1].lower(),
        source_property="filename",
    )


def _always_exists(_path: str) -> bool | None:
    return True


# -- make-portable planning ---------------------------------------------------


def test_plan_is_side_effect_free():
    """Building a plan must not touch the real filesystem - exists_checker
    is the ONLY filesystem contact, and it's fully injected."""

    calls = []

    def tracking_exists(path: str) -> bool | None:
        calls.append(path)
        return True

    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=tracking_exists)

    assert calls == [r"C:\proj\wood.jpg"]
    assert plan.plan_id
    assert plan.kind == "make_project_portable"


def test_copy_once_relink_many():
    same_path = r"C:\proj\shared.jpg"
    refs = [_ref(f"ref-{i}", "shared.jpg", same_path) for i in range(7)]
    plan = build_make_portable_plan(refs, _DEST, exists_checker=_always_exists)

    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    relinks = [op for op in plan.operations if op.kind == OperationKind.RELINK_TEXTURE]
    assert len(copies) == 1
    assert len(relinks) == 7
    assert {op.map_ref_id for op in relinks} == {f"ref-{i}" for i in range(7)}
    assert all(op.destination == copies[0].destination for op in relinks)


def test_missing_source_is_never_touched():
    ref = _ref("ref-1", "gone.jpg", r"C:\proj\gone.jpg", exists=False)
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    assert r"C:\proj\gone.jpg" in plan.missing_sources
    assert not any(op.kind in (OperationKind.COPY_FILE, OperationKind.RELINK_TEXTURE) for op in plan.operations)


def test_destination_collision_same_filename_different_source_gets_renamed_not_overwritten():
    ref_a = _ref("ref-a", "diffuse.jpg", r"C:\Assets\Wood\diffuse.jpg")
    ref_b = _ref("ref-b", "diffuse.jpg", r"D:\Downloads\Chair\diffuse.jpg")
    plan = build_make_portable_plan([ref_a, ref_b], _DEST, exists_checker=_always_exists)

    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    assert len(copies) == 2
    destinations = {op.destination for op in copies}
    assert len(destinations) == 2, "different sources must never share a destination filename"
    assert plan.conflicts, "a collision must be recorded, not silently resolved"


def test_same_source_referenced_twice_is_not_a_collision():
    """Two ExternalTextureReference entries with the SAME comparison_key
    (the normal reuse case) must not be treated as a naming conflict."""

    same_path = r"C:\proj\wood.jpg"
    ref_a = _ref("ref-a", "wood.jpg", same_path)
    ref_b = _ref("ref-b", "wood.jpg", same_path)
    plan = build_make_portable_plan([ref_a, ref_b], _DEST, exists_checker=_always_exists)

    assert plan.conflicts == ()
    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    assert len(copies) == 1


def test_already_portable_asset_is_skipped():
    ref = _ref("ref-1", "wood.jpg", r"D:\Project\Textures\wood.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    assert "ref-1" in plan.already_portable_ref_ids
    assert not any(op.kind == OperationKind.COPY_FILE for op in plan.operations)


def test_inaccessible_source_is_blocked_for_review_not_silently_dropped():
    def unknown_exists(_path: str) -> bool | None:
        return None  # simulates a permission error / unresolvable stat

    ref = _ref("ref-1", "locked.jpg", r"C:\proj\locked.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=unknown_exists)

    assert r"C:\proj\locked.jpg" in plan.unresolved
    relinks = [op for op in plan.operations if op.kind == OperationKind.RELINK_TEXTURE]
    assert len(relinks) == 1
    assert relinks[0].validation_state == ValidationState.BLOCKED
    assert relinks[0] not in plan.ready_operations


def test_unicode_path_is_handled():
    ref = _ref("ref-1", "tekstür_日本語.jpg", r"C:\proj\çalışma\tekstür_日本語.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    assert len(copies) == 1
    assert "tekstür_日本語" in copies[0].destination


def test_path_with_spaces_is_handled():
    ref = _ref("ref-1", "wood plank 01.jpg", r"C:\proj\my textures\wood plank 01.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    assert len(copies) == 1
    assert "wood plank 01.jpg" in copies[0].destination


def test_very_long_path_is_handled():
    long_dir = "\\".join(["deeply_nested_folder"] * 30)
    long_path = f"C:\\proj\\{long_dir}\\texture.jpg"
    ref = _ref("ref-1", "texture.jpg", long_path)
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    copies = [op for op in plan.operations if op.kind == OperationKind.COPY_FILE]
    assert len(copies) == 1
    assert copies[0].source == long_path


def test_plan_is_serializable_round_trip():
    from corona_doctor.repair.models import RepairPlan

    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg")
    plan = build_make_portable_plan([ref], _DEST, exists_checker=_always_exists)

    round_tripped = RepairPlan.from_dict(plan.to_dict())
    assert round_tripped == plan


def test_empty_references_produces_a_trivial_plan():
    plan = build_make_portable_plan([], _DEST, exists_checker=_always_exists)
    assert plan.ready_operations  # just the CREATE_DIRECTORY op
    assert plan.missing_sources == ()
    assert plan.conflicts == ()


# -- relink candidate ranking --------------------------------------------------


def test_zero_candidates_when_nothing_matches():
    candidates = find_relink_candidates("wood.jpg", [r"C:\assets\metal.jpg", r"C:\assets\stone.jpg"])
    assert candidates == []
    assert classify_candidates(candidates) == "none"


def test_single_exact_candidate():
    candidates = find_relink_candidates("wood.jpg", [r"C:\assets\wood.jpg"])
    assert len(candidates) == 1
    assert classify_candidates(candidates) == "single"


def test_multiple_plausible_candidates_are_not_auto_resolved():
    candidates = find_relink_candidates("wood.jpg", [r"C:\assets\a\wood.jpg", r"C:\assets\b\wood.jpg"])
    assert len(candidates) == 2
    assert classify_candidates(candidates) == "multiple"


def test_candidate_matching_is_case_insensitive_on_filename():
    candidates = find_relink_candidates("Wood.JPG", [r"C:\assets\wood.jpg"])
    assert len(candidates) == 1


def test_size_match_breaks_a_tie_in_scoring():
    def size_lookup(path: str) -> int | None:
        return {"C:\\a\\wood.jpg": 1000, "C:\\b\\wood.jpg": 2000}.get(path)

    candidates = find_relink_candidates(
        "wood.jpg",
        ["C:\\a\\wood.jpg", "C:\\b\\wood.jpg"],
        expected_size_bytes=1000,
        size_lookup=size_lookup,
    )
    assert candidates[0].path == "C:\\a\\wood.jpg"
    assert candidates[0].score > candidates[1].score


def test_candidate_ranking_is_deterministic_across_repeated_calls():
    paths = [r"C:\z\wood.jpg", r"C:\a\wood.jpg", r"C:\m\wood.jpg"]
    first = find_relink_candidates("wood.jpg", paths)
    second = find_relink_candidates("wood.jpg", list(reversed(paths)))
    assert [c.path for c in first] == [c.path for c in second]


def test_relink_plan_never_includes_a_copy_operation():
    ref = _ref("ref-1", "wood.jpg", r"C:\proj\wood.jpg", exists=False)
    plan = build_relink_plan(ref, r"D:\Found\wood.jpg")

    assert not any(op.kind == OperationKind.COPY_FILE for op in plan.operations)
    assert len(plan.operations) == 1
    assert plan.operations[0].new_value == r"D:\Found\wood.jpg"


def test_relink_plan_preserves_unsupported_map_property_for_the_adapter_to_reject():
    """The planner never validates whether source_property is actually
    settable on this map class - that check belongs to
    adapters/repair_adapter.py at apply time (see repair/transaction.py's
    relink callable), so an unsupported map still produces a plan; it
    just won't apply successfully."""

    ref = _ref("ref-1", "weird.jpg", r"C:\proj\weird.jpg", exists=False)
    object.__setattr__(ref, "source_property", None)  # simulates an unsupported map (no resolvable property)
    plan = build_relink_plan(ref, r"D:\Found\weird.jpg")
    assert plan.operations[0].source_property is None
