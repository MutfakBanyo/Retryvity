"""Deterministic demo scanner.

Produces a fixed, staged set of findings so the UI/model-view pipeline
(progress reporting, findings list, health score) can be exercised end to
end without a real 3ds Max scene. This is explicitly NOT a production
scanner — it must never be mistaken for real Corona/scene analysis.
Production scanners (geometry, materials, textures, ...) are future
milestones that will implement the same ``BaseScanner`` contract.
"""

from __future__ import annotations

import time
from typing import Iterator

from corona_doctor.core.models import Finding, Impact, Repairability, Severity
from corona_doctor.scanners.base import BaseScanner, ScanBatch

_DEMO_FINDINGS: tuple[Finding, ...] = (
    Finding(
        id="demo.critical.1",
        rule_id="demo.render.missing_texture",
        category="Textures",
        title="Missing texture file",
        summary="A material references a bitmap that could not be located on disk.",
        severity=Severity.CRITICAL,
        performance_impact=Impact.NONE,
        memory_impact=Impact.NONE,
        render_impact=Impact.HIGH,
        affected_items=("Material_Facade_01",),
        details="Demo finding — not derived from real scene analysis.",
        recommended_action="Relink the texture or restore the missing file.",
        repairability=Repairability.MANUAL,
    ),
    Finding(
        id="demo.critical.2",
        rule_id="demo.render.corona_not_active",
        category="Renderer",
        title="Corona is installed but not the active renderer",
        summary="Render output will not reflect Corona settings until it is set active.",
        severity=Severity.CRITICAL,
        performance_impact=Impact.NONE,
        memory_impact=Impact.NONE,
        render_impact=Impact.HIGH,
        details="Demo finding — not derived from real scene analysis.",
        recommended_action="Set Corona Renderer as the active renderer.",
        repairability=Repairability.REVIEW,
    ),
    *(
        Finding(
            id=f"demo.warning.{i}",
            rule_id="demo.geometry.high_poly",
            category="Geometry",
            title="High polygon count object",
            summary="An object has a substantially higher poly count than similar objects.",
            severity=Severity.WARNING,
            performance_impact=Impact.MEDIUM,
            memory_impact=Impact.MEDIUM,
            render_impact=Impact.LOW,
            affected_items=(f"Mesh_{i:02d}",),
            details="Demo finding — not derived from real scene analysis.",
            recommended_action="Consider optimizing or proxying this object.",
            repairability=Repairability.REVIEW,
        )
        for i in range(1, 5)
    ),
    *(
        Finding(
            id=f"demo.optimization.{i}",
            rule_id="demo.textures.oversized",
            category="Textures",
            title="Texture resolution larger than needed",
            summary="A texture is significantly larger than its on-screen footprint requires.",
            severity=Severity.OPTIMIZATION,
            performance_impact=Impact.LOW,
            memory_impact=Impact.MEDIUM,
            render_impact=Impact.NONE,
            affected_items=(f"Texture_{i:02d}",),
            details="Demo finding — not derived from real scene analysis.",
            recommended_action="Downscale the texture or enable mip streaming.",
            repairability=Repairability.SAFE,
        )
        for i in range(1, 4)
    ),
)

_STAGES: tuple[tuple[str, int], ...] = (
    ("environment", 1),
    ("geometry", 4),
    ("materials", 2),
    ("textures", 3),
)


class DemoScanner(BaseScanner):
    """Simulates a staged, incremental scan with deterministic results."""

    id = "demo"
    name = "Demo Scanner"

    def is_available(self) -> bool:
        return True

    def scan(self) -> Iterator[ScanBatch]:
        total = len(_DEMO_FINDINGS)
        completed = 0
        cursor = 0
        for stage, batch_size in _STAGES:
            # Small deliberate delay so staged progress is visible in the
            # UI; real scanners will instead yield naturally between
            # batches of actual work.
            time.sleep(0.05)
            batch = list(_DEMO_FINDINGS[cursor:cursor + batch_size])
            cursor += batch_size
            completed += len(batch)
            yield (stage, completed, total, batch)
