"""The six V0.1 classification outcomes, without 3ds Max."""

from __future__ import annotations

from revision_guard.core.compare import compare_snapshots
from revision_guard.core.models import ChangeType
from revision_guard.tests.factories import CUBE_VERTICES, make_record, make_snapshot, move_vertex

EDITED_CUBE = move_vertex(CUBE_VERTICES, 7, (0.75, 0.0, 0.0))


def _type_for(result, handle: int) -> ChangeType:
    return next(entry.change_type for entry in result.entries if entry.handle == handle)


def test_unchanged():
    before = make_snapshot(make_record(1, "Wall_001"))
    after = make_snapshot(make_record(1, "Wall_001"))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.UNCHANGED


def test_transform_changed():
    before = make_snapshot(make_record(1, "Chair_008"))
    after = make_snapshot(make_record(1, "Chair_008", position=(120.0, 0.0, 0.0)))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.TRANSFORM_CHANGED


def test_rotation_only_is_transform_changed():
    before = make_snapshot(make_record(1))
    after = make_snapshot(make_record(1, rotation=(0.0, 0.0, 0.7071, 0.7071)))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.TRANSFORM_CHANGED


def test_scale_only_is_transform_changed():
    before = make_snapshot(make_record(1))
    after = make_snapshot(make_record(1, scale=(1.0, 1.0, 2.5)))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.TRANSFORM_CHANGED


def test_geometry_changed_with_identical_counts():
    before = make_snapshot(make_record(1, "Wall_014"))
    after = make_snapshot(make_record(1, "Wall_014", vertices=EDITED_CUBE))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.GEOMETRY_CHANGED


def test_added():
    before = make_snapshot(make_record(1))
    after = make_snapshot(make_record(1), make_record(2, "Table_New"))
    result = compare_snapshots(before, after)
    assert _type_for(result, 2) is ChangeType.ADDED
    assert _type_for(result, 1) is ChangeType.UNCHANGED


def test_removed():
    before = make_snapshot(make_record(1), make_record(3, "Column_003"))
    after = make_snapshot(make_record(1))
    result = compare_snapshots(before, after)
    assert _type_for(result, 3) is ChangeType.REMOVED


def test_geometry_and_transform_changed():
    before = make_snapshot(make_record(1, "Slab_002"))
    after = make_snapshot(make_record(1, "Slab_002", position=(50.0, 0.0, 0.0), vertices=EDITED_CUBE))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.GEOMETRY_AND_TRANSFORM_CHANGED


def test_moving_an_object_does_not_look_like_a_geometry_edit():
    """The headline requirement: same geometry + moved object == TRANSFORM_CHANGED."""

    before = make_snapshot(make_record(1))
    after = make_snapshot(make_record(1, position=(1000.0, -250.0, 37.5), rotation=(0.0, 0.0, 0.7071, 0.7071)))
    assert _type_for(compare_snapshots(before, after), 1) is ChangeType.TRANSFORM_CHANGED


def test_counts_and_summary():
    before = make_snapshot(make_record(1), make_record(2), make_record(3, "Gone"))
    after = make_snapshot(
        make_record(1),
        make_record(2, position=(5.0, 0.0, 0.0)),
        make_record(4, "New"),
    )
    result = compare_snapshots(before, after)
    counts = result.counts()

    assert counts[ChangeType.UNCHANGED] == 1
    assert counts[ChangeType.TRANSFORM_CHANGED] == 1
    assert counts[ChangeType.REMOVED] == 1
    assert counts[ChangeType.ADDED] == 1
    assert result.changed_count == 3
    assert "Added=1" in result.summary_line()


def test_removed_nodes_are_not_selectable():
    before = make_snapshot(make_record(1, "Gone"), make_record(2, "Moved"))
    after = make_snapshot(make_record(2, "Moved", position=(9.0, 0.0, 0.0)))
    result = compare_snapshots(before, after)
    assert result.selectable_handles() == [2]


def test_rename_keeps_identity_and_reports_the_current_name():
    before = make_snapshot(make_record(1, "Old_Name"))
    after = make_snapshot(make_record(1, "New_Name"))
    result = compare_snapshots(before, after)
    entry = result.entries[0]
    assert entry.change_type is ChangeType.UNCHANGED
    assert entry.name == "New_Name"


def test_empty_snapshots_compare_cleanly():
    result = compare_snapshots(make_snapshot(), make_snapshot())
    assert result.entries == []
    assert result.changed_count == 0


def test_entries_are_ordered_by_category_then_name():
    before = make_snapshot(make_record(1, "zeta"), make_record(2, "alpha"))
    after = make_snapshot(
        make_record(1, "zeta", position=(5.0, 0.0, 0.0)),
        make_record(2, "alpha"),
        make_record(3, "beta"),
    )
    result = compare_snapshots(before, after)
    assert [entry.change_type for entry in result.entries] == [
        ChangeType.ADDED,
        ChangeType.TRANSFORM_CHANGED,
        ChangeType.UNCHANGED,
    ]


def test_snapshot_is_serialisable_to_primitives():
    import json

    snapshot = make_snapshot(make_record(1, "Wall_001"))
    payload = json.dumps(snapshot.to_dict())
    assert '"Wall_001"' in payload
