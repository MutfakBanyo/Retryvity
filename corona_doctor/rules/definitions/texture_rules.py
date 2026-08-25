"""TXT-00x Texture Doctor diagnostic rules.

Pure functions over :class:`TextureScanFacts` — never touch pymxs, never
touch the filesystem. Each rule produces at most ONE aggregate
:class:`Finding` (progressive disclosure: a count and a small sample in
``affected_items``, full detail in ``details`` — never one Finding per
texture, which would flood the findings list in a production scene).

Repairability is ``NONE``/``MANUAL`` everywhere in this milestone — no
rule here ever suggests or performs an automatic fix (see
docs/TEXTURE_DOCTOR.md, "What v1 does not detect/do").
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from corona_doctor.core.models import Finding, Impact, Repairability, Severity
from corona_doctor.core.rules import CallableRule, Rule, RuleDefinition
from corona_doctor.core.texture_models import ExternalTextureReference, TextureScanFacts, TextureThresholds
from corona_doctor.core.texture_query import filter_local_workstation_paths

_SAMPLE_LIMIT = 10


def _facts(context: dict[str, Any]) -> TextureScanFacts | None:
    facts = context.get("texture_facts")
    return facts if isinstance(facts, TextureScanFacts) else None


def _sample(items: list[str]) -> tuple[str, ...]:
    return tuple(items[:_SAMPLE_LIMIT])


def _oversized_sample_line(ref: ExternalTextureReference, thresholds: TextureThresholds) -> str:
    tier = ">= 16K threshold" if max(ref.width, ref.height) >= thresholds.oversized_strong_warning_px else ">= 8K threshold"
    usage_bits = []
    if ref.material_name:
        usage_bits.append(f"material {ref.material_name}")
    if ref.object_names:
        usage_bits.append(f"object(s) {', '.join(ref.object_names[:3])}")
    usage = f" — used by {', '.join(usage_bits)}" if usage_bits else ""
    return f"{ref.filename} — {ref.width}x{ref.height}, {ref.file_size_human} ({tier}){usage}"


def _make_missing_texture_rule() -> CallableRule:
    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None
        missing = [r for r in facts.texture_references if r.path_info.exists is False]
        if not missing:
            return None

        sample_lines = [f"{r.filename}  (used by {r.reference_count} reference(s))" for r in missing]
        details = (
            f"{len(missing)} texture reference(s) point to a file that could not be found.\n\n"
            + "\n".join(sample_lines[:_SAMPLE_LIMIT])
            + (f"\n… and {len(missing) - _SAMPLE_LIMIT} more." if len(missing) > _SAMPLE_LIMIT else "")
        )

        return Finding(
            id="TXT-001",
            rule_id="TXT-001",
            category="Textures",
            title="Missing texture",
            summary=f"{len(missing)} referenced texture file(s) could not be found on disk.",
            severity=Severity.CRITICAL,
            confidence=1.0,
            performance_impact=Impact.NONE,
            memory_impact=Impact.NONE,
            render_impact=Impact.HIGH,
            affected_items=_sample([r.filename for r in missing]),
            details=details,
            recommended_action="Relink each missing texture to its correct file, or remove the reference if it is no longer needed.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-001",
            category="Textures",
            title="Missing Texture",
            description="An external texture reference's file could not be located on disk.",
        ),
        fn=evaluate,
    )


def _make_duplicate_reference_rule() -> CallableRule:
    """TXT-002 semantics (audited against a real-host scan: 262 unique
    materials, 640 map nodes, 46 groups here): this measures REUSE — N
    distinct map nodes resolving to the same underlying file path — not
    "duplication" in the sense of a mistake. Multiple map nodes pointing
    at one shared bitmap is completely normal (an instanced/shared
    texture across several materials). This rule does not and cannot
    distinguish that from "probably-redundant map nodes that should be
    consolidated" — both look identical from path data alone — and it
    makes no claim about whether two *different* files share content
    (that would need a hash, which this milestone does not compute; see
    TXT-003 for the filename+size heuristic, explicitly capped at 0.6
    confidence for exactly that reason). Kept at OPTIMIZATION severity
    and worded as a neutral observation, never as an error.
    """

    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None

        groups: dict[str, list[ExternalTextureReference]] = defaultdict(list)
        for ref in facts.texture_references:
            if ref.path_info.comparison_key:
                groups[ref.path_info.comparison_key].append(ref)
        reuse_groups = {key: refs for key, refs in groups.items() if len(refs) > 1}
        if not reuse_groups:
            return None

        sample_lines = []
        for refs in list(reuse_groups.values())[:_SAMPLE_LIMIT]:
            materials = sorted({r.material_name for r in refs if r.material_name})
            sample_lines.append(f"{refs[0].filename} — {len(refs)} map node(s), materials: {', '.join(materials) or 'unknown'}")

        details = (
            f"{len(reuse_groups)} texture file(s) are pointed at by more than one map node — this is "
            "reuse, not necessarily a problem: the same shared/instanced bitmap referenced from several "
            "materials is a normal, often deliberate pattern. This rule cannot tell that apart from "
            "genuinely redundant map nodes that could be consolidated into one — both look identical from "
            "path data alone — so treat this as a list worth a quick look, not a list of defects.\n\n"
            + "\n".join(sample_lines)
        )

        return Finding(
            id="TXT-002",
            rule_id="TXT-002",
            category="Textures",
            title="Texture reused by multiple map nodes",
            summary=f"{len(reuse_groups)} texture file(s) are referenced by more than one map node.",
            severity=Severity.OPTIMIZATION,
            confidence=1.0,
            performance_impact=Impact.LOW,
            memory_impact=Impact.LOW,
            render_impact=Impact.NONE,
            affected_items=_sample([refs[0].filename for refs in reuse_groups.values()]),
            details=details,
            recommended_action="Review whether these map nodes can share a single instanced bitmap node; skip any where reuse is already intentional.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-002",
            category="Textures",
            title="Texture Reused By Multiple Map Nodes",
            description="The same underlying texture file is pointed at by more than one map node — reuse, not automatically a defect.",
        ),
        fn=evaluate,
    )


def _make_potential_duplicate_asset_rule() -> CallableRule:
    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None

        by_filename_size: dict[tuple[str, int], list[ExternalTextureReference]] = defaultdict(list)
        for ref in facts.texture_references:
            if ref.file_size_bytes is None or not ref.filename:
                continue
            by_filename_size[(ref.filename.lower(), ref.file_size_bytes)].append(ref)

        candidate_groups = []
        for refs in by_filename_size.values():
            distinct_paths = {r.path_info.comparison_key for r in refs}
            if len(distinct_paths) > 1:
                candidate_groups.append(refs)
        if not candidate_groups:
            return None

        sample_lines = []
        for refs in candidate_groups[:_SAMPLE_LIMIT]:
            paths = sorted({r.path_info.normalized_path for r in refs})
            sample_lines.append(f"{refs[0].filename}:\n  " + "\n  ".join(paths))

        details = (
            f"{len(candidate_groups)} filename+size match(es) found at different paths — same filename and "
            "identical file size, but the paths differ, so this is a POTENTIAL duplicate asset only. "
            "Matching filename and size does not prove the file contents are identical.\n\n"
            + "\n\n".join(sample_lines)
        )

        return Finding(
            id="TXT-003",
            rule_id="TXT-003",
            category="Textures",
            title="Potential duplicate asset path",
            summary=f"{len(candidate_groups)} texture(s) may exist at more than one path (same filename and size).",
            severity=Severity.OPTIMIZATION,
            confidence=0.6,
            performance_impact=Impact.NONE,
            memory_impact=Impact.LOW,
            render_impact=Impact.NONE,
            affected_items=_sample([refs[0].filename for refs in candidate_groups]),
            details=details,
            recommended_action="Verify manually (or via an on-demand hash check) whether these are the same asset before consolidating.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-003",
            category="Textures",
            title="Potential Duplicate Asset Paths",
            description="Same filename and file size found at different paths — possibly the same asset.",
        ),
        fn=evaluate,
    )


def _make_oversized_texture_rule(thresholds: TextureThresholds) -> CallableRule:
    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None

        strong = [
            r
            for r in facts.texture_references
            if r.width and r.height and max(r.width, r.height) >= thresholds.oversized_strong_warning_px
        ]
        warning = [
            r
            for r in facts.texture_references
            if r.width
            and r.height
            and thresholds.oversized_warning_px <= max(r.width, r.height) < thresholds.oversized_strong_warning_px
        ]
        if not strong and not warning:
            return None

        sample = strong + warning
        sample_lines = [_oversized_sample_line(r, thresholds) for r in sample[:_SAMPLE_LIMIT]]
        details = (
            "A texture's pixel dimensions exceeded a configured threshold — this is a heuristic, not a "
            "verdict: an 8K+ texture can be completely legitimate for a hero asset or a tight close-up "
            "framing. Large textures may increase scene memory use and load time; review whether the "
            "resolution is actually needed for how each one is used.\n\n"
            f">= {thresholds.oversized_strong_warning_px}px on either dimension: {len(strong)}\n"
            f"{thresholds.oversized_warning_px}-{thresholds.oversized_strong_warning_px - 1}px on either dimension: {len(warning)}\n\n"
            + "\n".join(sample_lines)
        )

        severity = Severity.WARNING if strong else Severity.OPTIMIZATION

        return Finding(
            id="TXT-004",
            rule_id="TXT-004",
            category="Textures",
            title="Oversized texture",
            summary=f"{len(strong) + len(warning)} texture(s) have unusually large pixel dimensions.",
            severity=severity,
            confidence=1.0,
            performance_impact=Impact.LOW,
            memory_impact=Impact.MEDIUM,
            render_impact=Impact.NONE,
            affected_items=_sample([r.filename for r in sample]),
            details=details,
            recommended_action="Downscale the source texture if the current resolution is not needed for the final render.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-004",
            category="Textures",
            title="Oversized Texture",
            description="A texture's pixel dimensions exceed a configurable threshold. Dimension-based only — not screen-space aware.",
        ),
        fn=evaluate,
    )


def _make_large_file_rule(thresholds: TextureThresholds) -> CallableRule:
    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None

        large = [r for r in facts.texture_references if r.file_size_bytes and r.file_size_bytes >= thresholds.large_file_warning_bytes]
        if not large:
            return None

        sample_lines = [f"{r.filename} — {r.file_size_human}" for r in large[:_SAMPLE_LIMIT]]
        details = (
            f"{len(large)} texture file(s) exceed {thresholds.large_file_warning_bytes // (1024 * 1024)} MB on disk.\n\n"
            "Disk size is not the same as decoded RAM usage — an uncompressed format at the same "
            "resolution will use more memory than a compressed one of the same file size.\n\n"
            + "\n".join(sample_lines)
        )

        return Finding(
            id="TXT-005",
            rule_id="TXT-005",
            category="Textures",
            title="Very large texture file",
            summary=f"{len(large)} texture file(s) are unusually large on disk.",
            severity=Severity.OPTIMIZATION,
            confidence=1.0,
            performance_impact=Impact.LOW,
            memory_impact=Impact.UNKNOWN,
            render_impact=Impact.NONE,
            affected_items=_sample([r.filename for r in large]),
            details=details,
            recommended_action="Consider a more efficient file format or compression for these textures.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-005",
            category="Textures",
            title="Very Large Texture File",
            description="A texture's on-disk file size exceeds a configurable threshold.",
        ),
        fn=evaluate,
    )


def _make_local_path_rule(thresholds: TextureThresholds) -> CallableRule:
    def evaluate(context: dict[str, Any]) -> Finding | None:
        facts = _facts(context)
        if facts is None:
            return None

        flagged = filter_local_workstation_paths(facts.texture_references, thresholds)
        if not flagged:
            return None

        sample_lines = [f"{r.filename} — {r.path_info.normalized_path}" for r in flagged[:_SAMPLE_LIMIT]]
        details = (
            f"{len(flagged)} texture(s) resolve to a workstation-specific path (under a user profile, "
            "Desktop, Downloads, Temp, or AppData). That is not a broken scene — it will render fine on "
            "this machine — but it is a portability risk: the file will not exist at that path on another "
            "workstation, on a render farm node, or for a collaborator who opens this project, so the scene "
            "will show a missing texture there even though it works here.\n\n" + "\n".join(sample_lines)
        )

        return Finding(
            id="TXT-006",
            rule_id="TXT-006",
            category="Textures",
            title="Local texture path",
            summary=f"{len(flagged)} texture(s) reference a workstation-specific local path.",
            severity=Severity.INFO,
            confidence=0.8,
            performance_impact=Impact.NONE,
            memory_impact=Impact.NONE,
            render_impact=Impact.NONE,
            affected_items=_sample([r.filename for r in flagged]),
            details=details,
            recommended_action="Move these textures into a shared project/asset location (and relink) before handing the scene to another workstation, a collaborator, or a render farm.",
            repairability=Repairability.MANUAL,
        )

    return CallableRule(
        definition=RuleDefinition(
            id="TXT-006",
            category="Textures",
            title="Local Texture Path",
            description="A texture path looks workstation-specific (user profile, Desktop, Downloads, Temp).",
        ),
        fn=evaluate,
    )


def build_texture_rules(thresholds: TextureThresholds | None = None) -> list[Rule]:
    thresholds = thresholds or TextureThresholds()
    return [
        _make_missing_texture_rule(),
        _make_duplicate_reference_rule(),
        _make_potential_duplicate_asset_rule(),
        _make_oversized_texture_rule(thresholds),
        _make_large_file_rule(thresholds),
        _make_local_path_rule(thresholds),
    ]
