"""Deterministic, documented candidate scoring — see
docs/SMART_RELINK.md, "Scoring model" for the full weight table and
rationale.

Every criterion below is either "known and matched", "known and didn't
match", or **"unknown — not evaluated"**. An unknown criterion is
excluded from ``max_possible_score`` entirely rather than counted
against the candidate (a candidate is never penalized for Corona Doctor
not knowing something about the original file) — this is what
``models.py``'s docstring calls the honesty boundary: nothing here ever
fabricates a comparison against metadata Corona Doctor doesn't actually
have.

No fuzzy/AI matching, no randomness, no external calls — same
(``filename``, ``known_metadata``, ``candidate_metadata``) input always
produces exactly the same score, every time.
"""

from __future__ import annotations

import difflib
import ntpath
from typing import Callable, Iterable

from corona_doctor.smart_relink.models import Candidate, CandidateMetadata, ConfidenceBand, KnownAssetMetadata, MissingAsset, ScoreEvidence

# Point weights — tunable, but centralized here so the "why 100 vs 10"
# question always has one answer. Exact filename dominates everything
# else on purpose: a byte-for-byte filename match is strong evidence
# even with zero other metadata.
_EXACT_FILENAME_WEIGHT = 100
_STEM_SIMILARITY_WEIGHT = 30
_EXTENSION_MATCH_WEIGHT = 10
_DIMENSION_MATCH_WEIGHT = 20
_ASPECT_RATIO_MATCH_WEIGHT = 10
_SIZE_SIMILARITY_WEIGHT = 15
_FOLDER_SIMILARITY_WEIGHT = 10

# Band thresholds as a fraction of the *applicable* max score (never the
# unconditional 195-point ceiling — see the "unknown is excluded, not
# penalized" rule above).
_HIGH_BAND_THRESHOLD = 0.75
_MEDIUM_BAND_THRESHOLD = 0.45

_STEM_SIMILARITY_MATCH_THRESHOLD = 0.6  # SequenceMatcher ratio counted as "matched" for the evidence line
_SIZE_SIMILARITY_MATCH_THRESHOLD = 0.85  # min/max ratio counted as "close enough" for the evidence line
_ASPECT_RATIO_TOLERANCE = 0.02


def _stem_and_ext(filename: str) -> tuple[str, str]:
    stem, _, ext = filename.rpartition(".")
    if not stem:
        return filename, ""
    return stem, ext.lower()


def _parent_folder_name(path: str) -> str:
    parent = ntpath.dirname(ntpath.normpath(path))
    return ntpath.basename(parent)


def score_candidate(missing: MissingAsset, candidate_path: str, candidate_metadata: CandidateMetadata) -> Candidate:
    """Score one candidate against one missing asset. See module
    docstring for the "unknown is excluded, not penalized" rule."""

    evidence: list[ScoreEvidence] = []
    score = 0
    max_score = 0
    known = missing.known_metadata

    target_name = ntpath.basename(missing.old_path)
    candidate_name = ntpath.basename(candidate_path)
    target_stem, target_ext = _stem_and_ext(target_name)
    candidate_stem, candidate_ext = _stem_and_ext(candidate_name)

    # -- filename ---------------------------------------------------------
    # Deliberately NOT added to score/max_score: an exact-filename match
    # already forces ConfidenceBand.EXACT directly (see _classify_band)
    # regardless of every other criterion below. Counting it as ordinary
    # points too would make HIGH/MEDIUM mathematically unreachable for a
    # legitimately strong RENAMED-file match (it would always be missing
    # this one large weight it can never earn by definition) - a renamed
    # file's score must be judged on its full points ceiling from the
    # other criteria alone.
    is_exact_filename = candidate_name.lower() == target_name.lower()
    evidence.append(
        ScoreEvidence(
            "exact filename match (forces EXACT band on its own)",
            is_exact_filename,
            _EXACT_FILENAME_WEIGHT if is_exact_filename else 0,
        )
    )

    similarity = difflib.SequenceMatcher(None, target_stem.lower(), candidate_stem.lower()).ratio()
    stem_points = round(similarity * _STEM_SIMILARITY_WEIGHT)
    max_score += _STEM_SIMILARITY_WEIGHT
    score += stem_points
    evidence.append(
        ScoreEvidence(f"filename similarity ({similarity:.0%})", similarity >= _STEM_SIMILARITY_MATCH_THRESHOLD, _STEM_SIMILARITY_WEIGHT)
    )

    # -- extension ----------------------------------------------------------
    max_score += _EXTENSION_MATCH_WEIGHT
    extension_matches = bool(target_ext) and candidate_ext == target_ext
    if extension_matches:
        score += _EXTENSION_MATCH_WEIGHT
    evidence.append(ScoreEvidence("extension match", extension_matches, _EXTENSION_MATCH_WEIGHT))

    # -- dimensions / aspect ratio (only if the ORIGINAL is actually known) --
    if known.width and known.height and candidate_metadata.width and candidate_metadata.height:
        max_score += _DIMENSION_MATCH_WEIGHT
        dims_match = (known.width, known.height) == (candidate_metadata.width, candidate_metadata.height)
        if dims_match:
            score += _DIMENSION_MATCH_WEIGHT
        evidence.append(ScoreEvidence(f"{candidate_metadata.width}x{candidate_metadata.height} resolution match", dims_match, _DIMENSION_MATCH_WEIGHT))

        max_score += _ASPECT_RATIO_MATCH_WEIGHT
        known_ratio = known.width / known.height
        candidate_ratio = candidate_metadata.width / candidate_metadata.height
        ratio_match = abs(known_ratio - candidate_ratio) <= _ASPECT_RATIO_TOLERANCE
        if ratio_match:
            score += _ASPECT_RATIO_MATCH_WEIGHT
        evidence.append(ScoreEvidence("same aspect ratio", ratio_match, _ASPECT_RATIO_MATCH_WEIGHT))
    else:
        evidence.append(ScoreEvidence("resolution comparison — original dimensions unknown", None, 0))

    # -- file size (only if the ORIGINAL size is actually known) ------------
    if known.file_size_bytes and candidate_metadata.file_size_bytes:
        max_score += _SIZE_SIMILARITY_WEIGHT
        smaller = min(known.file_size_bytes, candidate_metadata.file_size_bytes)
        larger = max(known.file_size_bytes, candidate_metadata.file_size_bytes)
        ratio = smaller / larger if larger else 0.0
        size_points = round(ratio * _SIZE_SIMILARITY_WEIGHT) if ratio >= _SIZE_SIMILARITY_MATCH_THRESHOLD else 0
        score += size_points
        evidence.append(ScoreEvidence(f"file size similar ({ratio:.0%} of original)", ratio >= _SIZE_SIMILARITY_MATCH_THRESHOLD, _SIZE_SIMILARITY_WEIGHT))
    else:
        evidence.append(ScoreEvidence("file size comparison — original file size unknown", None, 0))

    # -- folder-name similarity ----------------------------------------------
    max_score += _FOLDER_SIMILARITY_WEIGHT
    folder_similarity = difflib.SequenceMatcher(None, _parent_folder_name(missing.old_path).lower(), _parent_folder_name(candidate_path).lower()).ratio()
    folder_points = round(folder_similarity * _FOLDER_SIMILARITY_WEIGHT)
    score += folder_points
    evidence.append(ScoreEvidence(f"folder name similarity ({folder_similarity:.0%})", folder_similarity >= _STEM_SIMILARITY_MATCH_THRESHOLD, _FOLDER_SIMILARITY_WEIGHT))

    # -- creation/date evidence -----------------------------------------------
    # Deliberately never scored: the ORIGINAL file's own timestamp was lost
    # when it went missing — there is nothing to compare a candidate's
    # modified_at against. Recorded as an explicit "not available" line
    # rather than silently omitted, so the user sees why. See
    # docs/SMART_RELINK.md, "Metadata evidence".
    evidence.append(ScoreEvidence("creation/modification date — original timestamp not available", None, 0))

    band = _classify_band(is_exact_filename, score, max_score)
    return Candidate(
        path=candidate_path,
        score=score,
        max_possible_score=max_score,
        band=band,
        evidence=tuple(evidence),
        metadata=candidate_metadata,
    )


def _classify_band(is_exact_filename: bool, score: int, max_score: int) -> ConfidenceBand:
    if is_exact_filename:
        return ConfidenceBand.EXACT
    fraction = (score / max_score) if max_score else 0.0
    if fraction >= _HIGH_BAND_THRESHOLD:
        return ConfidenceBand.HIGH
    if fraction >= _MEDIUM_BAND_THRESHOLD:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def rank_candidates(
    missing: MissingAsset,
    candidate_paths: Iterable[str],
    metadata_lookup: Callable[[str], CandidateMetadata],
) -> list[Candidate]:
    """Score every candidate path and return them sorted best-first,
    deterministically tie-broken by path so repeated calls never
    reorder equally-scored candidates."""

    candidates = [score_candidate(missing, path, metadata_lookup(path)) for path in candidate_paths]
    candidates.sort(key=lambda c: (-c.percent, -c.score, c.path.lower()))
    return candidates


def is_bulk_acceptable(candidate: Candidate) -> bool:
    """Only EXACT candidates are eligible for "Accept All Exact
    Matches" — see docs/SMART_RELINK.md, "Confidence bands and bulk
    accept". HIGH/MEDIUM/LOW always require individual review."""

    return candidate.band == ConfidenceBand.EXACT
