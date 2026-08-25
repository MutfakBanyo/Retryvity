"""Unit tests for core/texture_query.py — pure filtering/sorting, no Qt/3ds Max."""

from __future__ import annotations

from corona_doctor.core.models import Finding, Repairability, Severity
from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType, TextureThresholds
from corona_doctor.core.texture_query import (
    TextureFilter,
    TextureSortKey,
    apply_filter,
    filter_by_extension,
    filter_by_map_class,
    filter_by_material,
    filter_by_object,
    filter_local_workstation_paths,
    local_workstation_path_count,
    sort_findings_by_severity,
    sort_references,
)


def _path_info(raw: str, path_type: PathType = PathType.LOCAL, exists: bool | None = True) -> PathInfo:
    return PathInfo(raw_path=raw, normalized_path=raw, comparison_key=raw.lower(), path_type=path_type, exists=exists)


def _ref(
    filename: str,
    *,
    path: str | None = None,
    path_type: PathType = PathType.LOCAL,
    exists: bool | None = True,
    width: int | None = None,
    height: int | None = None,
    size_bytes: int | None = None,
    reference_count: int = 1,
    map_class: str = "CoronaBitmap",
    material_name: str | None = "Mat_A",
    object_names: tuple[str, ...] = ("Box01",),
) -> ExternalTextureReference:
    path = path or f"C:/proj/{filename}"
    return ExternalTextureReference(
        ref_id=f"ref-{filename}",
        map_class=map_class,
        map_name=filename,
        material_name=material_name,
        object_names=object_names,
        path_info=_path_info(path, path_type=path_type, exists=exists),
        filename=filename,
        extension=filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        file_size_bytes=size_bytes,
        width=width,
        height=height,
        reference_count=reference_count,
    )


def _finding(rule_id: str, severity: Severity) -> Finding:
    return Finding(
        id=rule_id,
        rule_id=rule_id,
        category="Textures",
        title=rule_id,
        summary="",
        severity=severity,
        repairability=Repairability.NONE,
    )


# -- apply_filter -----------------------------------------------------------


def test_filter_all_returns_everything():
    refs = [_ref("a.jpg"), _ref("b.jpg")]
    assert apply_filter(refs, TextureFilter.ALL) == refs


def test_filter_missing():
    missing = _ref("a.jpg", exists=False)
    present = _ref("b.jpg", exists=True)
    assert apply_filter([missing, present], TextureFilter.MISSING) == [missing]


def test_filter_oversized_uses_threshold():
    small = _ref("small.jpg", width=2048, height=2048)
    big = _ref("big.jpg", width=8192, height=8192)
    result = apply_filter([small, big], TextureFilter.OVERSIZED)
    assert result == [big]

    strict = TextureThresholds(oversized_warning_px=1024)
    assert apply_filter([small, big], TextureFilter.OVERSIZED, thresholds=strict) == [small, big]


def test_filter_local():
    local = _ref("a.jpg", path_type=PathType.LOCAL)
    unc = _ref("b.jpg", path_type=PathType.NETWORK_UNC)
    assert apply_filter([local, unc], TextureFilter.LOCAL) == [local]


def test_filter_duplicate_uses_reference_count():
    shared = _ref("a.jpg", reference_count=3)
    unique = _ref("b.jpg", reference_count=1)
    assert apply_filter([shared, unique], TextureFilter.DUPLICATE) == [shared]


def test_apply_filter_never_mutates_input():
    refs = [_ref("a.jpg", exists=False), _ref("b.jpg")]
    original = list(refs)
    apply_filter(refs, TextureFilter.MISSING)
    assert refs == original


# -- value-parameterized filters ---------------------------------------------


def test_filter_by_extension_case_insensitive():
    jpg = _ref("wood.jpg")
    png = _ref("metal.PNG")
    assert filter_by_extension([jpg, png], "png") == [png]


def test_filter_by_map_class():
    bitmap = _ref("a.jpg", map_class="CoronaBitmap")
    triplanar = _ref("b.jpg", map_class="CoronaTriplanar")
    assert filter_by_map_class([bitmap, triplanar], "CoronaTriplanar") == [triplanar]


def test_filter_by_material():
    a = _ref("a.jpg", material_name="Mat_A")
    b = _ref("b.jpg", material_name="Mat_B")
    assert filter_by_material([a, b], "Mat_B") == [b]


def test_filter_by_object():
    a = _ref("a.jpg", object_names=("Box01", "Box02"))
    b = _ref("b.jpg", object_names=("Box03",))
    assert filter_by_object([a, b], "Box02") == [a]


# -- local workstation path helper (shared with TXT-006 + the report) -------


def test_local_workstation_path_count_matches_marker_list():
    workstation = _ref("a.jpg", path=r"C:\Users\alice\Desktop\a.jpg", path_type=PathType.LOCAL)
    project = _ref("b.jpg", path=r"C:\Project\Textures\b.jpg", path_type=PathType.LOCAL)
    refs = [workstation, project]
    assert filter_local_workstation_paths(refs) == [workstation]
    assert local_workstation_path_count(refs) == 1


# -- sorting: deterministic (secondary tie-break on filename) ---------------


def test_sort_by_filename():
    b = _ref("b.jpg")
    a = _ref("a.jpg")
    assert sort_references([b, a], TextureSortKey.FILENAME) == [a, b]


def test_sort_by_resolution_ties_broken_by_filename():
    z_small = _ref("z.jpg", width=100, height=100)
    a_small = _ref("a.jpg", width=100, height=100)
    big = _ref("m.jpg", width=1000, height=1000)
    result = sort_references([z_small, big, a_small], TextureSortKey.RESOLUTION)
    assert result == [a_small, z_small, big]


def test_sort_by_file_size():
    small = _ref("a.jpg", size_bytes=100)
    large = _ref("b.jpg", size_bytes=10_000)
    assert sort_references([large, small], TextureSortKey.FILE_SIZE) == [small, large]


def test_sort_by_reference_count():
    low = _ref("a.jpg", reference_count=1)
    high = _ref("b.jpg", reference_count=5)
    assert sort_references([high, low], TextureSortKey.REFERENCE_COUNT) == [low, high]


def test_sort_by_path():
    refs = [_ref("a.jpg", path="Z:/z.jpg"), _ref("b.jpg", path="A:/a.jpg")]
    result = sort_references(refs, TextureSortKey.PATH)
    assert [r.filename for r in result] == ["b.jpg", "a.jpg"]


def test_sort_reverse():
    a = _ref("a.jpg")
    b = _ref("b.jpg")
    assert sort_references([a, b], TextureSortKey.FILENAME, reverse=True) == [b, a]


def test_sort_is_deterministic_across_repeated_calls():
    refs = [_ref("c.jpg", width=100, height=100), _ref("a.jpg", width=100, height=100), _ref("b.jpg", width=100, height=100)]
    first = sort_references(refs, TextureSortKey.RESOLUTION)
    second = sort_references(list(reversed(refs)), TextureSortKey.RESOLUTION)
    assert [r.filename for r in first] == [r.filename for r in second] == ["a.jpg", "b.jpg", "c.jpg"]


# -- finding severity sort ---------------------------------------------------


def test_sort_findings_by_severity_most_severe_first():
    optimization = _finding("TXT-002", Severity.OPTIMIZATION)
    critical = _finding("TXT-001", Severity.CRITICAL)
    info = _finding("TXT-006", Severity.INFO)
    result = sort_findings_by_severity([optimization, info, critical])
    assert [f.rule_id for f in result] == ["TXT-001", "TXT-002", "TXT-006"]
