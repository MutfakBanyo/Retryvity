"""Production-facing Texture Doctor report formatter.

Pure string formatting over :class:`TextureDoctorResult` — no pymxs, no
Qt, no filesystem access, no new scene traversal (formatting a result the
scanner already produced must never re-scan — see docs/ARCHITECTURE.md,
"Chunked / incremental scanning" and TEXTURE_DOCTOR.md, "Performance").

This is what a user (or a future UI "copy report" action) sees — it MUST
NOT include raw Python ``repr()``, AnimHandle diagnostics, rejected-map
property dumps, or any other adapter-internal debug detail. Those stay in
``devtools/texture_probe.py``'s dev-diagnostics section, never here.
"""

from __future__ import annotations

from corona_doctor.core.texture_models import TextureDoctorResult
from corona_doctor.core.texture_query import local_workstation_path_count


def format_texture_doctor_report(result: TextureDoctorResult) -> str:
    inv = result.inventory
    local_count = local_workstation_path_count(result.texture_references)

    lines = [
        "Texture Doctor",
        "",
        f"{len(result.texture_references)} texture references",
        f"{inv.unique_external_texture_count} unique files",
        f"{inv.missing_texture_count} missing",
        f"{inv.oversized_8k_count} oversized",
        f"{inv.duplicate_group_count} reuse/duplicate groups",
        f"{local_count} local paths",
    ]

    if result.errors:
        lines += ["", f"Scanner errors: {len(result.errors)} (see developer diagnostics)"]

    if result.compatibility_warnings:
        lines += ["", "Compatibility warnings"]
        lines += [f"  {warning}" for warning in result.compatibility_warnings]

    lines += ["", "Findings"]
    if result.findings:
        for finding in result.findings:
            lines.append(f"  [{finding.severity.value.upper()}] {finding.rule_id}  {finding.title} — {finding.summary}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def format_host_validation_block(result: TextureDoctorResult, *, fallback_identities: int = 0) -> str:
    """The short "did this scan behave" summary for a real-host smoke test.

    Distinct from :func:`format_texture_doctor_report`: that one is what a
    user would read; this one is what a developer pastes into a bug report
    after a real 3ds Max run — see ``devtools/texture_probe.py``.

    ``fallback_identities`` (materials + maps that fell back to a per-scan
    identity because ``getHandleByAnim`` returned ``None`` — see
    ``adapters/scene_adapter.py::SceneAdapter._identity``) lives only in
    dev diagnostics, not in :class:`TextureDoctorResult` itself, so the
    caller passes it in explicitly when it has that data.
    """

    inv = result.inventory
    local_count = local_workstation_path_count(result.texture_references)

    lines = [
        "HOST VALIDATION",
        f"  scanner errors:            {len(result.errors)}",
        f"  compatibility warnings:    {len(result.compatibility_warnings)}",
        f"  fallback identities used:  {fallback_identities}",
        f"  external textures:        {len(result.texture_references)}",
        f"  missing:                   {inv.missing_texture_count}",
        f"  oversized (>= 8K):         {inv.oversized_8k_count}",
        f"  duplicate/reuse groups:    {inv.duplicate_group_count}",
        f"  local paths:               {local_count}",
        f"  total duration:            {result.timings.total_ms:.1f} ms",
    ]
    return "\n".join(lines)
