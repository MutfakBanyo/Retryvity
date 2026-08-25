"""Scene Inventory + Texture Doctor v1 — the first production scanner.

Strictly READ-ONLY: never assigns a scene/material/map property, never
changes selection, never touches the filesystem beyond ``stat``/reading
small image-header bytes. See docs/TEXTURE_DOCTOR.md for the full
read-only guarantee and known limitations.

Pipeline (each stage yields at least once, so a large scene never freezes
the host UI for long — see ui/scan_controller.py's QTimer-driven driver):

    scene nodes (chunked)
      -> materials/maps (chunked, recursive, generic — see scene_adapter.py)
      -> filesystem + image-header metadata (chunked, cached per path)
      -> rules (TextureScanFacts -> Findings)

Scanner collects facts (SceneInventory, ExternalTextureReference); rules
(rules/definitions/texture_rules.py) interpret them into Findings — see
docs/ARCHITECTURE.md's "scanner vs rule" boundary.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

from corona_doctor.adapters.image_metadata import read_image_dimensions
from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.adapters.path_utils import FilesystemMetadataCache, build_path_info, human_readable_size
from corona_doctor.adapters.scene_adapter import MapDiscovery, NodeFacts, SceneAdapter
from corona_doctor.core.models import Finding
from corona_doctor.core.rules import RuleEngine
from corona_doctor.core.texture_models import (
    ExternalTextureReference,
    ScanTimings,
    SceneInventory,
    TextureDoctorDiagnostics,
    TextureDoctorResult,
    TextureScanFacts,
    TextureThresholds,
)
from corona_doctor.logging.logger import get_logger
from corona_doctor.performance.profiler import Profiler
from corona_doctor.rules.loader import load_rules
from corona_doctor.scanners.base import BaseScanner, ScanBatch

_logger = get_logger("texture_doctor_scanner")

_NODE_BATCH_SIZE = 2000
_MAP_BATCH_SIZE = 200
_FS_BATCH_SIZE = 200


class TextureDoctorScanner(BaseScanner):
    """Scene Inventory + Texture Doctor v1: read-only, chunked, cancellable."""

    id = "texture_doctor"
    name = "Scene Inventory + Texture Doctor"

    def __init__(
        self,
        scene_adapter: SceneAdapter | None = None,
        thresholds: TextureThresholds | None = None,
        profiler: Profiler | None = None,
    ) -> None:
        self._scene = scene_adapter or SceneAdapter()
        self._thresholds = thresholds or TextureThresholds()
        self._profiler = profiler or Profiler()
        self._cancelled = False

        self.inventory: SceneInventory | None = None
        self.facts: TextureScanFacts | None = None
        self.texture_references: tuple[ExternalTextureReference, ...] = ()
        # The stable, production-facing result — see core/texture_models.py's
        # TextureDoctorResult docstring. inventory/facts/texture_references
        # above stay for existing callers (UI, tests); this bundles the same
        # data (minus dev-only diagnostics) into one object for anything new.
        self.result: TextureDoctorResult | None = None

    def is_available(self) -> bool:
        return self._scene.is_available()

    def cancel(self) -> None:
        """Request early termination. Safe at any point — read-only scan."""

        self._cancelled = True

    def scan(self) -> Iterator[ScanBatch]:
        started_at = time.perf_counter()
        self._cancelled = False

        node_facts: list[NodeFacts] = []
        node_total = self._scene.get_node_count()
        completed = 0

        with self._profiler.measure("texture_doctor.nodes"):
            for batch in self._scene.iter_node_facts(_NODE_BATCH_SIZE):
                node_facts.extend(batch)
                completed = len(node_facts)
                yield ("nodes", completed, max(node_total, completed), [])
                if self._cancelled:
                    _logger.info("Texture Doctor scan cancelled during node inventory")
                    return

        map_discoveries: list[MapDiscovery] = []
        with self._profiler.measure("texture_doctor.materials_maps"):
            for batch in self._scene.traverse_materials_and_maps(_MAP_BATCH_SIZE):
                map_discoveries.extend(batch)
                yield ("materials", len(map_discoveries), len(map_discoveries), [])
                if self._cancelled:
                    _logger.info("Texture Doctor scan cancelled during material/map traversal")
                    return

        texture_references: list[ExternalTextureReference] = []
        fs_cache = FilesystemMetadataCache()
        dims_cache: dict[str, tuple[int, int] | None] = {}

        with self._profiler.measure("texture_doctor.filesystem"):
            for start in range(0, len(map_discoveries), _FS_BATCH_SIZE):
                chunk = map_discoveries[start : start + _FS_BATCH_SIZE]
                for index, discovery in enumerate(chunk):
                    ref = _build_texture_reference(discovery, start + index, fs_cache, dims_cache)
                    if ref is not None:
                        texture_references.append(ref)
                yield ("textures", min(start + _FS_BATCH_SIZE, len(map_discoveries)), len(map_discoveries), [])
                if self._cancelled:
                    _logger.info("Texture Doctor scan cancelled during filesystem/metadata phase")
                    return

        texture_references = _apply_reference_counts(texture_references)

        nodes_with_material_count = sum(1 for n in node_facts if n.material_handle is not None)
        duration_ms = (time.perf_counter() - started_at) * 1000

        inventory = _build_inventory(
            node_facts=node_facts,
            texture_references=texture_references,
            scene_adapter=self._scene,
            nodes_with_material_count=nodes_with_material_count,
            thresholds=self._thresholds,
            duration_ms=duration_ms,
        )

        diagnostics = TextureDoctorDiagnostics(
            root_materials_encountered=self._scene.root_materials_encountered,
            materials_with_valid_handle=self._scene.materials_with_valid_handle,
            materials_using_fallback_identity=self._scene.materials_using_fallback_identity,
            sub_material_edges_traversed=self._scene.sub_material_edges_traversed,
            map_nodes_encountered=self._scene.map_nodes_encountered,
            maps_with_valid_handle=self._scene.maps_with_valid_handle,
            maps_using_fallback_identity=self._scene.maps_using_fallback_identity,
            external_file_backed_maps_recognized=self._scene.external_file_backed_maps_recognized,
            maps_with_candidate_filename_properties=self._scene.maps_with_candidate_filename_properties,
            maps_rejected_as_non_file_backed=self._scene.maps_rejected_as_non_file_backed,
            identity_samples=tuple(self._scene.identity_samples),
            rejected_map_samples=tuple(self._scene.rejected_map_samples),
        )
        compatibility_warnings = tuple(_check_invariants(inventory))
        for warning in compatibility_warnings:
            _logger.warning("Texture Doctor compatibility warning: %s", warning)

        self.facts = TextureScanFacts(
            inventory=inventory,
            texture_references=tuple(texture_references),
            unknown_map_classes=tuple(self._scene.unknown_map_classes),
            errors=tuple(self._scene.errors),
            diagnostics=diagnostics,
            compatibility_warnings=compatibility_warnings,
        )
        self.inventory = inventory
        self.texture_references = tuple(texture_references)

        with self._profiler.measure("texture_doctor.rules"):
            engine = RuleEngine(load_rules(self._thresholds))
            findings: list[Finding] = engine.run({"texture_facts": self.facts})

        timings = self._build_scan_timings(duration_ms)
        self.result = TextureDoctorResult.from_facts(self.facts, tuple(findings), timings)

        _logger.info(
            "Texture Doctor scan complete: %d nodes, %d unique materials, %d texture refs, %d findings (%.1f ms)",
            inventory.total_nodes,
            inventory.unique_material_count,
            len(texture_references),
            len(findings),
            duration_ms,
        )

        yield ("rules", 1, 1, findings)

    def _build_scan_timings(self, total_ms: float) -> ScanTimings:
        measurements = self._profiler.report()
        return ScanTimings(
            nodes_ms=measurements.get("texture_doctor.nodes", 0.0),
            materials_maps_ms=measurements.get("texture_doctor.materials_maps", 0.0),
            filesystem_ms=measurements.get("texture_doctor.filesystem", 0.0),
            rules_ms=measurements.get("texture_doctor.rules", 0.0),
            total_ms=total_ms,
        )




def _build_texture_reference(
    discovery: MapDiscovery,
    index: int,
    fs_cache: FilesystemMetadataCache,
    dims_cache: dict[str, tuple[int, int] | None],
) -> ExternalTextureReference | None:
    if discovery.raw_path is None:
        return None

    path_info = build_path_info(discovery.raw_path, exists_checker=fs_cache.exists)
    filename = os.path.basename(path_info.normalized_path) if path_info.normalized_path else discovery.raw_path
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    size_bytes: int | None = None
    if path_info.exists:
        size_bytes = fs_cache.size_bytes(path_info.normalized_path)

    width: int | None = None
    height: int | None = None
    if path_info.exists and path_info.normalized_path:
        if path_info.normalized_path not in dims_cache:
            dims_cache[path_info.normalized_path] = read_image_dimensions(path_info.normalized_path)
        dims = dims_cache[path_info.normalized_path]
        if dims is not None:
            width, height = dims

    # Fallback identities (see SceneAdapter._identity) are negative and
    # only meaningful within the scan that produced them — never a real
    # pymxs AnimHandle safe to pass to rt.getAnimByHandle later. A repair
    # action must not be offered a handle it could resolve to the wrong
    # object.
    map_handle = discovery.handle if discovery.handle is not None and discovery.handle > 0 else None

    return ExternalTextureReference(
        ref_id=f"ref-{index:06d}",
        map_class=discovery.map_class,
        map_name=discovery.map_name,
        material_name=discovery.material_name,
        object_names=discovery.object_names,
        path_info=path_info,
        filename=filename,
        extension=extension,
        file_size_bytes=size_bytes,
        file_size_human=human_readable_size(size_bytes),
        width=width,
        height=height,
        source_property=discovery.source_property,
        map_handle=map_handle,
    )


def _apply_reference_counts(refs: list[ExternalTextureReference]) -> list[ExternalTextureReference]:
    from collections import Counter
    from dataclasses import replace

    counts = Counter(r.path_info.comparison_key for r in refs if r.path_info.comparison_key)
    return [replace(r, reference_count=counts.get(r.path_info.comparison_key, 1)) for r in refs]


def _build_inventory(
    node_facts: list[NodeFacts],
    texture_references: list[ExternalTextureReference],
    scene_adapter: SceneAdapter,
    nodes_with_material_count: int,
    thresholds: TextureThresholds,
    duration_ms: float,
) -> SceneInventory:
    from collections import Counter

    superclass_counts = Counter(n.superclass_key for n in node_facts)
    extension_counts = Counter(r.extension.upper() or "OTHER" for r in texture_references)

    unique_paths = {r.path_info.comparison_key for r in texture_references if r.path_info.comparison_key}
    missing = sum(1 for r in texture_references if r.path_info.exists is False)
    oversized_8k = sum(
        1
        for r in texture_references
        if r.width and r.height and max(r.width, r.height) >= thresholds.oversized_warning_px
    )
    oversized_16k = sum(
        1
        for r in texture_references
        if r.width and r.height and max(r.width, r.height) >= thresholds.oversized_strong_warning_px
    )
    duplicate_groups = {
        key for key, count in Counter(r.path_info.comparison_key for r in texture_references).items() if count > 1
    }

    corona_light_count = sum(1 for n in node_facts if n.class_name in _CORONA_LIGHT_CLASSES)
    corona_camera_count = sum(1 for n in node_facts if n.class_name in _CORONA_CAMERA_CLASSES)

    return SceneInventory(
        total_nodes=len(node_facts),
        geometry_count=superclass_counts.get("geometry", 0),
        light_count=superclass_counts.get("light", 0),
        camera_count=superclass_counts.get("camera", 0),
        helper_count=superclass_counts.get("helper", 0),
        shape_count=superclass_counts.get("shape", 0),
        group_count=sum(1 for n in node_facts if n.is_group_head),
        hidden_count=sum(1 for n in node_facts if n.is_hidden),
        frozen_count=sum(1 for n in node_facts if n.is_frozen),
        nodes_with_material_count=nodes_with_material_count,
        unique_material_count=scene_adapter.unique_material_count,
        map_reference_count=scene_adapter.map_reference_count,
        unique_external_texture_count=len(unique_paths),
        corona_light_count=corona_light_count,
        corona_camera_count=corona_camera_count,
        missing_texture_count=missing,
        oversized_8k_count=oversized_8k,
        oversized_16k_count=oversized_16k,
        duplicate_group_count=len(duplicate_groups),
        extension_counts=dict(extension_counts),
        scan_duration_ms=duration_ms,
    )


_CORONA_LIGHT_CLASSES = ("CoronaLight", "CoronaSun")
_CORONA_CAMERA_CLASSES = ("CoronaCam",)


def _check_invariants(inventory: SceneInventory) -> list[str]:
    """No silent zeroes: flag scan results that contradict each other.

    These never crash/raise — they're logged (see caller) and surfaced in
    ``TextureScanFacts.compatibility_warnings`` for the devtools probe, not
    presented as an error in production UI. See docs/TEXTURE_DOCTOR.md,
    "No silent zeroes".
    """

    warnings: list[str] = []
    if inventory.nodes_with_material_count > 0 and inventory.unique_material_count == 0:
        warnings.append(
            f"{inventory.nodes_with_material_count} node(s) have a material assigned but "
            "0 unique materials were discovered during traversal — material identity or "
            "traversal is likely broken on this host."
        )
    if inventory.corona_light_count > inventory.light_count:
        warnings.append(
            f"corona_light_count ({inventory.corona_light_count}) exceeds light_count "
            f"({inventory.light_count}) — generic light classification is likely broken on this host."
        )
    if inventory.corona_camera_count > inventory.camera_count:
        warnings.append(
            f"corona_camera_count ({inventory.corona_camera_count}) exceeds camera_count "
            f"({inventory.camera_count}) — generic camera classification is likely broken on this host."
        )
    return warnings
