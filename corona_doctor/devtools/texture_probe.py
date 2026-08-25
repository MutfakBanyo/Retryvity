"""Development-only, READ-ONLY Scene Inventory + Texture Doctor probe.

Runs the real production scanner (``TextureDoctorScanner``) against the
current 3ds Max scene and prints THREE clearly separated sections:

  A) the production-facing report (``reports/texture_report.py`` — what a
     user would actually see; no raw repr/AnimHandle/internal dumps)
  B) developer diagnostics (scene node breakdown, AnimHandle fallback
     counters, rejected-map property samples — never shown in production
     UI, see ``core/texture_models.py::TextureDoctorDiagnostics``)
  C) a short HOST VALIDATION block for pasting into a bug report

It also writes a full structured JSON report for tuning. Strictly
read-only — same guarantee as the scanner itself (see
scanners/texture_doctor_scanner.py's module docstring). This module is a
development tool only: nothing in the production scan/rule/report path
depends on it (see docs/TEXTURE_DOCTOR.md, "Production result model") —
it depends on the production scanner and report formatter, not the other
way around.

Run from the 3ds Max Python listener::

    from corona_doctor.devtools.texture_probe import run_texture_probe
    run_texture_probe()
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from corona_doctor.core.diagnostics import DiagnosticEngine
from corona_doctor.core.events import EventBus
from corona_doctor.logging.logger import default_log_path
from corona_doctor.performance.profiler import Profiler
from corona_doctor.core.texture_models import TextureScanFacts
from corona_doctor.reports.texture_report import format_host_validation_block, format_texture_doctor_report
from corona_doctor.scanners.texture_doctor_scanner import TextureDoctorScanner


def _write_json_report(report: dict[str, Any]) -> Path:
    path = default_log_path().parent / "texture_probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def run_texture_probe(write_json: bool = True) -> dict[str, Any]:
    profiler = Profiler()
    scanner = TextureDoctorScanner(profiler=profiler)
    engine = DiagnosticEngine(EventBus())

    engine.run(scanner)

    facts = scanner.facts
    result = scanner.result

    if result is None or facts is None:
        print("Texture Doctor probe: scan did not complete (see errors above/in the log).")
        return {}

    with profiler.measure("texture_doctor.report_format"):
        production_report = format_texture_doctor_report(result)

    fallback_identities = facts.diagnostics.materials_using_fallback_identity + facts.diagnostics.maps_using_fallback_identity
    host_block = format_host_validation_block(result, fallback_identities=fallback_identities)

    print(production_report)
    print()
    print(_format_dev_diagnostics(facts))
    print()
    print(host_block)

    report: dict[str, Any] = {
        "inventory": asdict(result.inventory),
        "texture_references": [asdict(r) for r in result.texture_references],
        "unknown_map_classes": list(result.unknown_map_classes),
        "errors": list(result.errors),
        "diagnostics": asdict(facts.diagnostics),
        "compatibility_warnings": list(result.compatibility_warnings),
        "findings": [
            {
                "rule_id": f.rule_id,
                "title": f.title,
                "severity": f.severity.value,
                "summary": f.summary,
                "affected_items": list(f.affected_items),
            }
            for f in result.findings
        ],
        "timings_ms": profiler.report(),
    }

    if write_json:
        path = _write_json_report(report)
        print(f"\nJSON report written to: {path}")

    return report


def _format_dev_diagnostics(facts: TextureScanFacts) -> str:
    """Scene node breakdown + AnimHandle/rejected-map internals.

    Never shown in production UI/report — see
    ``core/texture_models.py::TextureDoctorDiagnostics``.
    """

    inv = facts.inventory
    diag = facts.diagnostics

    lines = [
        "Dev diagnostics (not production UI)",
        "",
        "Scene Inventory",
        f"  Nodes            {inv.total_nodes}",
        f"    Geometry       {inv.geometry_count}",
        f"    Lights         {inv.light_count}",
        f"    Cameras        {inv.camera_count}",
        f"    Helpers        {inv.helper_count}",
        f"    Hidden         {inv.hidden_count}",
        f"    Frozen         {inv.frozen_count}",
        f"  Nodes with material assigned  {inv.nodes_with_material_count}",
        f"  Unique materials              {inv.unique_material_count}",
        f"  16K+ textures                 {inv.oversized_16k_count}",
        f"  Unknown map classes           {len(facts.unknown_map_classes)}",
        "",
        f"  Root materials encountered              {diag.root_materials_encountered}",
        f"  Materials with valid AnimHandle          {diag.materials_with_valid_handle}",
        f"  Materials using fallback identity        {diag.materials_using_fallback_identity}",
        f"  Sub-material/sub-map edges traversed     {diag.sub_material_edges_traversed}",
        f"  Map nodes encountered                    {diag.map_nodes_encountered}",
        f"  Maps with valid AnimHandle                {diag.maps_with_valid_handle}",
        f"  Maps using fallback identity              {diag.maps_using_fallback_identity}",
        f"  External-file-backed maps recognized     {diag.external_file_backed_maps_recognized}",
        f"  Maps with candidate filename properties  {diag.maps_with_candidate_filename_properties}",
        f"  Maps rejected as non-file-backed         {diag.maps_rejected_as_non_file_backed}",
    ]

    if diag.rejected_map_samples:
        lines.append("  Rejected map class samples (first-seen per class):")
        for sample in diag.rejected_map_samples:
            props = ", ".join(sample.get("property_names", [])[:20]) or "(none)"
            lines.append(f"    {sample.get('map_class')}: properties = {props}")

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    run_texture_probe()
