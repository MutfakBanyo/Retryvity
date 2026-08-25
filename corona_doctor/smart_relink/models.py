"""Smart Asset Recovery domain models — pure dataclasses, no Qt/pymxs/
filesystem. See docs/SMART_RELINK.md.

``KnownAssetMetadata`` vs. ``CandidateMetadata`` is the honesty boundary
this whole system is built around: a missing file cannot supply
dimensions/size/date evidence that was never captured before it went
missing. ``KnownAssetMetadata`` defaults every field to ``None``
("unknown") and callers must never populate a field they cannot
legitimately trace to a prior scan/manifest — see
``scoring.py``'s docstring for how "unknown" is kept structurally
distinct from "known and didn't match" in every score.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum


class ConfidenceBand(str, Enum):
    """Only ``EXACT`` is eligible for bulk "Accept All Exact Matches" —
    see docs/SMART_RELINK.md, "Confidence bands and bulk accept". Every
    other band always requires individual user review."""

    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"  # zero candidates found at all


@dataclass(frozen=True)
class KnownAssetMetadata:
    """What Corona Doctor can legitimately claim to know about the
    ORIGINAL missing file. Every field is ``None`` unless it was
    actually captured before the file went missing (a prior successful
    Texture Doctor scan, a repair manifest entry, or — for the torture
    scene — the fixture's own ground truth). Passing a guessed/assumed
    value here would let the scorer silently fabricate evidence — see
    ``scoring.py``.
    """

    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None
    source: str = "unknown"  # e.g. "prior scan", "repair manifest", "torture fixture"


@dataclass(frozen=True)
class CandidateMetadata:
    """What was actually measured about ONE candidate file found on
    disk — lazily populated (see ``metadata.py``), never guessed.
    ``modified_at`` is the file's own filesystem modification time — a
    stand-in for EXIF/XMP creation-date evidence in this milestone (no
    EXIF/XMP byte-level parser is implemented — see
    docs/SMART_RELINK.md, "Metadata evidence — what's actually
    implemented" for why, and why the original file's own date is
    categorically unavailable regardless: it was lost when the file went
    missing, there is nothing to compare a candidate's date against)."""

    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None
    modified_at: float | None = None


@dataclass(frozen=True)
class ScoreEvidence:
    """One line of the transparent scoring breakdown shown to the user.
    ``matched`` is ``True``/``False`` when the criterion was actually
    evaluated, or ``None`` when it could not be evaluated at all (no
    known original value to compare against) — never a fabricated
    False. ``weight`` is the points this criterion was worth (0 when
    ``matched is None``, since an inapplicable criterion cannot
    penalize a candidate)."""

    label: str
    matched: bool | None
    weight: int


@dataclass(frozen=True)
class Candidate:
    """One scored candidate file for one missing asset — see
    ``scoring.py::score_candidate``."""

    path: str
    score: int
    max_possible_score: int
    band: ConfidenceBand
    evidence: tuple[ScoreEvidence, ...]
    metadata: CandidateMetadata

    @property
    def percent(self) -> int:
        if self.max_possible_score <= 0:
            return 100 if self.score > 0 else 0
        return round(100 * self.score / self.max_possible_score)


@dataclass(frozen=True)
class MissingAsset:
    """One missing texture, already de-duplicated by old path — a
    single physical missing file referenced by several map nodes is
    ONE ``MissingAsset`` with several ``map_ref_ids``, so one approved
    candidate repairs every reference through one RepairPlan (see
    docs/SMART_RELINK.md, "One missing file, many map nodes")."""

    asset_id: str  # stable id for this session — see session.py
    filename: str
    old_path: str
    known_metadata: KnownAssetMetadata
    map_ref_ids: tuple[str, ...]
    material_names: tuple[str, ...] = ()
    object_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndexedFile:
    """One file discovered while building a ``SearchIndex`` — see
    ``index.py``. Cheap fields only (filename shape + size); width/
    height/date are read lazily, only for plausible candidates."""

    path: str
    filename: str
    stem: str
    extension: str
    size_bytes: int | None


@dataclass
class SearchIndex:
    """In-memory index of one recovery session's selected roots — built
    once, reused for every missing asset in the session (see
    docs/SMART_RELINK.md, "Search index"). Not persisted across
    sessions in this milestone."""

    files: list[IndexedFile] = field(default_factory=list)
    root_errors: list[str] = field(default_factory=list)  # per-root/per-dir problems — never fatal
    cancelled: bool = False

    def candidates_for_filename(self, filename: str) -> list[IndexedFile]:
        """Exact filename matches only — see ``candidates_for_asset`` for
        the broader (also-catches-renamed-files) lookup ``scoring.py``
        actually needs."""

        target = filename.lower()
        return [f for f in self.files if f.filename.lower() == target]

    def candidates_for_asset(self, filename: str, *, min_stem_similarity: float = 0.5) -> list[IndexedFile]:
        """Cheap pre-filter for ``scoring.py::rank_candidates`` — every
        exact filename match, PLUS every same-extension file whose stem
        is at least ``min_stem_similarity`` similar (``difflib``, same
        string-similarity measure ``scoring.py`` itself uses for the
        final score). This is what lets a genuinely RENAMED file (see
        docs/SMART_RELINK.md, "Smart match when file was renamed") ever
        reach the scorer at all — an exact-filename-only lookup would
        never surface it, no matter how good its other evidence is.
        Deliberately still a cheap string-only comparison — no metadata
        read happens here (see docs/SMART_RELINK.md, "Search index").
        """

        target_name = filename.lower()
        stem, _, ext = filename.rpartition(".")
        target_stem = (stem or filename).lower()
        target_ext = ext.lower()

        results: list[IndexedFile] = []
        for f in self.files:
            if f.filename.lower() == target_name:
                results.append(f)
                continue
            if target_ext and f.extension != target_ext:
                continue
            similarity = difflib.SequenceMatcher(None, target_stem, f.stem.lower()).ratio()
            if similarity >= min_stem_similarity:
                results.append(f)
        return results
