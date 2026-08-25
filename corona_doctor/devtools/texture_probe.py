"""Development-only, READ-ONLY Scene Inventory + Texture Doctor probe.

Runs the real production scanner (``TextureDoctorScanner``) against the
current 3ds Max scene, prints a concise human-readable summary, and
writes a full structured JSON report for tuning. Strictly read-only —
same guarantee as the scanner itself (see
scanners/texture_doctor_scanner.py's module docstring).

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

    result = engine.run(scanner)

    facts = scanner.facts
    inventory = scanner.inventory

    report: dict[str, Any] = {
        "inventory": asdict(inventory) if inventory else None,
        "texture_references": [asdict(r) for r in scanner.texture_references],
        "unknown_map_classes": list(facts.unknown_map_classes) if facts else [],
        "errors": list(facts.errors) if facts else [],
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

    _print_summary(report)

    if write_json:
        path = _write_json_report(report)
        print(f"\nJSON report written to: {path}")

    return report


def _print_summary(report: dict[str, Any]) -> None:
    inv = report["inventory"] or {}
    lines = [
        "Scene Inventory",
        "",
        f"Nodes            {inv.get('total_nodes', 0)}",
        f"  Geometry       {inv.get('geometry_count', 0)}",
        f"  Lights         {inv.get('light_count', 0)}",
        f"  Cameras        {inv.get('camera_count', 0)}",
        f"  Helpers        {inv.get('helper_count', 0)}",
        f"  Hidden         {inv.get('hidden_count', 0)}",
        f"  Frozen         {inv.get('frozen_count', 0)}",
        "",
        f"Materials        {inv.get('material_count', 0)}  ({inv.get('unique_material_count', 0)} unique)",
        "",
        f"Texture references     {len(report['texture_references'])}",
        f"Unique texture files   {inv.get('unique_external_texture_count', 0)}",
        f"Missing                {inv.get('missing_texture_count', 0)}",
        f"8K+                    {inv.get('oversized_8k_count', 0)}",
        f"16K+                   {inv.get('oversized_16k_count', 0)}",
        f"Potential duplicates   {inv.get('duplicate_group_count', 0)} group(s)",
        "",
        f"Unknown map classes    {len(report['unknown_map_classes'])}",
        f"Errors                 {len(report['errors'])}",
        "",
        f"Scan duration          {inv.get('scan_duration_ms', 0):.1f} ms",
        "",
        "Findings",
    ]
    if report["findings"]:
        for f in report["findings"]:
            lines.append(f"  [{f['severity'].upper()}] {f['rule_id']}  {f['title']} — {f['summary']}")
    else:
        lines.append("  (none)")

    print("\n".join(lines))


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    run_texture_probe()
