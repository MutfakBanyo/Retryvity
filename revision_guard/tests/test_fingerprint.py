"""Fingerprint determinism and tolerance behaviour."""

from __future__ import annotations

from revision_guard.core.constants import MAX_HASHED_VERTICES
from revision_guard.core.fingerprint import (
    build_geometry_signature,
    build_transform_signature,
    canonical_quaternion,
    geometry_changed,
    quantize,
    transform_changed,
    vertex_indices_to_hash,
)
from revision_guard.tests.factories import CUBE_VERTICES, move_vertex


def test_digest_is_stable_across_calls():
    first = build_geometry_signature(8, 12, CUBE_VERTICES)
    second = build_geometry_signature(8, 12, CUBE_VERTICES)
    assert first.digest == second.digest


def test_digest_is_not_pythons_salted_hash():
    # A sha256 hex digest, so it is reproducible across processes.
    signature = build_geometry_signature(8, 12, CUBE_VERTICES)
    assert len(signature.digest) == 64
    assert int(signature.digest, 16) >= 0


def test_moved_vertex_detected_with_identical_counts():
    before = build_geometry_signature(8, 12, CUBE_VERTICES)
    moved = move_vertex(CUBE_VERTICES, 3, (0.5, 0.0, 0.0))
    after = build_geometry_signature(8, 12, moved)

    assert before.vertex_count == after.vertex_count
    assert before.face_count == after.face_count
    assert geometry_changed(before, after)


def test_float_noise_below_tolerance_is_not_a_change():
    before = build_geometry_signature(8, 12, CUBE_VERTICES)
    noisy = move_vertex(CUBE_VERTICES, 3, (1.0e-9, -1.0e-9, 1.0e-9))
    after = build_geometry_signature(8, 12, noisy)
    assert not geometry_changed(before, after)


def test_vertex_count_change_detected():
    before = build_geometry_signature(8, 12, CUBE_VERTICES)
    after = build_geometry_signature(9, 14, CUBE_VERTICES + [(9, 2.0, 2.0, 2.0)])
    assert geometry_changed(before, after)


def test_transform_translation_detected():
    before = build_transform_signature((0, 0, 0), (0, 0, 0, 1), (1, 1, 1))
    after = build_transform_signature((10, 0, 0), (0, 0, 0, 1), (1, 1, 1))
    assert transform_changed(before, after)


def test_transform_rotation_detected():
    before = build_transform_signature((0, 0, 0), (0, 0, 0, 1), (1, 1, 1))
    after = build_transform_signature((0, 0, 0), (0.0, 0.0, 0.7071, 0.7071), (1, 1, 1))
    assert transform_changed(before, after)


def test_transform_scale_detected():
    before = build_transform_signature((0, 0, 0), (0, 0, 0, 1), (1, 1, 1))
    after = build_transform_signature((0, 0, 0), (0, 0, 0, 1), (1, 2, 1))
    assert transform_changed(before, after)


def test_transform_float_noise_is_not_a_change():
    before = build_transform_signature((1.0, 2.0, 3.0), (0, 0, 0, 1), (1, 1, 1))
    after = build_transform_signature((1.0 + 1e-9, 2.0, 3.0 - 1e-9), (0, 0, 0, 1), (1, 1, 1))
    assert not transform_changed(before, after)


def test_negated_quaternion_is_the_same_rotation():
    assert canonical_quaternion((0.0, 0.0, 0.7071, -0.7071)) == canonical_quaternion(
        (0.0, 0.0, -0.7071, 0.7071)
    )
    before = build_transform_signature((0, 0, 0), (0.1, 0.2, 0.3, 0.9), (1, 1, 1))
    after = build_transform_signature((0, 0, 0), (-0.1, -0.2, -0.3, -0.9), (1, 1, 1))
    assert not transform_changed(before, after)


def test_quantize_is_symmetric_around_zero():
    assert quantize(0.0, 1e-4) == 0
    assert quantize(-0.0, 1e-4) == 0
    assert quantize(1.0, 1.0) == 1
    assert quantize(-1.0, 1.0) == -1


def test_non_finite_coordinates_do_not_raise():
    broken = [(1, float("nan"), 0.0, float("inf"))]
    signature = build_geometry_signature(1, 0, broken)
    assert len(signature.digest) == 64


def test_dense_mesh_falls_back_to_a_deterministic_sample():
    indices, sampled = vertex_indices_to_hash(MAX_HASHED_VERTICES * 3)
    again, _ = vertex_indices_to_hash(MAX_HASHED_VERTICES * 3)
    assert sampled
    assert indices == again
    assert len(indices) <= MAX_HASHED_VERTICES


def test_small_mesh_hashes_every_vertex():
    indices, sampled = vertex_indices_to_hash(8)
    assert not sampled
    assert indices == [1, 2, 3, 4, 5, 6, 7, 8]


def test_empty_mesh_is_handled():
    signature = build_geometry_signature(0, 0, [])
    assert signature.vertex_count == 0
    assert not geometry_changed(signature, build_geometry_signature(0, 0, []))
