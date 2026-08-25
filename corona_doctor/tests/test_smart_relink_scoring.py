"""Unit tests for smart_relink/scoring.py — pure, deterministic, no
filesystem/3ds Max."""

from __future__ import annotations

from corona_doctor.smart_relink.models import CandidateMetadata, ConfidenceBand, KnownAssetMetadata, MissingAsset
from corona_doctor.smart_relink.scoring import is_bulk_acceptable, rank_candidates, score_candidate


def _missing(filename="wood_floor_07.jpg", old_path=r"C:\OldProject\Textures\wood_floor_07.jpg", **known_kwargs) -> MissingAsset:
    return MissingAsset(
        asset_id="missing-1",
        filename=filename,
        old_path=old_path,
        known_metadata=KnownAssetMetadata(**known_kwargs),
        map_ref_ids=("ref-1",),
    )


def _meta(**kwargs) -> CandidateMetadata:
    return CandidateMetadata(**kwargs)


def test_exact_filename_match_is_exact_band_regardless_of_metadata():
    """EXACT band is forced by the filename match alone - a different
    folder or missing metadata (both present here) never downgrades it,
    even though they still show up as imperfect evidence lines."""

    missing = _missing()
    candidate = score_candidate(missing, r"D:\Library\Wood\Oak\wood_floor_07.jpg", _meta())
    assert candidate.band == ConfidenceBand.EXACT


def test_exact_filename_match_is_case_insensitive():
    missing = _missing(filename="Wood_Floor_07.JPG", old_path=r"C:\proj\Wood_Floor_07.JPG")
    candidate = score_candidate(missing, r"D:\Library\wood_floor_07.jpg", _meta())
    assert candidate.band == ConfidenceBand.EXACT


def test_renamed_file_with_no_known_metadata_scores_on_filename_similarity_only():
    missing = _missing()  # no known width/height/size
    candidate = score_candidate(missing, r"D:\Library\wood_floor_final.jpg", _meta(width=4096, height=4096))
    # Resolution/size evidence must be marked "unknown", not scored:
    resolution_evidence = [e for e in candidate.evidence if "resolution" in e.label][0]
    assert resolution_evidence.matched is None
    assert resolution_evidence.weight == 0
    assert candidate.band != ConfidenceBand.EXACT


def test_known_dimensions_matching_candidate_boosts_score():
    missing = _missing(width=4096, height=4096)
    low_evidence_candidate = score_candidate(missing, r"D:\Lib\unrelated_name.jpg", _meta())
    matching_candidate = score_candidate(missing, r"D:\Lib\unrelated_name.jpg", _meta(width=4096, height=4096))
    assert matching_candidate.score > low_evidence_candidate.score


def test_known_dimensions_not_matching_candidate_does_not_score_dimension_points():
    missing = _missing(width=4096, height=4096)
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(width=512, height=512))
    dim_evidence = [e for e in candidate.evidence if "resolution match" in e.label][0]
    assert dim_evidence.matched is False


def test_same_aspect_ratio_scores_even_when_absolute_dims_differ():
    missing = _missing(width=4096, height=2048)  # 2:1
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(width=2048, height=1024))  # also 2:1
    ratio_evidence = [e for e in candidate.evidence if "aspect ratio" in e.label][0]
    assert ratio_evidence.matched is True


def test_different_aspect_ratio_does_not_score():
    missing = _missing(width=4096, height=2048)
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(width=1000, height=1000))
    ratio_evidence = [e for e in candidate.evidence if "aspect ratio" in e.label][0]
    assert ratio_evidence.matched is False


def test_file_size_similarity_scores_when_close():
    missing = _missing(file_size_bytes=1_000_000)
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(file_size_bytes=950_000))
    size_evidence = [e for e in candidate.evidence if "file size" in e.label][0]
    assert size_evidence.matched is True


def test_file_size_similarity_does_not_score_when_very_different():
    missing = _missing(file_size_bytes=1_000_000)
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(file_size_bytes=50_000))
    size_evidence = [e for e in candidate.evidence if "file size" in e.label][0]
    assert size_evidence.matched is False


def test_missing_original_metadata_never_fabricates_a_comparison():
    """No known_metadata at all - every metadata-dependent evidence line
    must be explicitly 'unknown' (matched=None), never a fabricated
    True/False."""

    missing = _missing()  # all known_metadata fields None
    candidate = score_candidate(missing, r"D:\Lib\something_else.jpg", _meta(width=4096, height=4096, file_size_bytes=999))

    for label_fragment in ("resolution comparison", "file size comparison"):
        evidence = [e for e in candidate.evidence if label_fragment in e.label][0]
        assert evidence.matched is None
        assert evidence.weight == 0

    date_evidence = [e for e in candidate.evidence if "date" in e.label][0]
    assert date_evidence.matched is None


def test_date_evidence_is_never_scored_even_when_candidate_has_a_modified_time():
    """The original file's own timestamp is categorically unavailable
    (it went missing) - modified_at on the CANDIDATE must never be
    treated as a match/mismatch against nothing."""

    missing = _missing()
    candidate = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta(modified_at=1_700_000_000.0))
    date_evidence = [e for e in candidate.evidence if "date" in e.label][0]
    assert date_evidence.matched is None
    assert date_evidence.weight == 0


def test_scoring_is_deterministic():
    missing = _missing(width=4096, height=4096, file_size_bytes=1_000_000)
    meta = _meta(width=4096, height=4096, file_size_bytes=1_000_000)
    first = score_candidate(missing, r"D:\Lib\a.jpg", meta)
    second = score_candidate(missing, r"D:\Lib\a.jpg", meta)
    assert first == second


def test_confidence_bands_are_ordered_high_medium_low():
    missing = _missing(width=4096, height=4096, file_size_bytes=1_000_000)

    strong = score_candidate(missing, r"D:\Lib\Wood\wood_floor_07_renamed.jpg", _meta(width=4096, height=4096, file_size_bytes=1_000_000))
    weak = score_candidate(missing, r"D:\Lib\zzz\completely_unrelated.png", _meta())

    assert strong.band in (ConfidenceBand.HIGH, ConfidenceBand.MEDIUM)
    assert weak.band == ConfidenceBand.LOW


def test_rank_candidates_zero_candidates():
    missing = _missing()
    ranked = rank_candidates(missing, [], lambda p: _meta())
    assert ranked == []


def test_rank_candidates_one_exact_candidate():
    missing = _missing()
    ranked = rank_candidates(missing, [r"D:\Lib\wood_floor_07.jpg"], lambda p: _meta())
    assert len(ranked) == 1
    assert ranked[0].band == ConfidenceBand.EXACT


def test_rank_candidates_multiple_candidates_sorted_best_first():
    missing = _missing(width=4096, height=4096)
    paths = [r"D:\Lib\unrelated.png", r"D:\Lib\wood_floor_07.jpg", r"D:\Lib\wood_floor_renamed.jpg"]

    def lookup(p):
        if "wood_floor_07" in p:
            return _meta(width=4096, height=4096)
        if "renamed" in p:
            return _meta(width=4096, height=4096)
        return _meta()

    ranked = rank_candidates(missing, paths, lookup)
    assert ranked[0].path == r"D:\Lib\wood_floor_07.jpg"
    assert ranked[0].band == ConfidenceBand.EXACT


def test_rank_candidates_deterministic_tie_break_by_path():
    missing = _missing(old_path=r"C:\proj\unrelated_target.jpg", filename="unrelated_target.jpg")
    first = rank_candidates(missing, [r"D:\z\a.jpg", r"D:\a\a.jpg"], lambda p: _meta())
    second = rank_candidates(missing, [r"D:\a\a.jpg", r"D:\z\a.jpg"], lambda p: _meta())
    assert [c.path for c in first] == [c.path for c in second]


def test_only_exact_is_bulk_acceptable():
    missing = _missing()
    exact = score_candidate(missing, r"D:\Lib\wood_floor_07.jpg", _meta())
    non_exact = score_candidate(missing, r"D:\Lib\different.jpg", _meta())
    assert is_bulk_acceptable(exact) is True
    assert is_bulk_acceptable(non_exact) is False
