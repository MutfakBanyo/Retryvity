"""SmartRelink search session — one recovery pass over one set of
selected roots, covering every missing asset it was given. Qt-free (see
docs/SMART_RELINK.md, "Search session") so it is fully unit-testable and
reusable from ``devtools/smart_relink_probe.py`` without any UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.smart_relink.models import Candidate, ConfidenceBand, KnownAssetMetadata, MissingAsset, SearchIndex
from corona_doctor.smart_relink.scoring import is_bulk_acceptable


def missing_assets_from_references(
    references: list[ExternalTextureReference] | tuple[ExternalTextureReference, ...],
    *,
    known_metadata_lookup: dict[str, KnownAssetMetadata] | None = None,
) -> list[MissingAsset]:
    """Groups every ``ExternalTextureReference`` whose file is missing
    by its raw path — one physical missing file referenced by several
    map nodes becomes ONE ``MissingAsset`` (see docs/SMART_RELINK.md,
    "One missing file, many map nodes"). ``known_metadata_lookup`` is
    keyed by the missing raw path; when a path has no entry the asset's
    ``known_metadata`` is all-``None`` (fully unknown) — never guessed.
    """

    known_metadata_lookup = known_metadata_lookup or {}
    groups: dict[str, list[ExternalTextureReference]] = {}
    for ref in references:
        if ref.path_info.exists is not False:
            continue
        groups.setdefault(ref.path_info.raw_path, []).append(ref)

    assets: list[MissingAsset] = []
    for path in sorted(groups):
        refs = groups[path]
        sample = refs[0]
        assets.append(
            MissingAsset(
                asset_id=f"missing-{abs(hash(path)) % 10_000_000:07d}",
                filename=sample.filename,
                old_path=path,
                known_metadata=known_metadata_lookup.get(path, KnownAssetMetadata()),
                map_ref_ids=tuple(r.ref_id for r in refs),
                material_names=tuple(sorted({r.material_name for r in refs if r.material_name})),
                object_names=tuple(sorted({name for r in refs for name in r.object_names})),
            )
        )
    return assets


@dataclass
class SearchSession:
    roots: tuple[str, ...] = ()
    index: SearchIndex | None = None
    missing_assets: tuple[MissingAsset, ...] = ()
    candidates_by_asset: dict[str, list[Candidate]] = field(default_factory=dict)
    accepted: dict[str, str] = field(default_factory=dict)  # asset_id -> chosen candidate path
    rejected: dict[str, set[str]] = field(default_factory=dict)  # asset_id -> rejected candidate paths
    skipped: set[str] = field(default_factory=set)  # asset_id explicitly left unresolved by the user
    progress_current: int = 0
    progress_total: int = 0
    cancelled: bool = False

    def set_candidates(self, asset_id: str, candidates: list[Candidate]) -> None:
        self.candidates_by_asset[asset_id] = candidates

    def accept(self, asset_id: str, path: str) -> None:
        self.accepted[asset_id] = path
        self.skipped.discard(asset_id)

    def reject(self, asset_id: str, path: str) -> None:
        self.rejected.setdefault(asset_id, set()).add(path)
        if self.accepted.get(asset_id) == path:
            del self.accepted[asset_id]

    def skip(self, asset_id: str) -> None:
        self.skipped.add(asset_id)
        self.accepted.pop(asset_id, None)

    def accept_all_exact(self) -> int:
        """Selects the best candidate for every asset whose top
        candidate is EXACT — see ``scoring.py::is_bulk_acceptable``.
        Never touches HIGH/MEDIUM/LOW candidates. Returns how many
        assets were accepted this call."""

        count = 0
        for asset_id, candidates in self.candidates_by_asset.items():
            if not candidates:
                continue
            best = candidates[0]
            if is_bulk_acceptable(best) and asset_id not in self.accepted:
                self.accept(asset_id, best.path)
                count += 1
        return count

    def best_candidate(self, asset_id: str) -> Candidate | None:
        candidates = self.candidates_by_asset.get(asset_id) or []
        rejected = self.rejected.get(asset_id, set())
        remaining = [c for c in candidates if c.path not in rejected]
        return remaining[0] if remaining else None

    def summary_counts(self) -> dict[str, int]:
        exact = high = medium = low = none = 0
        for asset in self.missing_assets:
            best = self.best_candidate(asset.asset_id)
            if best is None:
                none += 1
            elif best.band == ConfidenceBand.EXACT:
                exact += 1
            elif best.band == ConfidenceBand.HIGH:
                high += 1
            elif best.band == ConfidenceBand.MEDIUM:
                medium += 1
            else:
                low += 1
        return {"exact": exact, "high": high, "medium": medium, "low": low, "unresolved": none}

    def accepted_pairs(self) -> list[tuple[str, str]]:
        """``[(asset_id, chosen_path), ...]`` for everything the user
        has actually accepted — the input to
        ``repair/planner.py::build_batch_relink_plan``."""

        return sorted(self.accepted.items())
