"""Unit tests for smart_relink/session.py — pure, no Qt/3ds Max."""

from __future__ import annotations

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType
from corona_doctor.smart_relink.models import Candidate, CandidateMetadata, ConfidenceBand, KnownAssetMetadata, ScoreEvidence
from corona_doctor.smart_relink.session import SearchSession, missing_assets_from_references


def _path_info(raw: str, exists: bool | None) -> PathInfo:
    return PathInfo(raw_path=raw, normalized_path=raw, comparison_key=raw.lower(), path_type=PathType.LOCAL, exists=exists)


def _ref(ref_id: str, filename: str, path: str, *, exists=False, material="Mtl", objects=("Box01",)) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id=ref_id,
        map_class="CoronaBitmap",
        map_name=filename,
        material_name=material,
        object_names=objects,
        path_info=_path_info(path, exists),
        filename=filename,
        extension="jpg",
    )


def _candidate(path: str, band: ConfidenceBand, score=100, max_score=100) -> Candidate:
    return Candidate(path=path, score=score, max_possible_score=max_score, band=band, evidence=(ScoreEvidence("x", True, 1),), metadata=CandidateMetadata())


# -- missing_assets_from_references ------------------------------------------


def test_only_missing_references_become_missing_assets():
    present = _ref("ref-1", "ok.jpg", r"C:\proj\ok.jpg", exists=True)
    missing = _ref("ref-2", "gone.jpg", r"C:\proj\gone.jpg", exists=False)
    assets = missing_assets_from_references([present, missing])

    assert len(assets) == 1
    assert assets[0].filename == "gone.jpg"


def test_one_missing_file_referenced_by_multiple_map_nodes_becomes_one_asset():
    """Part 19: one missing path referenced by several map nodes must
    become ONE MissingAsset with every ref_id, not several."""

    refs = [_ref(f"ref-{i}", "shared.jpg", r"C:\proj\shared.jpg", exists=False) for i in range(3)]
    assets = missing_assets_from_references(refs)

    assert len(assets) == 1
    assert set(assets[0].map_ref_ids) == {"ref-0", "ref-1", "ref-2"}


def test_missing_asset_collects_material_and_object_names():
    refs = [
        _ref("ref-1", "shared.jpg", r"C:\proj\shared.jpg", exists=False, material="Mtl_A", objects=("Box01",)),
        _ref("ref-2", "shared.jpg", r"C:\proj\shared.jpg", exists=False, material="Mtl_B", objects=("Box02", "Box03")),
    ]
    assets = missing_assets_from_references(refs)

    assert assets[0].material_names == ("Mtl_A", "Mtl_B")
    assert assets[0].object_names == ("Box01", "Box02", "Box03")


def test_known_metadata_lookup_populates_only_matching_paths():
    ref = _ref("ref-1", "gone.jpg", r"C:\proj\gone.jpg", exists=False)
    lookup = {r"C:\proj\gone.jpg": KnownAssetMetadata(width=4096, height=4096, source="prior scan")}
    assets = missing_assets_from_references([ref], known_metadata_lookup=lookup)

    assert assets[0].known_metadata.width == 4096
    assert assets[0].known_metadata.source == "prior scan"


def test_unlisted_missing_path_gets_fully_unknown_metadata_not_guessed():
    ref = _ref("ref-1", "gone.jpg", r"C:\proj\gone.jpg", exists=False)
    assets = missing_assets_from_references([ref])

    assert assets[0].known_metadata == KnownAssetMetadata()


# -- SearchSession ------------------------------------------------------------


def test_accept_and_reject_are_mutually_exclusive():
    session = SearchSession()
    session.accept("a1", "D:/found.jpg")
    assert session.accepted["a1"] == "D:/found.jpg"

    session.reject("a1", "D:/found.jpg")
    assert "a1" not in session.accepted
    assert "D:/found.jpg" in session.rejected["a1"]


def test_skip_clears_any_prior_acceptance():
    session = SearchSession()
    session.accept("a1", "D:/found.jpg")
    session.skip("a1")
    assert "a1" not in session.accepted
    assert "a1" in session.skipped


def test_accept_all_exact_only_touches_exact_band():
    session = SearchSession()
    session.set_candidates("a1", [_candidate("D:/exact.jpg", ConfidenceBand.EXACT)])
    session.set_candidates("a2", [_candidate("D:/high.jpg", ConfidenceBand.HIGH)])

    count = session.accept_all_exact()

    assert count == 1
    assert session.accepted == {"a1": "D:/exact.jpg"}


def test_accept_all_exact_never_overwrites_a_manual_choice():
    session = SearchSession()
    session.set_candidates("a1", [_candidate("D:/exact.jpg", ConfidenceBand.EXACT)])
    session.accept("a1", "D:/manually_chosen.jpg")

    count = session.accept_all_exact()

    assert count == 0
    assert session.accepted["a1"] == "D:/manually_chosen.jpg"


def test_best_candidate_skips_rejected_ones():
    session = SearchSession()
    session.set_candidates("a1", [_candidate("D:/first.jpg", ConfidenceBand.HIGH), _candidate("D:/second.jpg", ConfidenceBand.MEDIUM)])
    session.reject("a1", "D:/first.jpg")

    best = session.best_candidate("a1")
    assert best.path == "D:/second.jpg"


def test_best_candidate_none_when_zero_candidates():
    session = SearchSession()
    session.set_candidates("a1", [])
    assert session.best_candidate("a1") is None


def test_summary_counts_bucket_by_best_remaining_band():
    from corona_doctor.smart_relink.models import MissingAsset

    session = SearchSession()
    session.missing_assets = (
        MissingAsset(asset_id="a1", filename="a.jpg", old_path="C:/a.jpg", known_metadata=KnownAssetMetadata(), map_ref_ids=("r1",)),
        MissingAsset(asset_id="a2", filename="b.jpg", old_path="C:/b.jpg", known_metadata=KnownAssetMetadata(), map_ref_ids=("r2",)),
        MissingAsset(asset_id="a3", filename="c.jpg", old_path="C:/c.jpg", known_metadata=KnownAssetMetadata(), map_ref_ids=("r3",)),
    )
    session.set_candidates("a1", [_candidate("D:/x.jpg", ConfidenceBand.EXACT)])
    session.set_candidates("a2", [_candidate("D:/y.jpg", ConfidenceBand.HIGH)])
    session.set_candidates("a3", [])

    counts = session.summary_counts()
    assert counts == {"exact": 1, "high": 1, "medium": 0, "low": 0, "unresolved": 1}


def test_accepted_pairs_is_sorted_and_reflects_current_state():
    session = SearchSession()
    session.accept("a2", "D:/two.jpg")
    session.accept("a1", "D:/one.jpg")

    assert session.accepted_pairs() == [("a1", "D:/one.jpg"), ("a2", "D:/two.jpg")]
