"""Development-only, READ-ONLY Smart Asset Recovery probe.

Runs the real production Texture Doctor scanner, builds a
``smart_relink`` search index over the Torture Scene's recovery library
(see ``torture_scene.py``), and prints candidate rankings for every
missing texture it finds. Performs **no scene mutation** — this is
search + scoring only, never a relink (see docs/SMART_RELINK.md, "No
mutation during search").

Run from the 3ds Max Python Listener (one line, matching every other dev
entry point in this codebase)::

    from corona_doctor.devtools.smart_relink_probe import run_smart_relink_probe; run_smart_relink_probe()
"""

from __future__ import annotations

import os
from typing import Any

from corona_doctor.devtools.torture_manifest import load_torture_manifest
from corona_doctor.smart_relink.index import build_search_index
from corona_doctor.smart_relink.metadata import read_candidate_metadata
from corona_doctor.smart_relink.models import KnownAssetMetadata
from corona_doctor.smart_relink.scoring import rank_candidates
from corona_doctor.smart_relink.session import missing_assets_from_references


def run_smart_relink_probe(*, roots: list[str] | None = None, scanner: Any | None = None) -> dict:
    """``roots`` defaults to the last Torture Scene run's recovery
    library (``load_torture_manifest().smart_relink_recovery_root``).
    ``scanner`` is injectable for tests; defaults to a real
    ``TextureDoctorScanner`` run."""

    if scanner is None:
        from corona_doctor.core.diagnostics import DiagnosticEngine
        from corona_doctor.core.events import EventBus
        from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner

        scanner = TextureDoctorScanner()
        DiagnosticEngine(EventBus()).run(scanner)

    if scanner.result is None:
        print("Smart Relink probe: scan did not complete — see scanner errors/log.")
        return {"error": "scan did not complete"}

    if roots is None:
        manifest = load_torture_manifest()
        if manifest is None or not manifest.smart_relink_recovery_root:
            print("Smart Relink probe: no torture scene manifest found — run create_torture_scene() first, or pass roots=[...] explicitly.")
            return {"error": "no recovery root available"}
        roots = [manifest.smart_relink_recovery_root]

    known_metadata_lookup = _known_metadata_from_manifest()
    missing_assets = missing_assets_from_references(scanner.result.texture_references, known_metadata_lookup=known_metadata_lookup)

    if not missing_assets:
        print("Smart Relink probe: no missing textures in the current scan — nothing to search for.")
        return {"missing_assets": 0, "results": []}

    index = build_search_index(roots, walk_fn=lambda root: os.walk(root))
    for error in index.root_errors:
        print(f"Smart Relink probe: root error — {error}")

    results = []
    for asset in missing_assets:
        candidate_files = index.candidates_for_asset(asset.filename)
        candidates = rank_candidates(asset, [f.path for f in candidate_files], lambda p: read_candidate_metadata(p))
        results.append({"asset": asset, "candidates": candidates})
        _print_asset_result(asset, candidates)

    return {"missing_assets": len(missing_assets), "results": results, "root_errors": index.root_errors}


def _known_metadata_from_manifest() -> dict[str, KnownAssetMetadata]:
    """Torture-scene-only ground truth (see
    ``devtools/torture_manifest.py::FixtureRecord.known_width``/
    ``known_height``) — a real production scan has no such lookup and
    correctly gets an empty dict here (every asset then scores with
    "original dimensions unknown" — see ``smart_relink/scoring.py``)."""

    manifest = load_torture_manifest()
    if manifest is None:
        return {}
    lookup: dict[str, KnownAssetMetadata] = {}
    for fixture in manifest.fixtures:
        if fixture.known_width and fixture.known_height and fixture.created_asset_paths:
            missing_path = fixture.created_asset_paths[0]
            lookup[missing_path] = KnownAssetMetadata(
                width=fixture.known_width,
                height=fixture.known_height,
                source="torture fixture manifest",
            )
    return lookup


def _print_asset_result(asset, candidates) -> None:
    print(f"\n{asset.filename}")
    print(f"  old path: {asset.old_path}")
    print(f"  used by: {len(asset.map_ref_ids)} map(s), {len(asset.material_names)} material(s), {len(asset.object_names)} object(s)")
    if not candidates:
        print("  candidates: none — unresolved")
        return
    for i, candidate in enumerate(candidates, start=1):
        print(f"  #{i} [{candidate.band.value.upper()} · {candidate.percent}%] {candidate.path}")
        for line in candidate.evidence:
            mark = "?" if line.matched is None else ("✓" if line.matched else "✗")
            print(f"      {mark} {line.label}")


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    run_smart_relink_probe()
