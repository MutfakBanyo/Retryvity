"""Pure, side-effect-free repair planning.

Nothing here touches a file or the scene — every filesystem/scene query a
planner needs is injected as a callable, so these functions are fully
unit-testable and, per docs/REPAIR_ENGINE.md's "no mutation during
preview" invariant, structurally incapable of mutating anything (there is
no filesystem/pymxs import in this module at all).
"""

from __future__ import annotations

import hashlib
import ntpath
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Iterable

from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.repair.models import OperationKind, RepairOperation, RepairPlan, ValidationState

# -- Make Project Portable ---------------------------------------------------


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _collision_safe_name(filename: str, comparison_key: str) -> str:
    """Deterministic collision-safe rename: same input always produces
    the same output, so re-planning never renames differently on a
    second run. See docs/REPAIR_ENGINE.md, "Collision handling"."""

    stem, _, ext = filename.rpartition(".")
    if not stem:
        stem, ext = filename, ""
    digest = hashlib.sha1(comparison_key.encode("utf-8")).hexdigest()[:8]
    return f"{stem}__{digest}.{ext}" if ext else f"{stem}__{digest}"


def build_make_portable_plan(
    references: Iterable[ExternalTextureReference],
    destination_dir: str,
    *,
    exists_checker: Callable[[str], bool | None],
) -> RepairPlan:
    """Build a "Make Project Portable" plan: copy every unique external
    texture into ``destination_dir`` once, relink every map node that
    references it. See docs/REPAIR_ENGINE.md, "Make Project Portable" for
    the full policy this implements (copy-once/relink-many, never touch
    missing sources, deterministic collision handling, skip
    already-portable assets).

    ``exists_checker(path) -> True/False/None`` — ``None`` means
    "existence could not be determined" (e.g. a permission error), kept
    distinct from a confirmed-missing ``False`` so the two get different
    treatment (blocked-for-review vs. skipped-as-missing).
    """

    plan_id = _new_id("plan")
    destination_dir_norm = ntpath.normpath(destination_dir)
    destination_key = ntpath.normcase(destination_dir_norm)

    operations: list[RepairOperation] = [
        RepairOperation(
            op_id=_new_id("op"),
            kind=OperationKind.CREATE_DIRECTORY,
            reason="Destination asset directory for Make Project Portable.",
            destination=destination_dir_norm,
        )
    ]
    conflicts: list[str] = []
    missing_sources: list[str] = []
    unresolved: list[str] = []
    already_portable_ref_ids: list[str] = []

    # Group by unique source path — copy once, relink many.
    by_source: dict[str, list[ExternalTextureReference]] = {}
    for ref in references:
        key = ref.path_info.comparison_key
        if not key:
            continue
        by_source.setdefault(key, []).append(ref)

    used_destination_names: dict[str, str] = {}  # destination filename -> owning comparison_key

    for comparison_key in sorted(by_source):
        refs = by_source[comparison_key]
        sample = refs[0]
        source_path = sample.path_info.normalized_path

        if sample.path_info.exists is False:
            missing_sources.append(source_path)
            continue

        if ntpath.normcase(source_path).startswith(destination_key):
            already_portable_ref_ids.extend(r.ref_id for r in refs)
            continue

        exists = exists_checker(source_path)
        if exists is None:
            unresolved.append(source_path)
            for ref in refs:
                operations.append(
                    RepairOperation(
                        op_id=_new_id("op"),
                        kind=OperationKind.RELINK_TEXTURE,
                        reason="Source file access could not be verified.",
                        source=source_path,
                        map_ref_id=ref.ref_id,
                        map_handle=ref.map_handle,
                        map_class=ref.map_class,
                        source_property=ref.source_property,
                        old_value=source_path,
                        validation_state=ValidationState.BLOCKED,
                        blocked_reason="source file access could not be verified (inaccessible/permission error)",
                    )
                )
            continue
        if exists is False:
            missing_sources.append(source_path)
            continue

        filename = ntpath.basename(source_path)
        claimant = used_destination_names.get(filename.lower())
        if claimant is not None and claimant != comparison_key:
            filename = _collision_safe_name(filename, comparison_key)
            conflicts.append(f"{source_path} -> renamed to {filename} to avoid overwriting a different source file")
        used_destination_names[filename.lower()] = comparison_key

        destination_path = ntpath.normpath(ntpath.join(destination_dir_norm, filename))

        operations.append(
            RepairOperation(
                op_id=_new_id("op"),
                kind=OperationKind.COPY_FILE,
                reason="Copy external texture into the project asset directory (copied once, shared by every map node below).",
                source=source_path,
                destination=destination_path,
            )
        )
        for ref in refs:
            operations.append(
                RepairOperation(
                    op_id=_new_id("op"),
                    kind=OperationKind.RELINK_TEXTURE,
                    reason="Relink map node to the copied project-local asset.",
                    source=source_path,
                    destination=destination_path,
                    map_ref_id=ref.ref_id,
                    map_handle=ref.map_handle,
                    map_class=ref.map_class,
                    source_property=ref.source_property,
                    old_value=source_path,
                    new_value=destination_path,
                )
            )

    return RepairPlan(
        plan_id=plan_id,
        kind="make_project_portable",
        created_at=_now_iso(),
        operations=tuple(operations),
        conflicts=tuple(conflicts),
        missing_sources=tuple(missing_sources),
        unresolved=tuple(unresolved),
        already_portable_ref_ids=tuple(already_portable_ref_ids),
    )


# -- Missing Texture Relink ---------------------------------------------------

_EXACT_FILENAME_SCORE = 100
_EXTENSION_MATCH_SCORE = 20
_SIZE_MATCH_SCORE = 10


@dataclass(frozen=True)
class RelinkCandidate:
    path: str
    score: int
    reasons: tuple[str, ...]


def find_relink_candidates(
    missing_filename: str,
    candidate_paths: Iterable[str],
    *,
    expected_size_bytes: int | None = None,
    size_lookup: Callable[[str], int | None] | None = None,
) -> list[RelinkCandidate]:
    """Rank candidate files as replacements for one missing texture.

    ``candidate_paths`` is the caller-supplied result of searching one or
    more roots (see ``devtools``/UI code for the actual filesystem walk —
    this function never touches the filesystem itself beyond the
    optional injected ``size_lookup``). Deterministic scoring only —
    exact filename, extension, and (if both known) file size — never
    fuzzy/AI matching; see docs/REPAIR_ENGINE.md, "Missing texture
    relink" for why. Sorted highest score first, tie-broken by path for
    stable, repeatable ordering.
    """

    target_name = ntpath.basename(missing_filename)
    target_ext = target_name.rsplit(".", 1)[-1].lower() if "." in target_name else ""

    candidates: list[RelinkCandidate] = []
    for path in candidate_paths:
        name = ntpath.basename(path)
        reasons: list[str] = []
        score = 0

        if name.lower() == target_name.lower():
            score += _EXACT_FILENAME_SCORE
            reasons.append("exact filename match")
        else:
            continue  # a candidate that doesn't even match the filename is not a candidate

        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if target_ext and ext == target_ext:
            score += _EXTENSION_MATCH_SCORE
            reasons.append("extension match")

        if expected_size_bytes is not None and size_lookup is not None:
            actual_size = size_lookup(path)
            if actual_size is not None and actual_size == expected_size_bytes:
                score += _SIZE_MATCH_SCORE
                reasons.append("file size match")

        candidates.append(RelinkCandidate(path=path, score=score, reasons=tuple(reasons)))

    candidates.sort(key=lambda c: (-c.score, c.path.lower()))
    return candidates


def classify_candidates(candidates: list[RelinkCandidate]) -> str:
    """"none" | "single" | "multiple" — see docs/REPAIR_ENGINE.md,
    "Missing texture relink" for the exact policy each maps to. Never
    silently picks a winner: "single" still requires explicit user
    review/approval before any relink happens (see repair/transaction.py)."""

    if not candidates:
        return "none"
    top_score = candidates[0].score
    tied_at_top = [c for c in candidates if c.score == top_score]
    if len(tied_at_top) == 1:
        return "single"
    return "multiple"


def build_relink_plan(
    ref: ExternalTextureReference,
    chosen_path: str,
) -> RepairPlan:
    """One user-approved relink — see ``build_make_portable_plan`` for
    the bulk-repair sibling. No COPY_FILE: relinking a missing texture
    points at wherever the found file already lives; it never moves it."""

    return RepairPlan(
        plan_id=_new_id("plan"),
        kind="relink_missing_texture",
        created_at=_now_iso(),
        operations=(
            RepairOperation(
                op_id=_new_id("op"),
                kind=OperationKind.RELINK_TEXTURE,
                reason="User-approved relink to a located replacement file.",
                source=chosen_path,
                map_ref_id=ref.ref_id,
                map_handle=ref.map_handle,
                map_class=ref.map_class,
                source_property=ref.source_property,
                old_value=ref.path_info.raw_path,
                new_value=chosen_path,
            ),
        ),
    )
